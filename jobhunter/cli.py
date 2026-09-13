"""Command line entry point: python -m jobhunter {run,doctor,pack,probe}."""
from __future__ import annotations

import argparse
import logging
import os
import sys
from pathlib import Path

from . import pipeline
from .apply.pack import build_pack
from .config import Settings
from .dates import utcnow
from .http import make_client
from .models import Job
from .notify.mailer import email_missing_env
from .notify.telegram import telegram_missing_env
from .sources import REGISTRY
from .sources.base import SourceContext
from .state import State
from .text import html_to_text

# How to try an unknown company slug on each board-style ATS.
_PROBE_CONFIG = {
    "greenhouse": lambda slug: {"boards": [{"token": slug}]},
    "lever": lambda slug: {"boards": [{"site": slug}]},
    "ashby": lambda slug: {"boards": [{"name": slug}]},
    "smartrecruiters": lambda slug: {"companies": [{"id": slug}]},
}


def _print_report(report: "pipeline.RunReport") -> None:
    print()
    for name, count in report.fetched.items():
        print("  ok       %-16s %d postings" % (name, count))
    for name in report.failed:
        print("  FAILED   %s" % name)
    for name, why in report.skipped.items():
        print("  skipped  %-16s %s" % (name, why))
    print("\n  %d scanned -> %d passed filters -> %d new -> %d matches"
          % (report.scanned, report.candidates, report.new, len(report.matches)))
    for job in report.matches[:20]:
        print("  [%3d] %s | %s | %s" % (job.score, job.title, job.company, job.location))
    if len(report.matches) > 20:
        print("  ... %d more" % (len(report.matches) - 20))
    if report.errors:
        print("\n  errors:")
        for error in report.errors[:20]:
            print("   - " + error)
    if report.notified:
        print("\n  notified via " + ", ".join(report.notified))


def cmd_run(settings: Settings, args) -> int:
    only = [s.strip() for s in args.only.split(",") if s.strip()] if args.only else None
    try:
        report = pipeline.run(settings, dry_run=args.dry_run, only=only,
                              ignore_seen=args.ignore_seen, notify=not args.no_notify)
    except pipeline.NotificationError as exc:
        logging.error("all notifications failed; state not saved so the next run retries: %s", exc)
        return 1
    _print_report(report)
    print("\n  digest: %s" % (settings.output_dir / "digest.html"))
    if report.all_sources_failed:
        logging.error("every source failed")
        return 1
    return 0


def cmd_doctor(settings: Settings, args) -> int:
    state = State.load(settings.state_dir)
    print("state dir:  %s (%d seen keys)" % (settings.state_dir, len(state.seen)))
    print("output dir: %s\n" % settings.output_dir)
    for profile in settings.search_profiles:
        print("search profile %-28s %d title phrases, %d locations, %d keywords"
              % (profile.name, len(profile.title_include), len(profile.locations), len(profile.score_keywords)))
    print("\nsources:")
    for name, cls in REGISTRY.items():
        cfg = settings.sources.get(name) or {}
        source = cls(cfg, None)
        missing = source.missing_env()
        if not cfg.get("enabled"):
            status = "disabled"
        elif missing:
            status = "needs " + ", ".join(missing)
        else:
            status = "ready"
        print("  %-16s %-44s %s" % (name, status, source.describe()))
    print("\nnotifications:")
    print("  email     %s" % ("ready" if not email_missing_env() else "needs " + ", ".join(email_missing_env())))
    print("  telegram  %s" % ("ready" if not telegram_missing_env() else "needs " + ", ".join(telegram_missing_env())))
    print("  LLM packs %s" % ("ready" if os.environ.get("ANTHROPIC_API_KEY") else "static templates (no ANTHROPIC_API_KEY)"))
    candidate = settings.profile.get("candidate") or {}
    todos = [k for k, v in (settings.profile.get("standard_answers") or {}).items() if "TODO" in str(v)]
    print("\nprofile: %s" % (candidate.get("name") or "(no profile.yaml)"))
    if todos:
        print("  standard_answers still TODO: " + ", ".join(todos))
    return 0


def cmd_pack(settings: Settings, args) -> int:
    description = Path(args.description_file).read_text(encoding="utf-8") if args.description_file else ""
    if description.lstrip().startswith("<"):
        description = html_to_text(description)
    job = Job(title=args.title, company=args.company, url=args.url, source="manual:cli",
              location=args.location or "", description=description)
    with make_client() as client:
        folder = build_pack(job, settings.profile, settings.output_dir / "applications",
                            settings.section("llm"), client, utcnow())
    print("application pack written to %s" % folder)
    return 0


def cmd_probe(settings: Settings, args) -> int:
    """Check whether company slugs have a public board on Greenhouse / Lever / Ashby / SmartRecruiters."""
    logging.getLogger("jobhunter.sources").setLevel(logging.ERROR)
    profiles = settings.search_profiles
    with make_client() as client:
        ctx = SourceContext(client=client, now=utcnow())
        for slug in args.slugs:
            hits = 0
            for name, make_cfg in _PROBE_CONFIG.items():
                source = REGISTRY[name](make_cfg(slug), ctx)
                jobs = source.fetch()
                if source.errors or not jobs:
                    continue
                hits += 1
                local = [j for j in jobs if any(p.location_ok(j) for p in profiles)]
                matching = [j for j in local if any(p.title_ok(j.title) for p in profiles)]
                print("%-20s %-16s %4d jobs, %3d in your locations, %3d matching titles"
                      % (slug, name, len(jobs), len(local), len(matching)))
            if not hits:
                print("%-20s no public board found (try Workday or another slug spelling)" % slug)
    return 0


def main(argv=None) -> int:
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(errors="replace")  # job titles are not always cp1252-safe on Windows
        except AttributeError:
            pass

    parser = argparse.ArgumentParser(prog="jobhunter", description="Config-driven job hunter.")
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--profile", default="profile.yaml")
    parser.add_argument("-v", "--verbose", action="store_true")
    sub = parser.add_subparsers(dest="command")

    run = sub.add_parser("run", help="fetch, filter, score, notify and save state")
    run.add_argument("--dry-run", action="store_true", help="no notifications, no state saved; writes output/ only")
    run.add_argument("--only", help="comma-separated source names, e.g. greenhouse,workday")
    run.add_argument("--ignore-seen", action="store_true", help="treat every job as new")
    run.add_argument("--no-notify", action="store_true", help="save state but send nothing")

    sub.add_parser("doctor", help="show which sources, secrets and notifications are ready")

    pack = sub.add_parser("pack", help="build an application pack for a job you found yourself")
    pack.add_argument("--url", required=True)
    pack.add_argument("--title", required=True)
    pack.add_argument("--company", required=True)
    pack.add_argument("--location")
    pack.add_argument("--description-file", help="text or HTML file with the job description")

    probe = sub.add_parser("probe", help="find which public ATS board a company uses")
    probe.add_argument("slugs", nargs="+")

    args = parser.parse_args(argv)
    if not args.command:
        parser.print_help()
        return 2
    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(asctime)s %(levelname)-7s %(name)s: %(message)s")
    for noisy in ("httpx", "httpcore"):  # their INFO logs print full URLs, including API keys
        logging.getLogger(noisy).setLevel(logging.WARNING)

    settings = Settings.load(args.config, args.profile)
    commands = {"run": cmd_run, "doctor": cmd_doctor, "pack": cmd_pack, "probe": cmd_probe}
    return commands[args.command](settings, args)
