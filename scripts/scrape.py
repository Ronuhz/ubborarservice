#!/usr/bin/env python3
from __future__ import annotations

import argparse
from datetime import timezone
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any

import requests

from pipeline_utils import VERSION, SourceEntry, load_source_entries, utc_now_iso, write_json
from room_legend import build_room_lookup, fetch_room_legend, resolve_room_address, write_room_legend_json
from timetable_parser import ParsedTimetable, TimetableParseError, parse_timetable_html


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Scrape timetable HTML pages into per-group JSON files.")
    parser.add_argument("--config", required=True, help="Path to sources config JSON.")
    parser.add_argument("--out", required=True, help="Output directory for generated files.")
    parser.add_argument("--timeout", type=float, default=30.0, help="HTTP timeout in seconds (default: 30).")
    parser.add_argument(
        "--soft-fail-empty",
        action="store_true",
        help="Write an empty timetable file when no previous data exists and scraping fails.",
    )
    parser.add_argument(
        "--fail-on-errors",
        action="store_true",
        help="Exit with status code 1 if any source fails.",
    )
    parser.add_argument(
        "--room-legend-url",
        default="https://www.cs.ubbcluj.ro/files/orar/2025-2/sali/legenda.html",
        help="Legend page used to map room codes to addresses.",
    )
    parser.add_argument(
        "--skip-room-legend",
        action="store_true",
        help="Disable room code to address enrichment.",
    )
    return parser.parse_args()


def _timetable_path(out_dir: Path, entry: SourceEntry, group: int) -> Path:
    return out_dir / entry.academic_year / entry.program_id / f"y{entry.year}" / f"g{group}.json"


def _last_updated_from_headers(response: requests.Response) -> str | None:
    raw_last_modified = response.headers.get("Last-Modified")
    if not raw_last_modified:
        return None
    try:
        parsed = parsedate_to_datetime(raw_last_modified)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return parsed.astimezone(timezone.utc).date().isoformat()
    except (TypeError, ValueError, OverflowError):
        return None


def _make_timetable_payload(
    generated_at: str,
    entry: SourceEntry,
    group: int,
    days: list[dict[str, Any]],
    last_updated_at_source: str | None,
) -> dict[str, Any]:
    return {
        "version": VERSION,
        "generatedAt": generated_at,
        "academicYear": entry.academic_year,
        "programId": entry.program_id,
        "year": entry.year,
        "group": group,
        "lastUpdatedAtSource": last_updated_at_source,
        "days": days,
    }


def _write_group_files(
    out_dir: Path,
    entry: SourceEntry,
    parsed: ParsedTimetable,
    generated_at: str,
    last_updated_at_source: str | None,
    room_lookup: dict[str, str] | None = None,
) -> dict[str, int]:
    groups_to_write = sorted(set(entry.groups) or set(parsed.detected_groups))
    written = 0
    empty = 0
    for group in groups_to_write:
        days = _enrich_days_with_room_address(parsed.by_group.get(group, []), room_lookup or {})
        payload = _make_timetable_payload(generated_at, entry, group, days, last_updated_at_source)
        write_json(_timetable_path(out_dir, entry, group), payload)
        written += 1
        if not days:
            empty += 1
    return {"written": written, "empty": empty, "groupsWritten": groups_to_write}


def _write_empty_fallback(out_dir: Path, entry: SourceEntry, group: int, generated_at: str) -> None:
    payload = _make_timetable_payload(
        generated_at=generated_at,
        entry=entry,
        group=group,
        days=[],
        last_updated_at_source=None,
    )
    write_json(_timetable_path(out_dir, entry, group), payload)


def _run_scrape(entry: SourceEntry, timeout: float, session: requests.Session) -> tuple[ParsedTimetable, str | None]:
    response = session.get(entry.url, timeout=timeout)
    response.raise_for_status()
    parsed = parse_timetable_html(response.text, entry.groups)
    last_updated = _last_updated_from_headers(response)
    return parsed, last_updated


