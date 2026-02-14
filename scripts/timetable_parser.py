from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
import re
import unicodedata
from typing import Any

from bs4 import BeautifulSoup
from bs4.element import Tag

from pipeline_utils import normalize_space


DAY_ORDER = ["monday", "tuesday", "wednesday", "thursday", "friday"]

DAY_ALIASES = {
    "luni": "monday",
    "monday": "monday",
    "hetfo": "monday",
    "marti": "tuesday",
    "marți": "tuesday",
    "marţi": "tuesday",
    "tuesday": "tuesday",
    "kedd": "tuesday",
    "miercuri": "wednesday",
    "wednesday": "wednesday",
    "szerda": "wednesday",
    "joi": "thursday",
    "thursday": "thursday",
    "csutortok": "thursday",
    "vineri": "friday",
    "friday": "friday",
    "pentek": "friday",
}

TIME_RE = re.compile(r"\b(\d{1,2}(?::\d{2})?\s*[-–]\s*\d{1,2}(?::\d{2})?)\b")
GROUP_RE = re.compile(r"\b(\d{3,4})\b")
TYPE_TAG_RE = re.compile(r"\((?:c|s|l)\)", re.IGNORECASE)
TITLE_RE = re.compile(r"\b(?:prof\.?|asist\.?|conf\.?|lect\.?|dr\.?)", re.IGNORECASE)
ROOM_KEYWORD_RE = re.compile(r"\b(?:sala|room|amf(?:iteatru)?|aula|lab(?:orator)?)\b", re.IGNORECASE)
ROOM_CAPTURE_RE = re.compile(
    r"\b(?:sala|room|amf(?:iteatru)?|aula|lab(?:orator)?)\s*[:\-]?\s*([A-Za-z0-9._/-]+)",
    re.IGNORECASE,
)
GROUP_HEADING_RE = re.compile(r"\bgrupa\s+(\d{3,4})\b", re.IGNORECASE)
FORMATION_NUMERIC_RE = re.compile(r"^\d{3,4}(?:/\d+)?$")
FORMATION_TOKEN_RE = re.compile(r"^[A-Za-z]{1,6}\d{0,3}$")
SUBGROUP_PREFIX_RE = re.compile(r"^(?:sgr\.?|subgr\.?|gr\.?)\s*[\w/-]+\s*:\s*", re.IGNORECASE)
INLINE_ENTRY_RE = re.compile(
    r"^(?:(?:sapt\.?\s*[12]|week\s*[12])\s*:\s*)?"
    r"(?P<course>.+?)\s*\((?P<instructor>[^()]+)\)\s*,\s*(?P<room>[A-Za-z0-9_./-]+)$",
    re.IGNORECASE,
)


class TimetableParseError(RuntimeError):
    pass


@dataclass
class ParsedTimetable:
    by_group: dict[int, list[dict[str, Any]]]
    detected_groups: list[int]


