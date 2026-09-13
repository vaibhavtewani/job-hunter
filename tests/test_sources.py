"""Parsers against trimmed copies of real API responses (captured Sep 2026)."""
from jobhunter.sources import ashby, greenhouse, lever, serpapi, smartrecruiters, workday
from jobhunter.sources.email_parsers import match_job_link, parse_alert_html

from .helpers import NOW


def test_greenhouse():
    data = {"jobs": [{
        "absolute_url": "https://boards.greenhouse.io/careem/jobs/8783573002?gh_jid=8783573002",
        "location": {"name": "Dubai, United Arab Emirates"}, "id": 8783573002,
        "updated_at": "2026-09-08T11:02:32-04:00", "first_published": "2026-09-07T11:02:32-04:00",
        "title": " Strategy  Associate ", "company_name": "Careem",
    }]}
    [job] = greenhouse.parse_jobs(data, "careem")
    assert (job.title, job.company, job.location) == ("Strategy Associate", "Careem", "Dubai, United Arab Emirates")
    assert job.posted_at.day == 7 and job.extra == {"board": "careem", "job_id": "8783573002"}


def test_lever():
    items = [{
        "text": "Business Development Associate", "hostedUrl": "https://jobs.lever.co/fresha/abc",
        "categories": {"commitment": "Full-time", "location": "Dubai", "team": "BD", "allLocations": ["Dubai", "Abu Dhabi"]},
        "createdAt": 1779105321254, "descriptionPlain": "About the role", "workplaceType": "onsite",
        "lists": [{"text": "Requirements", "content": "<li>Excel</li>"}], "additionalPlain": "",
    }]
    [job] = lever.parse_postings(items, "fresha", "Fresha")
    assert job.location == "Dubai, Abu Dhabi" and not job.remote
    assert "Requirements: Excel" in job.description


def test_ashby_skips_unlisted():
    data = {"jobs": [
        {"title": "Strategy & Ops", "location": "Dubai", "secondaryLocations": [{"location": "Riyadh"}],
         "publishedAt": "2026-08-12T05:44:50.125+00:00", "isListed": True, "isRemote": False,
         "jobUrl": "https://jobs.ashbyhq.com/ziina/1", "descriptionPlain": "desc"},
        {"title": "Hidden", "isListed": False, "jobUrl": "https://jobs.ashbyhq.com/ziina/2"},
    ]}
    [job] = ashby.parse_jobs(data, "ziina", "Ziina")
    assert job.location == "Dubai, Riyadh" and job.description == "desc"


def test_smartrecruiters():
    items = [{
        "id": "744000149023210", "name": "Consultant - Automotive",
        "company": {"identifier": "RolandBerger", "name": "Roland Berger"},
        "releasedDate": "2026-09-11T13:29:20.586Z",
        "location": {"city": "Dubai", "country": "ae", "remote": False, "fullLocation": "Dubai, United Arab Emirates"},
        "experienceLevel": {"label": "Entry Level"},
    }]
    [job] = smartrecruiters.parse_postings(items, "RolandBerger")
    assert job.url == "https://jobs.smartrecruiters.com/RolandBerger/744000149023210"
    assert job.company == "Roland Berger" and job.extra["experience_level"] == "Entry Level"


def test_workday_multi_location_uses_search_term():
    board = {"host": "mmc.wd1.myworkdayjobs.com", "tenant": "mmc", "site": "MMC", "company": "Oliver Wyman"}
    posting = {"title": "Consultant Middle East", "externalPath": "/job/Dubai---Media/Consultant_R_1",
               "locationsText": "2 Locations", "postedOn": "Posted 3 Days Ago"}
    job = workday.parse_posting(posting, board, "Dubai", NOW)
    assert job.url == "https://mmc.wd1.myworkdayjobs.com/MMC/job/Dubai---Media/Consultant_R_1"
    assert job.location == "2 Locations (matched search: Dubai)"
    assert job.age_days(NOW) == 3


def test_serpapi():
    data = {"jobs_results": [{
        "title": "Strategy Analyst", "company_name": "Acme", "location": "Dubai - United Arab Emirates", "via": "LinkedIn",
        "description": "d", "detected_extensions": {"posted_at": "2 days ago"},
        "apply_options": [{"title": "LinkedIn", "link": "https://www.linkedin.com/jobs/view/1"}],
    }]}
    [job] = serpapi.parse_results(data, NOW)
    assert job.url == "https://www.linkedin.com/jobs/view/1" and job.extra["via"] == "LinkedIn"


def test_match_job_link_through_tracking_redirect():
    href = "https://click.bayt.com/?url=https%3A%2F%2Fwww.bayt.com%2Fen%2Fuae%2Fjobs%2Fbusiness-analyst-5123456%2F"
    assert match_job_link(href) == ("bayt", "5123456", "https://www.bayt.com/en/uae/jobs/business-analyst-5123456")
    assert match_job_link("https://www.linkedin.com/comm/jobs/view/4012345678/?trackingId=abc")[2] == \
        "https://www.linkedin.com/jobs/view/4012345678/"
    assert match_job_link("https://www.linkedin.com/feed/") is None


def test_parse_alert_html():
    html = """
    <table>
      <tr><td>
        <a href="https://www.linkedin.com/comm/jobs/view/4012345678/?trackingId=abc&refId=x"><img alt="logo"></a>
        <a href="https://www.linkedin.com/comm/jobs/view/4012345678/?trackingId=abc">Strategy Analyst</a>
        <p>Acme Consulting · Dubai, United Arab Emirates (On-site)</p>
        <p>Actively recruiting</p>
      </td></tr>
      <tr><td>
        <a href="https://click.bayt.com/?url=https%3A%2F%2Fwww.bayt.com%2Fen%2Fuae%2Fjobs%2Fbusiness-analyst-5123456%2F">Business Analyst</a>
        <div>Gulf Holdings</div><div>Abu Dhabi, UAE</div>
        <a href="https://click.bayt.com/?url=https%3A%2F%2Fwww.bayt.com%2Fen%2Fuae%2Fjobs%2Fbusiness-analyst-5123456%2F">View job</a>
      </td></tr>
    </table>"""
    assert parse_alert_html(html) == [
        {"board": "linkedin", "url": "https://www.linkedin.com/jobs/view/4012345678/", "title": "Strategy Analyst",
         "company": "Acme Consulting", "location": "Dubai, United Arab Emirates (On-site)"},
        {"board": "bayt", "url": "https://www.bayt.com/en/uae/jobs/business-analyst-5123456", "title": "Business Analyst",
         "company": "Gulf Holdings", "location": "Abu Dhabi, UAE"},
    ]
