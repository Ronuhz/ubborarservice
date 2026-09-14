from __future__ import annotations

from dataclasses import replace
from html import escape
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from timetable_parser import (
    ParseContext,
    build_audience,
    classify_formation_scope,
    detect_formation,
    parse_timetable_html,
)


CONTEXT_A = ParseContext("2025-2026", "profile-a", 1, frozenset({511, 512, 513}), frozenset({"IM1"}))
CONTEXT_B = ParseContext("2025-2026", "profile-b", 2, frozenset({721, 722, 723}), frozenset({"IE2"}))
TYPES = {"lecture": "C", "seminar": "S", "lab": "L"}
SCOPES = {"IM1": "cohort", "512": "group", "512/1": "subgroup", "AB7": "unknown", None: "unknown"}
EXPECTED = {"lecture": "cohort", "seminar": "group", "lab": "subgroup"}


def column_html(cell: str) -> str:
    return (
        '<table><tr><th>Ziua</th><th>Ora</th><th>512</th></tr>'
        f'<tr><td>Luni</td><td>10-12</td><td>{cell}</td></tr></table>'
    )


def audience_html(layout: str, class_type: str, formation: str | None) -> str:
    token = escape(formation) if formation is not None else ""
    tag = TYPES[class_type]
    if layout == "group-section":
        return (
            '<h2>Grupa 512</h2><table><tr><th>Ziua</th><th>Orele</th>'
            '<th>Frecventa</th><th>Sala</th><th>Formația</th><th>Tipul</th>'
            '<th>Disciplina</th><th>Cadrul didactic</th></tr>'
            f'<tr><td>Luni</td><td>10-12</td><td>sapt. 2</td><td>L301</td><td>{token}</td>'
            f'<td>{class_type}</td><td>Data Structures</td><td>Prof. Ada Lovelace</td></tr></table>'
        )
    if layout == "inline-prefix":
        prefix = f"gr. {token}: " if token else ""
        return column_html(f"{prefix}sapt. 2: Data Structures ({tag}) (Prof. Ada Lovelace), L301")
    prefix = f"{token}<br/>" if token else ""
    if layout == "inline-standalone":
        return column_html(f"{prefix}sapt. 2: Data Structures ({tag}) (Prof. Ada Lovelace), L301")
    return column_html(f"{prefix}Data Structures ({tag})<br/>Prof. Ada Lovelace<br/>Sala L301<br/>sapt. 2")


class AudienceClassificationTest(unittest.TestCase):
    def test_profiles_are_isolated(self) -> None:
        examples = [
            (CONTEXT_A, {"IM1": "cohort", "512": "group", "512/1": "subgroup", "512/2": "subgroup",
                         "999": "unknown", "IE2": "unknown", "unknown": "unknown", None: "unknown"}),
            (CONTEXT_B, {"IE2": "cohort", "722": "group", "722/1": "subgroup", "IM1": "unknown",
                         "512": "unknown", "512/1": "unknown"}),
        ]
        for context, cases in examples:
            for token, scope in cases.items():
                with self.subTest(profile=context.program_id, token=token):
                    self.assertEqual(classify_formation_scope(token, context), scope)

    def test_context_overrides_token_shape(self) -> None:
        numeric_cohort = replace(CONTEXT_B, cohort_formations=frozenset({"512", "cohort-2026"}))
        self.assertEqual(classify_formation_scope("512", CONTEXT_A), "group")
        self.assertEqual(classify_formation_scope("512", numeric_cohort), "cohort")
        self.assertEqual(classify_formation_scope("cohort-2026", numeric_cohort), "cohort")
        new_year = replace(CONTEXT_A, academic_year="2026-2027", known_groups=frozenset({42, 12001}))
        self.assertEqual(classify_formation_scope("512", new_year), "unknown")
        self.assertEqual(classify_formation_scope("42", new_year), "group")
        self.assertEqual(classify_formation_scope("12001/2", new_year), "subgroup")

    def test_malformed_subgroups_are_unknown(self) -> None:
        for token in ["512/", "512/x", "512/1/2", "0512", "999/1"]:
            with self.subTest(token=token):
                self.assertEqual(classify_formation_scope(token, CONTEXT_A), "unknown")

    def test_standardness_matrix_and_unknown_visibility(self) -> None:
        for class_type, expected in EXPECTED.items():
            for formation, scope in SCOPES.items():
                with self.subTest(class_type=class_type, formation=formation):
                    self.assertEqual(build_audience(formation, class_type, CONTEXT_A), {
                        "formation": formation, "scope": scope, "expectedScope": expected,
                        "isStandard": scope == "unknown" or scope == expected,
                    })

    def test_extraction_preserves_metadata(self) -> None:
        for line, token in [(" (512/1) ", "512/1"), ("subgr. 512/2: Data Structures (L)", "512/2"),
                            ("gr. 512: Data Structures (S)", "512"), ("IM1", "IM1"), ("AB7", "AB7"), ("AB", "AB"),
                            ("Formation: custom-token", "custom-token")]:
            with self.subTest(line=line):
                self.assertEqual(detect_formation([line], CONTEXT_A), token)
        for line in ["L301", "CR1", "Sala 512", "Prof. Ada Lovelace", "sapt. 2", "weekly", "Luni", "(C)", "10-12"]:
            with self.subTest(line=line):
                self.assertIsNone(detect_formation([line], CONTEXT_A))
        self.assertIsNone(detect_formation(["IM1", "512"], CONTEXT_A))


