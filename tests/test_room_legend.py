from __future__ import annotations

import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

try:
    from room_legend import build_room_lookup, parse_room_legend_html, resolve_room_address

    HAS_BS4 = True
except ModuleNotFoundError:
    HAS_BS4 = False
    build_room_lookup = None
    parse_room_legend_html = None
    resolve_room_address = None


LEGEND_HTML = """
<html>
  <body>
    <table>
      <tr><th>Sala</th><th>Adresa</th></tr>
      <tr><td>CR1</td><td>Str. Mihail Kogalniceanu nr. 1</td></tr>
      <tr><td>9/I</td><td>Str. Universitatii nr. 9</td></tr>
    </table>
  </body>
</html>
"""


@unittest.skipUnless(HAS_BS4, "beautifulsoup4 is not installed in this environment.")
class RoomLegendTest(unittest.TestCase):
    def test_parse_and_lookup(self) -> None:
        legend = parse_room_legend_html(LEGEND_HTML)
        lookup = build_room_lookup(legend)

        self.assertEqual(resolve_room_address("CR1", lookup), "Str. Mihail Kogalniceanu nr. 1")
        self.assertEqual(resolve_room_address("Sala CR1", lookup), "Str. Mihail Kogalniceanu nr. 1")
        self.assertEqual(resolve_room_address("9/I", lookup), "Str. Universitatii nr. 9")
        self.assertIsNone(resolve_room_address("UNKNOWN", lookup))


if __name__ == "__main__":
    unittest.main()
