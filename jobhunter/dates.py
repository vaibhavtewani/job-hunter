"""Date parsing for the many formats job sources use."""
from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime
from typing import Optional

_ISO = re.compile(
    r"^(\d{4}-\d{2}-\d{2})(?:[T ](\d{2}:\d{2}(?::\d{2})?)(\.\d+)?)?\s*(Z|[+-]\d{2}:?\d{2})?$"
)
_RELATIVE = re.compile(r"(\d+)(\+?)\s*(minute|min|hour|hr|day|week|month)s?\b", re.IGNORECASE)
_UNITS = {
    "minute": timedelta(minutes=1),
    "min": timedelta(minutes=1),
    "hour": timedelta(hours=1),
    "hr": timedelta(hours=1),
    "day": timedelta(days=1),
    "week": timedelta(weeks=1),
    "month": timedelta(days=30),
}


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


def parse_datetime(value) -> Optional[datetime]:
    """Parse ISO-8601 strings, epoch seconds/milliseconds, or RFC 2822 dates into aware UTC."""
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        dt = value
    elif isinstance(value, (int, float)):
        seconds = float(value) / 1000 if value > 1e11 else float(value)
        dt = datetime.fromtimestamp(seconds, tz=timezone.utc)
    else:
        text = str(value).strip()
        match = _ISO.match(text)
        if match:
            date, time_, _frac, tz = match.groups()
            if time_ and time_.count(":") == 1:
                time_ += ":00"
            iso = date + "T" + (time_ or "00:00:00")
            if tz and tz != "Z":
                iso += tz if ":" in tz else tz[:3] + ":" + tz[3:]
            dt = datetime.fromisoformat(iso)
        else:
            try:
                dt = parsedate_to_datetime(text)
            except (TypeError, ValueError, IndexError):
                return None
            if dt is None:
                return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def parse_relative(text: str, now: Optional[datetime] = None) -> Optional[datetime]:
    """Parse phrases like 'Posted 3 Days Ago', 'Posted Yesterday', '17 hours ago', '30+ days ago'."""
    if not text:
        return None
    now = now or utcnow()
    lowered = text.lower()
    if "today" in lowered or "just now" in lowered or "just posted" in lowered:
        return now
    if "yesterday" in lowered:
        return now - timedelta(days=1)
    match = _RELATIVE.search(lowered)
    if not match:
        return None
    count = int(match.group(1)) + (1 if match.group(2) else 0)  # "30+ days" is older than 30 days
    return now - count * _UNITS[match.group(3).lower()]
