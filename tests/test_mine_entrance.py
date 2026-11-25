import json
import math
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from spawnbound.config import DEFAULT_CONFIG
from spawnbound.domain.coordinates import GridPos
from spawnbound.domain.generation import WorldGenerator
from spawnbound.domain.model import SpaceKind
from spawnbound.domain.pathing import PlayerNavigation
from spawnbound.domain.session import GameSession
from spawnbound.domain.terrain import (
    MILL_SKIRT,
    MINE_FAR,
    MINE_NEAR,
    MINE_VIEW,
    TALL_OBJECTS,
    mill_distance,
    mill_site,
)

SEEDS = (1234, 0, 7, 1942955373)
SIZE = 128


def mine_of(world):
    caves = [p for p, portal in world.portals.items() if portal.target_kind is SpaceKind.CAVE]
    return caves


class MineEntranceTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.sessions = {seed: GameSession.create(seed, DEFAULT_CONFIG, chunk_preview_size=SIZE) for seed in SEEDS}

    def test_one_entrance_out_on_the_island(self):
        for seed, session in self.sessions.items():
            with self.subTest(seed=seed):
                world = session.world
                caves = mine_of(world)
                self.assertEqual(1, len(caves))
                mouth = caves[0]
                self.assertTrue(MINE_NEAR <= math.hypot(mouth.x - world.spawn.x, mouth.y - world.spawn.y) <= MINE_FAR)
                self.assertGreater(mill_distance(mouth, mill_site(world.spawn, SIZE)), MILL_SKIRT)

    def test_the_mouth_faces_the_camera_from_a_two_level_block(self):
        for seed, session in self.sessions.items():
            with self.subTest(seed=seed):
                world = session.world
                mouth = mine_of(world)[0]
                level = world.elevation_at(mouth)
                self.assertEqual(mouth + GridPos(1, 0), world.portals[mouth].approach)
                for dy in (-1, 0, 1):
                    self.assertEqual(level + 2, world.elevation_at(mouth + GridPos(-1, dy)))
                    self.assertEqual(level + 1, world.elevation_at(mouth + GridPos(-2, dy)))

    def test_nothing_tall_or_higher_stands_in_front_of_the_mouth(self):
        for seed, session in self.sessions.items():
            with self.subTest(seed=seed):
                world = session.world
                mouth = mine_of(world)[0]
                level = world.elevation_at(mouth)
                view = [mouth + d for d in MINE_VIEW if mouth + d in world.tile_map.tiles]
                self.assertEqual([], [q for q in view if (obj := world.objects.get(q)) is not None
                                      and obj.kind in TALL_OBJECTS])
                self.assertEqual([], [q for q in view if world.elevation_at(q) > level])

    def test_it_can_be_walked_to_entered_and_left(self):
        for seed, session in self.sessions.items():
            with self.subTest(seed=seed):
                world = session.world
                mouth = mine_of(world)[0]
                portal = world.portals[mouth]
                walker = PlayerNavigation(world, DEFAULT_CONFIG.max_step_height, swim=False)
                self.assertTrue(walker.reachable(world.spawn, portal.approach))
                session.player.place(world.surface_position(portal.approach))
                session.player.facing = GridPos(-1, 0)
                self.assertTrue(session.interact().success)
                self.assertIs(SpaceKind.CAVE, session.world.space_kind)
                exit_cell = next(iter(session.world.portals))
                session.player.place(session.world.surface_position(exit_cell))
                self.assertTrue(session.interact().success)
                self.assertIs(world, session.world)
                self.assertEqual(portal.approach, session.player.position)

    def test_small_islands_keep_the_entrance_beside_the_base(self):
        world = WorldGenerator().generate_chunk_preview(1234, 64)
        mouth = mine_of(world)[0]
        self.assertEqual(world.spawn + GridPos(7, 0), mouth)
        self.assertEqual(world.elevation_at(mouth) + 2, world.elevation_at(mouth + GridPos(-1, 0)))

    def test_the_art_pack_has_the_mouth_and_the_exit(self):
        manifest = json.loads((ROOT / "assets/native_32/manifest.json").read_text(encoding="utf-8"))
        for name in ("cave_entry", "cave_exit"):
            self.assertEqual([24, 38], manifest["sprites"][name]["pivot"])
            self.assertTrue((ROOT / "assets/native_32" / manifest["sprites"][name]["file"]).exists())


if __name__ == "__main__":
    unittest.main()