class AudienceParserTest(unittest.TestCase):
    def test_all_layouts_emit_audience_without_changing_other_fields(self) -> None:
        for layout in ["columnar", "group-section", "inline-prefix", "inline-standalone"]:
            for class_type, expected_scope in EXPECTED.items():
                for formation, scope in SCOPES.items():
                    with self.subTest(layout=layout, class_type=class_type, formation=formation):
                        parsed = parse_timetable_html(audience_html(layout, class_type, formation), [512], context=CONTEXT_A)
                        self.assertEqual(parsed.detected_groups, [512])
                        self.assertEqual(parsed.by_group[512], [{"day": "monday", "entries": [{
                            "time": "10–12", "frequency": "week2", "course": "Data Structures",
                            "type": class_type, "room": "L301", "instructor": "Prof. Ada Lovelace",
                            "audience": {"formation": formation, "scope": scope, "expectedScope": expected_scope,
                                         "isStandard": scope == "unknown" or scope == expected_scope},
                        }]}])

    def test_detected_groups_supply_context_when_configuration_is_empty(self) -> None:
        for layout in ["columnar", "group-section"]:
            with self.subTest(layout=layout):
                parsed = parse_timetable_html(audience_html(layout, "lab", "512/1"), [])
                self.assertEqual(parsed.detected_groups, [512])
                self.assertEqual(parsed.by_group[512][0]["entries"][0]["audience"]["scope"], "subgroup")

    def test_source_context_supports_nontraditional_cohort_names(self) -> None:
        for token in ["cohort-2026", "512", "L301"]:
            context = replace(CONTEXT_A, cohort_formations=frozenset({token}))
            parsed = parse_timetable_html(audience_html("columnar", "lecture", token), [512], context=context)
            entry = parsed.by_group[512][0]["entries"][0]
            self.assertEqual(entry["audience"]["scope"], "cohort")
            self.assertEqual(entry["course"], "Data Structures")
            self.assertEqual(entry["room"], "L301")

    def test_group_section_preserves_arbitrary_unknown_formation(self) -> None:
        parsed = parse_timetable_html(audience_html("group-section", "lab", "unmapped audience / A"), [512])
        self.assertEqual(parsed.by_group[512][0]["entries"][0]["audience"], {
            "formation": "unmapped audience / A", "scope": "unknown", "expectedScope": "subgroup", "isStandard": True,
        })

    def test_inline_deduplication_preserves_distinct_audiences(self) -> None:
        lines = [f"subgr. {token}: Data Structures (L) (Prof. Ada Lovelace), L301"
                 for token in ["512/1", "512/1", "512/2", "512"]]
        parsed = parse_timetable_html(column_html("<br/>".join(lines)), [512], context=CONTEXT_A)
        entries = parsed.by_group[512][0]["entries"]
        self.assertEqual([e["audience"]["formation"] for e in entries], ["512/1", "512/2", "512"])
        self.assertEqual([e["audience"]["isStandard"] for e in entries], [True, True, False])

    def test_bare_subgroup_number_is_not_inferred_from_destination_group(self) -> None:
        parsed = parse_timetable_html(column_html("sgr. 1: Data Structures (L) (Ada Lovelace), L301"), [512])
        self.assertEqual(parsed.by_group[512][0]["entries"][0]["audience"], {
            "formation": "1", "scope": "unknown", "expectedScope": "subgroup", "isStandard": True,
        })

    def test_multiline_prefix_preserves_course_and_audience(self) -> None:
        html = column_html("subgr. 512/1: Data Structures (L)<br/>Prof. Ada Lovelace<br/>Sala L301")
        parsed = parse_timetable_html(html, [512], context=CONTEXT_A)
        entry = parsed.by_group[512][0]["entries"][0]
        self.assertEqual(entry["course"], "Data Structures")
        self.assertEqual(entry["audience"], {
            "formation": "512/1", "scope": "subgroup", "expectedScope": "subgroup", "isStandard": True,
        })

    def test_unknown_cohort_without_configuration_remains_visible(self) -> None:
        for layout in ["columnar", "group-section", "inline-prefix"]:
            with self.subTest(layout=layout):
                parsed = parse_timetable_html(audience_html(layout, "seminar", "IM1"), [512])
                self.assertEqual(parsed.by_group[512][0]["entries"][0]["audience"], {
                    "formation": "IM1", "scope": "unknown", "expectedScope": "group", "isStandard": True,
                })

    def test_missing_formation_column_does_not_treat_numeric_room_as_audience(self) -> None:
        html = audience_html("group-section", "seminar", "512")
        html = html.replace("<th>Formația</th>", "").replace("<td>512</td>", "").replace("L301", "512")
        parsed = parse_timetable_html(html, [512], context=CONTEXT_A)
        entry = parsed.by_group[512][0]["entries"][0]
        self.assertEqual(entry["room"], "512")
        self.assertEqual(entry["audience"], {
            "formation": None, "scope": "unknown", "expectedScope": "group", "isStandard": True,
        })


if __name__ == "__main__":
    unittest.main()
