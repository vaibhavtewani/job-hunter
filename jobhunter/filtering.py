"""Search profiles, hard filters (title / location / age), and cross-source dedup within a run."""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Dict, Iterable, List, Optional

from .models import Job
from .text import find_phrases


def _strings(data: dict, key: str) -> List[str]:
    return [str(v) for v in (data.get(key) or [])]


@dataclass
class SearchProfile:
    name: str
    title_include: List[str]
    title_exclude: List[str] = field(default_factory=list)
    locations: List[str] = field(default_factory=list)
    preferred_locations: List[str] = field(default_factory=list)
    allow_remote: bool = False
    score_keywords: List[str] = field(default_factory=list)
    boost_phrases: List[str] = field(default_factory=list)
    penalty_title: List[str] = field(default_factory=list)
    penalty_text: List[str] = field(default_factory=list)

    @classmethod
    def from_dict(cls, data: dict) -> "SearchProfile":
        name = data.get("name")
        if not name:
            raise ValueError("every search profile needs a 'name'")
        if not data.get("title_include"):
            raise ValueError("search profile %r needs at least one 'title_include' phrase" % name)
        return cls(
            name=str(name),
            title_include=_strings(data, "title_include"),
            title_exclude=_strings(data, "title_exclude"),
            locations=_strings(data, "locations"),
            preferred_locations=_strings(data, "preferred_locations"),
            allow_remote=bool(data.get("allow_remote", False)),
            score_keywords=_strings(data, "score_keywords"),
            boost_phrases=_strings(data, "boost_phrases"),
            penalty_title=_strings(data, "penalty_title"),
            penalty_text=_strings(data, "penalty_text"),
        )

    def title_ok(self, title: str) -> bool:
        # Exclusions apply to the title only: descriptions routinely mention "senior stakeholders".
        return bool(find_phrases(title, self.title_include)) and not find_phrases(title, self.title_exclude)

    def location_ok(self, job: Job, trust_location: bool = False) -> bool:
        if trust_location or not self.locations:
            return True
        if job.remote and self.allow_remote:
            return True
        return bool(find_phrases(job.location, self.locations))


@dataclass
class Candidate:
    job: Job
    profiles: List[SearchProfile]


def filter_jobs(
    jobs: Iterable[Job],
    profiles: List[SearchProfile],
    max_age_days: float,
    trusted_location_sources: Iterable[str] = (),
    now: Optional[datetime] = None,
) -> List[Candidate]:
    trusted = set(trusted_location_sources)
    out = []
    for job in jobs:
        if not job.title or not job.url:
            continue
        age = job.age_days(now)
        if age is not None and age > max_age_days:
            continue
        trust = job.source_name in trusted
        matched = [p for p in profiles if p.title_ok(job.title) and p.location_ok(job, trust)]
        if matched:
            out.append(Candidate(job, matched))
    return out


def dedup_candidates(candidates: List[Candidate], priority: Dict[str, int]) -> List[Candidate]:
    """Collapse the same job found on several sources, keeping the highest-priority source's copy."""
    ordered = sorted(candidates, key=lambda c: priority.get(c.job.source_name, 99))
    taken: Dict[str, Candidate] = {}
    out = []
    for cand in ordered:
        existing = next((taken[k] for k in cand.job.keys if k in taken), None)
        if existing is not None:
            also = existing.job.extra.setdefault("also_on", [])
            if cand.job.source != existing.job.source and cand.job.source not in also:
                also.append(cand.job.source)
            continue
        for key in cand.job.keys:
            taken[key] = cand
        out.append(cand)
    return out
