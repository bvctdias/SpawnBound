import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "dependencias")]
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame

from spawnbound import item_icons, rest_menu
from spawnbound.config import DEFAULT_CONFIG
from spawnbound.crafting_view import TITLES, recipe_layout
from spawnbound.domain.coordinates import GridPos
from spawnbound.domain.crafting import RECIPES, shown_recipes
from spawnbound.domain.fish import FISH
from spawnbound.domain.model import ObjectKind, WorldObject
from spawnbound.domain.session import FOOD, FOOD_HEARTS, LIGHT_FOOD, RAW_MEAT, GameSession
from spawnbound.input import InputFrame
from spawnbound.renderer import PlaceholderRenderer
from spawnbound.prototype_art import PrototypeArtRenderer
from spawnbound.states import GameplayState
from spawnbound.view import camera_origin, station_outputs

DAY, AFTERNOON, NIGHT = DEFAULT_CONFIG.phase_durations
SIDES = (GridPos(1, 0), GridPos(0, 1), GridPos(-1, 0), GridPos(0, -1))
ROASTS = {"meat": "cooked_meat", "venison": "cooked_venison", "snake_meat": "cooked_snake_meat"}


def _session():
    session = GameSession.create(1234, DEFAULT_CONFIG, chunk_preview_size=128)
    session.wildlife.mobs.clear()
    return session


def _hold_nothing(bag):
    empty = next(i for i, stack in enumerate(bag.slots) if stack is None)
    bag.transfer(0, empty)
    bag.selected = 0


class FoodTests(unittest.TestCase):
    def test_roasted_meat_beats_raw_and_fruit_is_light(self):
        self.assertEqual(set(ROASTS), set(RAW_MEAT) - set(FISH))
        for raw, roasted in ROASTS.items():
            with self.subTest(raw=raw):
                self.assertEqual((-1, 1), (FOOD_HEARTS[raw], FOOD_HEARTS[roasted]))
                self.assertGreater(FOOD[roasted], 2 * FOOD[raw])
        self.assertIn("berry", LIGHT_FOOD)
        self.assertNotIn("berry", FOOD_HEARTS)
        self.assertGreaterEqual(FOOD["berry"], FOOD["brown_mushroom"])

    def test_raw_meat_gives_a_little_energy_for_a_heart(self):
        session = _session()
        player, bag = session.player, session.player.inventory
        bag.add("venison", 2)
        _hold_nothing(bag)
        player.energy, player.hearts = 40, 5
        result = session.eat()
        self.assertTrue(result.success)
        self.assertEqual((40 + FOOD["venison"], 4), (player.energy, player.hearts))
        self.assertIn("fogueira", result.message)
        player.hearts = 1
        self.assertFalse(session.eat().success)
        self.assertIn("último coração", session.last_message)
        player.hearts, player.energy = 5, player.max_energy
        self.assertFalse(session.eat().success)
        self.assertEqual(1, bag.quantity("venison"))

    def test_roasted_meat_heals_a_heart_and_is_eaten_before_raw(self):
        session = _session()
        player, bag = session.player, session.player.inventory
        bag.add("meat", 1)
        bag.add("cooked_meat", 1)
        _hold_nothing(bag)
        player.energy, player.hearts = 40, 5
        self.assertTrue(session.eat().success)
        self.assertEqual((40 + FOOD["cooked_meat"], 6), (player.energy, player.hearts))
        self.assertEqual((1, 0), (bag.quantity("meat"), bag.quantity("cooked_meat")))
        player.energy = player.max_energy
        bag.add("cooked_venison")
        self.assertTrue(session.eat().success)
        self.assertEqual((7, 1), (player.hearts, bag.quantity("meat")))

    def test_berries_are_picked_and_eaten_for_energy(self):
        session = _session()
        world, player, bag = session.world, session.player, session.player.inventory
        cell = next(p for p, o in sorted(world.objects.items()) if o.kind is ObjectKind.BERRY_BUSH
                    and any(world.is_walkable(p + d) and world.can_reach(p + d, p) and world.object_at(p + d) is None
                            for d in SIDES))
        player.position = next(cell + d for d in SIDES if world.is_walkable(cell + d)
                               and world.can_reach(cell + d, cell) and world.object_at(cell + d) is None)
        result = session.primary_action(cell)
        self.assertTrue(result.success)
        self.assertEqual("+1 frutas. Q para comer.", result.message)
        _hold_nothing(bag)
        player.energy, player.hearts = 30, 5
        self.assertTrue(session.eat().success)
        self.assertEqual((30 + FOOD["berry"], 5, 0), (player.energy, player.hearts, bag.quantity("berry")))
        bag.add("berry")
        player.energy = player.max_energy
        self.assertFalse(session.eat().success)
        self.assertEqual(1, bag.quantity("berry"))

    def test_icons_and_names_of_the_roasts(self):
        names = {"cooked_meat": "Carne assada", "cooked_venison": "Carne de cervo assada",
                 "cooked_snake_meat": "Carne de cobra assada"}
        for item, name in names.items():
            with self.subTest(item=item):
                self.assertEqual(name, item_icons.ITEMS[item][0])
                roast, raw = item_icons.icon(item), item_icons.icon(next(r for r, c in ROASTS.items() if c == item))
                self.assertEqual((32, 32), roast.get_size())
                self.assertNotEqual(pygame.image.tobytes(raw, "RGBA"), pygame.image.tobytes(roast, "RGBA"))


