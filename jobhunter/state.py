"""Persistent run state: which jobs were already seen and when each source last ran."""
from __future__ import annotations

import json
import os
from datetime import datetime, timedelta
from pathlib import Path
from typing import Dict, Optional

from .dates import parse_datetime, utcnow
from .models import Job


class State:
    def __init__(self, path: Path, data: Optional[dict] = None):
        data = data or {}
        self.path = path
        self.seen: Dict[str, str] = dict(data.get("seen", {}))
        self.sources_last_run: Dict[str, str] = dict(data.get("sources_last_run", {}))

    @classmethod
    def load(cls, state_dir) -> "State":
        path = Path(state_dir) / "seen.json"
        if path.exists():
            with open(path, encoding="utf-8") as fh:
                return cls(path, json.load(fh))
        return cls(path)

    def is_seen(self, job: Job) -> bool:
        return any(key in self.seen for key in job.keys)

    def mark_seen(self, job: Job, when: Optional[datetime] = None) -> None:
        stamp = (when or utcnow()).isoformat(timespec="seconds")
        for key in job.keys:
            self.seen.setdefault(key, stamp)

    def last_run(self, source: str) -> Optional[datetime]:
        return parse_datetime(self.sources_last_run.get(source))

    def mark_source_run(self, source: str, when: Optional[datetime] = None) -> None:
        self.sources_last_run[source] = (when or utcnow()).isoformat(timespec="seconds")

    def prune(self, retention_days: int, now: Optional[datetime] = None) -> int:
        cutoff = (now or utcnow()) - timedelta(days=retention_days)
        stale = [k for k, v in self.seen.items() if (parse_datetime(v) or cutoff) < cutoff]
        for key in stale:
            del self.seen[key]
        return len(stale)

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        with open(tmp, "w", encoding="utf-8") as fh:
            json.dump(
                {"version": 1, "sources_last_run": self.sources_last_run, "seen": self.seen},
                fh,
                indent=1,
                sort_keys=True,
            )
        os.replace(tmp, self.path)
