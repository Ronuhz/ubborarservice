# UBB FMI Timetable Service Technical Specification

## Document Metadata

- Project: UBB FMI Timetable Service
- Repository: `ubborarservice`
- Status: Active
- Purpose: Define the technical contract and operational behavior of the open-source timetable data service powering the UBB FMI app.

## 1. Scope

UBB FMI Timetable Service converts publicly available university timetable HTML pages into normalized, static JSON artifacts. These artifacts are published via GitHub Pages and consumed by mobile clients.

The service is intentionally static-first:

- No runtime API server.
- No dynamic database dependency.
- No app-side HTML parsing.

## 2. System Overview

### 2.1 Architectural Components

- Data source: Public UBB timetable HTML pages.
- Scraper/parser: Python scripts (`requests`, `beautifulsoup4`).
- Build pipeline: Python CLI scripts.
- Scheduler/orchestration: GitHub Actions.
- Distribution: GitHub Pages (`gh-pages` branch).
- Consumer: UBB FMI app and API testing collection (`apitesting.paw`).

### 2.2 Data Flow

1. Load source definitions from `config/sources.json`.
2. Fetch and parse timetable pages into canonical records.
3. Optionally enrich room codes with addresses from the legend page.
4. Emit per-group timetable JSON files.
5. Build aggregate/supporting payloads (`catalog.json`, `announcements.json`, `discounts.json`, `rooms.json`).
6. Publish `dist/` to GitHub Pages.

## 3. Design Objectives

- Reliability: Partial source failures must not invalidate successful outputs.
- Contract stability: Payloads follow explicit JSON schemas.
- Low operational cost: Free-tier hosting and automation.
- Simplicity: Deterministic files with predictable paths.
- Consumer resilience: Support offline caching and graceful empty states.

## 4. Inputs and Configuration

### 4.1 Timetable Sources (`config/sources.json`)

Supported root shapes:

- `academicYear` with `programs` list
- `sources` list (per-entry `academicYear` optional)
- `academicYears` list containing `programs` and/or `sources`

Each source entry supports:

- `academicYear` (optional if inherited)
- `programId` (or `id` as fallback key)
- `title` (or `programTitle`)
- `year` (integer >= 1)
- `url` (HTML source)
- `groups` (list of ints or comma-separated string)

If `title` is omitted, a readable title is derived from `programId`.

### 4.2 Announcements Configuration (`config/announcements.json`)

Optional manual item source consumed by `scripts/build_announcements.py`.

Expected shape:

```json
{
  "items": [
    {
      "id": "string",
      "title": "string",
      "message": "string",
      "severity": "info | warning | critical"
    }
  ]
}
```

### 4.3 Discounts Configuration (`config/discounts.json`)

Input for `scripts/build_discounts.py`.

Each discount item requires:

- `id`, `title`, `subtitle`, `badge`, `url`, `symbolName`
- `topColor`, `bottomColor`, `accentColor`
- Color channels `red|green|blue` in `[0, 1]`

### 4.4 Optional Source Discovery

`scripts/generate_sources.py` can crawl an index page and generate `config/sources.json`, with optional:

- `--program-map` for stable `programId` mapping
- `--include-master`
- `--skip-group-detection`

## 5. Pipeline Components

### 5.1 Scraper (`scripts/scrape.py`)

Responsibilities:

- Fetch all configured timetable sources.
- Parse timetable structures into normalized entries.
- Write one file per `(academicYear, programId, year, group)`.
- Write operational status to `dist/.scrape-status.json`.

Key options:

- `--soft-fail-empty`: create empty timetable files when a failed source has no prior output.
- `--fail-on-errors`: exit with non-zero status when any source fails.
- `--room-legend-url`: override legend source.
- `--skip-room-legend`: disable room enrichment.

### 5.2 Timetable Parsing (`scripts/timetable_parser.py`)

Supported layouts:

- Group-section tables (for example, `Grupa 511` sections).
- Columnar tables with group columns.

Normalization rules:

- `day`: canonicalized to `monday` ... `friday` (Romanian/English/Hungarian aliases supported).
- `frequency`: `weekly`, `week1`, `week2`.
- `type`: `lecture`, `seminar`, `lab`.
- `time`: normalized to dash-separated ranges (`11-13`, `08:00-10:00`).

De-duplication occurs per day entry key:

- `(time, frequency, course, type, room, instructor)`

