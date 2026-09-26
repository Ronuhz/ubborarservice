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
5. Build aggregate/supporting payloads (`catalog.json`, `announcements.json`, `rooms.json`).
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
- `cohortFormations` (optional list of non-empty strings; defaults to `[]`)

If `title` is omitted, a readable title is derived from `programId`.

`cohortFormations` identifies whole program/year audiences for this exact source. Values are whitespace-normalized,
deduplicated, and merged alongside groups when duplicate source definitions occur. They are never shared across
academic years, programs, study years, or URLs. Invalid values fail configuration loading.
The checked-in values were verified in the formation columns of the configured source pages.

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

### 4.3 Optional Source Discovery

`scripts/generate_sources.py` can crawl an index page and generate `config/sources.json`, with optional:

- `--program-map` for stable `programId` mapping
- `--include-master`
- `--skip-group-detection`

Discovery retains reviewed `cohortFormations` from an existing output configuration only for an exact match on
`(academicYear, programId, year, url)`. New sources receive an empty list and require explicit configuration
after verifying their cohort identifiers. Neither filenames nor global naming patterns define cohort scope.

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
- `time`: normalized to en-dash-separated ranges (`11–13`, `08:00–10:00`).
- `audience`: emitted for every entry, including multi-line cells, compact inline entries, and group-section rows.

Cell entries are deduplicated by:

- `(time, frequency, course, type, room, instructor, audience.formation)`

Distinct formations remain separate even when all other entry fields match.

Parsing receives `ParseContext` built from the current `SourceEntry`, including academic year, program ID,
study year, known groups, and configured cohort formations. Groups detected in section headings or column headers
supplement that context. The destination group of an output file does not imply an entry's audience.

Formation extraction preserves dedicated `Formatia`/`Formation`/`Audience` column values, standalone formation
lines, and `gr.`/`sgr.`/`subgr.` prefixes before metadata is stripped. Inline prefixes apply to their own entry;
unambiguous standalone metadata applies to entries in the same cell chunk. A bare subgroup number is retained
without inventing a parent group. Absent or ambiguous formation metadata becomes `null`.

Classification compares exact identifiers against source-specific metadata:

1. A configured cohort identifier → `cohort`.
2. An exact known group identifier → `group`.
3. A known group followed by `/` and a numeric subgroup identifier → `subgroup`.
4. All other values → `unknown`.

Token patterns may locate formation candidates in unstructured cells, but never determine audience scope.
Unrecognized values from explicit formation columns/prefixes remain in `formation` even when classification is unknown.

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

- `version`: `2` (timetable contract version)
- `academicYear`, `programId`, `year`, `group`
- `lastUpdatedAtSource` (ISO date from source `Last-Modified` header, nullable)
- `days[]` with normalized entries

Each entry requires an `audience` object with exactly these fields:

| Field | Contract |
| --- | --- |
| `formation` | Source formation string, or `null` when missing/ambiguous |
| `scope` | `cohort`, `group`, `subgroup`, or `unknown` |
| `expectedScope` | `cohort` for lectures, `group` for seminars, `subgroup` for labs |
| `isStandard` | `true` when scopes match or actual scope is `unknown`; otherwise `false` |

Example of a group-wide lab:

```json
{
  "time": "10–12",
  "frequency": "weekly",
  "course": "Data Structures",
  "type": "lab",
  "room": "L301",
  "instructor": "Example Name",
  "audience": {
    "formation": "512",
    "scope": "group",
    "expectedScope": "subgroup",
    "isStandard": false
  }
}
```

Clients can filter on `isStandard` when presenting cohort classes. Unknown metadata remains default-visible.
The service does not expose inferred retake status, upper-year status, or UI preference fields.

### 6.3 `announcements.json`

Schema: `schemas/announcements.schema.json`

- `items[]` with `id`, `title`, `message`, `severity`
- Optional `symbolName`, `startsAt`, `endsAt`

### 6.4 `rooms.json`

Schema: `schemas/rooms.schema.json`

- `rooms[]` entries with `code` and `address`

### 6.5 `.scrape-status.json` (Operational)

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
- Timetable version 2 adds required `audience` metadata. The timetable schema validates version 2 specifically;
  catalog, announcements, rooms, and scrape status retain version 1.
- Successful scrapes and newly created empty fallbacks write version 2. Existing files retained after a failed
  scrape are not rewritten or relabeled; a retained/cached version 1 file must be treated as default-visible by clients.
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
