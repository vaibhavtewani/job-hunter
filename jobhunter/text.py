"""Text helpers: whitespace/HTML cleanup, normalisation for keys, and phrase matching."""
from __future__ import annotations

import html
import re
import unicodedata
from functools import lru_cache
from typing import Iterable, List

from bs4 import BeautifulSoup

_WS = re.compile(r"\s+")
_DASHES = str.maketrans({"–": "-", "—": "-", "‒": "-", "−": "-"})


def clean_ws(value) -> str:
    return _WS.sub(" ", str(value or "")).strip()


def html_to_text(raw: str) -> str:
    """Convert (possibly entity-escaped) HTML to plain text."""
    if not raw:
        return ""
    if "&lt;" in raw:  # Greenhouse returns escaped HTML
        raw = html.unescape(raw)
    return clean_ws(BeautifulSoup(raw, "html.parser").get_text(" "))


def normalize(value: str) -> str:
    """Lowercase ASCII words separated by single spaces; used for dedup keys."""
    value = unicodedata.normalize("NFKD", value or "").encode("ascii", "ignore").decode()
    return " ".join(re.sub(r"[^a-z0-9]+", " ", value.lower()).split())


@lru_cache(maxsize=4096)
def _phrase_re(phrase: str):
    words = phrase.lower().translate(_DASHES).split()
    body = r"[\s\-_/]+".join(re.escape(w) for w in words)
    # Word-ish boundaries that also work for phrases like "m&a" or "0-2 years".
    return re.compile(r"(?<![a-z0-9])" + body + r"(?![a-z0-9])", re.IGNORECASE)


def find_phrases(text: str, phrases: Iterable[str]) -> List[str]:
    """Return the phrases (in the given order) that occur in text as whole words."""
    haystack = (text or "").translate(_DASHES)
    return [p for p in phrases if p and p.strip() and _phrase_re(p.strip()).search(haystack)]


def slugify(value: str, max_len: int = 40) -> str:
    return normalize(value).replace(" ", "-")[:max_len].strip("-") or "x"
