import os
import random
import sys
import unittest
from collections import Counter
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "dependencias")]

import pygame

from spawnbound.config import DEFAULT_CONFIG
from spawnbound.crafting_view import recipe_layout
from spawnbound.domain.crafting import RECIPES, Production, shown_recipes
from spawnbound.domain.fish import COOKED, FISH, FRESH, NIGHT, DAY, SEA, Swim, biting, pick_fish, water_of
from spawnbound.domain.inventory import Inventory
from spawnbound.domain.model import TileKind
from spawnbound.domain.session import FOOD, FOOD_HEARTS, ITEM_NAMES, GameSession
from spawnbound.item_icons import ITEMS, icon


class FishTableTests(unittest.TestCase):
    def test_six_fish_in_each_water_with_every_way_of_swimming(self):
        for water in (FRESH, SEA):
            fish = [f for f in FISH.values() if f.water == water]
            self.assertEqual(6, len(fish), water)
            self.assertTrue(any(f.period == NIGHT for f in fish), water)
            self.assertTrue(any(f.period == DAY for f in fish), water)
        self.assertEqual(set(Swim), {f.swim for f in FISH.values()})
        for fish in FISH.values():
            self.assertTrue(0 < fish.difficulty <= 100, fish.item)

    def test_who_bites_by_day_and_by_night(self):
        for water in (FRESH, SEA):
            day, night = set(biting(water, False)), set(biting(water, True))
            self.assertFalse({f for f in day if f.period == NIGHT})
            self.assertFalse({f for f in night if f.period == DAY})
            self.assertTrue(day & night, "the fish of any hour bite at both")

    def test_the_rare_ones_bite_less(self):
        rng = random.Random(5)
        counts = Counter(pick_fish(rng, FRESH, False).item for _ in range(3000))
        self.assertGreater(counts["lambari"], 5 * counts["pirarucu"])
        self.assertGreater(counts["pirarucu"], 0)
        self.assertNotIn("bagre", counts, "the catfish bites only at night")


class WaterTests(unittest.TestCase):
    def test_rivers_and_lakes_are_fresh_and_the_sea_is_salty(self):
        for seed in (1234, 77, 2024):
            with self.subTest(seed=seed):
                world = GameSession.create(seed, DEFAULT_CONFIG, chunk_preview_size=128).world
                tiles = world.tile_map.tiles
                water = [cell for cell, tile in tiles.items() if tile.kind is TileKind.WATER]
                self.assertIs(SEA, water_of(world, min(water, key=lambda c: (c.x, c.y))), "the open sea")
                if world.river_cells:
                    self.assertIs(FRESH, water_of(world, next(iter(world.river_cells))))
                if world.sea_cells:
                    self.assertIs(SEA, water_of(world, next(iter(world.sea_cells))))
                land = next(cell for cell, tile in tiles.items() if tile.kind is TileKind.GRASS)
                self.assertIsNone(water_of(world, land))


class FoodTests(unittest.TestCase):
    def test_raw_fish_costs_a_heart_and_roasted_fish_heals_one(self):
        for item, fish in FISH.items():
            with self.subTest(item=item):
                self.assertEqual((-1, 1), (FOOD_HEARTS[item], FOOD_HEARTS[COOKED[item]]))
                self.assertGreater(FOOD[COOKED[item]], 2 * FOOD[item])
                self.assertIn(item, ITEM_NAMES)
                self.assertIn(COOKED[item], ITEM_NAMES)

    def test_q_eats_roasted_food_first(self):
        order = list(FOOD)
        roasted = [i for i in order if FOOD_HEARTS.get(i, 0) > 0]
        raw = [i for i in order if FOOD_HEARTS.get(i, 0) < 0]
        self.assertLess(max(order.index(i) for i in roasted), min(order.index(i) for i in raw))
        self.assertEqual(sorted((FOOD[i] for i in roasted), reverse=True), [FOOD[i] for i in roasted])


class CampfireTests(unittest.TestCase):
    def test_every_fish_roasts_at_the_campfire(self):
        products = {recipe.product: recipe for recipe in RECIPES["campfire"]}
        bag = Inventory()
        for item in FISH:
            recipe = products[COOKED[item]]
            self.assertEqual({item: 1}, recipe.costs)
            bag.add(item, 1)
            station = Production("campfire")
            self.assertEqual("", station.start(recipe, bag, 0.))
            station.collect(bag, recipe.seconds)
            self.assertEqual(1, bag.quantity(COOKED[item]))

    def test_the_panel_lists_a_fish_once_it_is_in_the_bag(self):
        bag = Inventory()
        self.assertEqual(3, len(shown_recipes("campfire", bag)), "the three meats")
        bag.add("tilapia", 2)
        self.assertIn("cooked_tilapia", [r.product for r in shown_recipes("campfire", bag)])
        self.assertNotIn("cooked_atum", [r.product for r in shown_recipes("campfire", bag)])

    def test_with_every_fish_the_campfire_shows_two_columns_on_the_screen(self):
        bag = Inventory()
        for item in FISH:
            bag.add(item, 1)
        layout = recipe_layout(DEFAULT_CONFIG, "campfire", bag)
        self.assertEqual(15, len(layout.rows))
        self.assertEqual(2, len({row[0] for row in layout.rows}))
        collect = pygame.Rect(layout.collect)
        for row in map(pygame.Rect, layout.rows):
            self.assertLessEqual(row.bottom, DEFAULT_CONFIG.virtual_height)
            self.assertGreaterEqual(row.left, 0)
            self.assertLessEqual(row.right, DEFAULT_CONFIG.virtual_width)
            self.assertFalse(row.colliderect(collect))
            self.assertGreaterEqual(row.height, 24)


class ArtTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pygame.init()

    def test_each_fish_and_each_roasted_fish_has_a_drawing_of_its_own(self):
        raw = {pygame.image.tobytes(icon(item, 1), "RGBA") for item in FISH}
        roasted = {pygame.image.tobytes(icon(COOKED[item], 1), "RGBA") for item in FISH}
        self.assertEqual(12, len(raw))
        self.assertEqual(12, len(roasted))
        for item, fish in FISH.items():
            self.assertEqual(fish.name, ITEMS[item][0])
            self.assertTrue(ITEMS[COOKED[item]][0].startswith(fish.name + " assad"))
            self.assertGreater(pygame.mask.from_surface(icon(item, 1)).count(), 40)


if __name__ == "__main__":
    unittest.main()
