"""Greenhouse public Job Board API (https://developers.greenhouse.io/job-board.html)."""
from __future__ import annotations

from typing import List, Optional

from ..dates import parse_datetime
from ..models import Job
from ..text import clean_ws, html_to_text
from .base import Source

API = "https://boards-api.greenhouse.io/v1/boards/"


def parse_jobs(data: dict, token: str, company: Optional[str] = None) -> List[Job]:
    jobs = []
    for item in data.get("jobs") or []:
        jobs.append(
            Job(
                title=clean_ws(item.get("title")),
                company=company or item.get("company_name") or token,
                url=item.get("absolute_url") or "",
                source="greenhouse:" + token,
                location=clean_ws((item.get("location") or {}).get("name")),
                description=html_to_text(item.get("content") or ""),
                posted_at=parse_datetime(item.get("first_published") or item.get("updated_at")),
                extra={"board": token, "job_id": str(item.get("id", ""))},
            )
        )
    return jobs


class GreenhouseSource(Source):
    name = "greenhouse"

    def fetch(self) -> List[Job]:
        jobs: List[Job] = []
        for board in self.cfg.get("boards") or []:
            token = board["token"]
            try:
                # Listing without content=true keeps the payload small; descriptions come via enrich().
                data = self.get_json(API + token + "/jobs")
            except Exception as exc:
                self.fail(token, exc)
                continue
            jobs.extend(parse_jobs(data, token, board.get("company")))
        return jobs

    def enrich(self, job: Job) -> None:
        data = self.get_json("%s%s/jobs/%s" % (API, job.extra["board"], job.extra["job_id"]))
        job.description = html_to_text(data.get("content") or "")
