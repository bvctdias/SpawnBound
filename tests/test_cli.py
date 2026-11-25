from __future__ import annotations

import sys
import unittest
from pathlib import Path


SOURCE_ROOT = Path(__file__).resolve().parents[1] / "src"
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

from spawnbound.cli import ISLAND_PREVIEW_SIZE, build_parser


class CliTests(unittest.TestCase):
    def test_chunk_preview_is_the_default_map(self) -> None:
        self.assertTrue(build_parser().parse_args([]).chunk_preview)
        self.assertEqual(128, ISLAND_PREVIEW_SIZE)

    def test_previous_vertical_slice_remains_available(self) -> None:
        self.assertFalse(build_parser().parse_args(["--prototype-map"]).chunk_preview)


if __name__ == "__main__":
    unittest.main()
