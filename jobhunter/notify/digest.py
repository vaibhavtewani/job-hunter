"""Renders the digest (HTML + plain text) for a run."""
from __future__ import annotations

from pathlib import Path
from typing import Tuple

from jinja2 import Environment, FileSystemLoader

TEMPLATES = Path(__file__).resolve().parent.parent / "templates"
_html_env = Environment(loader=FileSystemLoader(str(TEMPLATES)), autoescape=True)
_text_env = Environment(loader=FileSystemLoader(str(TEMPLATES)), autoescape=False, trim_blocks=True, lstrip_blocks=True)


def _badge_color(score: int, high_score: int) -> str:
    if score >= high_score:
        return "#1a7f37"
    return "#9a6700" if score >= 50 else "#6e7781"


def render_digest(report, max_jobs: int, high_score: int) -> Tuple[str, str, str]:
    """Return (subject, html, text). `report` is a pipeline.RunReport."""
    matches = report.matches
    if matches:
        top = matches[0]
        subject = "Job Hunter: %d new match%s, top: %s @ %s (%d)" % (
            len(matches), "" if len(matches) == 1 else "es", top.title, top.company, top.score)
    else:
        subject = "Job Hunter: no new matches"
    context = {
        "subject": subject,
        "jobs": matches[:max_jobs],
        "total": len(matches),
        "report": report,
        "run_time": report.started_at.strftime("%Y-%m-%d %H:%M"),
        "badge": lambda score: _badge_color(score, high_score),
    }
    html = _html_env.get_template("digest.html.j2").render(**context)
    text = _text_env.get_template("digest.txt.j2").render(**context)
    return subject, html, text
