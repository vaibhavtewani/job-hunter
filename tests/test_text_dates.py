from datetime import datetime, timedelta, timezone

from jobhunter.dates import parse_datetime, parse_relative
from jobhunter.models import Job
from jobhunter.text import find_phrases, html_to_text

from .helpers import NOW


def test_find_phrases_uses_word_boundaries():
    assert find_phrases("Senior Strategy Manager", ["senior"]) == ["senior"]
    assert find_phrases("Partnerships Lead", ["partner"]) == []
    assert find_phrases("M&A Analyst", ["m&a"]) == ["m&a"]
    assert find_phrases("Sr. Consultant", ["sr"]) == ["sr"]
    assert find_phrases("Entry-level role, 0–2 years", ["entry level", "0-2 years"]) == ["entry level", "0-2 years"]


def test_html_to_text_handles_escaped_html():
    assert html_to_text("&lt;p&gt;Hello &amp;amp; welcome&lt;/p&gt;") == "Hello & welcome"


def test_parse_datetime_formats():
    assert parse_datetime("2026-09-07T11:02:32-04:00") == datetime(2026, 9, 7, 15, 2, 32, tzinfo=timezone.utc)
    assert parse_datetime("2026-08-12T05:44:50.125+00:00") == datetime(2026, 8, 12, 5, 44, 50, tzinfo=timezone.utc)
    assert parse_datetime("2026-09-11T13:29:20.586Z").day == 11
    assert parse_datetime(1779105321254).year == 2026
    assert parse_datetime("Mon, 14 Sep 2026 08:00:00 +0400") == datetime(2026, 9, 14, 4, tzinfo=timezone.utc)
    assert parse_datetime("garbage") is None


def test_parse_relative():
    assert parse_relative("Posted Today", NOW) == NOW
    assert parse_relative("Posted Yesterday", NOW) == NOW - timedelta(days=1)
    assert parse_relative("Posted 3 Days Ago", NOW) == NOW - timedelta(days=3)
    assert parse_relative("Posted 30+ Days Ago", NOW) == NOW - timedelta(days=31)
    assert parse_relative("17 hours ago", NOW) == NOW - timedelta(hours=17)
    assert parse_relative("no date", NOW) is None


def test_url_key_ignores_tracking_parameters():
    a = Job("t", "c", "https://www.linkedin.com/jobs/view/123/?trackingId=x&refId=y", "s")
    b = Job("t", "c", "http://linkedin.com/jobs/view/123", "s")
    assert a.url_key == b.url_key
    assert Job("t", "c", "https://x.com/j?gh_jid=1", "s").url_key != Job("t", "c", "https://x.com/j?gh_jid=2", "s").url_key
