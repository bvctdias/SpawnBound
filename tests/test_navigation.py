from __future__ import annotations

import sys
import unittest
from pathlib import Path


SOURCE_ROOT = Path(__file__).resolve().parents[1] / "src"
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

from spawnbound.domain.coordinates import GridPos
from spawnbound.domain.navigation import find_path, find_path_to_any


class NavigationTests(unittest.TestCase):
    def test_multi_goal_search_matches_minimum_weighted_single_goal_cost(self):
        tiles = {GridPos(x, y) for x in range(12) for y in range(12)}
        blocked = {GridPos(4, y) for y in range(10)}
        walkable = tiles - blocked
        start = GridPos(1, 4)
        goals = (GridPos(8, 4), GridPos(3, 9), GridPos(2, 10))
        def cost(path):
            previous = start
            result = 0
            for p in path:
                d = p - previous
                result += 14 if d.x and d.y else 10
                previous = p
            return result
        route = find_path_to_any(start, goals, walkable.__contains__)
        self.assertIn(route[-1], goals)
        self.assertEqual(min(cost(find_path(start, p, walkable.__contains__)) for p in goals), cost(route))

    def test_multi_goal_search_distinguishes_here_from_unreachable(self):
        start = GridPos(0, 0)
        isolated = GridPos(2, 2)
        valid = {start, isolated}
        self.assertEqual((), find_path_to_any(start, (start, isolated), valid.__contains__))
        self.assertIsNone(find_path_to_any(start, (isolated,), valid.__contains__))

    def test_straight_destination_does_not_create_a_zigzag(self) -> None:
        start = GridPos(0, 0)
        destination = GridPos(4, 0)

        path = find_path(start, destination, lambda _position: True)

        self.assertEqual(
            tuple(GridPos(x, 0) for x in range(1, 5)),
            path,
        )

    def test_astar_routes_around_blocked_cells(self) -> None:
        tiles = {GridPos(x, y) for x in range(5) for y in range(5)}
        blocked = {GridPos(1, 1), GridPos(2, 2), GridPos(3, 3)}
        walkable = tiles - blocked

        path = find_path(GridPos(0, 0), GridPos(4, 4), walkable.__contains__)

        self.assertTrue(path)
        self.assertEqual(GridPos(4, 4), path[-1])
        self.assertTrue(all(position in walkable for position in path))
        previous = GridPos(0, 0)
        for position in path:
            self.assertLessEqual(max(abs(position.x - previous.x), abs(position.y - previous.y)), 1)
            previous = position

    def test_astar_returns_no_path_for_an_isolated_destination(self) -> None:
        walkable = {GridPos(0, 0), GridPos(2, 2)}

        self.assertEqual(
            (),
            find_path(GridPos(0, 0), GridPos(2, 2), walkable.__contains__),
        )


if __name__ == "__main__":
    unittest.main()
