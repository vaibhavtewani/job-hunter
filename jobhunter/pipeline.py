"""One run: fetch -> filter -> dedup -> enrich -> score -> application packs -> digest -> notify -> save state."""
from __future__ import annotations

import json
import logging
import os
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Sequence

import httpx

from .apply.pack import build_pack
from .config import Settings
from .dates import utcnow
from .filtering import Candidate, dedup_candidates, filter_jobs
from .http import DEFAULT_USER_AGENT, make_client, redact
from .models import Job
from .notify.digest import render_digest
from .notify.mailer import email_missing_env, send_email
from .notify.telegram import send_telegram, telegram_missing_env
from .scoring import apply_best_score
from .sources import REGISTRY, SOURCE_PRIORITY
from .sources.base import Source, SourceContext
from .state import State

log = logging.getLogger(__name__)


class NotificationError(RuntimeError):
    """Every notification channel failed; state is not saved so the next run retries."""


@dataclass
class RunReport:
    started_at: datetime
    fetched: Dict[str, int] = field(default_factory=dict)
    failed: List[str] = field(default_factory=list)
    skipped: Dict[str, str] = field(default_factory=dict)
    errors: List[str] = field(default_factory=list)
    candidates: int = 0
    new: int = 0
    matches: List[Job] = field(default_factory=list)
    notified: List[str] = field(default_factory=list)

    @property
    def scanned(self) -> int:
        return sum(self.fetched.values())

    @property
    def all_sources_failed(self) -> bool:
        return bool(self.failed) and not self.fetched


def build_sources(settings: Settings, ctx: SourceContext, state: State, only: Optional[Sequence[str]],
                  now: datetime, report: RunReport) -> List[Source]:
    if only:
        unknown = set(only) - set(REGISTRY)
        if unknown:
            raise ValueError("unknown source(s): %s (known: %s)" % (", ".join(sorted(unknown)), ", ".join(REGISTRY)))
    sources = []
    for name, cls in REGISTRY.items():
        if only and name not in only:
            continue
        cfg = settings.sources.get(name) or {}
        if not cfg.get("enabled", False):
            report.skipped[name] = "disabled in config"
            continue
        source = cls(cfg, ctx)
        missing = source.missing_env()
        if missing:
            report.skipped[name] = "missing env " + ", ".join(missing)
            continue
        last = state.last_run(name)
        interval = source.min_interval_hours
        if not only and interval and last and (now - last).total_seconds() < interval * 3600:
            report.skipped[name] = "last ran %s UTC, min interval %gh" % (last.strftime("%d %b %H:%M"), interval)
            continue
        sources.append(source)
    return sources


def _fetch_all(sources: List[Source], state: State, report: RunReport, now: datetime) -> List[Job]:
    jobs: List[Job] = []
    if not sources:
        return jobs
    with ThreadPoolExecutor(max_workers=min(8, len(sources))) as pool:
        futures = [(source, pool.submit(source.fetch)) for source in sources]
        for source, future in futures:
            try:
                got = future.result()
            except Exception as exc:
                got = None
                source.fail("fetch", exc)
            report.errors.extend(source.errors)
            if got is None or (source.errors and not got):
                report.failed.append(source.name)
                continue
            report.fetched[source.name] = len(got)
            state.mark_source_run(source.name, now)
            jobs.extend(got)
            log.info("%-16s %5d postings%s", source.name, len(got),
                     " (%d partial errors)" % len(source.errors) if source.errors else "")
    return jobs


def _enrich(candidates: List[Candidate], sources: Dict[str, Source], limit: int) -> None:
    todo = [c.job for c in candidates
            if not c.job.description and c.job.source_name in sources and sources[c.job.source_name].supports_enrich]
    if len(todo) > limit:
        log.info("enriching %d of %d new jobs (max_enrich_per_run)", limit, len(todo))
        todo = todo[:limit]

    def work(job: Job) -> None:
        try:
            sources[job.source_name].enrich(job)
        except Exception as exc:
            log.debug("could not enrich %s: %s", job.url, redact(str(exc)))

    with ThreadPoolExecutor(max_workers=6) as pool:
        list(pool.map(work, todo))


