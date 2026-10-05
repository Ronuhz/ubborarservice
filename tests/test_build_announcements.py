from __future__ import annotations

import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from build_announcements import _auto_failure_announcement, _build_payloads


class BuildAnnouncementsTest(unittest.TestCase):
    def test_cli_preserves_live_feed_and_publishes_translations(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            subprocess.run(
                [sys.executable, str(ROOT / "scripts/build_announcements.py"),
                 "--out", directory, "--announcements", str(ROOT / "config/announcements.json"),
                 "--status", str(Path(directory) / "missing-status.json")],
                check=True, capture_output=True,
            )
            legacy = json.loads((Path(directory) / "announcements.json").read_text())
            bilingual = json.loads((Path(directory) / "announcements-v2.json").read_text())
        self.assertEqual(legacy["version"], 1)
        self.assertEqual(bilingual["version"], 2)
        self.assertEqual(legacy["generatedAt"], bilingual["generatedAt"])
        self.assertEqual(legacy["items"], [{
            "id": "schedule-updated-2026-10-05", "title": "Orarul a fost actualizat",
            "message": "Orarul a fost modificat. Aplicația afișează deja noul orar și este la zi.",
            "severity": "info", "symbolName": "calendar",
        }])
        translated = bilingual["items"][0]
        self.assertEqual(translated["title"]["ro"], legacy["items"][0]["title"])
        self.assertEqual(translated["title"]["en"], "Timetable updated")
        self.assertEqual(translated["message"]["ro"], legacy["items"][0]["message"])
        self.assertNotIn("legacyLanguage", translated)

    def test_failure_notice_is_bilingual_with_shared_metadata(self) -> None:
        item = _auto_failure_announcement({"generatedAt": "2026-10-05T12:00:00Z", "failures": ["a", "b"]})
        legacy, bilingual = _build_payloads([item])
        self.assertIn("2 source(s)", legacy["items"][0]["message"])
        self.assertIn("2 surse", bilingual["items"][0]["message"]["ro"])
        self.assertEqual(item["startsAt"], "2026-10-05T00:00:00Z")
        self.assertEqual(item["endsAt"], "2026-10-07T00:00:00Z")
        for field in ("id", "severity", "symbolName", "startsAt", "endsAt"):
            self.assertEqual(legacy["items"][0][field], bilingual["items"][0][field])

    def test_missing_or_empty_translation_rejected(self) -> None:
        for text in ("legacy", {"en": "Title"}, {"en": "Title", "ro": " "}, {"en": "Title", "ro": 1}):
            with self.subTest(text=text), self.assertRaises(ValueError):
                _build_payloads([{"id": "notice", "title": text, "message": {"en": "Message", "ro": "Mesaj"}}])

    def test_deduplication_and_empty_feeds(self) -> None:
        item = {"id": "notice", "title": {"en": "Title", "ro": "Titlu"}, "message": {"en": "Message", "ro": "Mesaj"}}
        legacy, bilingual = _build_payloads([item, item, {"id": " "}])
        self.assertEqual(len(legacy["items"]), 1)
        self.assertEqual(len(bilingual["items"]), 1)
        for payload in _build_payloads([]):
            self.assertEqual(payload["items"], [])
        self.assertIsNone(_auto_failure_announcement({"failures": []}))


if __name__ == "__main__":
    unittest.main()
