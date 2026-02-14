from __future__ import annotations

from pathlib import Path
import re
from typing import Any

from bs4 import BeautifulSoup
import requests

from pipeline_utils import normalize_space, write_json


ROOM_TOKEN_RE = re.compile(r"[A-Za-z0-9_./-]+")


def _normalized_room_key(value: str) -> str:
    cleaned = normalize_space(value).strip()
    return re.sub(r"\s+", "", cleaned).upper()


def parse_room_legend_html(html: str) -> dict[str, str]:
    soup = BeautifulSoup(html, "html.parser")
    legend: dict[str, str] = {}

    for table in soup.find_all("table"):
        for row in table.find_all("tr"):
            cells = row.find_all(["td", "th"])
            if len(cells) < 2:
                continue

            room_raw = normalize_space(cells[0].get_text(" ", strip=True))
            address_raw = normalize_space(cells[1].get_text(" ", strip=True))
            if not room_raw:
                continue
            if _normalized_room_key(room_raw) == _normalized_room_key("Sala"):
                continue

            candidates = [room_raw]
            candidates.extend(part.strip() for part in re.split(r"[;,]", room_raw) if part.strip())
            for candidate in candidates:
                if candidate not in legend:
                    legend[candidate] = address_raw

    return legend


def fetch_room_legend(
    session: requests.Session,
    url: str,
    timeout: float,
) -> dict[str, str]:
    response = session.get(url, timeout=timeout)
    response.raise_for_status()
    return parse_room_legend_html(response.text)


def build_room_lookup(legend: dict[str, str]) -> dict[str, str]:
    lookup: dict[str, str] = {}
    for room_code, address in legend.items():
        key = _normalized_room_key(room_code)
        if key and key not in lookup:
            lookup[key] = address
    return lookup


def resolve_room_address(room_value: str, room_lookup: dict[str, str]) -> str | None:
    room_value = normalize_space(room_value)
    if not room_value:
        return None

    direct_key = _normalized_room_key(room_value)
    if direct_key in room_lookup:
        return room_lookup[direct_key]

    tokens = ROOM_TOKEN_RE.findall(room_value)
    for token in tokens:
        token_key = _normalized_room_key(token)
        if token_key in room_lookup:
            return room_lookup[token_key]
    return None


def write_room_legend_json(path: Path, legend: dict[str, str]) -> None:
    payload: dict[str, Any] = {"rooms": []}
    for room in sorted(legend):
        payload["rooms"].append(
            {
                "code": room,
                "address": legend[room],
            }
        )
    write_json(path, payload)