def _fold(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    without_diacritics = "".join(ch for ch in normalized if not unicodedata.combining(ch))
    return without_diacritics.lower()


def normalize_day(value: str) -> str | None:
    folded = _fold(normalize_space(value))
    for alias, canonical in DAY_ALIASES.items():
        if re.search(rf"\b{re.escape(alias)}\b", folded):
            return canonical
    return None


def normalize_time(value: str) -> str:
    value = value.strip().replace(" ", "")
    return re.sub(r"[-–]", "–", value, count=1)


def _extract_cell_text(cell: Tag) -> str:
    raw = cell.get_text("\n", strip=True)
    return normalize_space(raw, keep_newlines=True)


def _main_table_score(table: Tag) -> int:
    text = _fold(table.get_text(" ", strip=True))
    day_hits = sum(1 for token in DAY_ALIASES if token in text)
    group_hits = len(GROUP_RE.findall(text))
    row_count = len(table.find_all("tr"))
    return (day_hits * 10) + min(group_hits, 40) + row_count


def _select_main_table(soup: BeautifulSoup) -> Tag:
    tables = soup.find_all("table")
    if not tables:
        raise TimetableParseError("No table was found on the source page.")
    return max(tables, key=_main_table_score)


def _expand_table(table: Tag) -> list[list[str]]:
    grid: list[list[str]] = []
    spans: dict[int, dict[str, Any]] = {}

    def fill_span(row: list[str], start_col: int) -> int:
        col = start_col
        while col in spans:
            row.append(spans[col]["text"])
            spans[col]["rows"] -= 1
            if spans[col]["rows"] <= 0:
                del spans[col]
            col += 1
        return col

    for tr in table.find_all("tr"):
        row: list[str] = []
        col = fill_span(row, 0)
        for cell in tr.find_all(["th", "td"]):
            col = fill_span(row, col)
            text = _extract_cell_text(cell)
            try:
                rowspan = max(1, int(cell.get("rowspan", 1)))
            except (TypeError, ValueError):
                rowspan = 1
            try:
                colspan = max(1, int(cell.get("colspan", 1)))
            except (TypeError, ValueError):
                colspan = 1
            for _ in range(colspan):
                row.append(text)
                if rowspan > 1:
                    spans[col] = {"rows": rowspan - 1, "text": text}
                col += 1
        fill_span(row, col)
        grid.append(row)

    max_cols = max((len(row) for row in grid), default=0)
    return [row + [""] * (max_cols - len(row)) for row in grid]


def _extract_group_from_header(cell_text: str, expected_groups: set[int]) -> int | None:
    matches = [int(group) for group in GROUP_RE.findall(cell_text)]
    if not matches:
        return None
    if expected_groups:
        for match in matches:
            if match in expected_groups:
                return match
        return None
    if len(matches) == 1:
        return matches[0]
    return None


def _detect_group_columns(grid: list[list[str]], expected_groups: list[int]) -> dict[int, int]:
    expected_set = set(expected_groups)
    best_mapping: dict[int, int] = {}
    for row in grid[:12]:
        mapping: dict[int, int] = {}
        for col, cell in enumerate(row):
            group = _extract_group_from_header(cell, expected_set)
            if group is None:
                continue
            mapping[col] = group
        if len(mapping) > len(best_mapping):
            best_mapping = mapping

    if expected_set:
        best_mapping = {col: group for col, group in best_mapping.items() if group in expected_set}

    if best_mapping:
        return best_mapping

    if expected_set and grid:
        # Fallback for simple tables where headers are malformed: map trailing columns to configured groups.
        first_row_len = len(grid[0])
        columns = list(range(max(0, first_row_len - len(expected_set)), first_row_len))
        return {column: group for column, group in zip(columns, sorted(expected_set))}

    return {}


def _extract_time(row: list[str]) -> str | None:
    for cell in row:
        match = TIME_RE.search(cell)
        if match:
            return normalize_time(match.group(1))
    return None


def _detect_frequency(text: str) -> str:
    folded = _fold(text)
    has_week1 = bool(re.search(r"\b(?:week\s*1|sapt\.?\s*1|saptamana\s*1|impar(?:a)?)\b", folded))
    has_week2 = bool(re.search(r"\b(?:week\s*2|sapt\.?\s*2|saptamana\s*2|par(?:a)?)\b", folded))
    if has_week1 and has_week2:
        return "weekly"
    if has_week1:
        return "week1"
    if has_week2:
        return "week2"
    if re.search(r"\b(?:weekly|saptamanal)\b", folded):
        return "weekly"
    return "weekly"


def _detect_type(text: str) -> str:
    folded = _fold(text)
    if re.search(r"\((?:c|curs)\)", text, re.IGNORECASE):
        return "lecture"
    if re.search(r"\((?:s|sem)\)", text, re.IGNORECASE):
        return "seminar"
    if re.search(r"\((?:l|lab)\)", text, re.IGNORECASE):
        return "lab"
    if re.search(r"\b(?:lecture|course|curs)\b", folded):
        return "lecture"
    if re.search(r"\bseminar\b", folded):
        return "seminar"
    if re.search(r"\b(?:lab|laborator)\b", folded):
        return "lab"
    return "lecture"


def _detect_room(lines: list[str]) -> str:
    for line in lines:
        match = ROOM_CAPTURE_RE.search(line)
        if match:
            return match.group(1).strip()
    for line in lines:
        if ROOM_KEYWORD_RE.search(line):
            return line.strip()
    for line in lines:
        token = normalize_space(line)
        if not token or " " in token:
            continue
        if _is_frequency_line(token):
            continue
        if _is_formation_line(token):
            continue
        if _is_time_or_day_token(token):
            continue
        if TITLE_RE.search(token):
            continue
        return token
    return ""


def _is_frequency_line(line: str) -> bool:
    folded = _fold(line)
    return bool(re.search(r"\b(?:week\s*[12]|weekly|sapt|impar|par)\b", folded))


def _is_time_or_day_token(line: str) -> bool:
    cleaned = normalize_space(line)
    if TIME_RE.fullmatch(cleaned):
        return True
    return normalize_day(cleaned) is not None and len(cleaned.split()) <= 2


def _strip_subgroup_prefix(line: str) -> str:
    return SUBGROUP_PREFIX_RE.sub("", normalize_space(line)).strip()


def _is_formation_line(line: str) -> bool:
    cleaned = _strip_subgroup_prefix(line).strip("() ")
    if not cleaned:
        return False
    if FORMATION_NUMERIC_RE.fullmatch(cleaned):
        return True
    if not FORMATION_TOKEN_RE.fullmatch(cleaned):
        return False

    upper = cleaned.upper()
    # Keep common room-code patterns out of formation detection.
    if upper.startswith(("CR", "LAB", "AMF", "AULA", "ROOM", "SALA")):
        return False
    if re.fullmatch(r"C\d+[A-Z0-9._/-]*", upper):
        return False
    if re.fullmatch(r"L\d+[A-Z0-9._/-]*", upper):
        return False
    return True


def _is_room_line(line: str) -> bool:
    return bool(ROOM_KEYWORD_RE.search(line))


def _is_instructor_line(line: str) -> bool:
    if TITLE_RE.search(line):
        return True
    if _is_room_line(line):
        return False
    words = [word for word in re.split(r"\s+", line.strip()) if word]
    if len(words) < 2:
        return False
    capitalized = sum(1 for word in words if word[0].isupper())
    return capitalized >= 2 and not _is_frequency_line(line)


def _detect_instructor(lines: list[str]) -> str:
    for line in lines:
        if TITLE_RE.search(line):
            return line.strip()
    for line in lines:
        if _is_instructor_line(line):
            return line.strip()
    return ""


def _strip_inline_metadata(value: str) -> str:
    value = _strip_subgroup_prefix(value)
    value = TYPE_TAG_RE.sub("", value)
    value = re.sub(r"\b(?:week\s*[12]|weekly|sapt\.?\s*[12]?|impar(?:a)?|par(?:a)?)\b", "", value, flags=re.IGNORECASE)
    value = re.sub(r"\s+", " ", value).strip(" -")
    return value


def _detect_course(lines: list[str]) -> str:
    for line in lines:
        if _is_frequency_line(line) or _is_room_line(line) or _is_instructor_line(line) or _is_formation_line(line):
            continue
        cleaned = _strip_inline_metadata(line)
        if cleaned:
            return cleaned
    if lines:
        for line in lines:
            cleaned = _strip_inline_metadata(line)
            if cleaned and not _is_formation_line(cleaned):
                return cleaned
    return "Unknown"


def _split_cell_chunks(text: str) -> list[str]:
    chunks = [normalize_space(chunk, keep_newlines=True) for chunk in re.split(r"\n{2,}", text) if normalize_space(chunk)]
    if chunks:
        return chunks
    return [normalize_space(text, keep_newlines=True)] if normalize_space(text) else []


def _parse_inline_entry_line(line: str, time_slot: str) -> dict[str, str] | None:
    cleaned = normalize_space(line)
    if not cleaned:
        return None
    stripped = _strip_subgroup_prefix(cleaned)
    match = INLINE_ENTRY_RE.match(stripped)
    if not match:
        return None
    course = _strip_inline_metadata(match.group("course"))
    if not course:
        return None
    return {
        "time": time_slot,
        "frequency": _detect_frequency(stripped),
        "course": course,
        "type": _detect_type(stripped),
        "room": normalize_space(match.group("room")),
        "instructor": normalize_space(match.group("instructor")),
    }


def _parse_inline_chunk(chunk: str, time_slot: str) -> list[dict[str, str]]:
    entries: list[dict[str, str]] = []
    for line in chunk.splitlines():
        parsed = _parse_inline_entry_line(line, time_slot)
        if parsed:
            entries.append(parsed)
    return entries


def _parse_cell_entries(text: str, time_slot: str) -> list[dict[str, str]]:
    text = normalize_space(text, keep_newlines=True)
    if not text:
        return []
    if text in {"-", "—"}:
        return []
    if normalize_day(text) and len(text.split()) <= 2:
        return []
    if TIME_RE.fullmatch(text):
        return []

    entries: list[dict[str, str]] = []
    for chunk in _split_cell_chunks(text):
        inline_entries = _parse_inline_chunk(chunk, time_slot)
        if inline_entries:
            entries.extend(inline_entries)
            continue

        lines = [line for line in chunk.splitlines() if line]
        lines = [line for line in lines if not normalize_day(line)]
        lines = [line for line in lines if not TIME_RE.fullmatch(line)]
        lines = [line for line in lines if not _is_formation_line(line)]
        if not lines:
            continue
        entry = {
            "time": time_slot,
            "frequency": _detect_frequency(chunk),
            "course": _detect_course(lines),
            "type": _detect_type(chunk),
            "room": _detect_room(lines),
            "instructor": _detect_instructor(lines),
        }
        if entry["course"]:
            entries.append(entry)
    deduped: list[dict[str, str]] = []
    seen: set[tuple[str, str, str, str, str, str]] = set()
    for entry in entries:
        key = (
            entry["time"],
            entry["frequency"],
            entry["course"],
            entry["type"],
            entry["room"],
            entry["instructor"],
        )
        if key in seen:
            continue
        seen.add(key)
        deduped.append(entry)
    return deduped


def _grouped_to_days(
    grouped_entries: dict[int, dict[str, list[dict[str, str]]]],
    target_groups: list[int],
) -> dict[int, list[dict[str, Any]]]:
    by_group: dict[int, list[dict[str, Any]]] = {}
    for group in target_groups:
        days: list[dict[str, Any]] = []
        for day in DAY_ORDER:
            day_entries = grouped_entries.get(group, {}).get(day, [])
            if day_entries:
                days.append({"day": day, "entries": day_entries})
        by_group[group] = days
    return by_group


def _header_name_to_key(value: str) -> str | None:
    folded = _fold(value)
    if re.search(r"\bziua\b|\bday\b", folded):
        return "day"
    if re.search(r"\bora\b|\borele\b|\btime\b", folded):
        return "time"
    if re.search(r"\bfrecventa\b|\bfrecventa\b|\bfrequency\b", folded):
        return "frequency"
    if re.search(r"\bsala\b|\broom\b", folded):
        return "room"
    if re.search(r"\btip(?:ul)?\b|\btype\b", folded):
        return "type"
    if re.search(r"\bdisciplina\b|\bmateria\b|\bcourse\b", folded):
        return "course"
    if re.search(r"\bcadr(?:ul)?\s+didactic\b|\binstructor\b|\bprofesor\b", folded):
        return "instructor"
    return None


def _extract_group_heading(value: str) -> int | None:
    match = GROUP_HEADING_RE.search(value)
    if not match:
        return None
    try:
        return int(match.group(1))
    except ValueError:
        return None


def _extract_table_group(table: Tag) -> int | None:
    caption = table.find("caption")
    if caption:
        group = _extract_group_heading(normalize_space(caption.get_text(" ", strip=True)))
        if group is not None:
            return group

    for row in table.find_all("tr")[:3]:
        row_text = normalize_space(row.get_text(" ", strip=True))
        group = _extract_group_heading(row_text)
        if group is not None:
            return group

    sibling = table.previous_sibling
    hop_count = 0
    while sibling is not None and hop_count < 6:
        if isinstance(sibling, Tag):
            sibling_text = normalize_space(sibling.get_text(" ", strip=True))
            group = _extract_group_heading(sibling_text)
            if group is not None:
                return group
        sibling = sibling.previous_sibling
        hop_count += 1

    return None


def _parse_group_table_rows(grid: list[list[str]]) -> tuple[list[dict[str, str]], int]:
    best_header_idx = -1
    best_header_map: dict[str, int] = {}
    best_score = -1

    scan_limit = min(4, len(grid))
    for idx in range(scan_limit):
        mapping: dict[str, int] = {}
        for col, cell in enumerate(grid[idx]):
            key = _header_name_to_key(cell)
            if key and key not in mapping:
                mapping[key] = col
        score = len(mapping)
        if score > best_score:
            best_score = score
            best_header_idx = idx
            best_header_map = mapping

    if not best_header_map:
        return [], -1
    if "day" not in best_header_map or "time" not in best_header_map:
        return [], -1

    entries: list[dict[str, str]] = []
    for row in grid[best_header_idx + 1 :]:
        day_col = best_header_map["day"]
        time_col = best_header_map["time"]
        if day_col >= len(row) or time_col >= len(row):
            continue

        day = normalize_day(row[day_col])
        if not day:
            continue

        raw_time = row[time_col]
        time_match = TIME_RE.search(raw_time)
        if not time_match:
            continue
        time_slot = normalize_time(time_match.group(1))

        frequency_value = ""
        if "frequency" in best_header_map and best_header_map["frequency"] < len(row):
            frequency_value = row[best_header_map["frequency"]]

        type_value = ""
        if "type" in best_header_map and best_header_map["type"] < len(row):
            type_value = row[best_header_map["type"]]

        room_value = ""
        if "room" in best_header_map and best_header_map["room"] < len(row):
            room_value = row[best_header_map["room"]]

        course_value = ""
        if "course" in best_header_map and best_header_map["course"] < len(row):
            course_value = row[best_header_map["course"]]

        instructor_value = ""
        if "instructor" in best_header_map and best_header_map["instructor"] < len(row):
            instructor_value = row[best_header_map["instructor"]]

        row_blob = " ".join(cell for cell in row if cell)
        lines_for_fallback = [cell for cell in row if cell]
        entry = {
            "day": day,
            "time": time_slot,
            "frequency": _detect_frequency(frequency_value or row_blob),
            "course": normalize_space(course_value) or _detect_course(lines_for_fallback),
            "type": _detect_type(type_value or row_blob),
            "room": normalize_space(room_value) or _detect_room(lines_for_fallback),
            "instructor": normalize_space(instructor_value) or _detect_instructor(lines_for_fallback),
        }
        if entry["course"]:
            entries.append(entry)

    return entries, best_header_idx


def _parse_group_section_layout(soup: BeautifulSoup, expected_groups: list[int]) -> ParsedTimetable | None:
    expected_set = set(expected_groups)
    grouped_entries: dict[int, dict[str, list[dict[str, str]]]] = defaultdict(lambda: defaultdict(list))
    detected_groups: set[int] = set()
    current_group: int | None = None

    for node in soup.find_all(["h1", "h2", "h3", "h4", "h5", "h6", "p", "div", "strong", "b", "table"]):
        if node.name != "table":
            group = _extract_group_heading(normalize_space(node.get_text(" ", strip=True)))
            if group is not None:
                current_group = group
            continue

        table_group = _extract_table_group(node) or current_group
        if table_group is None:
            continue
        if expected_set and table_group not in expected_set:
            continue

        grid = _expand_table(node)
        if not grid:
            continue
        parsed_rows, _ = _parse_group_table_rows(grid)
        if not parsed_rows:
            continue

        detected_groups.add(table_group)
        for row_entry in parsed_rows:
            day = row_entry.pop("day")
            grouped_entries[table_group][day].append(row_entry)

    if not detected_groups:
        return None

    target_groups = sorted(expected_set or detected_groups)
    by_group = _grouped_to_days(grouped_entries, target_groups)
    return ParsedTimetable(by_group=by_group, detected_groups=sorted(detected_groups))


def _parse_columnar_layout(soup: BeautifulSoup, expected_groups: list[int]) -> ParsedTimetable:
    table = _select_main_table(soup)
    grid = _expand_table(table)
    if not grid:
        raise TimetableParseError("Timetable table is empty.")

    group_columns = _detect_group_columns(grid, expected_groups)
    if not group_columns:
        raise TimetableParseError("Could not detect group columns in timetable table.")

    detected_groups = sorted(set(group_columns.values()))
    target_groups = sorted(set(expected_groups) or set(detected_groups))

    grouped_entries: dict[int, dict[str, list[dict[str, str]]]] = {
        group: defaultdict(list) for group in target_groups
    }

    current_day: str | None = None
    for row in grid:
        row_day = next((day for day in (normalize_day(cell) for cell in row) if day), None)
        if row_day:
            current_day = row_day
        if current_day is None:
            continue
        time_slot = _extract_time(row)
        if not time_slot:
            continue
        for column, group in group_columns.items():
            if group not in grouped_entries:
                continue
            if column >= len(row):
                continue
            parsed_entries = _parse_cell_entries(row[column], time_slot)
            if parsed_entries:
                grouped_entries[group][current_day].extend(parsed_entries)

    by_group = _grouped_to_days(grouped_entries, target_groups)
    return ParsedTimetable(by_group=by_group, detected_groups=detected_groups)


def parse_timetable_html(html: str, expected_groups: list[int]) -> ParsedTimetable:
    soup = BeautifulSoup(html, "html.parser")

    grouped_layout = _parse_group_section_layout(soup, expected_groups)
    if grouped_layout is not None:
        return grouped_layout

    return _parse_columnar_layout(soup, expected_groups)
