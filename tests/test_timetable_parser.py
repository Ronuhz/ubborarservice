from __future__ import annotations

import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

try:
    from timetable_parser import parse_timetable_html

    HAS_BS4 = True
except ModuleNotFoundError:
    HAS_BS4 = False
    parse_timetable_html = None


SAMPLE_HTML = """
<html>
  <body>
    <table>
      <tr>
        <th>Ziua</th>
        <th>Ora</th>
        <th>511</th>
        <th>512</th>
      </tr>
      <tr>
        <td rowspan="2">Luni</td>
        <td>08-10</td>
        <td>Programare (C)<br/>Prof. Ada Lovelace<br/>Sala CR1</td>
        <td>-</td>
      </tr>
      <tr>
        <td>10-12</td>
        <td>Programare (L)<br/>Asist. Alan Turing<br/>Laborator 2<br/>sapt. 1</td>
        <td>Programare (L)<br/>Asist. Grace Hopper<br/>Laborator 3<br/>sapt. 2</td>
      </tr>
      <tr>
        <td>Marti</td>
        <td>12-14</td>
        <td>Algebra (S)<br/>Conf. Emmy Noether<br/>sala 101</td>
        <td>Algebra (S)<br/>Conf. Emmy Noether<br/>sala 101</td>
      </tr>
    </table>
  </body>
</html>
"""

GROUP_SECTION_HTML = """
<html>
  <body>
    <h2>Grupa 211</h2>
    <table>
      <tr>
        <th>Ziua</th>
        <th>Orele</th>
        <th>Frecventa</th>
        <th>Sala</th>
        <th>Tipul</th>
        <th>Disciplina</th>
        <th>Cadrul didactic</th>
      </tr>
      <tr>
        <td>Luni</td>
        <td>8-10</td>
        <td>sapt. 1</td>
        <td>CR406</td>
        <td>Seminar</td>
        <td>Programare functionala</td>
        <td>Asist. John Doe</td>
      </tr>
    </table>
    <h2>Grupa 212</h2>
    <table>
      <tr>
        <th>Ziua</th>
        <th>Orele</th>
        <th>Frecventa</th>
        <th>Sala</th>
        <th>Tipul</th>
        <th>Disciplina</th>
        <th>Cadrul didactic</th>
      </tr>
      <tr>
        <td>Marti</td>
        <td>10-12</td>
        <td>sapt. 2</td>
        <td>CR1</td>
        <td>Laborator</td>
        <td>Baze de date</td>
        <td>Asist. Jane Doe</td>
      </tr>
    </table>
  </body>
</html>
"""

FORMATION_CELL_HTML = """
<html>
  <body>
    <table>
      <tr>
        <th>Ziua</th>
        <th>Ora</th>
        <th>511</th>
      </tr>
      <tr>
        <td>Luni</td>
        <td>10-12</td>
        <td>IM1<br/>Fundamentele programarii<br/>Asist. Alice Bob<br/>CR1</td>
      </tr>
    </table>
  </body>
</html>
"""

INLINE_COMPACT_HTML = """
<html>
  <body>
    <table>
      <tr>
        <th>Ziua</th>
        <th>Ora</th>
        <th>511</th>
      </tr>
      <tr>
        <td>Marti</td>
        <td>14-16</td>
        <td>sapt. 1: Programare WEB (RUFF Laura), 9/I</td>
      </tr>
    </table>
  </body>
</html>
"""


@unittest.skipUnless(HAS_BS4, "beautifulsoup4 is not installed in this environment.")
class TimetableParserTest(unittest.TestCase):
    def test_parse_expected_groups(self) -> None:
        parsed = parse_timetable_html(SAMPLE_HTML, [511, 512])

        self.assertEqual(parsed.detected_groups, [511, 512])
        self.assertIn(511, parsed.by_group)
        self.assertIn(512, parsed.by_group)

        days_511 = parsed.by_group[511]
        self.assertEqual(days_511[0]["day"], "monday")
        self.assertEqual(days_511[1]["day"], "tuesday")

        monday_entries_511 = days_511[0]["entries"]
        self.assertEqual(len(monday_entries_511), 2)
        self.assertEqual(monday_entries_511[0]["time"], "08–10")
        self.assertEqual(monday_entries_511[0]["frequency"], "weekly")
        self.assertEqual(monday_entries_511[0]["type"], "lecture")
        self.assertEqual(monday_entries_511[1]["frequency"], "week1")
        self.assertEqual(monday_entries_511[1]["type"], "lab")

        days_512 = parsed.by_group[512]
        monday_entries_512 = days_512[0]["entries"]
        self.assertEqual(len(monday_entries_512), 1)
        self.assertEqual(monday_entries_512[0]["frequency"], "week2")

    def test_parse_group_sections_layout(self) -> None:
        parsed = parse_timetable_html(GROUP_SECTION_HTML, [])

        self.assertEqual(parsed.detected_groups, [211, 212])
        self.assertEqual(parsed.by_group[211][0]["day"], "monday")
        self.assertEqual(parsed.by_group[211][0]["entries"][0]["type"], "seminar")
        self.assertEqual(parsed.by_group[211][0]["entries"][0]["frequency"], "week1")

        self.assertEqual(parsed.by_group[212][0]["day"], "tuesday")
        self.assertEqual(parsed.by_group[212][0]["entries"][0]["type"], "lab")
        self.assertEqual(parsed.by_group[212][0]["entries"][0]["frequency"], "week2")

    def test_parse_formation_line_ignores_group_marker(self) -> None:
        parsed = parse_timetable_html(FORMATION_CELL_HTML, [511])
        entry = parsed.by_group[511][0]["entries"][0]

        self.assertEqual(entry["course"], "Fundamentele programarii")
        self.assertEqual(entry["instructor"], "Asist. Alice Bob")
        self.assertEqual(entry["room"], "CR1")

    def test_parse_inline_compact_entry(self) -> None:
        parsed = parse_timetable_html(INLINE_COMPACT_HTML, [511])
        entry = parsed.by_group[511][0]["entries"][0]

        self.assertEqual(entry["course"], "Programare WEB")
        self.assertEqual(entry["instructor"], "RUFF Laura")
        self.assertEqual(entry["room"], "9/I")
        self.assertEqual(entry["frequency"], "week1")


if __name__ == "__main__":
    unittest.main()
