from pathlib import Path

from jobhunter import pipeline
from jobhunter.apply.pack import build_pack
from jobhunter.config import Settings, load_yaml
from jobhunter.dates import utcnow
from jobhunter.models import Job
from jobhunter.sources import REGISTRY
from jobhunter.sources.base import Source

from .helpers import NOW

ROOT = Path(__file__).resolve().parents[1]
SECRET_ENV = ("GMAIL_ADDRESS", "GMAIL_APP_PASSWORD", "TELEGRAM_BOT_TOKEN", "TELEGRAM_CHAT_ID",
              "SERPAPI_KEY", "ANTHROPIC_API_KEY", "STATE_DIR", "OUTPUT_DIR", "GITHUB_REPOSITORY")


class FakeSource(Source):
    name = "fake"

    def fetch(self):
        return [
            Job(title="Strategy Analyst", company="Acme", url="https://acme.example/jobs/1", source="fake:acme",
                location="Dubai, UAE", description="Graduate role: market sizing and Excel.", posted_at=utcnow()),
            Job(title="Senior Strategy Director", company="Acme", url="https://acme.example/jobs/2", source="fake:acme",
                location="Dubai, UAE", posted_at=utcnow()),
        ]


def test_repo_config_and_profile_are_valid():
    settings = Settings.load(ROOT / "config.yaml", ROOT / "profile.yaml")
    assert settings.search_profiles
    assert set(settings.sources) <= set(REGISTRY)
    assert settings.profile["candidate"]["name"]


def test_pipeline_end_to_end(tmp_path, monkeypatch):
    for var in SECRET_ENV:
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setattr(pipeline, "REGISTRY", {"fake": FakeSource})
    monkeypatch.setattr(pipeline, "SOURCE_PRIORITY", {"fake": 0})
    config = {
        "run": {"state_dir": "state", "output_dir": "out"},
        "digest": {"min_score": 40, "high_score": 50},
        "search_profiles": [{"name": "t", "title_include": ["strategy"], "title_exclude": ["senior"],
                             "locations": ["dubai"], "score_keywords": ["market sizing", "excel"]}],
        "sources": {"fake": {"enabled": True}},
    }
    settings = Settings(config, load_yaml(ROOT / "profile.yaml"), tmp_path)

    first = pipeline.run(settings)
    assert [j.title for j in first.matches] == ["Strategy Analyst"]
    assert (tmp_path / "out" / "digest.html").exists()
    assert (tmp_path / "state" / "seen.json").exists()
    assert len(list((tmp_path / "state" / "applications").iterdir())) == 1

    second = pipeline.run(settings)
    assert second.candidates == 1 and second.new == 0 and second.matches == []


class MultiLocationSource(Source):
    """Like Workday: the listing says '2 Locations', the detail page reveals them."""
    name = "multi"

    def fetch(self):
        return [Job(title="Strategy Consultant", company="Acme", url="https://acme.example/jobs/3", source="multi:acme",
                    location="2 Locations (matched search: Dubai)", posted_at=utcnow())]

    def enrich(self, job):
        job.description = "Consulting role."
        job.location = "Luxembourg, Brussels"


def test_location_rechecked_after_enrichment(tmp_path, monkeypatch):
    for var in SECRET_ENV:
        monkeypatch.delenv(var, raising=False)
    monkeypatch.setattr(pipeline, "REGISTRY", {"multi": MultiLocationSource})
    monkeypatch.setattr(pipeline, "SOURCE_PRIORITY", {"multi": 0})
    config = {
        "run": {"state_dir": "state", "output_dir": "out"},
        "search_profiles": [{"name": "t", "title_include": ["strategy"], "locations": ["dubai"]}],
        "sources": {"multi": {"enabled": True}},
    }
    report = pipeline.run(Settings(config, {}, tmp_path))
    assert report.new == 1 and report.matches == []


def test_static_pack_only_reorders_profile_bullets(tmp_path, monkeypatch):
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    profile = load_yaml(ROOT / "profile.yaml")
    job = Job(title="Pricing Strategy Analyst", company="Acme", url="https://acme.example/1", source="manual:cli",
              location="Dubai", description="Pricing, revenue dashboards and competitor benchmarking for hotel partners.",
              score=80, reasons=["title: strategy"])
    folder = build_pack(job, profile, tmp_path, {}, None, NOW)
    assert sorted(p.name for p in folder.iterdir()) == ["README.md", "answers.yaml", "cover_letter.md", "cv_tailored.md", "job.json"]
    cv = (folder / "cv_tailored.md").read_text(encoding="utf-8")
    for role in profile["experience"] + profile["projects"]:
        for bullet in role["bullets"]:
            assert bullet in cv
    letter = (folder / "cover_letter.md").read_text(encoding="utf-8")
    assert "Dear Hiring Team at Acme" in letter and "118+ hotel partner portfolios" in letter
