"""Workday career sites, via the JSON endpoint their own front end calls (/wday/cxs/<tenant>/<site>/jobs)."""
from __future__ import annotations

import re
from datetime import datetime
from typing import Dict, List

from ..dates import parse_relative
from ..models import Job
from ..text import clean_ws, html_to_text
from .base import Source

PAGE_SIZE = 20  # Workday rejects larger pages
_MULTI_LOCATION = re.compile(r"^\d+\s+locations?$", re.IGNORECASE)


def parse_posting(posting: dict, board: dict, term: str, now: datetime) -> Job:
    location = clean_ws(posting.get("locationsText"))
    if term and (not location or _MULTI_LOCATION.match(location)):
        # "2 Locations" hides the cities; the location search term that returned it is the best hint.
        location = "%s (matched search: %s)" % (location or "location not listed", term)
    path = posting.get("externalPath") or ""
    return Job(
        title=clean_ws(posting.get("title")),
        company=board.get("company") or board["tenant"],
        url="https://%s/%s%s" % (board["host"], board["site"], path),
        source="workday:" + board["tenant"],
        location=location,
        posted_at=parse_relative(posting.get("postedOn") or "", now),
        extra={"host": board["host"], "tenant": board["tenant"], "site": board["site"], "path": path},
    )


class WorkdaySource(Source):
    name = "workday"

    def fetch(self) -> List[Job]:
        jobs: Dict[str, Job] = {}
        default_terms = self.cfg.get("search") or [""]
        max_pages = int(self.cfg.get("max_pages", 3))
        for board in self.cfg.get("boards") or []:
            api = "https://%s/wday/cxs/%s/%s/jobs" % (board["host"], board["tenant"], board["site"])
            for term in board.get("search") or default_terms:
                try:
                    total = 0
                    for page in range(max_pages):
                        payload = {"appliedFacets": {}, "limit": PAGE_SIZE, "offset": page * PAGE_SIZE, "searchText": term}
                        data = self.post_json(api, payload)
                        if page == 0:
                            total = int(data.get("total") or 0)  # only reported on the first page
                        postings = data.get("jobPostings") or []
                        for posting in postings:
                            job = parse_posting(posting, board, term, self.ctx.now)
                            jobs.setdefault(job.url, job)
                        if len(postings) < PAGE_SIZE or (page + 1) * PAGE_SIZE >= total:
                            break
                except Exception as exc:
                    self.fail("%s/%s %r" % (board["tenant"], board["site"], term), exc)
        return list(jobs.values())

    def enrich(self, job: Job) -> None:
        e = job.extra
        data = self.get_json("https://%s/wday/cxs/%s/%s%s" % (e["host"], e["tenant"], e["site"], e["path"]))
        info = data.get("jobPostingInfo") or {}
        job.description = html_to_text(info.get("jobDescription") or "")
        locations = [clean_ws(loc) for loc in [info.get("location")] + list(info.get("additionalLocations") or []) if loc]
        if locations and "(matched search:" in job.location:
            job.location = ", ".join(dict.fromkeys(locations))
