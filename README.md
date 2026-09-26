# UBB FMI Timetable Service

UBB FMI Timetable Service is the open-source data pipeline that powers the UBB FMI app.

It retrieves public timetable pages from the Faculty of Mathematics and Computer Science (UBB), normalizes them into stable JSON contracts, and publishes static artifacts that the mobile client can fetch and cache.

**[API Documentation](./API.md)**

## Why This Service Exists

- Provide a reliable, low-cost backend for timetable delivery.
- Keep runtime complexity out of the mobile app.
- Publish versioned, schema-backed JSON with predictable paths.
- Run unattended through scheduled automation.

## What Gets Published

The pipeline generates static JSON files under `dist/`:

- `catalog.json`: available academic years, programs, years, and groups.
- `rooms.json`: room code to address mapping from the published legend page.
- `/{academicYear}/{programId}/y{year}/g{group}.json`: per-group timetable payloads.
- `.scrape-status.json`: pipeline status, warnings, and failures for operational use.

## Runtime Architecture

1. `scripts/scrape.py` downloads and parses timetable sources, then writes per-group files.
2. `scripts/build_catalog.py` builds the catalog from `config/sources.json` and optional scrape status overrides.
3. GitHub Actions publishes `dist/` to the `gh-pages` branch.

## Repository Layout

- `scripts/`: scraping, parsing, generation, and build utilities.
- `config/`: source definitions and content configuration.
- `schemas/`: JSON schemas for all public payloads.
- `tests/`: parser and builder unit tests.
- `.github/workflows/update-timetables.yml`: scheduled pipeline + publication workflow.
- `apitesting.paw`: API testing collection.

## Quick Start (Local)

### 1) Install dependencies

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
```

### 2) Run the full pipeline

```bash
python scripts/scrape.py --config config/sources.json --out dist --soft-fail-empty
python scripts/build_catalog.py --config config/sources.json --out dist --status dist/.scrape-status.json
```

### 3) Validate with tests

```bash
pip install -r requirements-dev.txt
python -m unittest discover -s tests -v
```

## Source Configuration

Primary input: `config/sources.json`.

Supported shapes:

- Root `academicYear` + `programs`.
- Root `sources` where each source can define its own `academicYear`.
- `academicYears` buckets containing nested `programs` or `sources`.

Each source entry supports:

- `academicYear` (optional when inherited from parent)
- `programId`
- `title`
- `year`
- `url`
- `groups` (array of ints or comma-separated string)
- `cohortFormations` (optional array of whole program/year formation identifiers; defaults to `[]`)

Formation identifiers belong to the specific academic year, program, and study year of each source.
For example, a source can configure `"groups": [511, 512]` and `"cohortFormations": ["IM1"]`.
The checked-in cohort identifiers were verified against the configured timetable pages.
Review them when adding sources or changing academic years; the parser never derives cohorts from a URL or token shape.

## Optional Source Discovery

You can generate `config/sources.json` from the official timetable index:

```bash
python scripts/generate_sources.py \
  --index-url https://www.cs.ubbcluj.ro/files/orar/2026-1/tabelar/index.html \
  --academic-year 2026-2027 \
  --program-map config/program-map.example.json \
  --out config/sources.json
```

Discovery preserves `cohortFormations` from the existing output only when academic year, program ID,
study year, and source URL all match. New sources receive `[]`; add verified cohort identifiers before publishing.

## Publication and Hosting

The default workflow runs in GitHub Actions and publishes static files via GitHub Pages.

Workflow: `.github/workflows/update-timetables.yml`

Behavior:

- Runs daily at `06:00 UTC`.
- During July and August, only Monday runs are executed.
- Publishes `dist/` to `gh-pages` using `peaceiris/actions-gh-pages`.

Expected public URLs:

- `https://<user>.github.io/<repo>/catalog.json`
- `https://<user>.github.io/<repo>/rooms.json`
- `https://<user>.github.io/<repo>/<academicYear>/<programId>/y<year>/g<group>.json`

## Data Contracts

Public schemas are versioned in `schemas/`:

- `schemas/catalog.schema.json`
- `schemas/timetable.schema.json`
- `schemas/rooms.schema.json`

Timetable payloads use **version 2**. Every entry includes:

```json
"audience": {
  "formation": "512",
  "scope": "group",
  "expectedScope": "subgroup",
  "isStandard": false
}
```

`formation` preserves the source identifier (or `null` when absent or ambiguous).
`scope` is `cohort`, `group`, `subgroup`, or `unknown`, classified using only that source's configured
cohorts and configured/detected groups. Expected scopes are `lecture → cohort`, `seminar → group`,
and `lab → subgroup`. Known mismatches set `isStandard` to `false`; unknown formations always use
`true` so clients keep them visible. The service exposes structural metadata; client UI wording is independent.

Cached or retained version 1 timetables have no guaranteed audience metadata;
clients should default such entries to visible until a successful version 2 refresh.

## Failure Behavior

- Source-level failures do not stop other sources from processing.
- Existing timetable files remain valid if a source fails.
- With `--soft-fail-empty`, missing new files are created as empty payloads.
- `dist/.scrape-status.json` records failures and warnings for downstream steps.

## License and Contributions

This repository is intended to serve as the public backend for the UBB FMI app.

For external contributions, prefer focused changes with tests and schema compatibility preserved.
