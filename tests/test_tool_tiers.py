import json
import os
import sys
import unittest
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "dependencias")]

import pygame

from spawnbound.config import DEFAULT_CONFIG
from spawnbound.domain.coordinates import GridPos
from spawnbound.crafting_view import recipe_layout
from spawnbound.domain.crafting import RECIPES, shown_recipes
from spawnbound.domain.inventory import Stack
from spawnbound.domain.mobs import HEALTH, Mob, MobKind
from spawnbound.domain.model import OBJECT_SPECS, ObjectKind, WorldObject
from spawnbound.domain.session import ActionCode, GameSession
from spawnbound.domain.tools import (AXES, CRAFTED_TOOLS, PICKAXES, SICKLES, STARTER_TOOLS, STEPS, STRENGTH, SWORD_DAMAGES, SWORDS,
                                     TIERED, TOOLS, UPGRADES, ToolTier, tool_name)
from spawnbound.item_icons import HELD, ITEMS, held_tool, icon

EAST = GridPos(1, 0)
PLAYER = ROOT / "assets/native_32/player"


class TierTableTests(unittest.TestCase):
    def test_every_kind_has_the_four_tiers_and_the_pickaxe_prices(self):
        for kind, table in TIERED.items():
            chain = sorted(table, key=table.get)
            self.assertEqual([ToolTier.WOOD, ToolTier.STONE, ToolTier.COPPER, ToolTier.QUARTZ],
                             [table[item] for item in chain], kind)
            for step, item in enumerate(chain[:-1]):
                self.assertEqual((chain[step + 1], STEPS[step][0]), UPGRADES[item][:2])
            self.assertNotIn(chain[-1], UPGRADES)
        self.assertEqual(16, len(TOOLS - set(CRAFTED_TOOLS)))

    def test_the_starter_set_is_the_wooden_one(self):
        self.assertEqual(("pickaxe", "axe", "sickle", "sword"), STARTER_TOOLS)
        for item in STARTER_TOOLS:
            self.assertTrue(tool_name(item).endswith("de madeira"), item)
        session = GameSession.create(1234, DEFAULT_CONFIG, chunk_preview_size=16)
        self.assertEqual(list(STARTER_TOOLS), [s.item for s in session.player.inventory.slots[:4]])

    def test_the_bench_upgrades_every_kind(self):
        products = {recipe.product for recipe in RECIPES["bench"]}
        for item, (better, *_rest) in UPGRADES.items():
            self.assertIn(better, products, item)

    def test_the_bench_lists_only_the_next_tier_of_the_tools_in_the_bag(self):
        session = GameSession.create(1234, DEFAULT_CONFIG, chunk_preview_size=16)
        bag = session.player.inventory
        shown = shown_recipes("bench", bag)
        upgrades = [recipe.product for recipe in shown if recipe.product in {better for better, *_ in UPGRADES.values()}]
        self.assertEqual(["stone_pickaxe", "stone_axe", "stone_sword", "stone_sickle"], upgrades)
        self.assertEqual(len(shown), len(recipe_layout(DEFAULT_CONFIG, "bench", bag).rows))
        self.assertGreaterEqual(min(row[3] for row in recipe_layout(DEFAULT_CONFIG, "bench", bag).rows), 24,
                                "rows tall enough for an icon and its numbers")
        bag.slots[1] = Stack("copper_axe", 1)
        self.assertIn("quartz_axe", [recipe.product for recipe in shown_recipes("bench", bag)])
        self.assertNotIn("stone_axe", [recipe.product for recipe in shown_recipes("bench", bag)])


