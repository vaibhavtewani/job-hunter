"""The adapter interface every job source implements."""
from __future__ import annotations

import logging
import os
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

import httpx

from ..http import redact, request_json
from ..models import Job

log = logging.getLogger(__name__)


@dataclass
class SourceContext:
    client: Optional[httpx.Client]
    now: datetime


class Source(ABC):
    name = ""
    required_env: Tuple[str, ...] = ()
    default_trust_location = False

    def __init__(self, cfg: Optional[Dict[str, Any]], ctx: Optional[SourceContext]):
        self.cfg = cfg or {}
        self.ctx = ctx
        self.errors: List[str] = []
        # Trusted sources were already location-targeted upstream (e.g. an alert set up for "Dubai").
        self.trust_location = bool(self.cfg.get("trust_location", self.default_trust_location))

    @abstractmethod
    def fetch(self) -> List[Job]:
        """Return every current posting this source can see; filtering happens later."""

    def enrich(self, job: Job) -> None:
        """Optionally fill in details (usually the description) for a new job that passed filters."""

    @property
    def supports_enrich(self) -> bool:
        return type(self).enrich is not Source.enrich

    @property
    def min_interval_hours(self) -> float:
        return float(self.cfg.get("min_interval_hours") or 0)

    def missing_env(self) -> List[str]:
        return [var for var in self.required_env if not os.environ.get(var)]

    def describe(self) -> str:
        for key in ("boards", "companies", "queries", "senders"):
            if key in self.cfg:
                return "%d %s" % (len(self.cfg.get(key) or []), key)
        return ""

    def fail(self, label: str, exc: BaseException) -> None:
        text = redact(str(exc)).strip()
        message = "%s:%s: %s" % (self.name, label, text.splitlines()[0] if text else type(exc).__name__)
        self.errors.append(message)
        log.warning(message)

    def get_json(self, url: str, **kwargs):
        return request_json(self.ctx.client, "GET", url, **kwargs)

    def post_json(self, url: str, payload: dict, **kwargs):
        return request_json(self.ctx.client, "POST", url, json=payload, **kwargs)