def _enrich_days_with_room_address(
    days: list[dict[str, Any]],
    room_lookup: dict[str, str],
) -> list[dict[str, Any]]:
    if not room_lookup:
        return days

    enriched_days: list[dict[str, Any]] = []
    for day in days:
        new_day: dict[str, Any] = {"day": day.get("day"), "entries": []}
        entries = day.get("entries", [])
        if not isinstance(entries, list):
            enriched_days.append(new_day)
            continue
        for entry in entries:
            if not isinstance(entry, dict):
                continue
            entry_copy = dict(entry)
            room = str(entry_copy.get("room") or "").strip()
            if room:
                room_address = resolve_room_address(room, room_lookup)
                if room_address:
                    entry_copy["roomAddress"] = room_address
            new_day["entries"].append(entry_copy)
        enriched_days.append(new_day)
    return enriched_days


def main() -> int:
    args = _parse_args()
    config_path = Path(args.config)
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    generated_at = utc_now_iso()
    entries = load_source_entries(config_path)

    source_failures: list[dict[str, str]] = []
    source_warnings: list[dict[str, Any]] = []
    source_summaries: list[dict[str, Any]] = []
    success_count = 0
    written_count = 0
    empty_count = 0
    room_lookup: dict[str, str] = {}
    room_legend_count = 0

    with requests.Session() as session:
        session.headers.update({"User-Agent": "ubborarservice-timetable-pipeline/1.0"})
        if not args.skip_room_legend:
            try:
                legend = fetch_room_legend(session, args.room_legend_url, args.timeout)
                room_lookup = build_room_lookup(legend)
                room_legend_count = len(legend)
                if legend:
                    write_room_legend_json(out_dir / "rooms.json", legend)
            except requests.RequestException as exc:
                source_warnings.append(
                    {
                        "warning": f"Room legend fetch failed ({args.room_legend_url}): {exc}",
                    }
                )

        for entry in entries:
            try:
                parsed, last_updated = _run_scrape(entry, args.timeout, session)
                stats = _write_group_files(out_dir, entry, parsed, generated_at, last_updated, room_lookup)
                written_count += stats["written"]
                empty_count += stats["empty"]
                success_count += 1
                source_summaries.append(
                    {
                        "academicYear": entry.academic_year,
                        "programId": entry.program_id,
                        "year": entry.year,
                        "url": entry.url,
                        "configuredGroups": entry.groups,
                        "detectedGroups": parsed.detected_groups,
                        "groupsWritten": stats["groupsWritten"],
                    }
                )

                missing_groups = sorted(set(entry.groups) - set(parsed.detected_groups))
                if missing_groups:
                    source_warnings.append(
                        {
                            "academicYear": entry.academic_year,
                            "programId": entry.program_id,
                            "year": entry.year,
                            "url": entry.url,
                            "warning": f"Configured groups missing in parsed source: {missing_groups}",
                        }
                    )
            except (requests.RequestException, TimetableParseError, ValueError) as exc:
                source_failures.append(
                    {
                        "academicYear": entry.academic_year,
                        "programId": entry.program_id,
                        "year": str(entry.year),
                        "url": entry.url,
                        "error": str(exc),
                    }
                )
                groups_to_consider = entry.groups
                for group in groups_to_consider:
                    group_path = _timetable_path(out_dir, entry, group)
                    if group_path.exists():
                        continue
                    if args.soft_fail_empty:
                        _write_empty_fallback(out_dir, entry, group, generated_at)

    status_payload = {
        "version": VERSION,
        "generatedAt": generated_at,
        "sourcesTotal": len(entries),
        "sourcesSucceeded": success_count,
        "sourcesFailed": len(source_failures),
        "timetableFilesWritten": written_count,
        "timetableFilesEmpty": empty_count,
        "roomsInLegend": room_legend_count,
        "failures": source_failures,
        "warnings": source_warnings,
        "sources": source_summaries,
    }
    write_json(out_dir / ".scrape-status.json", status_payload)

    print(
        f"Processed {len(entries)} sources. Success: {success_count}, "
        f"failed: {len(source_failures)}, files written: {written_count}, empty: {empty_count}"
    )
    if source_failures:
        print("Failed sources:")
        for failure in source_failures:
            print(f" - {failure['url']}: {failure['error']}")

    if args.fail_on_errors and source_failures:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
