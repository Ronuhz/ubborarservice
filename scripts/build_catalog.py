#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from pipeline_utils import VERSION, SourceEntry, load_source_entries, read_json, utc_now_iso, write_json


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build catalog.json from timetable source config.")
    parser.add_argument("--config", required=True, help="Path to sources config JSON.")
    parser.add_argument("--out", required=True, help="Output directory where catalog.json is written.")
    parser.add_argument(
        "--status",
        default=None,
        help="Optional scrape status JSON (dist/.scrape-status.json) to use detected groups.",
    )
    return parser.parse_args()


def _status_group_overrides(path: Path | None) -> dict[tuple[str, str, int, str], list[int]]:
    if path is None or not path.exists():
        return {}
    payload = read_json(path)
    if not isinstance(payload, dict):
        return {}
    sources = payload.get("sources")
    if not isinstance(sources, list):
        return {}

    overrides: dict[tuple[str, str, int, str], list[int]] = {}
    for source in sources:
        if not isinstance(source, dict):
            continue
        academic_year = source.get("academicYear")
        program_id = source.get("programId")
        year = source.get("year")
        url = source.get("url")
        detected_groups = source.get("detectedGroups")
        if not isinstance(academic_year, str) or not isinstance(program_id, str) or not isinstance(url, str):
            continue
        if not isinstance(year, int):
            continue
        if not isinstance(detected_groups, list):
            continue
        groups: list[int] = []
        for group in detected_groups:
            if isinstance(group, int):
                groups.append(group)
        if groups:
            overrides[(academic_year, program_id, year, url)] = sorted(set(groups))
    return overrides


def _build_catalog(
    entries: list[SourceEntry],
    group_overrides: dict[tuple[str, str, int, str], list[int]] | None = None,
) -> dict[str, Any]:
    group_overrides = group_overrides or {}
    academic_years = sorted({entry.academic_year for entry in entries})
    programs: dict[str, dict[str, Any]] = {}

    for entry in entries:
        override_key = (entry.academic_year, entry.program_id, entry.year, entry.url)
        groups_for_catalog = group_overrides.get(override_key, entry.groups)

        bucket = programs.setdefault(
            entry.program_id,
            {
                "id": entry.program_id,
                "title": entry.program_title,
                "yearsByNumber": {},
            },
        )
        if not bucket["title"] and entry.program_title:
            bucket["title"] = entry.program_title

        years_by_number = bucket["yearsByNumber"]
        group_set = years_by_number.setdefault(entry.year, set())
        group_set.update(groups_for_catalog)

    catalog_programs: list[dict[str, Any]] = []
    for program_id in sorted(programs):
        program_bucket = programs[program_id]
        years = []
        for year in sorted(program_bucket["yearsByNumber"]):
            groups = sorted(program_bucket["yearsByNumber"][year])
            years.append({"year": year, "groups": groups})
        catalog_programs.append(
            {
                "id": program_bucket["id"],
                "title": program_bucket["title"],
                "years": years,
            }
        )

    return {
        "version": VERSION,
        "generatedAt": utc_now_iso(),
        "academicYears": academic_years,
        "programs": catalog_programs,
    }


def main() -> int:
    args = _parse_args()
    entries = load_source_entries(Path(args.config))
    overrides = _status_group_overrides(Path(args.status)) if args.status else {}
    catalog = _build_catalog(entries, overrides)
    write_json(Path(args.out) / "catalog.json", catalog)
    print(f"Wrote catalog for {len(catalog['programs'])} programs.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
