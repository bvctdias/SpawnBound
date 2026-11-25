from __future__ import annotations

import sys
import unittest
from collections import Counter
from pathlib import Path


SOURCE_ROOT = Path(__file__).resolve().parents[1] / "src"
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

from spawnbound.domain.coordinates import GridPos, NEIGHBOR_DIRECTIONS
from spawnbound.domain.generation import WorldGenerator, flood_fill, validate_world
from spawnbound.domain.model import PALMS, Biome, GrassVariant, ObjectKind, TileKind, TreeVariant, World


class GenerationTests(unittest.TestCase):
    def test_same_seed_creates_same_world(self) -> None:
        generator = WorldGenerator()
        self.assertEqual(generator.generate(1234).signature(), generator.generate(1234).signature())

    def test_different_seeds_vary_layout(self) -> None:
        generator = WorldGenerator()
        self.assertNotEqual(generator.generate(1234).signature(), generator.generate(5678).signature())

    def test_first_two_hundred_seeds_are_completable(self) -> None:
        generator = WorldGenerator()
        for seed in range(200):
            with self.subTest(seed=seed):
                result = validate_world(generator.generate(seed))
                self.assertTrue(result.valid, result.errors)

    def test_larger_noise_island_is_reproducible_and_permeable(self) -> None:
        generator = WorldGenerator()
        world = generator.generate_chunk_preview(seed=1234, size=128)
        self.assertEqual(16384, len(world.tile_map.tiles))
        self.assertEqual(128, world.chunk_preview_size)
        self.assertEqual(set(Biome), {tile.biome for tile in world.tile_map.tiles.values()})
        self.assertEqual(set(GrassVariant), {tile.variant for tile in world.tile_map.tiles.values()})
        kinds = Counter(tile.kind for tile in world.tile_map.tiles.values())
        self.assertEqual({TileKind.GRASS, TileKind.WATER}, set(kinds))
        self.assertGreater(kinds[TileKind.WATER], 0)
        self.assertEqual(world.signature(), generator.generate_chunk_preview(1234, 128).signature())
        self.assertTrue(world.is_walkable(world.spawn))
        self.assertTrue(world.is_walkable(world.camp))
        self.assertEqual(1.0, _walkable_reachable_fraction(world))
        outdoor_resources = {ObjectKind.CACTUS, ObjectKind.TREE, ObjectKind.ROCK, ObjectKind.BERRY_BUSH, ObjectKind.FALLEN_LOG,
                             ObjectKind.MUSHROOM}
        self.assertEqual(outdoor_resources | {ObjectKind.WINDMILL, ObjectKind.WAYSTONE, ObjectKind.DOCK},
                         {obj.kind for obj in world.objects.values()})
        pairs = [(tile.biome, world.tile_map.tiles[GridPos(pos.x + 1, pos.y)].biome)
                 for pos, tile in world.tile_map.tiles.items() if pos.x < 127]
        self.assertGreater(sum(a == b for a, b in pairs) / len(pairs), .90)
        biome_tiles = Counter(tile.biome for tile in world.tile_map.tiles.values())
        biome_trees = Counter(world.tile_map.tiles[pos].biome for pos, obj in world.objects.items()
                              if obj.kind is ObjectKind.TREE)
        self.assertGreater(biome_trees[Biome.FOREST] / biome_tiles[Biome.FOREST],
                           2 * biome_trees[Biome.MEADOW] / biome_tiles[Biome.MEADOW])

    def test_noise_islands_remain_connected_across_seeds(self) -> None:
        generator = WorldGenerator()
        for seed in range(20):
            with self.subTest(seed=seed):
                world = generator.generate_chunk_preview(seed, 64)
                blocked = {pos for pos, obj in world.objects.items() if obj.blocks_movement}
                self.assertFalse(_contains_solid_tree_square(blocked))
                self.assertEqual(1.0, _walkable_reachable_fraction(world))
                self.assertTrue(all(pos in world.tile_map.tiles for pos in world.objects))
                for pos, obj in world.objects.items():
                    biome = world.tile_map.tiles[pos].biome
                    if obj.kind is ObjectKind.TREE:
                        self.assertEqual(biome is Biome.DRY, obj.variant in PALMS)
                    if obj.kind is ObjectKind.CACTUS:
                        self.assertEqual(Biome.DRY, biome)

    def test_lakes_sit_below_every_shore_and_hold_no_objects(self) -> None:
        for seed in (1234, 0, 7):
            with self.subTest(seed=seed):
                world = WorldGenerator().generate_chunk_preview(seed, 128)
                water = {p for p, tile in world.tile_map.tiles.items() if tile.kind is TileKind.WATER}
                self.assertTrue(water)
                self.assertFalse(water & set(world.objects))
                self.assertFalse(water & set(world.portals))
                self.assertNotIn(world.spawn, water)
                self.assertNotIn(world.camp, water)
                for p in water:
                    self.assertFalse(world.is_walkable(p))
                    self.assertEqual(0, world.elevation_at(p))
                    for d in NEIGHBOR_DIRECTIONS:
                        neighbor = world.tile_map.tile_at(p + d)
                        if neighbor is not None and neighbor.kind is not TileKind.WATER:
                            self.assertGreaterEqual(neighbor.elevation, 1)
                self.assertEqual(1.0, _walkable_reachable_fraction(world))

    def test_low_wide_objects_never_overhang_higher_ground(self) -> None:
        sides = (GridPos(1, -1), GridPos(1, 0), GridPos(0, 1))
        low = (ObjectKind.ROCK, ObjectKind.BERRY_BUSH, ObjectKind.FALLEN_LOG)
        for seed in (1234, 0, 7):
            with self.subTest(seed=seed):
                world = WorldGenerator().generate_chunk_preview(seed, 128)
                for p, obj in world.objects.items():
                    if obj.kind not in low:
                        continue
                    for d in sides:
                        neighbor = world.tile_map.tile_at(p + d)
                        if neighbor is not None:
                            self.assertLessEqual(neighbor.elevation, world.elevation_at(p), (p, d))

    def test_mine_rocks_rest_on_their_platform_without_overhanging_higher_ground(self) -> None:
        from spawnbound.config import DEFAULT_CONFIG
        from spawnbound.domain.model import SpaceKind
        from spawnbound.domain.session import GameSession
        sides = (GridPos(1, -1), GridPos(1, 0), GridPos(0, 1))
        for seed in (1234, 0, 7):
            with self.subTest(seed=seed):
                session = GameSession.create(seed, DEFAULT_CONFIG, chunk_preview_size=128)
                portal = next(p for p in session.world.portals.values() if p.target_kind is SpaceKind.CAVE)
                session.player.position = portal.approach
                session.player.facing = portal.position - portal.approach
                session.interact()
                mine = session.world
                self.assertIs(SpaceKind.CAVE, mine.space_kind)
                self.assertTrue(mine.objects)
                for p, obj in mine.objects.items():
                    self.assertEqual(mine.elevation_at(p), obj.elevation)
                    for d in sides:
                        neighbor = mine.tile_map.tile_at(p + d)
                        if neighbor is not None:
                            self.assertLessEqual(neighbor.elevation, mine.elevation_at(p), (p, d))

    def test_preview_size_validation_and_small_map(self) -> None:
        with self.assertRaises(ValueError):
            WorldGenerator().generate_chunk_preview(1, 7)
        world = WorldGenerator().generate_chunk_preview(1, 8)
        self.assertEqual(64, len(world.tile_map.tiles))
        self.assertEqual(1.0, _walkable_reachable_fraction(world))


def _contains_solid_tree_square(trees: set[GridPos]) -> bool:
    return any(
        {
            GridPos(tree.x, tree.y),
            GridPos(tree.x + 1, tree.y),
            GridPos(tree.x, tree.y + 1),
            GridPos(tree.x + 1, tree.y + 1),
        }
        <= trees
        for tree in trees
    )


def _walkable_reachable_fraction(world: World) -> float:
    walkable = {
        position
        for position in world.tile_map.tiles
        if world.is_walkable(position)
    }
    return len(flood_fill(world.spawn, walkable)) / len(walkable)


if __name__ == "__main__":
    unittest.main()
