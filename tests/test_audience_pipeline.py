from __future__ import annotations

import argparse
from copy import deepcopy
import json
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import Mock, patch

from jsonschema import Draft202012Validator, FormatChecker, ValidationError

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import generate_sources
from pipeline_utils import SourceEntry, VERSION, load_source_entries
from scrape import _run_scrape, _timetable_path, _write_empty_fallback, _write_group_files
from test_audience import SCOPES, TYPES, audience_html


SOURCE = SourceEntry("2025-2026", "profile-a", "Profile A", 1, "https://example.org/source.html", [512], ("IM1",))


class AudiencePipelineTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        schema = json.loads((ROOT / "schemas/timetable.schema.json").read_text())
        Draft202012Validator.check_schema(schema)
        cls.validator = Draft202012Validator(schema, format_checker=FormatChecker())

    def test_scrape_writes_valid_v2_payloads_with_room_enrichment(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            for layout in ["columnar", "group-section", "inline-prefix", "inline-standalone"]:
                for class_type in TYPES:
                    for formation in SCOPES:
                        with self.subTest(layout=layout, class_type=class_type, formation=formation):
                            session = Mock()
                            session.get.return_value.text = audience_html(layout, class_type, formation)
                            session.get.return_value.headers = {"Last-Modified": "Mon, 14 Sep 2026 10:00:00 GMT"}
                            parsed, updated = _run_scrape(SOURCE, 30, session)
                            stats = _write_group_files(Path(tmp), SOURCE, parsed, "2026-09-14T12:00:00Z", updated,
                                                       {"L301": "Example Street 1"})
                            self.assertEqual(stats, {"written": 1, "empty": 0, "groupsWritten": [512]})
                            payload = json.loads(_timetable_path(Path(tmp), SOURCE, 512).read_text())
                            self.validator.validate(payload)
                            self.assertEqual(payload["version"], 2)
                            self.assertEqual(payload["lastUpdatedAtSource"], "2026-09-14")
                            entry = payload["days"][0]["entries"][0]
                            self.assertEqual(entry["audience"]["scope"], SCOPES[formation])
                            self.assertEqual(entry["roomAddress"], "Example Street 1")
                            self.assertNotIn("roomAddress", parsed.by_group[512][0]["entries"][0])

    def test_empty_fallback_is_v2_and_other_payload_versions_stay_v1(self) -> None:
        with tempfile.TemporaryDirectory() as tmp:
            _write_empty_fallback(Path(tmp), SOURCE, 512, "2026-09-14T12:00:00Z")
            payload = json.loads(_timetable_path(Path(tmp), SOURCE, 512).read_text())
            self.validator.validate(payload)
            self.assertEqual(payload["version"], 2)
            self.assertEqual(payload["days"], [])
            self.assertEqual(VERSION, 1)

    def test_schema_requires_complete_strict_audience(self) -> None:
        entry_schema = self.validator.schema["properties"]["days"]["items"]["properties"]["entries"]["items"]
        validator = Draft202012Validator(entry_schema)
        valid = {"time": "10–12", "course": "Data Structures", "type": "lab", "frequency": "weekly",
                 "room": "L301", "instructor": "Ada Lovelace", "audience": {
                     "formation": None, "scope": "unknown", "expectedScope": "subgroup", "isStandard": True}}
        validator.validate(valid)
        missing = deepcopy(valid)
        del missing["audience"]
        with self.assertRaises(ValidationError):
            validator.validate(missing)
        for field in valid["audience"]:
            missing = deepcopy(valid)
            del missing["audience"][field]
            with self.subTest(missing=field), self.assertRaises(ValidationError):
                validator.validate(missing)
        for field, value in [("formation", 512), ("scope", "retake"), ("expectedScope", "unknown"),
                             ("isStandard", None), ("isRetake", True)]:
            invalid = deepcopy(valid)
            invalid["audience"][field] = value
            with self.subTest(field=field), self.assertRaises(ValidationError):
                validator.validate(invalid)


class AudienceSourceConfigTest(unittest.TestCase):
    def load(self, payload):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "sources.json"
            path.write_text(json.dumps(payload))
            return load_source_entries(path)

    def test_configuration_is_scoped_merged_and_normalized(self) -> None:
        base = {"programId": "a", "year": 1, "url": "https://example.org/a", "groups": [511]}
        entries = self.load({"academicYear": "2025-2026", "sources": [
            dict(base, cohortFormations=[" IM1 ", "IM1"]),
            dict(base, groups=[512], cohortFormations=["IM1-alt"]),
            dict(base, programId="b", cohortFormations=["IE2"]),
            dict(base, year=2, cohortFormations=["IM2"]),
        ], "academicYears": [{"academicYear": "2026-2027", "programs": [base]}]})
        self.assertEqual(entries[0].groups, [511, 512])
        self.assertEqual(entries[0].cohort_formations, ("IM1", "IM1-alt"))
        self.assertEqual([e.cohort_formations for e in entries[1:]], [("IM2",), ("IE2",), ()])

    def test_configuration_rejects_invalid_cohort_values(self) -> None:
        for value in [None, "IM1", [512], [""], ["  "], [True]]:
            with self.subTest(value=value), self.assertRaisesRegex(ValueError, "cohortFormations"):
                self.load({"academicYear": "2025-2026", "sources": [{
                    "programId": "a", "year": 1, "url": "https://example.org/a", "cohortFormations": value}]})

    def test_discovery_preserves_only_same_source_year_metadata(self) -> None:
        for academic_year, expected in [("2025-2026", ["IM1"]), ("2026-2027", [])]:
            with self.subTest(academic_year=academic_year), tempfile.TemporaryDirectory() as tmp:
                path = Path(tmp) / "sources.json"
                path.write_text(json.dumps({"academicYear": "2025-2026", "programs": [{
                    "programId": "profile-a", "year": 1, "url": SOURCE.url, "cohortFormations": ["IM1"]}]}))
                args = argparse.Namespace(out=str(path), academic_year=academic_year, program_map=None,
                                          index_url="https://example.org/index.html", timeout=30,
                                          include_master=False, skip_group_detection=True)
                with patch.object(generate_sources, "_parse_args", return_value=args), \
                     patch.object(generate_sources.requests, "Session"), \
                     patch.object(generate_sources, "_collect_rows", return_value=[{
                         "title": "Profile A", "year": 1, "url": SOURCE.url}]), \
                     patch("builtins.print"):
                    self.assertEqual(generate_sources.main(), 0)
                self.assertEqual(json.loads(path.read_text())["programs"][0]["cohortFormations"], expected)


if __name__ == "__main__":
    unittest.main()
