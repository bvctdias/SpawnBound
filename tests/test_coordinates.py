from __future__ import annotations

import sys
import unittest
from pathlib import Path


SOURCE_ROOT = Path(__file__).resolve().parents[1] / "src"
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

from spawnbound.domain.coordinates import (
    GridPos,
    grid_to_screen,
    screen_to_grid,
    screen_to_grid_cell,
)


class CoordinateTests(unittest.TestCase):
    def test_projection_round_trip(self) -> None:
        for position in (GridPos(0, 0), GridPos(3, -2), GridPos(-7, 5), GridPos(12, 9)):
            screen_x, screen_y = grid_to_screen(position, tile_width=64, tile_height=32)
            grid_x, grid_y = screen_to_grid(screen_x, screen_y, tile_width=64, tile_height=32)
            self.assertAlmostEqual(position.x, grid_x)
            self.assertAlmostEqual(position.y, grid_y)

    def test_click_selects_the_isometric_diamond(self) -> None:
        center_x, center_y = grid_to_screen(GridPos(4, 7), tile_width=64, tile_height=32)

        for offset in ((0, 0), (31, 0), (-31, 0), (0, 15), (0, -15)):
            with self.subTest(offset=offset):
                self.assertEqual(
                    GridPos(4, 7),
                    screen_to_grid_cell(
                        center_x + offset[0],
                        center_y + offset[1],
                        tile_width=64,
                        tile_height=32,
                    ),
                )

    def test_click_beyond_the_right_edge_selects_the_neighbor(self) -> None:
        center_x, center_y = grid_to_screen(GridPos(4, 7), tile_width=64, tile_height=32)

        self.assertEqual(
            GridPos(5, 6),
            screen_to_grid_cell(center_x + 33, center_y, tile_width=64, tile_height=32),
        )


if __name__ == "__main__":
    unittest.main()
