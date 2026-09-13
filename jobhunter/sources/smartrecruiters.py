"""SmartRecruiters public Posting API (https://developers.smartrecruiters.com/docs/posting-api)."""
from __future__ import annotations

from typing import List, Optional

from ..dates import parse_datetime
from ..models import Job
from ..text import clean_ws, html_to_text
from .base import Source

API = "https://api.smartrecruiters.com/v1/companies/%s/postings"
PAGE_SIZE = 100


def parse_postings(items: list, company_id: str, company: Optional[str] = None) -> List[Job]:
    jobs = []
    for post in items or []:
        loc = post.get("location") or {}
        location = loc.get("fullLocation") or ", ".join(
            part for part in (loc.get("city"), loc.get("region"), loc.get("country")) if part
        )
        owner = post.get("company") or {}
        jobs.append(
            Job(
                title=clean_ws(post.get("name")),
                company=company or owner.get("name") or company_id,
                url="https://jobs.smartrecruiters.com/%s/%s" % (owner.get("identifier") or company_id, post.get("id")),
                source="smartrecruiters:" + company_id,
                location=clean_ws(location),
                remote=bool(loc.get("remote")),
                posted_at=parse_datetime(post.get("releasedDate")),
                extra={
                    "company_id": company_id,
                    "posting_id": str(post.get("id")),
                    "experience_level": (post.get("experienceLevel") or {}).get("label") or "",
                },
            )
        )
    return jobs


class SmartRecruitersSource(Source):
    name = "smartrecruiters"

    def fetch(self) -> List[Job]:
        jobs: List[Job] = []
        max_pages = int(self.cfg.get("max_pages", 5))
        for entry in self.cfg.get("companies") or []:
            company_id = entry["id"]
            try:
                for page in range(max_pages):
                    data = self.get_json(API % company_id, params={"limit": PAGE_SIZE, "offset": page * PAGE_SIZE})
                    items = data.get("content") or []
                    jobs.extend(parse_postings(items, company_id, entry.get("company")))
                    if len(items) < PAGE_SIZE or (page + 1) * PAGE_SIZE >= int(data.get("totalFound") or 0):
                        break
            except Exception as exc:
                self.fail(company_id, exc)
        return jobs

    def enrich(self, job: Job) -> None:
        data = self.get_json((API % job.extra["company_id"]) + "/" + job.extra["posting_id"])
        sections = (data.get("jobAd") or {}).get("sections") or {}
        parts = [
            html_to_text((sections.get(key) or {}).get("text") or "")
            for key in ("jobDescription", "qualifications", "additionalInformation")
        ]
        job.description = "\n\n".join(p for p in parts if p)
        if data.get("postingUrl"):
            job.extra["posting_url"] = data["postingUrl"]
