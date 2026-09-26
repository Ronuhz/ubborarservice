import json
from pathlib import Path
import sys
import unittest

from jsonschema import Draft202012Validator, FormatChecker

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from build_academic_calendar import build_calendar


class AcademicCalendarTest(unittest.TestCase):
    def test_published_calendar_has_all_tracks_and_valid_dates(self):
        config = json.loads((ROOT / "config/academic-calendar.json").read_text())
        payload = build_calendar(config, "2026-09-26T12:00:00Z")
        schema = json.loads((ROOT / "schemas/academic-calendar.schema.json").read_text())
        Draft202012Validator(schema, format_checker=FormatChecker()).validate(payload)

        self.assertEqual(payload["academicYear"], json.loads((ROOT / "config/sources.json").read_text())["academicYear"])
        self.assertEqual(len(payload["calendars"]), 4)
        for calendar in payload["calendars"]:
            first, second = calendar["semesters"]
            self.assertEqual(first["teachingStartsOn"], "2026-09-28")
            self.assertEqual(first["teachingEndsOn"], "2027-01-17")
            self.assertEqual(second["teachingStartsOn"], "2027-02-22")
            self.assertTrue(any(p["type"] == "vacation" for p in second["periods"]))

        by_track = {(tuple(c["languages"]), c["studyYearKind"]): c for c in payload["calendars"]}
        self.assertEqual(by_track[("ro", "en"), "nonterminal"]["semesters"][1]["teachingEndsOn"], "2027-06-06")
        self.assertEqual(by_track[("hu", "de"), "terminal"]["semesters"][1]["teachingEndsOn"], "2027-06-27")
        self.assertIn({"type": "vacation", "startDate": "2027-03-29", "endDate": "2027-04-04", "name": "Easter"}, by_track[("hu", "de"), "terminal"]["semesters"][1]["periods"])

    def test_rejects_invalid_period_dates(self):
        config = {"academicYear": "2026-2027", "sourceUrl": "https://example.org", "calendars": [{
            "languages": ["ro"], "studyYearKind": "terminal", "semesters": [{
                "semester": 1, "periods": [{"type": "teaching", "startDate": "2027-02-02", "endDate": "2027-02-01"}]
            }]
        }]}
        with self.assertRaises(ValueError):
            build_calendar(config, "2026-09-26T12:00:00Z")
