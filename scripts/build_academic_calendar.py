#!/usr/bin/env python3
from __future__ import annotations

import argparse
from datetime import date
from pathlib import Path
from typing import Any

from pipeline_utils import VERSION, read_json, utc_now_iso, write_json


def build_calendar(config: dict[str, Any], generated_at: str) -> dict[str, Any]:
    academic_year = config.get("academicYear")
    calendars = config.get("calendars")
    if not isinstance(academic_year, str) or not academic_year:
        raise ValueError("academicYear is required")
    if not isinstance(calendars, list) or not calendars:
        raise ValueError("calendars must be a nonempty array")

    result: list[dict[str, Any]] = []
    for calendar in calendars:
        if not isinstance(calendar, dict) or not isinstance(calendar.get("semesters"), list):
            raise ValueError("each calendar needs semesters")
        semesters = []
        for semester in calendar["semesters"]:
            periods = semester.get("periods") if isinstance(semester, dict) else None
            if not isinstance(periods, list) or not periods:
                raise ValueError("each semester needs periods")
            teaching = []
            for period in periods:
                if not isinstance(period, dict) or period.get("type") not in {"teaching", "vacation"}:
                    raise ValueError("period type must be teaching or vacation")
                try:
                    start = date.fromisoformat(period["startDate"])
                    end = date.fromisoformat(period["endDate"])
                except (KeyError, TypeError, ValueError) as exc:
                    raise ValueError("period dates must be ISO 8601 dates") from exc
                if start > end:
                    raise ValueError("period startDate must not follow endDate")
                if period["type"] == "teaching":
                    teaching.append(period)
            if not teaching:
                raise ValueError("each semester needs a teaching period")
            semesters.append({
                "semester": semester["semester"],
                "teachingStartsOn": min(p["startDate"] for p in teaching),
                "teachingEndsOn": max(p["endDate"] for p in teaching),
                "periods": periods,
            })
        result.append({
            "languages": calendar["languages"],
            "studyYearKind": calendar["studyYearKind"],
            "semesters": semesters,
        })
    return {
        "version": VERSION,
        "generatedAt": generated_at,
        "academicYear": academic_year,
        "sourceUrl": config["sourceUrl"],
        "calendars": result,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Build academic-calendar.json from reviewed UBB dates.")
    parser.add_argument("--config", default="config/academic-calendar.json")
    parser.add_argument("--out", required=True)
    args = parser.parse_args()
    payload = build_calendar(read_json(Path(args.config)), utc_now_iso())
    write_json(Path(args.out) / "academic-calendar.json", payload)
    print(f"Wrote academic calendar for {payload['academicYear']}.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