class TierEffectTests(unittest.TestCase):
    def setUp(self):
        self.session = GameSession.create(1234, DEFAULT_CONFIG, chunk_preview_size=16)
        self.session.world.objects.clear()
        self.session.wildlife.mobs.clear()
        self.bag = self.session.player.inventory
        self.cell = self.session.player.position + EAST
        self.session.player.facing = EAST

    def hold(self, item):
        self.bag.slots[0] = Stack(item, 1)
        self.bag.selected = 0
        self.session.player.energy = self.session.player.max_energy

    def test_better_axes_fell_more_wood_per_blow(self):
        world = self.session.world
        for item, tier in AXES.items():
            with self.subTest(item=item):
                tree = WorldObject.create(self.cell, ObjectKind.TREE, elevation=world.elevation_at(self.cell))
                world.objects[self.cell] = tree
                self.hold(item)
                self.assertIs(ActionCode.RESOURCE_HIT, self.session.primary_action(self.cell).code)
                self.assertEqual(OBJECT_SPECS[ObjectKind.TREE].durability - STRENGTH[tier], tree.durability)

    def test_better_swords_hurt_more(self):
        self.assertEqual([2, 3, 4, 5], [SWORD_DAMAGES[tier] for tier in sorted(SWORD_DAMAGES)])
        location = self.session.world.surface_position(self.cell)
        for item, tier in SWORDS.items():
            with self.subTest(item=item):
                deer = Mob(3, MobKind.DEER, HEALTH[MobKind.DEER], location, location, 0.)
                self.session.wildlife.mobs[3] = deer
                self.hold(item)
                self.assertIs(ActionCode.MOB_HIT, self.session.attack_mob(3).code)
                self.assertEqual(HEALTH[MobKind.DEER] - SWORD_DAMAGES[tier], deer.hp)

    def test_a_stone_sickle_or_better_prepares_the_soil_in_one_pass(self):
        world = self.session.world
        for item, passes in (("sickle", 2), ("stone_sickle", 1), ("copper_sickle", 1), ("quartz_sickle", 1)):
            with self.subTest(item=item):
                world.tilled_soil.pop(self.cell, None)
                self.hold(item)
                if self.session.soil_obstacle(self.cell):
                    self.skipTest("the cell east of the spawn is not free grass on this seed")
                for _ in range(passes):
                    self.assertIs(ActionCode.SOIL_TILLED, self.session.till_soil(self.cell).code)
                self.assertEqual(2, world.tilled_soil[self.cell])

    def test_u_improves_the_selected_axe_sword_or_sickle(self):
        for item, (better, costs, _name, _ingredients) in UPGRADES.items():
            if item in PICKAXES:
                continue
            with self.subTest(item=item):
                self.hold(item)
                self.assertIs(ActionCode.MISSING_MATERIALS, self.session.upgrade_tool().code)
                for material, amount in costs.items():
                    self.bag.add(material, amount)
                result = self.session.upgrade_tool()
                self.assertIs(ActionCode.CRAFTED, result.code)
                self.assertEqual(better, self.bag.slots[0].item)
                self.assertEqual(f"{tool_name(better)} equipad{'o' if better in AXES else 'a'}.", result.message)

    def test_u_on_something_that_is_not_a_tool(self):
        self.bag.slots[0] = Stack("wood", 3)
        self.bag.selected = 0
        self.assertIs(ActionCode.TOOL_REQUIRED, self.session.upgrade_tool().code)
        self.hold("quartz_sword")
        self.assertIs(ActionCode.BLOCKED, self.session.upgrade_tool().code)


class TierArtTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pygame.init()

    def test_every_tier_has_an_icon_and_a_held_drawing_of_its_own(self):
        for kind, table in TIERED.items():
            images = {pygame.image.tobytes(icon(item, 1), "RGBA") for item in table}
            self.assertEqual(4, len(images), f"the four {kind} tiers look alike")
            for item in table:
                self.assertEqual(tool_name(item), ITEMS[item][0])
                self.assertIn(item, HELD)
                self.assertGreater(pygame.mask.from_surface(held_tool(item)).count(), 20)

    def test_the_player_atlas_has_a_sheet_for_every_tool_but_the_wooden_pickaxe(self):
        spec = json.loads((PLAYER / "animation.json").read_text("utf-8"))
        self.assertEqual(set(TOOLS) - {"pickaxe"}, set(spec["upgrades"]))
        for item, sheet in spec["upgrades"].items():
            self.assertTrue((PLAYER / sheet).is_file(), sheet)


if __name__ == "__main__":
    unittest.main()
