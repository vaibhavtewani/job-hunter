"""Lever public postings API (https://github.com/lever/postings-api)."""
from __future__ import annotations

from typing import List, Optional

from ..dates import parse_datetime
from ..models import Job
from ..text import clean_ws, html_to_text
from .base import Source

API = {"global": "https://api.lever.co/v0/postings/", "eu": "https://api.eu.lever.co/v0/postings/"}


def parse_postings(items: list, site: str, company: Optional[str] = None) -> List[Job]:
    jobs = []
    for post in items or []:
        cats = post.get("categories") or {}
        locations = list(cats.get("allLocations") or []) or ([cats["location"]] if cats.get("location") else [])
        sections = [post.get("descriptionPlain") or ""]
        for block in post.get("lists") or []:
            sections.append(clean_ws(block.get("text")) + ": " + html_to_text(block.get("content") or ""))
        sections.append(post.get("additionalPlain") or "")
        jobs.append(
            Job(
                title=clean_ws(post.get("text")),
                company=company or site,
                url=post.get("hostedUrl") or "",
                source="lever:" + site,
                location=", ".join(dict.fromkeys(clean_ws(loc) for loc in locations if loc)),
                description="\n\n".join(s.strip() for s in sections if s and s.strip()),
                remote=post.get("workplaceType") == "remote",
                posted_at=parse_datetime(post.get("createdAt")),
                extra={"team": cats.get("team") or "", "commitment": cats.get("commitment") or ""},
            )
        )
    return jobs


class LeverSource(Source):
    name = "lever"

    def fetch(self) -> List[Job]:
        jobs: List[Job] = []
        for board in self.cfg.get("boards") or []:
            site = board["site"]
            base = API.get(board.get("region", "global"), API["global"])
            try:
                items = self.get_json(base + site, params={"mode": "json"})
            except Exception as exc:
                self.fail(site, exc)
                continue
            jobs.extend(parse_postings(items, site, board.get("company")))
        return jobs
