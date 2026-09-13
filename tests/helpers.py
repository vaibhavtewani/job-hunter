from datetime import datetime, timedelta, timezone

from jobhunter.filtering import SearchProfile
from jobhunter.models import Job

NOW = datetime(2026, 9, 14, 12, 0, tzinfo=timezone.utc)

PROFILE = SearchProfile.from_dict({
    "name": "test",
    "title_include": ["strategy", "business analyst", "consultant"],
    "title_exclude": ["senior", "director", "head of"],
    "locations": ["dubai", "uae", "riyadh"],
    "preferred_locations": ["dubai"],
    "score_keywords": ["market sizing", "stakeholder", "excel"],
    "boost_phrases": ["graduate", "0-2 years"],
    "penalty_title": ["manager"],
    "penalty_text": ["arabic speaker", "7+ years"],
})


def make_job(title, location="Dubai, UAE", description="", source="greenhouse:acme", company="Acme",
             url=None, age_days=1):
    return Job(
        title=title,
        company=company,
        url=url or "https://jobs.example.com/%s/%s" % (company, title.replace(" ", "-")),
        source=source,
        location=location,
        description=description,
        posted_at=NOW - timedelta(days=age_days),
    )
