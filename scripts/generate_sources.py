#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path
import re
from typing import Any
from urllib.parse import urljoin, urlparse
import unicodedata

import requests
from bs4 import BeautifulSoup

from pipeline_utils import normalize_space, read_json, write_json
from timetable_parser import TimetableParseError, parse_timetable_html


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Generate config/sources.json entries by crawling the UBB timetable index page."
    )
    parser.add_argument("--index-url", required=True, help="Index URL, e.g. .../tabelar/index.html")
    parser.add_argument("--academic-year", required=True, help="Academic year label to write into config.")
    parser.add_argument("--out", required=True, help="Output sources JSON path.")
    parser.add_argument(
        "--program-map",
        default=None,
        help="Optional JSON map for program IDs/titles keyed by source title or title slug.",
    )
    parser.add_argument("--timeout", type=float, default=30.0, help="HTTP timeout in seconds (default: 30).")
    parser.add_argument(
        "--include-master",
        action="store_true",
        help="Include Master sections in addition to Studii Licenta.",
    )
    parser.add_argument(
        "--skip-group-detection",
        action="store_true",
        help="Skip per-page group detection and leave groups empty.",
    )
    return parser.parse_args()


def _fold(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    without_diacritics = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    return without_diacritics.lower()


def _slugify(value: str) -> str:
    folded = _fold(value)
    slug = re.sub(r"[^a-z0-9]+", "-", folded).strip("-")
    return slug or "program"


def _extract_year(text: str, href: str) -> int | None:
    for candidate in (text, Path(urlparse(href).path).name):
        match = re.search(r"\b(?:an(?:ul)?\s*)?([1-6])\b", _fold(candidate))
        if match:
            try:
                return int(match.group(1))
            except ValueError:
                continue
    return None


def _is_index_link(href: str) -> bool:
    name = Path(urlparse(href).path).name.lower()
    return name in {"index.html", "index.htm"}


def _load_program_map(path: Path | None) -> dict[str, Any]:
    if path is None:
        return {}
    payload = read_json(path)
    if not isinstance(payload, dict):
        raise ValueError("Program map must be a JSON object.")
    return payload


def _resolve_program(title: str, program_map: dict[str, Any]) -> tuple[str, str]:
    slug = _slugify(title)
    mapping = program_map.get(title)
    if mapping is None:
        mapping = program_map.get(slug)

    if isinstance(mapping, str):
        return mapping.strip(), title
    if isinstance(mapping, dict):
        mapped_id = str(mapping.get("id") or "").strip()
        mapped_title = str(mapping.get("title") or title).strip()
        if mapped_id:
            return mapped_id, mapped_title
    return slug, title


def _collect_rows(index_html: str, index_url: str, include_master: bool) -> list[dict[str, Any]]:
    soup = BeautifulSoup(index_html, "html.parser")
    rows: list[dict[str, Any]] = []
    current_level: str | None = None

    for tr in soup.find_all("tr"):
        cells = tr.find_all(["td", "th"])
        if not cells:
            continue

        row_text = normalize_space(tr.get_text(" ", strip=True))
        folded_row = _fold(row_text)
        if "studii licenta" in folded_row:
            current_level = "licenta"
            continue
        if "studii master" in folded_row:
            current_level = "master"
            continue
        if current_level != "licenta" and not (include_master and current_level == "master"):
            continue

        first_cell = normalize_space(cells[0].get_text(" ", strip=True)) if cells else ""
        if not first_cell:
            continue
        if _fold(first_cell).startswith("specializarea"):
            continue

        anchors = [a for a in tr.find_all("a", href=True)]
        if not anchors:
            continue

        for anchor in anchors:
            href = urljoin(index_url, anchor["href"])
            if _is_index_link(href):
                continue
            if not href.lower().endswith(".html"):
                continue
            year = _extract_year(normalize_space(anchor.get_text(" ", strip=True)), href)
            if year is None:
                continue
            rows.append(
                {
                    "title": first_cell,
                    "year": year,
                    "url": href,
                    "level": current_level,
                }
            )

    return rows


def _detect_groups(
    session: requests.Session,
    source_url: str,
    timeout: float,
) -> list[int]:
    response = session.get(source_url, timeout=timeout)
    response.raise_for_status()
    parsed = parse_timetable_html(response.text, [])
    return parsed.detected_groups


def main() -> int:
    args = _parse_args()
    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)

    program_map = _load_program_map(Path(args.program_map)) if args.program_map else {}

    with requests.Session() as session:
        session.headers.update({"User-Agent": "ubborarservice-source-generator/1.0"})
        index_response = session.get(args.index_url, timeout=args.timeout)
        index_response.raise_for_status()
        discovered_rows = _collect_rows(index_response.text, args.index_url, args.include_master)

        if not discovered_rows:
            raise RuntimeError("No timetable rows were discovered from the index page.")

        by_key: dict[tuple[str, int, str], dict[str, Any]] = {}
        detection_failures: list[str] = []
        for row in discovered_rows:
            program_id, display_title = _resolve_program(row["title"], program_map)
            key = (program_id, row["year"], row["url"])
            source = by_key.get(key)
            if source is None:
                source = {
                    "programId": program_id,
                    "title": display_title,
                    "year": row["year"],
                    "url": row["url"],
                    "groups": [],
                }
                by_key[key] = source

            if args.skip_group_detection:
                continue

            try:
                detected_groups = _detect_groups(session, row["url"], args.timeout)
                source["groups"] = sorted(set(source["groups"]) | set(detected_groups))
            except (requests.RequestException, TimetableParseError, ValueError) as exc:
                detection_failures.append(f"{row['url']}: {exc}")

    programs = sorted(
        by_key.values(),
        key=lambda item: (item["programId"], item["year"], item["url"]),
    )
    payload = {
        "academicYear": args.academic_year,
        "programs": programs,
    }
    write_json(out_path, payload)

    print(f"Generated {len(programs)} source entries to {out_path}.")
    if detection_failures:
        print(f"Group detection failed for {len(detection_failures)} page(s):")
        for failure in detection_failures:
            print(f" - {failure}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