class CookingTests(unittest.TestCase):
    def setUp(self):
        self.session = _session()
        self.bag = self.session.player.inventory
        self.state = GameplayState(self.session, DEFAULT_CONFIG)
        self.bag.add("campfire")
        self.bag.selected = next(i for i, s in enumerate(self.bag.slots) if s and s.item == "campfire")
        player = self.session.player
        side = next(d for d in SIDES if self.session.can_place(player.position + d))
        self.cell = player.position + side
        self.assertTrue(self.session.place_furniture(self.cell, "campfire").success)
        player.facing = side
        self.fire = self.session.world.objects[self.cell]

    def _open_cooking(self, by_key=False):
        self.state.step(InputFrame(interact_pressed=True), 0)
        self.assertTrue(self.state.rest_open)
        cook = rest_menu.layout(DEFAULT_CONFIG)[1].center
        self.state.step(InputFrame(craft_pressed=True) if by_key else InputFrame(destination_click=cook), 0)
        self.assertFalse(self.state.rest_open)
        self.assertTrue(self.state.inventory_open)
        self.assertEqual("campfire", self.state.craft_panel.equipment)
        self.assertIs(self.fire.production, self.state.craft_panel.production)

    def test_the_campfire_roasts_raw_meat_without_fuel(self):
        self.assertEqual("Fogueira", TITLES["campfire"])
        self.assertEqual({r.product: r.costs for r in RECIPES["campfire"] if not set(r.costs) & set(FISH)},
                         {roast: {raw: 1} for raw, roast in ROASTS.items()})
        self.assertIn(self.cell, self.session.world.placed_stations)
        self.session.cycle_seconds = DAY * .3
        self.bag.add("meat", 2)
        self._open_cooking()
        layout = recipe_layout(DEFAULT_CONFIG, "campfire", self.bag)
        row = next(box for box, r in zip(layout.rows, shown_recipes("campfire", self.bag)) if r.product == "cooked_meat")
        for _ in range(2):
            self.state.step(InputFrame(destination_click=(row[0] + 10, row[1] + 10)), 0)
        self.assertEqual((0, 2), (self.bag.quantity("meat"), self.fire.production.pending))
        for _ in range(4):
            self.state.step(InputFrame(), 2.)
        self.state.step(InputFrame(destination_click=(layout.collect[0] + 5, layout.collect[1] + 5)), 0)
        self.assertEqual(2, self.bag.quantity("cooked_meat"))
        self.assertIsNone(self.fire.production.recipe)

    def test_c_opens_the_recipes_and_the_roast_waits_in_a_bubble(self):
        self.bag.add("snake_meat")
        self._open_cooking(by_key=True)
        recipe = next(r for r in RECIPES["campfire"] if r.product == "cooked_snake_meat")
        self.assertEqual("", self.fire.production.start(recipe, self.bag, self.session.production_seconds))
        self.state.step(InputFrame(pause_pressed=True), 0)
        self.assertFalse(self.state.inventory_open)
        self.session.advance_time(recipe.seconds + .1)
        origin = camera_origin(self.session, DEFAULT_CONFIG)
        self.assertEqual([self.fire], [obj for obj, _ in station_outputs(self.session, origin, DEFAULT_CONFIG)])
        pygame.font.init()
        renderer = PlaceholderRenderer(pygame.Surface((960, 540)), DEFAULT_CONFIG)
        renderer.draw_gameplay(self.session, debug=False)
        art = PrototypeArtRenderer(pygame.Surface((960, 540)), DEFAULT_CONFIG, ROOT / "assets/native_32/manifest.json")
        art.draw_gameplay(self.session, debug=False)

    def test_the_campfire_still_draws_and_is_clicked_as_a_campfire(self):
        from spawnbound.view import object_contains
        obj = WorldObject.create(GridPos(4, 4), ObjectKind.CAMPFIRE)
        self.assertIsNotNone(obj.production)
        self.assertTrue(object_contains(obj, 0, -18))
        self.assertFalse(object_contains(obj, 22, 0))


if __name__ == "__main__":
    unittest.main()
