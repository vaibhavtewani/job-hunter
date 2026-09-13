# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
python -m venv .venv && .venv/Scripts/python -m pip install -r requirements-dev.txt   # Windows paths
.venv/Scripts/python -m pytest                                   # all tests (offline, <1s)
.venv/Scripts/python -m pytest tests/test_sources.py::test_lever # single test
.venv/Scripts/python -m jobhunter doctor                         # config / secrets readiness
.venv/Scripts/python -m jobhunter run --dry-run                  # live fetch; no notifications, no state saved
.venv/Scripts/python -m jobhunter run --dry-run --only workday --ignore-seen
.venv/Scripts/python -m jobhunter probe <company-slug>...        # find a company's public ATS board
```

The local machine only has **Python 3.7**; CI and the scheduled workflow use 3.12. Keep code 3.7-compatible: `from __future__ import annotations` in every module, `typing.List/Dict` (not `list[str]`) outside annotations, no walrus operator, no `zoneinfo`, no `str.removeprefix`.

No linter is configured.

## Architecture

A config-driven job hunter for configurable role profiles (first user: an entry-level strategy/consulting candidate targeting the GCC). One run of `jobhunter/pipeline.py:run`:

**fetch (sources in parallel) → filter → cross-source dedup → drop already-seen → enrich descriptions → re-check location → score → application packs → render digest → notify → save state.**

- `config.yaml` = *what* to search (search profiles, sources, thresholds). `profile.yaml` = *who* is applying (CV content, standard screening answers). A new profession should need only config; a new board only a new adapter.
- **Sources** (`jobhunter/sources/`) subclass `Source`: `fetch()` returns every current posting as `Job`; optional `enrich(job)` fills the description and is called only for new jobs that passed filters (bounded by `max_enrich_per_run`). Order of `SOURCE_CLASSES` in `sources/__init__.py` is the dedup priority (direct employer ATS beats SerpApi beats email). A source is `failed` only if it raises or has errors and zero jobs; board-level errors are recorded via `self.fail()` and shown in the digest.
- Source choice is deliberate, to avoid anti-bot blocking and maintenance: public ATS JSON (Greenhouse, Lever, Ashby, SmartRecruiters, Workday `/wday/cxs/`), SerpApi Google Jobs, and board alert emails read over IMAP. **Do not add scraping of LinkedIn/Bayt/GulfTalent pages or any logged-in session automation.**
- **Filtering rules:** `title_exclude` applies to the title only. Unknown posting dates are kept. Sources with `trust_location` (gmail alerts) skip the location check. Workday "N Locations" listings pass on the search term, then get re-checked after enrichment reveals real locations.
- **Dedup/state:** `Job.keys` = canonical-URL hash + company/title hash. Every new job that passes filters is marked seen, even if it scores below `min_score`. State (`seen.json`) lives in `STATE_DIR`; in GitHub Actions that is a worktree of the orphan `state` branch, committed after each run (packs go there too). If all notification channels fail, `NotificationError` is raised before state is saved so the next run retries.
- **Scoring** (`scoring.py`) is deterministic and returns human-readable reasons shown in the digest; constants at the top of the file.
- **Application packs** (`apply/pack.py`) re-order profile bullets by keyword overlap and never reword them; with `ANTHROPIC_API_KEY`, `apply/llm.py` drafts summary/cover letter/gaps via the Messages API over httpx (profile sent without contact details or `standard_answers`). Humans submit applications; no auto-submit or CAPTCHA handling.
- Templates (digest HTML/text, pack markdown) are Jinja2 files in `jobhunter/templates/`.
- Secrets come only from env vars (see README table). `httpx`/`httpcore` loggers are forced to WARNING and errors pass through `http.redact()` because request URLs can carry API keys.
