import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from spawnbound.config import DEFAULT_CONFIG
from spawnbound.domain.coordinates import GridPos
from spawnbound.domain.generation import WorldGenerator
from spawnbound.domain.model import Biome, ObjectKind, TileKind
from spawnbound.domain.pathing import PlayerNavigation
from spawnbound.domain.pathing import PlayerNavigation
from spawnbound.domain.session import GameSession

SEEDS = (1234, 0, 7, 99, 952265258, 1995926428)
SIZE = 128


class IslandRuleTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.islands = {seed: GameSession.create(seed, DEFAULT_CONFIG, chunk_preview_size=SIZE) for seed in SEEDS}

    def test_the_same_seed_builds_the_same_island(self):
        again = WorldGenerator().generate_chunk_preview(SEEDS[0], SIZE)
        self.assertEqual(self.islands[SEEDS[0]].world.signature(), again.signature())

    def test_all_dry_ground_is_one_walkable_region(self):
        for seed, session in self.islands.items():
            with self.subTest(seed=seed):
                world = session.world
                walker = PlayerNavigation(world, DEFAULT_CONFIG.max_step_height, swim=False)
                ground = [p for p in world.tile_map.tiles if world.is_walkable(p)]
                self.assertTrue(all(walker.reachable(world.spawn, p) for p in ground))
                self.assertTrue(world.is_walkable(world.camp))
                for portal in world.portals.values():
                    self.assertTrue(walker.reachable(world.spawn, portal.approach), portal.portal_id)

    def test_water_stays_within_its_share_of_the_island(self):
        for seed, session in self.islands.items():
            with self.subTest(seed=seed):
                world = session.world
                tiles = world.tile_map.tiles
                water = {p for p, t in tiles.items() if t.kind is TileKind.WATER}
                self.assertGreater(len(water - world.sea_cells) / len(tiles), .02)
                self.assertLessEqual(len(water - world.sea_cells) / len(tiles), .12)
                self.assertLess(len(world.sea_cells) / len(tiles), .12)
                self.assertTrue(world.sea_cells <= water)

    def test_the_base_is_a_flat_meadow_clearing_in_the_centre(self):
        for seed, session in self.islands.items():
            with self.subTest(seed=seed):
                world = session.world
                self.assertEqual(GridPos(SIZE // 2, SIZE // 2), world.spawn)
                core = [p for p in world.tile_map.tiles
                        if (p.x - world.spawn.x) ** 2 + (p.y - world.spawn.y) ** 2 <= 36]
                self.assertEqual({world.elevation_at(world.spawn)}, {world.elevation_at(p) for p in core})
                self.assertTrue(all(world.tile_map.tiles[p].biome is Biome.MEADOW for p in core))
                trees = [p for p, o in world.objects.items() if o.kind is ObjectKind.TREE
                         and (p.x - world.spawn.x) ** 2 + (p.y - world.spawn.y) ** 2 <= 64]
                self.assertEqual([], trees)

    def test_forests_leave_room_to_see_and_walk(self):
        for seed, session in self.islands.items():
            with self.subTest(seed=seed):
                world = session.world
                trees = {p for p, o in world.objects.items() if o.kind is ObjectKind.TREE}
                densest = max(sum(GridPos(x + dx, y + dy) in trees for dx in range(-4, 5) for dy in range(-4, 5))
                              for x in range(4, SIZE - 4, 2) for y in range(4, SIZE - 4, 2))
                self.assertLessEqual(densest, 81 // 3)

    def test_relief_follows_the_height_profile(self):
        for seed, session in self.islands.items():
            with self.subTest(seed=seed):
                world = session.world
                land = [t.elevation for t in world.tile_map.tiles.values() if t.kind is not TileKind.WATER]
                self.assertGreaterEqual(min(land), 1)
                self.assertGreaterEqual(max(land), 4)
                border = [GridPos(a, b) for a in range(SIZE) for b in (0, SIZE - 1)]
                self.assertTrue(any(p in world.sea_cells for p in border))
                self.assertTrue(any(p not in world.sea_cells for p in border))

    def test_every_island_has_a_river_mouth_the_swimmer_can_reach(self):
        for seed, session in self.islands.items():
            with self.subTest(seed=seed):
                world = session.world
                navigation = PlayerNavigation(world, 1)
                mouth = world.river_mouth
                self.assertIsNotNone(mouth)
                self.assertTrue(mouth.x in (0, SIZE - 1) or mouth.y in (0, SIZE - 1))
                self.assertIn(mouth, world.river_cells)
                self.assertTrue(all(world.tile_map.kind_at(p) is TileKind.WATER for p in world.river_cells))
                self.assertTrue(navigation.reachable(world.spawn, mouth))
                sea = next(mouth + d for d in (GridPos(1, 0), GridPos(-1, 0), GridPos(0, 1), GridPos(0, -1))
                           if mouth + d not in world.tile_map.tiles)
                self.assertTrue(navigation.reachable(world.spawn, sea))

    def test_rivers_follow_a_noise_band_down_to_the_sea(self):
        for seed, session in self.islands.items():
            with self.subTest(seed=seed):
                world = session.world
                rivers = world.river_cells
                self.assertGreater(len(rivers), 28)
                self.assertLessEqual(len(rivers) / len(world.tile_map.tiles), .04)
                self.assertFalse(rivers & world.sea_cells)
                xs, ys = {p.x for p in rivers}, {p.y for p in rivers}
                self.assertGreater(min(len(xs), len(ys)), 6)

    def test_fish_shelters_open_onto_clear_shallow_water(self):
        for seed, session in self.islands.items():
            with self.subTest(seed=seed):
                world = session.world
                navigation = PlayerNavigation(world, 1)
                refuges = world.fish_refuges
                self.assertTrue(set(refuges) & world.river_cells)
                for home, lane in refuges.items():
                    for step in range(4):
                        tile = world.tile_map.tile_at(GridPos(home.x + lane.x * step, home.y + lane.y * step))
                        self.assertIs(TileKind.WATER, tile.kind)
                        self.assertFalse(tile.deep_water)
                    self.assertTrue(any(navigation.reachable(world.spawn, GridPos(home.x + dx, home.y + dy))
                                        for dx in range(-6, 7) for dy in range(-6, 7) if dx * dx + dy * dy <= 36))


if __name__ == "__main__":
    unittest.main()
