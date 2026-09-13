"""Optional Claude drafting of the summary, cover letter, talking points and gaps for one job."""
from __future__ import annotations

import copy
import json
import os
import re
from typing import Any, Dict

import httpx
import yaml

from ..models import Job

API_URL = "https://api.anthropic.com/v1/messages"
DEFAULT_MODEL = "claude-haiku-4-5-20251001"

SYSTEM_PROMPT = """You help a job seeker draft application materials for one specific job.
Rules:
- Use ONLY facts stated in the candidate profile. Never invent employers, titles, numbers, degrees, skills, languages, visas or dates.
- If the job asks for something the profile does not show, list it under "gaps" instead of claiming it.
- Plain, confident, specific British English. No clichés ("I am thrilled", "passionate", "dynamic").
- Respond with one JSON object and nothing else."""

USER_TEMPLATE = """CANDIDATE PROFILE (YAML):
{profile}

JOB
Title: {title}
Company: {company}
Location: {location}
Description:
{description}

Return JSON with exactly these keys:
- "summary": 2-3 sentence CV summary tailored to this job.
- "cover_letter": cover letter under 300 words, addressed "Dear Hiring Team at {company},", signed with the candidate's name.
- "talking_points": 3-5 short strings, each tied to a specific achievement in the profile.
- "gaps": list of requirements in the job that the profile does not evidence (empty list if none)."""


def _shareable_profile(profile: Dict[str, Any]) -> Dict[str, Any]:
    """Strip contact details and screening answers; the model doesn't need them."""
    shared = copy.deepcopy(profile)
    candidate = shared.get("candidate") or {}
    for key in ("email", "phones", "phone", "linkedin"):
        candidate.pop(key, None)
    shared.pop("standard_answers", None)
    return shared


def draft_materials(client: httpx.Client, llm_cfg: Dict[str, Any], profile: Dict[str, Any], job: Job) -> Dict[str, Any]:
    prompt = USER_TEMPLATE.format(
        profile=yaml.safe_dump(_shareable_profile(profile), sort_keys=False, allow_unicode=True),
        title=job.title,
        company=job.company,
        location=job.location or "not stated",
        description=(job.description or "Not available.")[:8000],
    )
    response = client.post(
        API_URL,
        headers={"x-api-key": os.environ["ANTHROPIC_API_KEY"], "anthropic-version": "2023-06-01"},
        json={
            "model": llm_cfg.get("model") or DEFAULT_MODEL,
            "max_tokens": int(llm_cfg.get("max_tokens", 1500)),
            "system": SYSTEM_PROMPT,
            "messages": [{"role": "user", "content": prompt}],
        },
        timeout=90,
    )
    response.raise_for_status()
    text = "".join(block.get("text", "") for block in response.json().get("content", []) if block.get("type") == "text")
    found = re.search(r"\{.*\}", text, re.DOTALL)
    if not found:
        raise ValueError("model response contained no JSON object")
    data = json.loads(found.group(0))
    return {
        "summary": str(data.get("summary") or ""),
        "cover_letter": str(data.get("cover_letter") or ""),
        "talking_points": [str(p) for p in data.get("talking_points") or []][:5],
        "gaps": [str(g) for g in data.get("gaps") or []][:8],
    }
