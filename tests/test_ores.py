import os
import sys
import unittest
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "dependencias")]
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame

from spawnbound.config import DEFAULT_CONFIG
from spawnbound.domain.coordinates import NEIGHBOR_DIRECTIONS
from spawnbound.domain.model import ORE_YIELDS, ObjectKind, SpaceKind, TileKind
from spawnbound.domain.session import ActionCode, GameSession
from spawnbound.domain.inventory import Stack
from spawnbound.domain.spaces import COAL_TO, COPPER_FROM, QUARTZ_FROM, ore_variant, walking_depth
from spawnbound.domain.tools import ORE_TIERS, PICKAXES, ToolTier
from spawnbound.item_icons import ITEMS, icon

SEEDS = (1234, 7, 99, 952265258)


def mine_of(seed):
    session = GameSession.create(seed, DEFAULT_CONFIG, chunk_preview_size=128)
    portal = next(p for p in session.world.portals.values() if p.target_kind is SpaceKind.CAVE)
    cave, _ = session.spaces.resolve(session.world, portal)
    return session, cave


class OreTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.mines = {seed: mine_of(seed) for seed in SEEDS}

    def test_rarer_ores_need_more_depth(self):
        rolls = [i / 200 for i in range(200)]
        for depth in (0, .1, COPPER_FROM):
            self.assertEqual({"cave_stone", "coal_ore"}, {ore_variant(depth, r) for r in rolls})
        self.assertNotIn("coal_ore", {ore_variant(COAL_TO, r) for r in rolls})
        self.assertNotIn("quartz_ore", {ore_variant(QUARTZ_FROM, r) for r in rolls})
        shares = [Counter(ore_variant(d / 10, r) for r in rolls) for d in range(11)]
        stone = [s["cave_stone"] for s in shares]
        self.assertEqual(stone, sorted(stone, reverse=True))
        self.assertGreater(shares[10]["quartz_ore"], 0)
        self.assertGreater(shares[10]["copper_ore"], 0)

    def test_generated_mines_place_ores_by_walking_distance_from_the_entrance(self):
        counts = Counter()
        for seed, (_, cave) in self.mines.items():
            with self.subTest(seed=seed):
                floors = {p for p, t in cave.tile_map.tiles.items() if t.kind is TileKind.CAVE_FLOOR}
                depth = walking_depth(floors, cave.spawn)
                self.assertEqual(0, depth[cave.spawn])
                self.assertEqual(1, max(depth.values()))
                for p, obj in cave.objects.items():
                    if obj.kind is not ObjectKind.ROCK:
                        continue
                    counts[obj.variant] += 1
                    if obj.variant == "copper_ore":
                        self.assertGreater(depth[p], COPPER_FROM)
                    elif obj.variant == "quartz_ore":
                        self.assertGreater(depth[p], QUARTZ_FROM)
                    elif obj.variant == "coal_ore":
                        self.assertLess(depth[p], COAL_TO)
                    else:
                        self.assertEqual("cave_stone", obj.variant)
        self.assertGreater(counts["copper_ore"], 0)
        self.assertGreater(counts["quartz_ore"], 0)
        self.assertGreater(counts["coal_ore"], 0)
        self.assertGreater(counts["cave_stone"], counts["copper_ore"] + counts["quartz_ore"] + counts["coal_ore"])

    def test_every_mine_has_coal_within_reach_of_the_entrance(self):
        for seed, (_, cave) in self.mines.items():
            with self.subTest(seed=seed):
                coal = [p for p, o in cave.objects.items() if o.variant == "coal_ore"]
                self.assertTrue(any(cave.is_walkable(p + d) and cave.can_reach(p + d, p)
                                    for p in coal for d in NEIGHBOR_DIRECTIONS))

    def test_the_far_end_of_every_mine_has_quartz(self):
        for seed, (_, cave) in self.mines.items():
            with self.subTest(seed=seed):
                floors = {p for p, t in cave.tile_map.tiles.items() if t.kind is TileKind.CAVE_FLOOR}
                depth = walking_depth(floors, cave.spawn)
                rocks = [p for p, o in cave.objects.items() if o.kind is ObjectKind.ROCK]
                if max(depth.get(p, 0) for p in rocks) > QUARTZ_FROM:
                    self.assertTrue(any(cave.objects[p].variant == "quartz_ore" for p in rocks))

    def test_mining_an_ore_gives_its_material_and_more_experience(self):
        for variant, (drops, xp) in ORE_YIELDS.items():
            with self.subTest(variant=variant):
                session, cave = next((s, w) for s, c in self.mines.values() for w in (c, s.world)
                                     if any(o.variant == variant for o in w.objects.values()))
                rock = next(p for p, o in cave.objects.items() if o.variant == variant)
                stand = next(rock + d for d in NEIGHBOR_DIRECTIONS
                             if cave.is_walkable(rock + d) and cave.can_reach(rock + d, rock))
                outside, original = session.world, cave.objects[rock]
                session.world, session.player.position = cave, stand
                bag = session.player.inventory
                tier = ORE_TIERS.get(variant, (ToolTier.WOOD, ""))[0]
                tool, bag.slots[bag.selected] = bag.slots[bag.selected], Stack(
                    next(item for item, level in PICKAXES.items() if level == tier), 1)
                try:
                    level, before = session.player.level, session.player.xp
                    held = {item: session.player.inventory.quantity(item) for item, _ in drops}
                    for _ in range(9):
                        result = session.primary_action(rock)
                        if result.code is ActionCode.RESOURCE_GATHERED:
                            break
                    self.assertIs(ActionCode.RESOURCE_GATHERED, result.code)
                    for item, amount in drops:
                        self.assertEqual(held[item] + amount, session.player.inventory.quantity(item))
                        self.assertIn(item, result.message)
                    self.assertEqual(0, session.player.inventory.quantity("stone"))
                    gained = session.player.xp - before if session.player.level == level else None
                    if gained is not None:
                        self.assertEqual(xp, gained)
                finally:
                    bag.slots[bag.selected] = tool
                    session.world, session.player.position = outside, outside.spawn
                    original.durability = original.spec.durability
                    cave.objects[rock] = original

    def test_ore_materials_have_inventory_icons(self):
        for drops, _ in ORE_YIELDS.values():
            for item, _ in drops:
                self.assertIn(item, ITEMS)
                image = icon(item, 1)
                self.assertEqual((16, 16), image.get_size())
                self.assertGreater(pygame.mask.from_surface(image).count(), 60)


if __name__ == "__main__":
    unittest.main()
