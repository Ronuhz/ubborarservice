from __future__ import annotations

import json
import sys
from pathlib import Path
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from build_discounts import _build_payload, _load_offers


class BuildDiscountsTest(unittest.TestCase):
    def test_load_offers_and_dedupe(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            discounts_path = Path(tmp_dir) / "discounts.json"
            discounts_path.write_text(
                json.dumps(
                    {
                        "items": [
                            {
                                "id": "github-pack",
                                "title": "discount.offer.github_pack.title",
                                "subtitle": "discount.offer.github_pack.subtitle",
                                "badge": "discount.offer.github_pack.badge",
                                "url": "https://education.github.com/pack",
                                "symbolName": "chevron.left.forwardslash.chevron.right",
                                "topColor": {"red": 0.09, "green": 0.09, "blue": 0.11},
                                "bottomColor": {"red": 0.22, "green": 0.22, "blue": 0.27},
                                "accentColor": {"red": 0.52, "green": 0.81, "blue": 1.0},
                            },
                            {
                                "id": "github-pack",
                                "title": "duplicate-should-drop",
                                "subtitle": "duplicate-should-drop",
                                "badge": "duplicate-should-drop",
                                "url": "https://example.org",
                                "symbolName": "xmark",
                                "topColor": {"red": 0.1, "green": 0.1, "blue": 0.1},
                                "bottomColor": {"red": 0.2, "green": 0.2, "blue": 0.2},
                                "accentColor": {"red": 0.3, "green": 0.3, "blue": 0.3},
                            },
                        ]
                    }
                ),
                encoding="utf-8",
            )

            offers = _load_offers(discounts_path)
            self.assertEqual(len(offers), 1)
            self.assertEqual(offers[0]["id"], "github-pack")

            payload = _build_payload(offers)
            self.assertEqual(payload["version"], 1)
            self.assertEqual(len(payload["items"]), 1)


if __name__ == "__main__":
    unittest.main()
