"""Deterministic, explainable 0-100 relevance score for a job against a search profile."""
from __future__ import annotations

from datetime import datetime
from typing import List, Optional, Tuple

from .filtering import SearchProfile
from .models import Job
from .text import find_phrases

TITLE_BASE = 40
TITLE_EXTRA = 5
TITLE_CAP = 50
KEYWORD_EACH, KEYWORD_CAP = 4, 30
BOOST_EACH, BOOST_CAP = 6, 15
PENALTY_EACH = 15
PREFERRED_LOCATION = 10
FRESH_DAYS, FRESH_BONUS = 3, 5


def score_job(job: Job, profile: SearchProfile, now: Optional[datetime] = None) -> Tuple[int, List[str]]:
    reasons: List[str] = []
    score = 0
    text = job.title + "\n" + job.description

    title_hits = find_phrases(job.title, profile.title_include)
    if title_hits:
        score += min(TITLE_BASE + TITLE_EXTRA * (len(title_hits) - 1), TITLE_CAP)
        reasons.append("title: " + ", ".join(title_hits))

    keywords = find_phrases(text, profile.score_keywords)
    if keywords:
        score += min(KEYWORD_EACH * len(keywords), KEYWORD_CAP)
        reasons.append("keywords: " + ", ".join(keywords[:8]) + (" +%d" % (len(keywords) - 8) if len(keywords) > 8 else ""))

    boosts = find_phrases(text, profile.boost_phrases)
    if boosts:
        score += min(BOOST_EACH * len(boosts), BOOST_CAP)
        reasons.append("entry-level signals: " + ", ".join(boosts))

    penalties = find_phrases(job.title, profile.penalty_title) + find_phrases(text, profile.penalty_text)
    if penalties:
        score -= PENALTY_EACH * len(penalties)
        reasons.append("penalties: " + ", ".join(penalties))

    preferred = find_phrases(job.location, profile.preferred_locations)
    if preferred:
        score += PREFERRED_LOCATION
        reasons.append("preferred location")

    age = job.age_days(now)
    if age is not None and age <= FRESH_DAYS:
        score += FRESH_BONUS
        reasons.append("fresh")

    return max(0, min(100, score)), reasons


def apply_best_score(job: Job, profiles: List[SearchProfile], now: Optional[datetime] = None) -> None:
    best = None
    for profile in profiles:
        score, reasons = score_job(job, profile, now)
        if best is None or score > best[0]:
            best = (score, reasons, profile.name)
    if best:
        job.score, job.reasons, job.profile = best
