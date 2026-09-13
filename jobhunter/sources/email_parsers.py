"""Best-effort extraction of jobs from board alert emails.

Alert layouts change without notice, so parsing relies on stable job URL patterns and treats the text
around each link as hints. Tune the patterns against real emails in your inbox.
"""
from __future__ import annotations

import re
from collections import OrderedDict
from typing import Dict, List, Optional, Tuple
from urllib.parse import unquote

from bs4 import BeautifulSoup

from ..text import clean_ws

# (board, pattern with the job id as group 1, canonical URL template or None to reuse the matched URL)
BOARD_PATTERNS = [
    ("linkedin", re.compile(r"linkedin\.com/(?:comm/)?jobs/view/(?:[^/?#\s\"']*?-)?(\d{6,})", re.I),
     "https://www.linkedin.com/jobs/view/{id}/"),
    ("indeed", re.compile(r"indeed\.[a-z.]+/(?:rc/clk|viewjob|pagead/clk|m/viewjob)[^\s\"'#]*?[?&](?:jk|vjk)=([0-9a-f]{10,})", re.I),
     "https://www.indeed.com/viewjob?jk={id}"),
    ("bayt", re.compile(r"bayt\.com/[^\s\"'?#]*?/jobs/[^\s\"'?#]*?-(\d{5,})/?", re.I), None),
    ("gulftalent", re.compile(r"gulftalent\.com/[^\s\"'?#]*?jobs/[^\s\"'?#]*?-(\d{4,})", re.I), None),
    ("naukrigulf", re.compile(r"naukrigulf\.com/[^\s\"'?#]*?-jid-(\d{6,})", re.I), None),
]

_NOISE = re.compile(
    r"^(view( job| jobs| all.*| more.*| details)?|apply( now)?|easy apply|see (all|more).*|save( job)?|learn more|new|"
    r"promoted|actively recruiting|be an early applicant|recommended.*|\d+\s+(applicants?|connections?|alumni|school alumni).*|"
    r".{0,2})$",
    re.I,
)
_SEPARATORS = (" · ", " • ", " | ", " - ")


def match_job_link(href: str) -> Optional[Tuple[str, str, str]]:
    """Return (board, job_id, canonical_url) if href (possibly a tracking redirect) points at a job."""
    decoded = unquote(unquote(href or ""))
    for board, pattern, template in BOARD_PATTERNS:
        found = pattern.search(decoded)
        if found:
            url = template.format(id=found.group(1)) if template else "https://www." + found.group(0).rstrip("/")
            return board, found.group(1), url
    return None


def _context_lines(anchor, own_key: Tuple[str, str], max_depth: int = 6) -> List[str]:
    """Text of the largest ancestor block that contains links to this job only."""
    lines: List[str] = []
    node = anchor
    for _ in range(max_depth):
        parent = node.parent
        if parent is None or parent.name in ("body", "html", "[document]"):
            break
        keys = set()
        for link in parent.find_all("a", href=True):
            matched = match_job_link(link["href"])
            if matched:
                keys.add(matched[:2])
        if keys - {own_key}:
            break
        lines = [clean_ws(s) for s in parent.stripped_strings]
        node = parent
    return [line for line in lines if line]


def _company_and_location(lines: List[str], title: str) -> Tuple[str, str]:
    rest = [line for line in lines if line != title and not _NOISE.match(line)]
    if not rest:
        return "", ""
    first = rest[0]
    for sep in _SEPARATORS:
        if sep in first:
            company, location = first.split(sep, 1)
            return company.strip(), location.strip()
    return first, rest[1] if len(rest) > 1 else ""


def parse_alert_html(html: str) -> List[Dict[str, str]]:
    soup = BeautifulSoup(html or "", "html.parser")
    found: "OrderedDict[Tuple[str, str], dict]" = OrderedDict()
    for anchor in soup.find_all("a", href=True):
        matched = match_job_link(anchor["href"])
        if not matched:
            continue
        board, job_id, url = matched
        entry = found.setdefault((board, job_id), {"board": board, "url": url, "texts": [], "anchor": anchor})
        text = clean_ws(anchor.get_text(" "))
        if text and text not in entry["texts"]:
            entry["texts"].append(text)

    results = []
    for key, entry in found.items():
        context = _context_lines(entry["anchor"], key)
        texts = [t for t in entry["texts"] if not _NOISE.match(t)]
        title = texts[0] if texts else next((line for line in context if not _NOISE.match(line)), "")
        if not title:
            continue
        company, location = _company_and_location(texts[1:] + context, title)
        results.append({"board": entry["board"], "url": entry["url"], "title": title, "company": company, "location": location})
    return results
