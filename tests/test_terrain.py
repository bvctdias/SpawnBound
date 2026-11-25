from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from spawnbound.config import GameConfig
from spawnbound.domain.coordinates import GridPos
from spawnbound.domain.model import ObjectKind, TileKind, WorldObject
from spawnbound.domain.navigation import find_path
from spawnbound.domain.session import GameSession
from spawnbound.domain.terrain import reachable_surface
from spawnbound.input import InputFrame
from spawnbound.states import HOP_SECONDS, GameplayState
from spawnbound.view import camera_origin, pick_world_point, screen_center, terrain_polygons


DEFAULT_CONFIG = GameConfig(camera_zoom=1)


class TerrainTests(unittest.TestCase):
    def test_clicking_visible_side_selects_top_without_bypassing_cliffs(self):
        for height in (1, 3):
            self.setUp()
            p = self.session.player.position
            target = p + GridPos(1, 0)
            self.session.world.tile_map.add(target, TileKind.GRASS, elevation=height)
            state = GameplayState(self.session, DEFAULT_CONFIG)
            origin = camera_origin(self.session, DEFAULT_CONFIG, state.visual_position3d)
            face = terrain_polygons(self.session.world, target, origin, DEFAULT_CONFIG)[1]
            click = tuple(sum(point[axis] for point in face) / len(face) for axis in (0, 1))
            hit = pick_world_point(self.session, click, origin, DEFAULT_CONFIG)
            self.assertEqual(target, hit.position)
            self.assertFalse(hit.surface)
            state.step(InputFrame(destination_click=click), 0)
            state.step(InputFrame(), HOP_SECONDS)
            self.assertEqual(target if height == 1 else p, self.session.player.position)

    def setUp(self):
        self.session = GameSession.create(1234, DEFAULT_CONFIG, chunk_preview_size=8)
        self.session.world.objects.clear()
        self.session.world.strict_diagonals = True

    def test_automatic_up_down_steps_and_logical_z(self):
        p = self.session.player.position
        target = p + GridPos(1, 0)
        self.session.world.tile_map.add(target, TileKind.GRASS, elevation=1)
        self.assertTrue(self.session.move(GridPos(1, 0)).success)
        self.assertEqual(1, self.session.player.position3d.z)
        self.assertTrue(self.session.move(GridPos(-1, 0)).success)
        self.assertEqual(0, self.session.player.position3d.z)

    def test_cliff_blocks_both_astar_and_actual_movement(self):
        p = self.session.player.position
        target = p + GridPos(1, 0)
        self.session.world.tile_map.add(target, TileKind.GRASS, elevation=3)
        self.assertFalse(self.session.move(GridPos(1, 0)).success)
        self.assertEqual((), find_path(p, target, self.session.world.is_walkable, self.session.can_step))
        self.assertEqual(p, self.session.player.position)

    def test_diagonal_cannot_cut_solid_corners(self):
        p = self.session.player.position
        blocker = p + GridPos(1, 0)
        self.session.world.objects[blocker] = WorldObject.create(blocker, ObjectKind.ROCK)
        self.assertFalse(self.session.can_step(p, p + GridPos(1, 1)))
        path = find_path(p, p + GridPos(1, 1), self.session.world.is_walkable, self.session.can_step)
        self.assertTrue(path)
        self.assertGreater(len(path), 1)

    def test_click_and_visual_interpolation_use_height(self):
        p = self.session.player.position
        target = p + GridPos(1, 0)
        self.session.world.tile_map.add(target, TileKind.GRASS, elevation=1)
        state = GameplayState(self.session, DEFAULT_CONFIG)
        origin = camera_origin(self.session, DEFAULT_CONFIG, state.visual_position3d)
        click = screen_center(self.session.world.surface_position(target), origin, DEFAULT_CONFIG)
        self.assertEqual(target, pick_world_point(self.session, click, origin, DEFAULT_CONFIG).position)
        state.step(InputFrame(destination_click=click), 0)
        state.step(InputFrame(), HOP_SECONDS / 2)
        self.assertAlmostEqual(.5, state.visual_position3d[2])
        self.assertAlmostEqual(p.x + .5, state.visual_position3d[0])
        state.step(InputFrame(), HOP_SECONDS / 2)
        self.assertEqual(1, state.visual_position3d[2])

    def test_resources_on_unreachable_heights_cannot_be_hit(self):
        target = self.session.player.position + GridPos(1, 0)
        self.session.world.tile_map.add(target, TileKind.GRASS, elevation=3)
        self.session.world.objects[target] = WorldObject.create(target, ObjectKind.ROCK, elevation=3)
        self.assertFalse(self.session.primary_action(target).success)
        self.assertEqual(100, self.session.player.energy)

    def test_generated_relief_and_portals_are_reachable_with_real_step_rule(self):
        for seed in range(8):
            with self.subTest(seed=seed):
                session = GameSession.create(seed, DEFAULT_CONFIG, chunk_preview_size=64)
                world = session.world
                reachable = reachable_surface(world)
                walkable = {p for p in world.tile_map.tiles if world.is_walkable(p)}
                self.assertEqual(walkable, reachable)
                self.assertGreater(len({tile.elevation for tile in world.tile_map.tiles.values()}), 1)
                for portal in world.portals.values():
                    self.assertIn(portal.approach, reachable)
                for obj in world.objects.values():
                    self.assertEqual(world.elevation_at(obj.position), obj.position3d.z)
