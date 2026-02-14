from __future__ import annotations

import json
import sys
from pathlib import Path
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from build_catalog import _build_catalog
from pipeline_utils import load_source_entries


class BuildCatalogTest(unittest.TestCase):
    def test_build_catalog_from_config(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            config_path = Path(tmp_dir) / "sources.json"
            config_path.write_text(
                json.dumps(
                    {
                        "academicYear": "2025-2026",
                        "programs": [
                            {
                                "programId": "informatica-maghiara",
                                "title": "Informatics - Hungarian track",
                                "year": 1,
                                "url": "https://example.org/im1.html",
                                "groups": [511, 512],
                            },
                            {
                                "programId": "informatica-maghiara",
                                "title": "Informatics - Hungarian track",
                                "year": 2,
                                "url": "https://example.org/im2.html",
                                "groups": [521, 522],
                            },
                        ],
                    }
                ),
                encoding="utf-8",
            )

            entries = load_source_entries(config_path)
            catalog = _build_catalog(entries)

            self.assertEqual(catalog["academicYears"], ["2025-2026"])
            self.assertEqual(len(catalog["programs"]), 1)
            program = catalog["programs"][0]
            self.assertEqual(program["id"], "informatica-maghiara")
            self.assertEqual(program["years"][0]["groups"], [511, 512])
            self.assertEqual(program["years"][1]["groups"], [521, 522])

    def test_build_catalog_with_detected_group_overrides(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            config_path = Path(tmp_dir) / "sources.json"
            config_path.write_text(
                json.dumps(
                    {
                        "academicYear": "2025-2026",
                        "programs": [
                            {
                                "programId": "informatica-maghiara",
                                "title": "Informatics - Hungarian track",
                                "year": 1,
                                "url": "https://example.org/im1.html",
                                "groups": [511, 512],
                            }
                        ],
                    }
                ),
                encoding="utf-8",
            )

            entries = load_source_entries(config_path)
            overrides = {
                ("2025-2026", "informatica-maghiara", 1, "https://example.org/im1.html"): [511],
            }
            catalog = _build_catalog(entries, overrides)
            program = catalog["programs"][0]
            self.assertEqual(program["years"][0]["groups"], [511])


if __name__ == "__main__":
    unittest.main()
