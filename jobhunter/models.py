"""The unified Job record every source normalises into, plus the dedup keys derived from it."""
from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Dict, List, Optional
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from .dates import utcnow
from .text import normalize

# Query parameters that identify a job; everything else (utm_*, trackingId, refId...) is dropped.
_KEEP_QUERY = {"gh_jid", "jk", "vjk", "jobid", "job_id", "currentjobid"}
_COMPANY_SUFFIX = re.compile(
    r"\b(llc|ltd|limited|inc|incorporated|fz|fze|fzco|fzllc|dmcc|plc|pjsc|wll|co|company|holding|holdings|group)\b"
)


def canonical_url(url: str) -> str:
    parts = urlsplit((url or "").strip())
    query = sorted((k, v) for k, v in parse_qsl(parts.query) if k.lower() in _KEEP_QUERY)
    host = parts.netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    return urlunsplit(("https", host, parts.path.rstrip("/") or "/", urlencode(query), ""))


def company_key(name: str) -> str:
    return " ".join(_COMPANY_SUFFIX.sub(" ", normalize(name)).split())


def _digest(value: str) -> str:
    return hashlib.sha1(value.encode("utf-8")).hexdigest()[:16]


@dataclass
class Job:
    title: str
    company: str
    url: str
    source: str  # "<source name>:<detail>", e.g. "greenhouse:careem"
    location: str = ""
    description: str = ""
    posted_at: Optional[datetime] = None
    remote: bool = False
    extra: Dict[str, Any] = field(default_factory=dict)
    # Filled in by the pipeline.
    profile: str = ""
    score: int = 0
    reasons: List[str] = field(default_factory=list)

    @property
    def source_name(self) -> str:
        return self.source.split(":", 1)[0]

    @property
    def url_key(self) -> str:
        return "u:" + _digest(canonical_url(self.url))

    @property
    def title_key(self) -> Optional[str]:
        """Same company + same title = same job, even when found on different boards."""
        company = company_key(self.company)
        if not company:
            return None
        return "t:" + _digest(company + "|" + normalize(self.title))

    @property
    def keys(self) -> List[str]:
        return [k for k in (self.url_key, self.title_key) if k]

    def age_days(self, now: Optional[datetime] = None) -> Optional[float]:
        if not self.posted_at:
            return None
        return ((now or utcnow()) - self.posted_at).total_seconds() / 86400

    def to_dict(self, include_description: bool = False) -> Dict[str, Any]:
        data = {
            "title": self.title,
            "company": self.company,
            "location": self.location,
            "url": self.url,
            "source": self.source,
            "remote": self.remote,
            "posted_at": self.posted_at.isoformat() if self.posted_at else None,
            "profile": self.profile,
            "score": self.score,
            "reasons": self.reasons,
            "extra": {k: v for k, v in self.extra.items() if isinstance(v, (str, int, float, bool, list))},
        }
        if include_description:
            data["description"] = self.description
        return data