### 5.3 Room Legend Enrichment (`scripts/room_legend.py`)

By default, the scraper fetches room legend HTML and writes `rooms.json`.

When room mapping exists:

- timetable entries keep `room`
- optional `roomAddress` is injected

Legend fetch failure is non-fatal and recorded as a warning.

### 5.4 Catalog Builder (`scripts/build_catalog.py`)

Outputs `catalog.json` from source config.

If `--status` is provided and contains detected groups, those group values override configured groups for catalog accuracy.

### 5.5 Announcements Builder (`scripts/build_announcements.py`)

Outputs `announcements.json`.

Combines:

- Manual announcements (`config/announcements.json`)
- Optional auto-generated warning item when scrape failures are present

Automatic warning TTL:

- Starts at run date 00:00:00Z
- Ends at +2 days

### 5.6 Discounts Builder (`scripts/build_discounts.py`)

Outputs `discounts.json` after strict field and color validation.

Duplicate `id` values are deduplicated first-win.

## 6. Output Contracts

All public payload schemas live in `schemas/`.

### 6.1 `catalog.json`

Schema: `schemas/catalog.schema.json`

Required top-level keys:

- `version` (int)
- `generatedAt` (ISO-8601 datetime)
- `academicYears` (`YYYY-YYYY`)
- `programs[]`

### 6.2 Timetable per Group

Path pattern:

```text
/{academicYear}/{programId}/y{year}/g{group}.json
```

Schema: `schemas/timetable.schema.json`

Key fields:

- `academicYear`, `programId`, `year`, `group`
- `lastUpdatedAtSource` (ISO date from source `Last-Modified` header, nullable)
- `days[]` with normalized entries

### 6.3 `announcements.json`

Schema: `schemas/announcements.schema.json`

- `items[]` with `id`, `title`, `message`, `severity`
- Optional `symbolName`, `startsAt`, `endsAt`

### 6.4 `discounts.json`

Schema: `schemas/discounts.schema.json`

- Presentation metadata for in-app offers
- Strict color validation (`0..1` channel values)

### 6.5 `rooms.json`

Schema: `schemas/rooms.schema.json`

- `rooms[]` entries with `code` and `address`

### 6.6 `.scrape-status.json` (Operational)

Internal operational payload used by downstream build steps.

Primary fields include:

- `sourcesTotal`, `sourcesSucceeded`, `sourcesFailed`
- `timetableFilesWritten`, `timetableFilesEmpty`
- `roomsInLegend`
- `failures[]`, `warnings[]`, `sources[]`

## 7. Static Endpoint Model

Published endpoints are static files on GitHub Pages:

- `GET /catalog.json`
- `GET /announcements.json`
- `GET /discounts.json`
- `GET /rooms.json`
- `GET /{academicYear}/{programId}/y{year}/g{group}.json`

Behavior expectations for consumers:

- `200`: parse and cache.
- `404` on group timetable: treat as no data yet, not a fatal API error.

## 8. Scheduling and Deployment

Workflow file:

- `.github/workflows/update-timetables.yml`

Execution model:

- Trigger: `schedule` + `workflow_dispatch`
- Cron: `0 6 * * *` (06:00 UTC daily)
- Cadence override: July/August runs only on Monday
- Publish action: `peaceiris/actions-gh-pages@v4`
- Publish target: `gh-pages` (orphan history)

## 9. Failure and Continuity Semantics

- Source failures are isolated; successful sources continue.
- Existing files are not deleted by a failed source run.
- `--soft-fail-empty` creates explicit empty payloads where needed.
- Announcements can expose delayed-refresh state to clients.
- Pipeline can be configured to fail CI with `--fail-on-errors`.

## 10. Compatibility and Versioning

- Payloads include `version` for contract evolution.
- Schema changes should preserve backward compatibility unless coordinated with app release.
- Enum values (`day`, `frequency`, `type`) are stable API surface and must not be changed casually.

## 11. Security and Operational Constraints

- Sources are public HTML pages; no authentication secrets required for scraping.
- Publication uses GitHub Actions `GITHUB_TOKEN` with `contents: write`.
- No user-generated content ingestion.
- No PII processing is expected in timetable artifacts.

## 12. Non-Goals

- Real-time backend API with dynamic query execution
- In-app scraping/parsing of source HTML
- Paid hosting dependencies or vendor lock-in
- Localization layer inside service payload generation
