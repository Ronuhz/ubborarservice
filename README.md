# UBBOrar Timetable Pipeline

This repository implements the timetable pipeline from `TIMETABLE_PIPELINE_SPEC.md`.

It scrapes public university timetable HTML pages and publishes static JSON files that can be hosted on GitHub Pages.

## Outputs

The pipeline generates:

- `catalog.json`
- `announcements.json`
- `discounts.json`
- `rooms.json` (room code -> address legend)
- Per-group timetable files:
  - `{academicYear}/{programId}/y{year}/g{group}.json`

## Configuration

Edit `config/sources.json` to define sources.

Supported formats:

- Root `academicYear` + `programs` list
- Root `sources` list (each source has its own `academicYear`)
- `academicYears` list with nested `programs` or `sources`

Each source/program entry supports:

- `academicYear` (optional if inherited from parent)
- `programId`
- `title` (display text used in catalog)
- `year`
- `url`
- `groups` (array or comma-separated string)

## Local Run

Install dependencies:

```bash
pip install -r requirements.txt
```

Generate data:

```bash
python scripts/scrape.py --config config/sources.json --out dist --soft-fail-empty
python scripts/build_catalog.py --config config/sources.json --out dist --status dist/.scrape-status.json
python scripts/build_announcements.py --out dist --announcements config/announcements.json --status dist/.scrape-status.json
python scripts/build_discounts.py --out dist --discounts config/discounts.json
```

By default `scrape.py` also fetches:

- `https://www.cs.ubbcluj.ro/files/orar/2025-1/sali/legenda.html`

and enriches timetable entries with optional `roomAddress` (when room code matches), while also writing `dist/rooms.json`.

If the semester path changes, override it:

```bash
python scripts/scrape.py --config config/sources.json --out dist --room-legend-url https://www.cs.ubbcluj.ro/files/orar/<semester>/sali/legenda.html
```

Auto-generate `config/sources.json` from the official index (Licenta rows):

```bash
python scripts/generate_sources.py \
  --index-url https://www.cs.ubbcluj.ro/files/orar/2025-1/tabelar/index.html \
  --academic-year 2025-2026 \
  --program-map config/program-map.example.json \
  --out config/sources.json
```

## GitHub Actions + Pages

Workflow file: `.github/workflows/update-timetables.yml`

What it does:

1. Runs daily at `06:00 UTC`.
2. Uses a weekly cadence (Monday only) during July/August.
3. Runs scraper/build scripts.
4. Publishes `dist/` to `gh-pages`.

Expected public URLs:

- `https://<user>.github.io/<repo>/catalog.json`
- `https://<user>.github.io/<repo>/announcements.json`
- `https://<user>.github.io/<repo>/discounts.json`
- `https://<user>.github.io/<repo>/rooms.json`
- `https://<user>.github.io/<repo>/<academicYear>/<programId>/y<year>/g<group>.json`

## Schemas

JSON schemas are available in:

- `schemas/catalog.schema.json`
- `schemas/timetable.schema.json`
- `schemas/announcements.schema.json`
- `schemas/discounts.schema.json`
- `schemas/rooms.schema.json`

## Failure Behavior

- If a source fetch/parse fails, existing timetable files are kept.
- If no previous file exists and `--soft-fail-empty` is used, an empty timetable file is written.
- `scripts/scrape.py` writes `dist/.scrape-status.json`.
- `scripts/build_announcements.py` can generate an automatic warning announcement when failures are detected.
