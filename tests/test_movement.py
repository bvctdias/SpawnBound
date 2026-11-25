import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from spawnbound.config import DEFAULT_CONFIG
from spawnbound.domain.coordinates import GridPos, WorldPos
from spawnbound.domain.model import ObjectKind, TileKind, WorldObject
from spawnbound.domain.movement import segment_cells, segment_allowed
from spawnbound.domain.session import GameSession


class ContinuousMovementTests(unittest.TestCase):
    def setUp(self):
        self.session = GameSession.create(1234, DEFAULT_CONFIG, chunk_preview_size=8)
        self.session.world.objects.clear()
        self.session.world.strict_diagonals = True
        self.p = self.session.player.position

    def test_boundary_ownership_matches_picking_including_negative_coordinates(self):
        self.assertEqual(GridPos(3, -1), WorldPos(2.5, -1.5, 0).grid)

    def test_large_delta_checks_every_cell_not_only_endpoint(self):
        blocker = self.p + GridPos(1, 0)
        self.session.world.objects[blocker] = WorldObject.create(blocker, ObjectKind.ROCK)
        before = self.session.player.position3d
        self.assertFalse(self.session.move_continuous(self.p.x + 3.25, self.p.y).success)
        self.assertEqual(before, self.session.player.position3d)

    def test_trace_checks_short_crossings_between_two_boundaries(self):
        self.assertIn(GridPos(1, 0), segment_cells(WorldPos(0, 0, 0), WorldPos(2, 1.9999, 0)))

    def test_diagonal_cannot_cut_blocked_corner(self):
        side = self.p + GridPos(1, 0)
        self.session.world.objects[side] = WorldObject.create(side, ObjectKind.ROCK)
        self.assertFalse(self.session.move_continuous(self.p.x + 1, self.p.y + 1).success)

    def test_continuous_steps_allow_one_level_but_block_cliff(self):
        next_cell = self.p + GridPos(1, 0)
        self.session.world.tile_map.add(next_cell, TileKind.GRASS, elevation=1)
        self.assertTrue(self.session.move_continuous(self.p.x + .75, self.p.y + .125).success)
        self.assertEqual(1, self.session.player.position3d.z)
        self.assertTrue(self.session.move_continuous(self.p.x, self.p.y).success)
        self.session.world.tile_map.add(next_cell, TileKind.GRASS, elevation=3)
        self.assertFalse(self.session.move_continuous(self.p.x + .75, self.p.y).success)

    def test_cannot_move_into_void_or_smooth_across_a_step(self):
        before = self.session.player.position3d
        self.assertFalse(self.session.move_continuous(-1, -1).success)
        self.assertEqual(before, self.session.player.position3d)
        next_cell = self.p + GridPos(1, 0)
        self.session.world.tile_map.add(next_cell, TileKind.GRASS, elevation=1)
        target = self.session.world.surface_position(next_cell)
        self.assertFalse(segment_allowed(self.session.world, before, target, flat=True))
