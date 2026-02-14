# UBBOrar Timetable Data Pipeline – Technical Specification

## Goal
Create a low‑cost, reliable pipeline that converts the university’s public timetable HTML pages into JSON files that the app can fetch and cache. Hosting should be free or near‑free. Updates should be easy and automated. No Vercel.

## Summary of the Chosen Architecture
- **Scraper/Parser:** Python (BeautifulSoup) or Node (cheerio). (Python recommended for simplicity.)
- **Scheduler:** GitHub Actions cron (free).
- **Hosting:** GitHub Pages (free) serving static JSON.
- **App:** Fetch JSON from GitHub Pages, cache locally, show last updated time, and handle missing data gracefully.

## Data Sources
University timetable pages, one per program/year only for "Studii Licenta" (example):
- https://www.cs.ubbcluj.ro/files/orar/2025-1/tabelar/index.html

Each HTML page contains multiple groups and their session entries.

## Output JSON Structure
Two JSONs are required:

### 1) Catalog JSON (settings data)
Used to populate subject/program, year, group, and academic year in the app.

Filename: `catalog.json`

```json
{
  "version": 1,
  "generatedAt": "2026-02-13T12:00:00Z",
  "academicYears": ["2024-2025", "2025-2026"],
  "programs": [
    {
      "id": "informatica-maghiara",
      "title": "Informatics - Hungarian track",
      "years": [
        {
          "year": 1,
          "groups": [511, 512]
        },
        {
          "year": 2,
          "groups": [521, 522]
        }
      ]
    }
  ]
}
```

Notes:
- `title` is **display text** only (not localized, per requirement).
- `programs[].id` should match app `StudyProgram` IDs.
- If a program/year has no groups listed, the app should hide/disable the Group picker.

### 2) Timetable JSON (actual timetable data)
One JSON file per program/year/group/academic year, or a single combined JSON with filtering fields. Recommended: **per‑group file** for simpler app fetching.

Filename format:
```
{academicYear}/{programId}/y{year}/g{group}.json
```

Example path:
```
2025-2026/informatica-maghiara/y1/g511.json
```

Schema:
```json
{
  "version": 1,
  "generatedAt": "2026-02-13T12:00:00Z",
  "academicYear": "2025-2026",
  "programId": "informatica-maghiara",
  "year": 1,
  "group": 511,
  "lastUpdatedAtSource": "2026-02-10",
  "days": [
    {
      "day": "monday",
      "entries": [
        {
          "time": "11–13",
          "frequency": "weekly",
          "course": "Computer Architecture",
          "type": "lecture",
          "room": "CR0001",
          "instructor": "Asist. Sandor Csanad"
        }
      ]
    }
  ]
}
```

Notes:
- All strings are **non‑localized**.
- `frequency` values: `weekly`, `week1`, `week2`.
- `type` values: `lecture`, `seminar`, `lab`.
- `day` values: `monday`, `tuesday`, `wednesday`, `thursday`, `friday`.

### 3) Announcements JSON (optional)
Used for in‑app announcements with severity and optional symbol.

Filename: `announcements.json`

```json
{
  "version": 1,
  "generatedAt": "2026-02-13T12:00:00Z",
  "items": [
    {
      "id": "refresh-delayed-2026-02-13",
      "title": "Timetable refresh delayed",
      "message": "We have not received the latest timetable updates yet.",
      "severity": "warning",
      "symbolName": "exclamationmark.triangle.fill",
      "startsAt": "2026-02-13T00:00:00Z",
      "endsAt": "2026-02-15T00:00:00Z"
    }
  ]
}
```

Notes:
- `symbolName` is optional; app can fallback to severity default.
- If `startsAt`/`endsAt` are omitted, the app shows it always.

## Scraper Details
### Tools
- Python 3.11+
- `requests` for HTTP
- `beautifulsoup4` for parsing

### Steps
1. Read a **source list** of timetable URLs and metadata. Example config file:

```json
{
  "academicYear": "2025-2026",
  "programs": [
    {
      "programId": "informatica-maghiara",
      "year": 1,
      "url": "https://www.cs.ubbcluj.ro/files/orar/2025-1/tabelar/IM1.html",
      "groups": [511, 512]
    }
  ]
}
```

2. For each `url`, parse the HTML table.
3. Extract per‑group timetable rows.
4. Normalize to the JSON schema.
5. Write out per‑group JSON files.
6. Generate/refresh `catalog.json` and `announcements.json`.

### HTML Parsing Strategy (high level)
- Each timetable page is usually a table with days as sections.
- Identify **group columns** and **day rows** by header labels.
- Extract time, course, type, room, instructor, and frequency.
- If the page format changes, update the parser once and re‑run.

