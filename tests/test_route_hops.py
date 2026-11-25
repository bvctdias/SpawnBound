import random
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "dependencias")]

from spawnbound.animation import MotionKind
from spawnbound.config import DEFAULT_CONFIG
from spawnbound.domain.coordinates import GridPos
from spawnbound.domain.generation import WorldGenerator
from spawnbound.domain.model import NEIGHBOR_DIRECTIONS, ObjectKind, SpaceKind, TileKind, WorldObject
from spawnbound.domain.pathing import PlayerNavigation
from spawnbound.domain.session import ActionCode, GameSession
from spawnbound.domain.spaces import exit_landing
from spawnbound.input import InputFrame
from spawnbound.states import HOP_PLANTED, HOP_SECONDS, GameplayState

EAST = GridPos(1, 0)


def flat_state():
    session = GameSession.create(1234, DEFAULT_CONFIG, chunk_preview_size=8)
    session.world.objects.clear()
    session.wildlife.mobs.clear()
    return GameplayState(session, DEFAULT_CONFIG)


class HopTests(unittest.TestCase):
    def test_a_route_climbs_and_drops_one_level_steps_by_itself(self):
        state = flat_state()
        session = state.session
        p = session.player.position
        for x in (1, 2):
            session.world.tile_map.add(p + GridPos(x, 0), TileKind.GRASS, elevation=x)
        path = session.navigation.route(p, (p + GridPos(2, 0),))
        self.assertEqual((p + EAST, p + GridPos(2, 0)), path)
        state._path = path
        state.step(InputFrame(), 3 * HOP_SECONDS)
        self.assertEqual(p + GridPos(2, 0), session.player.position)
        self.assertEqual(2, session.player.elevation)

    def test_the_feet_stay_planted_for_the_crouch_and_the_landing(self):
        state = flat_state()
        session = state.session
        p = session.player.position
        session.world.tile_map.add(p + EAST, TileKind.GRASS, elevation=1)
        state._path = (p + EAST,)
        state.step(InputFrame(), HOP_SECONDS * HOP_PLANTED * .8)
        self.assertEqual(MotionKind.JUMP, state.player_pose.motion)
        self.assertAlmostEqual(p.x, state.visual_position3d[0])
        state.step(InputFrame(), HOP_SECONDS * (1 - HOP_PLANTED * 1.6))
        self.assertAlmostEqual(p.x + 1, state.visual_position3d[0])
        self.assertEqual(MotionKind.JUMP, state.player_pose.motion, "still landing")

    def test_flat_walking_is_no_hop(self):
        state = flat_state()
        p = state.session.player.position
        state._path = (p + EAST, p + GridPos(2, 0))
        state.step(InputFrame(), .1)
        self.assertEqual(MotionKind.WALK, state.player_pose.motion)

    def test_space_jumps_in_place(self):
        state = flat_state()
        p = state.session.player.position
        state.step(InputFrame(jump_pressed=True), HOP_SECONDS / 2)
        self.assertEqual(MotionKind.JUMP, state.player_pose.motion)
        self.assertEqual(p, state.session.player.position)
        state.step(InputFrame(), HOP_SECONDS)
        self.assertEqual(MotionKind.IDLE, state.player_pose.motion)

    def test_a_cliff_still_stops_the_route(self):
        state = flat_state()
        session = state.session
        p = session.player.position
        session.world.tile_map.add(p + EAST, TileKind.GRASS, elevation=2)
        self.assertFalse(session.navigation.reachable(p, p + EAST))


class DockTests(unittest.TestCase):
    def test_the_dock_is_reached_on_foot_from_the_camp(self):
        for seed in [random.Random(2026 + i).randrange(2_147_483_647) for i in range(3)]:
            with self.subTest(seed=seed):
                world = WorldGenerator().generate_chunk_preview(seed, 128)
                approaches = [world.dock - d for d in NEIGHBOR_DIRECTIONS
                              if world.is_walkable(world.dock - d)
                              and world.can_reach(world.dock - d, world.dock, DEFAULT_CONFIG.max_step_height)]
                walking = PlayerNavigation(world, DEFAULT_CONFIG.max_step_height, swim=False)
                self.assertTrue(any(walking.reachable(world.spawn, cell) for cell in approaches))


class HouseExitTests(unittest.TestCase):
    def setUp(self):
        self.session = GameSession.create(1234, DEFAULT_CONFIG, chunk_preview_size=64)
        door = next(p for p in self.session.world.portals.values() if p.target_kind is SpaceKind.INTERIOR)
        self.session.player.place(self.session.world.surface_position(door.approach))
        self.session.player.facing = door.position - door.approach
        self.assertIs(ActionCode.SPACE_CHANGED, self.session.interact().code)
        self.house = self.session.world
        self.assertIs(SpaceKind.INTERIOR, self.house.space_kind)

    def stand(self, cell, facing=GridPos(0, -1)):
        self.session.world = self.house
        self.session.player.place(self.house.surface_position(cell))
        self.session.player.facing = facing

    def test_the_landing_is_two_cells_wide(self):
        landing = exit_landing(self.house)
        self.assertEqual(4, len(landing))
        self.assertEqual(2, len({cell.x for cell in landing}))

    def test_every_landing_cell_leads_out_facing_any_way(self):
        for cell in sorted(exit_landing(self.house)):
            for facing in (GridPos(0, -1), GridPos(1, 0), GridPos(-1, 0)):
                with self.subTest(cell=cell, facing=facing):
                    self.stand(cell, facing)
                    result = self.session.interact()
                    self.assertIs(ActionCode.SPACE_CHANGED, result.code)
                    self.assertIs(SpaceKind.OUTDOOR, self.session.world.space_kind)

    def test_furniture_faced_from_the_landing_opens_instead(self):
        cell = min((c for c in exit_landing(self.house) if c not in self.house.portals), key=lambda c: (c.y, c.x))
        chest = cell + GridPos(0, -1)
        self.house.objects[chest] = WorldObject.create(chest, ObjectKind.CHEST)
        self.stand(cell, GridPos(0, -1))
        self.assertIs(ActionCode.CHEST_OPENED, self.session.interact().code)
        self.assertIs(self.house, self.session.world)

    def test_the_deck_is_not_the_way_out(self):
        self.stand(self.house.spawn + GridPos(0, -3))
        self.assertIsNot(ActionCode.SPACE_CHANGED, self.session.interact().code)
        self.assertIs(self.house, self.session.world)


if __name__ == "__main__":
    unittest.main()
