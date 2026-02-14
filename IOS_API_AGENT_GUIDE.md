# iOS Agent Guide: Using the Timetable API

This guide is for agents that build or modify the iOS app integration for the timetable backend.

## Base URL

Use the GitHub Pages base:

`https://<user>.github.io/<repo>`

Example (replace with your real values):

`https://hunor.github.io/ubb-orar-data`

## Endpoints

### 1) Catalog

- `GET /catalog.json`
- Purpose: populate academic year, program, year, group selectors.

Response keys:

- `academicYears: [String]`
- `programs[].id: String`
- `programs[].title: String`
- `programs[].years[].year: Int`
- `programs[].years[].groups: [Int]`

### 2) Announcements

- `GET /announcements.json`
- Purpose: show in-app notices.

Response keys:

- `items[].id`
- `items[].title`
- `items[].message`
- `items[].severity` (`info | warning | critical`)
- optional `items[].symbolName`
- optional `items[].startsAt`, `items[].endsAt`

### 3) Rooms

- `GET /rooms.json`
- Purpose: room code to address legend (fallback/lookup in app if needed).

Response keys:

- `rooms[].code`
- `rooms[].address`

### 4) Timetable (per group)

- `GET /{academicYear}/{programId}/y{year}/g{group}.json`

Example:

- `/2025-2026/informatica-maghiara/y1/g511.json`

Response keys:

- `academicYear`
- `programId`
- `year`
- `group`
- `lastUpdatedAtSource`
- `days[].day` (`monday` ... `friday`)
- `days[].entries[]`:
  - `time`
  - `frequency` (`weekly | week1 | week2`)
  - `course`
  - `type` (`lecture | seminar | lab`)
  - `room`
  - optional `roomAddress`
  - `instructor`

## Recommended Client Flow

1. On app launch, fetch `catalog.json` and cache it.
2. Fetch `announcements.json` and filter by `startsAt/endsAt` if present.
3. Build timetable URL from selected values:
   - `/{academicYear}/{programId}/y{year}/g{group}.json`
4. If timetable response is `404`, treat as “no data available yet”, not a hard error.
5. Display freshness from:
   - `generatedAt` (pipeline generation time)
   - `lastUpdatedAtSource` (source update date when available)
6. Use cached data offline.

## HTTP/Error Handling Rules

- `200`: decode JSON and cache.
- `404` on timetable: show empty-state message.
- network errors: show cached data if available.
- decoding errors: log and fallback to cache.

## Swift Model Notes

- `group` and `year` are integers.
- `generatedAt`, `startsAt`, `endsAt` are ISO-8601 date-time strings.
- `lastUpdatedAtSource` is ISO date (`yyyy-MM-dd`) or `null`.
- `roomAddress` is optional.

## Minimal URL Builder

```swift
func timetablePath(academicYear: String, programId: String, year: Int, group: Int) -> String {
    "/\(academicYear)/\(programId)/y\(year)/g\(group).json"
}
```

## Integration Checklist for Agents

- Ensure `programId` values match app enum/raw IDs exactly.
- Do not localize backend string enums (`day`, `type`, `frequency`) before decoding.
- Handle missing optional fields safely (`symbolName`, `roomAddress`, `startsAt`, `endsAt`).
- Treat timetable `404` as valid empty-state behavior.
