"""Google for Jobs results through SerpApi (https://serpapi.com/google-jobs-api). Paid API with a small free tier."""
from __future__ import annotations

import os
from datetime import datetime
from typing import List

from ..dates import parse_relative
from ..models import Job
from ..text import clean_ws
from .base import Source

API = "https://serpapi.com/search.json"


def parse_results(data: dict, now: datetime) -> List[Job]:
    jobs = []
    for item in data.get("jobs_results") or []:
        options = item.get("apply_options") or []
        url = (options[0].get("link") if options else "") or item.get("share_link") or ""
        ext = item.get("detected_extensions") or {}
        jobs.append(
            Job(
                title=clean_ws(item.get("title")),
                company=clean_ws(item.get("company_name")),
                url=url,
                source="serpapi:google_jobs",
                location=clean_ws(item.get("location")),
                description=item.get("description") or "",
                remote=bool(ext.get("work_from_home")),
                posted_at=parse_relative(ext.get("posted_at") or "", now),
                extra={"via": clean_ws(item.get("via")), "apply_on": [o.get("title") for o in options][:5]},
            )
        )
    return jobs


class SerpApiSource(Source):
    name = "serpapi"
    required_env = ("SERPAPI_KEY",)

    def fetch(self) -> List[Job]:
        jobs: List[Job] = []
        for query in self.cfg.get("queries") or []:
            params = {"engine": "google_jobs", "q": query["q"], "hl": query.get("hl", "en"), "api_key": os.environ["SERPAPI_KEY"]}
            for key in ("location", "gl"):
                if query.get(key):
                    params[key] = query[key]
            label = query["q"] + (" @ " + query["location"] if query.get("location") else "")
            try:
                data = self.get_json(API, params=params)
            except Exception as exc:
                self.fail(label, exc)
                continue
            if data.get("error"):
                if "hasn't returned any results" not in data["error"]:
                    self.fail(label, RuntimeError(data["error"]))
                continue
            jobs.extend(parse_results(data, self.ctx.now))
        return jobs
