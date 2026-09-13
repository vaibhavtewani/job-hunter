"""Ashby public job board API (https://developers.ashbyhq.com/docs/public-job-posting-api)."""
from __future__ import annotations

from typing import List, Optional

from ..dates import parse_datetime
from ..models import Job
from ..text import clean_ws, html_to_text
from .base import Source

API = "https://api.ashbyhq.com/posting-api/job-board/"


def parse_jobs(data: dict, board: str, company: Optional[str] = None) -> List[Job]:
    jobs = []
    for item in data.get("jobs") or []:
        if item.get("isListed") is False:
            continue
        locations = [item.get("location")] + [
            s.get("location") for s in item.get("secondaryLocations") or [] if isinstance(s, dict)
        ]
        jobs.append(
            Job(
                title=clean_ws(item.get("title")),
                company=company or board,
                url=item.get("jobUrl") or "",
                source="ashby:" + board,
                location=", ".join(dict.fromkeys(clean_ws(loc) for loc in locations if loc)),
                description=item.get("descriptionPlain") or html_to_text(item.get("descriptionHtml") or ""),
                remote=bool(item.get("isRemote")) or item.get("workplaceType") == "Remote",
                posted_at=parse_datetime(item.get("publishedAt")),
                extra={"department": item.get("department") or "", "apply_url": item.get("applyUrl") or ""},
            )
        )
    return jobs


class AshbySource(Source):
    name = "ashby"

    def fetch(self) -> List[Job]:
        jobs: List[Job] = []
        for board in self.cfg.get("boards") or []:
            name = board["name"]
            try:
                data = self.get_json(API + name)
            except Exception as exc:
                self.fail(name, exc)
                continue
            jobs.extend(parse_jobs(data, name, board.get("company")))
        return jobs
