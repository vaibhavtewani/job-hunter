from datetime import timedelta

from jobhunter.filtering import dedup_candidates, filter_jobs
from jobhunter.scoring import score_job
from jobhunter.state import State

from .helpers import NOW, PROFILE, make_job


def test_title_exclude_applies_to_title_only():
    jobs = [make_job("Strategy Analyst", description="work with senior stakeholders"), make_job("Senior Strategy Analyst")]
    assert [c.job.title for c in filter_jobs(jobs, [PROFILE], 21, now=NOW)] == ["Strategy Analyst"]


def test_location_and_age_filters():
    jobs = [
        make_job("Strategy Analyst", location="London, UK"),
        make_job("Strategy Analyst", age_days=40),
        make_job("Business Analyst", location="Riyadh, Saudi Arabia"),
    ]
    assert [c.job.location for c in filter_jobs(jobs, [PROFILE], 21, now=NOW)] == ["Riyadh, Saudi Arabia"]


def test_trusted_source_skips_location_check():
    job = make_job("Strategy Analyst", location="", source="gmail_alerts:linkedin")
    assert filter_jobs([job], [PROFILE], 21, now=NOW) == []
    assert len(filter_jobs([job], [PROFILE], 21, trusted_location_sources={"gmail_alerts"}, now=NOW)) == 1


def test_entry_level_scores_above_experienced():
    good = make_job("Strategy Analyst", description="Graduate role, 0-2 years. Market sizing, Excel, stakeholder management.")
    weak = make_job("Strategy Manager", location="Riyadh", description="7+ years required. Arabic speaker.", age_days=10)
    good_score, reasons = score_job(good, PROFILE, NOW)
    assert good_score > 70 > score_job(weak, PROFILE, NOW)[0]
    assert any(r.startswith("title:") for r in reasons)


def test_dedup_across_sources_prefers_direct_employer():
    via_google = make_job("Strategy Analyst", source="serpapi:google_jobs", company="Acme LLC",
                          url="https://www.linkedin.com/jobs/view/1?trk=abc")
    direct = make_job("Strategy Analyst", source="greenhouse:acme", company="Acme",
                      url="https://boards.greenhouse.io/acme/jobs/9")
    out = dedup_candidates(filter_jobs([via_google, direct], [PROFILE], 21, now=NOW), {"greenhouse": 0, "serpapi": 5})
    assert len(out) == 1
    assert out[0].job.source == "greenhouse:acme"
    assert out[0].job.extra["also_on"] == ["serpapi:google_jobs"]


def test_state_roundtrip_and_prune(tmp_path):
    state = State.load(tmp_path)
    job = make_job("Strategy Analyst")
    assert not state.is_seen(job)
    state.mark_seen(job, NOW - timedelta(days=100))
    state.mark_source_run("greenhouse", NOW)
    state.save()

    again = State.load(tmp_path)
    assert again.is_seen(make_job("Strategy Analyst", url="https://elsewhere.example/1"))  # same company + title
    assert again.last_run("greenhouse") == NOW
    assert again.prune(90, NOW) == 2
    assert not again.is_seen(job)
