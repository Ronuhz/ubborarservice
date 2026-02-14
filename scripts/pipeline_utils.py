from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import json
import re
from datetime import datetime, timezone
from typing import Any


VERSION = 1


@dataclass(frozen=True)
class SourceEntry:
    academic_year: str
    program_id: str
    program_title: str
    year: int
    url: str
    groups: list[int]


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def normalize_space(value: str, keep_newlines: bool = False) -> str:
    value = value.strip()
    if keep_newlines:
        lines = [re.sub(r"[ \t]+", " ", line).strip() for line in value.splitlines()]
        lines = [line for line in lines if line]
        return "\n".join(lines)
    return re.sub(r"\s+", " ", value)


def read_json(path: Path) -> Any:
    with path.open("r", encoding="utf-8") as handle:
        return json.load(handle)


def write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as handle:
        json.dump(payload, handle, ensure_ascii=False, indent=2, sort_keys=False)
        handle.write("\n")


def _safe_title_from_program_id(program_id: str) -> str:
    return " ".join(part.capitalize() for part in re.split(r"[-_]+", program_id.strip()) if part)


def _parse_groups(raw_groups: Any, source_label: str) -> list[int]:
    if raw_groups is None:
        return []
    if isinstance(raw_groups, str):
        parts = [part.strip() for part in raw_groups.split(",") if part.strip()]
    elif isinstance(raw_groups, list):
        parts = raw_groups
    else:
        raise ValueError(f"{source_label}: 'groups' must be a list or comma-separated string.")

    groups: list[int] = []
    for raw in parts:
        try:
            groups.append(int(raw))
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{source_label}: invalid group value '{raw}'.") from exc

    return sorted(set(groups))


def _parse_source(raw: dict[str, Any], default_academic_year: str | None, source_label: str) -> SourceEntry:
    academic_year = str(raw.get("academicYear") or default_academic_year or "").strip()
    if not academic_year:
        raise ValueError(f"{source_label}: 'academicYear' is required.")

    program_id = str(raw.get("programId") or raw.get("id") or "").strip()
    if not program_id:
        raise ValueError(f"{source_label}: 'programId' is required.")

    url = str(raw.get("url") or "").strip()
    if not url:
        raise ValueError(f"{source_label}: 'url' is required.")

    if "year" not in raw:
        raise ValueError(f"{source_label}: 'year' is required.")

    try:
        year = int(raw["year"])
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{source_label}: 'year' must be an integer.") from exc

    if year < 1:
        raise ValueError(f"{source_label}: 'year' must be >= 1.")

    groups = _parse_groups(raw.get("groups", []), source_label)

    title = str(raw.get("title") or raw.get("programTitle") or "").strip()
    if not title:
        title = _safe_title_from_program_id(program_id)

    return SourceEntry(
        academic_year=academic_year,
        program_id=program_id,
        program_title=title,
        year=year,
        url=url,
        groups=groups,
    )


def _collect_sources(root: dict[str, Any]) -> list[SourceEntry]:
    by_key: dict[tuple[str, str, int, str], SourceEntry] = {}
    default_academic_year = str(root.get("academicYear") or root.get("defaultAcademicYear") or "").strip() or None

    def add_many(items: list[dict[str, Any]], default_year: str | None, section_label: str) -> None:
        for index, raw_source in enumerate(items):
            source_label = f"{section_label}[{index}]"
            parsed = _parse_source(raw_source, default_year, source_label)
            key = (parsed.academic_year, parsed.program_id, parsed.year, parsed.url)
            existing = by_key.get(key)
            if not existing:
                by_key[key] = parsed
                continue
            merged_groups = sorted(set(existing.groups) | set(parsed.groups))
            merged_title = existing.program_title or parsed.program_title
            by_key[key] = SourceEntry(
                academic_year=existing.academic_year,
                program_id=existing.program_id,
                program_title=merged_title,
                year=existing.year,
                url=existing.url,
                groups=merged_groups,
            )

    direct_sources = root.get("sources")
    if isinstance(direct_sources, list):
        add_many(direct_sources, default_academic_year, "sources")

    direct_programs = root.get("programs")
    if isinstance(direct_programs, list):
        add_many(direct_programs, default_academic_year, "programs")

    by_year = root.get("academicYears")
    if isinstance(by_year, list):
        for year_index, year_bucket in enumerate(by_year):
            if not isinstance(year_bucket, dict):
                raise ValueError(f"academicYears[{year_index}] must be an object.")
            bucket_year = str(year_bucket.get("academicYear") or "").strip()
            if not bucket_year:
                raise ValueError(f"academicYears[{year_index}]: 'academicYear' is required.")
            bucket_sources = year_bucket.get("sources")
            if isinstance(bucket_sources, list):
                add_many(bucket_sources, bucket_year, f"academicYears[{year_index}].sources")
            bucket_programs = year_bucket.get("programs")
            if isinstance(bucket_programs, list):
                add_many(bucket_programs, bucket_year, f"academicYears[{year_index}].programs")

    return sorted(
        by_key.values(),
        key=lambda entry: (entry.academic_year, entry.program_id, entry.year, entry.url),
    )


def load_source_entries(config_path: Path) -> list[SourceEntry]:
    raw = read_json(config_path)
    if not isinstance(raw, dict):
        raise ValueError("Config root must be an object.")

    entries = _collect_sources(raw)
    if not entries:
        raise ValueError("No sources found. Add 'programs', 'sources', or 'academicYears' in config.")
    return entries
