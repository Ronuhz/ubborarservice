#!/usr/bin/env python3
from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from pipeline_utils import VERSION, read_json, utc_now_iso, write_json


REQUIRED_OFFER_FIELDS = [
    "id",
    "title",
    "subtitle",
    "badge",
    "url",
    "symbolName",
    "topColor",
    "bottomColor",
    "accentColor",
]


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build discounts.json for the iOS app.")
    parser.add_argument("--out", required=True, help="Output directory where discounts.json is written.")
    parser.add_argument(
        "--discounts",
        default="config/discounts.json",
        help="Discounts config JSON path (default: config/discounts.json).",
    )
    return parser.parse_args()


def _validate_color(color: Any, offer_id: str, field_name: str) -> dict[str, float]:
    if not isinstance(color, dict):
        raise ValueError(f"{offer_id}: '{field_name}' must be an object with red/green/blue.")
    result: dict[str, float] = {}
    for channel in ("red", "green", "blue"):
        if channel not in color:
            raise ValueError(f"{offer_id}: '{field_name}.{channel}' is required.")
        value = color[channel]
        if not isinstance(value, (int, float)):
            raise ValueError(f"{offer_id}: '{field_name}.{channel}' must be numeric.")
        channel_value = float(value)
        if channel_value < 0.0 or channel_value > 1.0:
            raise ValueError(f"{offer_id}: '{field_name}.{channel}' must be between 0 and 1.")
        result[channel] = channel_value
    return result


def _normalize_offer(raw_offer: Any) -> dict[str, Any] | None:
    if not isinstance(raw_offer, dict):
        return None
    offer: dict[str, Any] = {}
    for field in REQUIRED_OFFER_FIELDS:
        if field not in raw_offer:
            raise ValueError(f"Offer is missing required field '{field}'.")

    offer_id = str(raw_offer["id"]).strip()
    if not offer_id:
        raise ValueError("Offer 'id' cannot be empty.")

    offer["id"] = offer_id
    offer["title"] = str(raw_offer["title"]).strip()
    offer["subtitle"] = str(raw_offer["subtitle"]).strip()
    offer["badge"] = str(raw_offer["badge"]).strip()
    offer["url"] = str(raw_offer["url"]).strip()
    offer["symbolName"] = str(raw_offer["symbolName"]).strip()

    for text_field in ("title", "subtitle", "badge", "url", "symbolName"):
        if not offer[text_field]:
            raise ValueError(f"{offer_id}: '{text_field}' cannot be empty.")

    offer["topColor"] = _validate_color(raw_offer["topColor"], offer_id, "topColor")
    offer["bottomColor"] = _validate_color(raw_offer["bottomColor"], offer_id, "bottomColor")
    offer["accentColor"] = _validate_color(raw_offer["accentColor"], offer_id, "accentColor")
    return offer


def _load_offers(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    payload = read_json(path)
    if not isinstance(payload, dict) or not isinstance(payload.get("items"), list):
        raise ValueError(f"{path}: expected an object with an 'items' array.")

    deduped: list[dict[str, Any]] = []
    seen_ids: set[str] = set()
    for raw_offer in payload["items"]:
        offer = _normalize_offer(raw_offer)
        if offer is None:
            continue
        if offer["id"] in seen_ids:
            continue
        seen_ids.add(offer["id"])
        deduped.append(offer)
    return deduped


def _build_payload(offers: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "version": VERSION,
        "generatedAt": utc_now_iso(),
        "items": offers,
    }


def main() -> int:
    args = _parse_args()
    out_dir = Path(args.out)
    out_dir.mkdir(parents=True, exist_ok=True)

    offers = _load_offers(Path(args.discounts))
    payload = _build_payload(offers)
    write_json(out_dir / "discounts.json", payload)
    print(f"Wrote {len(offers)} discounts.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