def _build_packs(settings: Settings, matches: List[Job], high_score: int, dry_run: bool,
                 client: httpx.Client, now: datetime) -> None:
    cfg = settings.section("applications")
    if not cfg.get("enabled", True):
        return
    root = (settings.output_dir if dry_run else settings.state_dir) / "applications"
    repo = os.environ.get("GITHUB_REPOSITORY")
    server = os.environ.get("GITHUB_SERVER_URL", "https://github.com")
    branch = os.environ.get("STATE_BRANCH", "state")
    min_score = int(cfg.get("min_score", high_score))
    for job in [j for j in matches if j.score >= min_score][: int(cfg.get("max_per_run", 10))]:
        try:
            folder = build_pack(job, settings.profile, root, settings.section("llm"), client, now)
        except Exception as exc:
            log.warning("could not build application pack for %s @ %s: %s", job.title, job.company, exc)
            continue
        job.extra["pack_dir"] = str(folder)
        if repo and not dry_run:
            job.extra["pack_link"] = "%s/%s/tree/%s/applications/%s" % (server, repo, branch, folder.name)
        else:
            job.extra["pack_link"] = folder.resolve().as_uri()


def _write_outputs(out_dir: Path, report: RunReport, html: str, text: str) -> None:
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "digest.html").write_text(html, encoding="utf-8")
    (out_dir / "digest.txt").write_text(text, encoding="utf-8")
    summary = {
        "started_at": report.started_at.isoformat(timespec="seconds"),
        "fetched": report.fetched,
        "failed": report.failed,
        "skipped": report.skipped,
        "errors": report.errors,
        "candidates": report.candidates,
        "new": report.new,
        "notified": report.notified,
        "matches": [job.to_dict() for job in report.matches],
    }
    (out_dir / "last_run.json").write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding="utf-8")


def _notify(settings: Settings, report: RunReport, subject: str, html: str, text: str,
            high_score: int, client: httpx.Client) -> None:
    cfg = settings.section("notify")
    problems = []

    email_cfg = cfg.get("email") or {}
    if report.matches and email_cfg.get("enabled", True):
        missing = email_missing_env()
        if missing:
            log.warning("email digest skipped: missing env %s", ", ".join(missing))
        else:
            try:
                send_email(subject, html, text, email_cfg)
                report.notified.append("email")
            except Exception as exc:
                problems.append("email: " + redact(str(exc)))

    tg_cfg = cfg.get("telegram") or {}
    hot = [j for j in report.matches if j.score >= int(tg_cfg.get("min_score", high_score))]
    if hot and tg_cfg.get("enabled", True) and not telegram_missing_env():
        try:
            send_telegram(client, hot[:20])
            report.notified.append("telegram")
        except Exception as exc:
            problems.append("telegram: " + redact(str(exc)))

    for problem in problems:
        log.error("notification failed: %s", problem)
    if problems and not report.notified:
        raise NotificationError("; ".join(problems))


def run(settings: Settings, dry_run: bool = False, only: Optional[Sequence[str]] = None,
        ignore_seen: bool = False, notify: bool = True) -> RunReport:
    now = utcnow()
    report = RunReport(started_at=now)
    run_cfg = settings.run
    digest_cfg = settings.section("digest")
    state = State.load(settings.state_dir)
    profiles = settings.search_profiles
    min_score = int(digest_cfg.get("min_score", 40))
    high_score = int(digest_cfg.get("high_score", 70))

    user_agent = run_cfg.get("user_agent") or DEFAULT_USER_AGENT
    with make_client(user_agent, float(run_cfg.get("request_timeout_s", 20))) as client:
        ctx = SourceContext(client=client, now=now)
        sources = build_sources(settings, ctx, state, only, now, report)
        jobs = _fetch_all(sources, state, report, now)

        trusted = [s.name for s in sources if s.trust_location]
        candidates = filter_jobs(jobs, profiles, float(run_cfg.get("max_age_days", 21)), trusted, now)
        candidates = dedup_candidates(candidates, SOURCE_PRIORITY)
        report.candidates = len(candidates)

        new = candidates if ignore_seen else [c for c in candidates if not state.is_seen(c.job)]
        report.new = len(new)
        _enrich(new, {s.name: s for s in sources}, int(run_cfg.get("max_enrich_per_run", 80)))
        relevant = []
        for cand in new:
            state.mark_seen(cand.job, now)
            # Enrichment can reveal the real location (Workday "2 Locations"), so check it again.
            cand.profiles = [p for p in cand.profiles if p.location_ok(cand.job, cand.job.source_name in trusted)]
            if cand.profiles:
                apply_best_score(cand.job, cand.profiles, now)
                relevant.append(cand)

        report.matches = sorted((c.job for c in relevant if c.job.score >= min_score),
                                key=lambda j: (-j.score, j.company.lower(), j.title.lower()))
        _build_packs(settings, report.matches, high_score, dry_run, client, now)
        subject, html, text = render_digest(report, int(digest_cfg.get("max_jobs", 40)), high_score)
        _write_outputs(settings.output_dir, report, html, text)
        if notify and not dry_run:
            _notify(settings, report, subject, html, text, high_score, client)

    if not dry_run:
        state.prune(int(run_cfg.get("seen_retention_days", 120)), now)
        state.save()
    return report
