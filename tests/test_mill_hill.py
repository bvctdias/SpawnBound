import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from spawnbound.config import DEFAULT_CONFIG
from spawnbound.domain.coordinates import EAST
from spawnbound.domain.generation import WorldGenerator
from spawnbound.domain.model import Biome, ObjectKind, TileKind
from spawnbound.domain.pathing import PlayerNavigation
from spawnbound.domain.session import ActionCode, GameSession
from spawnbound.domain.terrain import (
    MILL_FOOT,
    MILL_RISE,
    MILL_SKIRT,
    MILL_TOP,
    mill_distance,
    mill_rise,
    mill_site,
)

SEEDS = (1234, 0, 99, 1097127993)
SIZE = 128


class MillHillTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.islands = {seed: GameSession.create(seed, DEFAULT_CONFIG, chunk_preview_size=SIZE).world
                       for seed in SEEDS}

    def hill(self, world, reach=MILL_FOOT):
        site = mill_site(world.spawn, SIZE)
        return site, [p for p in world.tile_map.tiles if mill_distance(p, site) <= reach]

    def test_terraces_step_one_level_up_to_a_flat_top(self):
        self.assertEqual([3, 3, 2, 2, 1, 1, 0], [mill_rise(d) for d in (0, MILL_TOP, 4, 5.5, 6, 7.5, 7.6)])
        for seed, world in self.islands.items():
            with self.subTest(seed=seed):
                site, cells = self.hill(world)
                base = world.elevation_at(world.spawn)
                self.assertEqual(base + MILL_RISE, world.elevation_at(site))
                for p in cells:
                    self.assertEqual(base + mill_rise(mill_distance(p, site)), world.elevation_at(p), p)
                    tile = world.tile_map.tiles[p]
                    self.assertIs(TileKind.GRASS, tile.kind)
                    self.assertIs(Biome.MEADOW, tile.biome)

    def test_the_windmill_stands_alone_with_walkable_ground_around_it(self):
        for seed, world in self.islands.items():
            with self.subTest(seed=seed):
                site, _cells = self.hill(world)
                self.assertEqual([site], [p for p in world.objects if mill_distance(p, site) <= MILL_FOOT + 1])
                self.assertIs(world.objects[site].kind, ObjectKind.WINDMILL)
                self.assertEqual(world.elevation_at(site), world.objects[site].elevation)
                self.assertFalse(world.is_walkable(site))
                walker = PlayerNavigation(world, DEFAULT_CONFIG.max_step_height, swim=False)
                top = [p for p in world.tile_map.tiles if mill_distance(p, site) <= MILL_TOP]
                self.assertTrue(all(walker.reachable(world.spawn, p) for p in top if p != site))
                self.assertFalse(set(top) & world.river_cells)

    def test_it_stands_above_the_base_on_screen_clear_of_the_entrances(self):
        for seed, world in self.islands.items():
            with self.subTest(seed=seed):
                site = mill_site(world.spawn, SIZE)
                self.assertEqual(site.x - site.y, world.spawn.x - world.spawn.y)
                self.assertLess(site.x + site.y, world.spawn.x + world.spawn.y)
                for spot in (world.camp, *world.portals):
                    self.assertGreater(mill_distance(spot, site), MILL_SKIRT)

    def test_small_islands_keep_only_the_clearing(self):
        world = WorldGenerator().generate_chunk_preview(1234, 64)
        self.assertIsNone(mill_site(world.spawn, 64))
        self.assertEqual(float("inf"), mill_distance(world.spawn, None))

    def test_repair_only_spends_the_full_recipe_once(self):
        game = GameSession.create(7, DEFAULT_CONFIG, chunk_preview_size=96)
        site = mill_site(game.world.spawn, 96)
        game.player.place(game.world.surface_position(site - EAST))
        game.player.facing = EAST
        mill = game.world.objects[site]
        bag = game.player.inventory
        bag.add("wood", 12)
        bag.add("stone", 4)
        self.assertEqual(ActionCode.MISSING_MATERIALS, game.interact().code)
        self.assertEqual((12, 4), (bag.quantity("wood"), bag.quantity("stone")))
        self.assertNotEqual("restored", mill.variant)
        bag.add("stone", 2)
        self.assertEqual(ActionCode.WINDMILL_REPAIRED, game.interact().code)
        self.assertEqual("restored", mill.variant)
        self.assertFalse(game.interact().success)
        self.assertEqual((2, 1), (bag.quantity("wood"), bag.quantity("stone")))


if __name__ == "__main__":
    unittest.main()
