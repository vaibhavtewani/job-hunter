"""Builds an application pack folder for one job: tailored CV, cover letter draft, standard answers.

Without an API key everything is deterministic: CV bullets are only re-ordered, never rewritten.
"""
from __future__ import annotations

import json
import logging
import os
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

import httpx
import yaml
from jinja2 import Environment, FileSystemLoader

from ..http import redact
from ..models import Job
from ..text import normalize, slugify
from .llm import DEFAULT_MODEL, draft_materials

log = logging.getLogger(__name__)

TEMPLATES = Path(__file__).resolve().parent.parent / "templates"
_env = Environment(loader=FileSystemLoader(str(TEMPLATES)), autoescape=False, trim_blocks=True, lstrip_blocks=True)

_STOPWORDS = frozenset(
    "a an and are as at be been by for from has have in into is it its of on or our per that the their this to "
    "was we were will with within across using including you your role team work working experience ability "
    "strong skills about who what which also can all any more most other such than them they".split()
)


def _stems(text: str) -> Set[str]:
    # Six-character prefixes are a crude stemmer: strategy/strategic, consulting/consultant.
    return {tok[:6] for tok in normalize(text).split() if len(tok) > 2 and tok not in _STOPWORDS}


def _relevance(bullet: str, job_stems: Set[str], title_stems: Set[str]) -> int:
    stems = _stems(bullet)
    return len(stems & job_stems) + 2 * len(stems & title_stems)


def tailor_profile(profile: Dict[str, Any], job: Job) -> Dict[str, Any]:
    job_stems = _stems(job.title + " " + job.description)
    title_stems = _stems(job.title)

    def reorder(items: List[dict]) -> List[dict]:
        out = []
        for item in items or []:
            bullets = sorted(item.get("bullets") or [], key=lambda b: _relevance(b, job_stems, title_stems), reverse=True)
            out.append(dict(item, bullets=bullets))
        return out

    experience = reorder(profile.get("experience"))
    projects = reorder(profile.get("projects"))
    all_bullets = [b for item in experience + projects for b in item["bullets"]]
    talking_points = sorted(all_bullets, key=lambda b: _relevance(b, job_stems, title_stems), reverse=True)[:3]
    return {"experience": experience, "projects": projects, "talking_points": talking_points}


def build_pack(
    job: Job,
    profile: Dict[str, Any],
    out_root: Path,
    llm_cfg: Optional[Dict[str, Any]],
    client: Optional[httpx.Client],
    now: datetime,
) -> Path:
    llm_cfg = llm_cfg or {}
    candidate = profile.get("candidate") or {}
    letter_cfg = profile.get("cover_letter") or {}
    folder = Path(out_root) / ("%s_%s_%s_%s" % (
        now.strftime("%Y-%m-%d"), slugify(job.company, 25), slugify(job.title, 40), job.url_key[2:8]))
    folder.mkdir(parents=True, exist_ok=True)

    tailored = tailor_profile(profile, job)
    drafted: Dict[str, Any] = {}
    if client is not None and llm_cfg.get("enabled", True) and os.environ.get("ANTHROPIC_API_KEY"):
        try:
            drafted = draft_materials(client, llm_cfg, profile, job)
        except Exception as exc:
            log.warning("LLM drafting failed for %s @ %s, using templates: %s", job.title, job.company, redact(str(exc)))

    def fill(text: str) -> str:
        return (text or "").replace("{company}", job.company).replace("{title}", job.title)

    context = {
        "job": job,
        "c": candidate,
        "now": now,
        "summary": drafted.get("summary") or candidate.get("summary", ""),
        "education": profile.get("education") or [],
        "experience": tailored["experience"],
        "projects": tailored["projects"],
        "skills": profile.get("skills") or {},
        "talking_points": drafted.get("talking_points") or tailored["talking_points"],
        "gaps": drafted.get("gaps") or [],
        "llm_model": (llm_cfg.get("model") or DEFAULT_MODEL) if drafted else None,
        "opening": fill(letter_cfg.get("opening", "")),
        "closing": fill(letter_cfg.get("closing", "")),
    }
    cover_letter = drafted.get("cover_letter") or _env.get_template("cover_letter.md.j2").render(**context)

    (folder / "README.md").write_text(_env.get_template("pack_readme.md.j2").render(**context), encoding="utf-8")
    (folder / "cv_tailored.md").write_text(_env.get_template("cv_tailored.md.j2").render(**context), encoding="utf-8")
    (folder / "cover_letter.md").write_text(cover_letter.strip() + "\n", encoding="utf-8")
    answers = {"job": {"title": job.title, "company": job.company, "url": job.url},
               "answers": profile.get("standard_answers") or {}}
    (folder / "answers.yaml").write_text(
        "# Copied from profile.yaml standard_answers. Fix TODOs there once, not per job.\n"
        + yaml.safe_dump(answers, sort_keys=False, allow_unicode=True),
        encoding="utf-8",
    )
    (folder / "job.json").write_text(json.dumps(job.to_dict(include_description=True), indent=2, ensure_ascii=False), encoding="utf-8")
    return folder