## Hosting (GitHub Pages)
- Repository `ubb-orar-data` (example)
- `gh-pages` branch contains `/catalog.json`, `/announcements.json`, and timetable folders.
- Enable GitHub Pages in settings, serve from `gh-pages` root.

Expected public URLs:
```
https://<user>.github.io/ubb-orar-data/catalog.json
https://<user>.github.io/ubb-orar-data/announcements.json
https://<user>.github.io/ubb-orar-data/2025-2026/informatica-maghiara/y1/g511.json
```

## API Endpoints (Static JSON)
All endpoints are static files on GitHub Pages. They should be cacheable (long TTL) and include a `generatedAt` timestamp in JSON.

### 1) Catalog
**GET** `/catalog.json`

Returns the settings catalog used to populate subject, year, and group pickers.

Example response:
```json
{
  "version": 1,
  "generatedAt": "2026-02-13T12:00:00Z",
  "academicYears": ["2024-2025", "2025-2026"],
  "programs": [
    {
      "id": "informatica-maghiara",
      "title": "Informatics - Hungarian track",
      "years": [
        { "year": 1, "groups": [511, 512] },
        { "year": 2, "groups": [521, 522] }
      ]
    }
  ]
}
```

### 2) Announcements
**GET** `/announcements.json`

Returns announcements to display in the app.

Example response:
```json
{
  "version": 1,
  "generatedAt": "2026-02-13T12:00:00Z",
  "items": [
    {
      "id": "refresh-delayed-2026-02-13",
      "title": "Timetable refresh delayed",
      "message": "We have not received the latest timetable updates yet.",
      "severity": "warning",
      "symbolName": "exclamationmark.triangle.fill",
      "startsAt": "2026-02-13T00:00:00Z",
      "endsAt": "2026-02-15T00:00:00Z"
    }
  ]
}
```

### 3) Timetable (per group)
**GET** `/{academicYear}/{programId}/y{year}/g{group}.json`

Returns the timetable for one program/year/group in a specific academic year.

Example response:
```json
{
  "version": 1,
  "generatedAt": "2026-02-13T12:00:00Z",
  "academicYear": "2025-2026",
  "programId": "informatica-maghiara",
  "year": 1,
  "group": 511,
  "lastUpdatedAtSource": "2026-02-10",
  "days": [
    {
      "day": "monday",
      "entries": [
        {
          "time": "11–13",
          "frequency": "weekly",
          "course": "Computer Architecture",
          "type": "lecture",
          "room": "CR0001",
          "instructor": "Asist. Sandor Csanad"
        }
      ]
    }
  ]
}
```

### Error/empty responses
Because these are static files, missing data should result in 404. The app should treat 404 as “no data available yet” and show a friendly message. If you need a soft‑failure, you can generate an empty file like:
```json
{
  "version": 1,
  "generatedAt": "2026-02-13T12:00:00Z",
  "academicYear": "2025-2026",
  "programId": "informatica-maghiara",
  "year": 1,
  "group": 511,
  "lastUpdatedAtSource": null,
  "days": []
}
```

## Automation (GitHub Actions)
### Schedule
- Daily at 06:00 UTC during semester
- Weekly outside semester

### Example workflow (pseudo)
```yaml
name: Update Timetables
on:
  schedule:
    - cron: "0 6 * * *"
  workflow_dispatch:

jobs:
  scrape:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
      - run: pip install -r requirements.txt
      - run: python scripts/scrape.py --config config/sources.json --out dist
      - run: python scripts/build_catalog.py --config config/sources.json --out dist
      - run: python scripts/build_announcements.py --out dist
      - run: |
          git checkout --orphan gh-pages
          cp -R dist/* .
          git add .
          git commit -m "Update timetables"
          git push --force origin gh-pages
```

## App Integration (later)
- Fetch `catalog.json` at launch with caching.
- Cache to disk and use cached data if offline.
- Fetch timetable JSON based on selected program/year/group/academic year.
- Show a “last updated” date from JSON.

## Error Handling / Monitoring
- If a URL fetch fails, keep the last successful JSON.
- Add a simple log and summary in GitHub Actions output.
- Optionally add a “refresh delayed” announcement when scraping fails.

## Security / Load Considerations
- Use caching headers in GitHub Pages if possible.

## What to Hand to the Next Agent
- Create the `ubb-orar-data` repo.
- Write the Python scraper.
- Implement the GitHub Actions workflow.
- Produce the JSON schemas above.
- Document the public URLs for the app.

## Non‑Goals
- No real‑time HTML parsing in app.
- No Firebase or paid hosting.
- No localization for the new JSON data (as requested).
