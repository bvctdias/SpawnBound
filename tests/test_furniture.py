import os
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "dependencias")]
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame

from spawnbound import repair_menu
from spawnbound.config import DEFAULT_CONFIG
from spawnbound.crafting_view import CraftPanel, recipe_layout
from spawnbound.domain import crafting
from spawnbound.domain.archipelago import dock_restored
from spawnbound.domain.coordinates import GridPos
from spawnbound.domain.crafting import DOCK_REPAIR, MIRRORED, RECIPES, TURNABLE, Production
from spawnbound.domain.inventory import Inventory, Stack
from spawnbound.domain.model import ObjectKind, WorldObject
from spawnbound.domain.session import ActionCode, GameSession
from spawnbound.input import InputFrame
from spawnbound.inventory_hud import InventoryHUD
from spawnbound.pixel_font import PixelFont
from spawnbound.prototype_art import PrototypeArtRenderer
from spawnbound.renderer import PlaceholderRenderer
from spawnbound.states import PACK_SECONDS, ClickIntent, GameplayState
from spawnbound.view import camera_origin, object_contains, screen_center, station_outputs
from test_islands import new_session, stand_at_dock

EAST = GridPos(1, 0)
MANIFEST = ROOT / "assets/native_32/manifest.json"


def flat_session():
    session = GameSession.create(1234, DEFAULT_CONFIG, chunk_preview_size=16)
    session.world.objects.clear()
    session.wildlife.mobs.clear()
    return session


def recipe(product):
    return next(r for kind in RECIPES.values() for r in kind if r.product == product)


class RepairPanelTests(unittest.TestCase):
    def setUp(self):
        self.session = new_session()
        self.dock = stand_at_dock(self.session)
        self.state = GameplayState(self.session, DEFAULT_CONFIG)
        self.bag = self.session.player.inventory

    def fill(self):
        for item, n in DOCK_REPAIR.items():
            self.bag.add(item, n)

    def test_e_opens_the_panel_and_spends_nothing(self):
        self.fill()
        self.state.step(InputFrame(interact_pressed=True), 0)
        self.assertEqual(self.session.world.dock, self.state.repair_open)
        self.assertFalse(dock_restored(self.dock))
        self.assertEqual(DOCK_REPAIR["wood"], self.bag.quantity("wood"))

    def test_e_again_repairs_once_everything_is_in_the_bag(self):
        self.fill()
        self.state.step(InputFrame(interact_pressed=True), 0)
        self.state.step(InputFrame(interact_pressed=True), 0)
        self.assertIsNone(self.state.repair_open)
        self.assertTrue(dock_restored(self.dock))
        self.assertEqual(0, self.bag.quantity("wood"))

    def test_without_the_materials_the_button_does_nothing_and_e_closes(self):
        self.bag.add("wood", 3)
        self.state.step(InputFrame(interact_pressed=True), 0)
        button = repair_menu.layout(DEFAULT_CONFIG, len(DOCK_REPAIR))[2]
        self.state.step(InputFrame(destination_click=button.center), 0)
        self.assertIsNotNone(self.state.repair_open)
        self.assertFalse(dock_restored(self.dock))
        self.state.step(InputFrame(interact_pressed=True), 0)
        self.assertIsNone(self.state.repair_open)
        self.assertEqual(3, self.bag.quantity("wood"))

    def test_the_button_repairs(self):
        self.fill()
        self.state.step(InputFrame(interact_pressed=True), 0)
        button = repair_menu.layout(DEFAULT_CONFIG, len(DOCK_REPAIR))[2]
        self.state.step(InputFrame(destination_click=button.center), 0)
        self.assertTrue(dock_restored(self.dock))

    def test_the_panel_shows_each_material_have_and_need(self):
        pygame.font.init()
        self.bag.add("wood", 4)
        self.state.step(InputFrame(interact_pressed=True), 0)
        renderer = PlaceholderRenderer(pygame.Surface((960, 540)), DEFAULT_CONFIG)
        drawn = []
        real = repair_menu.draw
        with patch.object(repair_menu, "draw", lambda *a, **k: drawn.append(a) or real(*a, **k)):
            self.state.draw(renderer)
        (_, _, _, kind, needs, have, _), = drawn
        self.assertEqual(("dock", DOCK_REPAIR, {"wood": 4, "stone": 0}), (kind, needs, have))
        self.assertTrue(renderer._ui_bounds.width > 300)

    def test_a_click_on_the_ruin_opens_the_panel(self):
        self.state._pending_target = self.session.world.dock
        self.state._pending_intent = ClickIntent.PRIMARY_ACTION
        self.state._complete_pending_target()
        self.assertEqual(self.session.world.dock, self.state.repair_open)
        self.assertEqual("", self.session.notice)

    def test_e_consertar_shows_over_the_ruin_the_player_faces(self):
        pygame.font.init()
        renderer = PlaceholderRenderer(pygame.Surface((960, 540)), DEFAULT_CONFIG)
        texts = []
        real = renderer.pixel_font.render
        with patch.object(renderer.pixel_font, "render", lambda text, *a, **k: texts.append(text) or real(text, *a, **k)):
            self.state.draw(renderer)
        self.assertIn("[E] Consertar", texts)


class PackTests(unittest.TestCase):
    def setUp(self):
        self.session = flat_session()
        self.bag = self.session.player.inventory
        p = self.session.player.position
        self.cell = p + EAST
        self.chest = WorldObject.create(self.cell, ObjectKind.CHEST, elevation=self.session.world.elevation_at(self.cell))
        self.session.world.objects[self.cell] = self.chest
        self.chest.storage.slots[0] = Stack("stone", 7)
        self.state = GameplayState(self.session, DEFAULT_CONFIG)

    def click(self, held):
        origin = camera_origin(self.session, DEFAULT_CONFIG, self.state.visual_position3d)
        x, y = screen_center(self.chest.position3d, origin, DEFAULT_CONFIG)
        click = DEFAULT_CONFIG.world_to_view((x, y - 8))
        self.state.step(InputFrame(destination_click=click, primary_held=held), 0)

    def test_holding_packs_the_chest_with_what_it_held(self):
        self.click(held=True)
        steps = round(PACK_SECONDS / .05) + 2
        for _ in range(steps):
            self.state.step(InputFrame(primary_held=True), .05)
        self.assertNotIn(self.cell, self.session.world.objects)
        self.assertEqual((1, 7), (self.bag.quantity("chest"), self.bag.quantity("stone")))

    def test_it_shakes_while_held(self):
        self.click(held=True)
        self.state.step(InputFrame(primary_held=True), .05)
        self.assertTrue(any(a.impact and a.subject is self.chest for a in self.session.afterimages))
        self.assertIn(self.cell, self.session.world.objects)

    def test_letting_go_sooner_uses_it_as_a_click(self):
        self.click(held=True)
        self.state.step(InputFrame(primary_held=True), .3)
        self.state.step(InputFrame(), .05)
        self.assertIn(self.cell, self.session.world.objects)
        self.assertEqual("Pressione E para abrir o bau.", self.session.notice)

    def test_a_quick_click_never_packs(self):
        self.click(held=False)
        for _ in range(30):
            self.state.step(InputFrame(), .05)
        self.assertIn(self.cell, self.session.world.objects)

    def test_a_full_bag_keeps_it_in_place(self):
        for i in range(len(self.bag.slots)):
            if self.bag.slots[i] is None:
                self.bag.slots[i] = Stack("wood", 64)
        self.session.player.facing = EAST
        result = self.session.take_furniture()
        self.assertIs(ActionCode.INVENTORY_FULL, result.code)
        self.assertIn(self.cell, self.session.world.objects)
        self.assertEqual("Sem espaço na mochila para o móvel e o que ele guarda.", self.session.notice)

    def test_a_campfire_packs_with_the_roast_and_the_raw_meat(self):
        fire_cell = self.session.player.position + GridPos(-1, 0)
        fire = WorldObject.create(fire_cell, ObjectKind.CAMPFIRE, elevation=self.session.world.elevation_at(fire_cell))
        self.session.world.objects[fire_cell] = fire
        self.bag.add("meat", 2)
        now = self.session.production_seconds
        for _ in range(2):
            self.assertEqual("", fire.production.start(recipe("cooked_meat"), self.bag, now))
        self.session.production_seconds += recipe("cooked_meat").seconds + .01
        self.session.player.facing = GridPos(-1, 0)
        self.assertTrue(self.session.take_furniture().success)
        self.assertEqual((1, 1, 1), (self.bag.quantity("campfire"), self.bag.quantity("cooked_meat"),
                                     self.bag.quantity("meat")))


class CampfireQueueTests(unittest.TestCase):
    def setUp(self):
        self.fire = Production("campfire")
        self.bag = Inventory()
        for item in ("meat", "venison", "snake_meat"):
            self.bag.add(item, 5)

    def start(self, product, now=0.):
        return self.fire.start(recipe(product), self.bag, now)

    def test_each_kind_roasts_after_the_last_and_the_roast_piles_up(self):
        meat, venison = recipe("cooked_meat"), recipe("cooked_venison")
        self.assertEqual("", self.start("cooked_meat"))
        self.assertEqual("", self.start("cooked_meat"))
        self.assertEqual("", self.start("cooked_venison"))
        self.assertEqual("", self.start("cooked_snake_meat"))
        both = 2 * meat.seconds
        self.fire.refresh(both + venison.seconds - .01)
        self.assertEqual([("cooked_meat", 2)], self.fire.outputs)
        self.fire.refresh(both + venison.seconds)
        self.assertEqual([("cooked_meat", 2), ("cooked_venison", 1)], self.fire.outputs)
        self.fire.refresh(100.)
        self.assertEqual([("cooked_meat", 2), ("cooked_venison", 1), ("cooked_snake_meat", 1)], self.fire.outputs)
        self.assertEqual("", self.fire.collect(self.bag, 100.))
        self.assertEqual((2, 1, 1), tuple(self.bag.quantity(i) for i in
                                          ("cooked_meat", "cooked_venison", "cooked_snake_meat")))
        self.assertEqual(((), None, {}), (tuple(self.fire.queue), self.fire.recipe, self.fire.stock))

    def test_at_most_four_kinds(self):
        self.assertEqual(4, crafting.QUEUE_KINDS["campfire"])
        with patch.dict(crafting.QUEUE_KINDS, {"campfire": 2}):
            self.start("cooked_meat")
            self.start("cooked_venison")
            self.assertEqual("Até 2 tipos por vez.", self.start("cooked_snake_meat"))
            self.assertEqual(5, self.bag.quantity("snake_meat"))
            self.assertEqual("", self.start("cooked_meat"))

    def test_cancel_gives_back_everything_not_yet_roasted(self):
        self.start("cooked_meat")
        self.start("cooked_venison")
        self.start("cooked_venison")
        self.assertEqual("", self.fire.cancel(self.bag, 0.))
        self.assertEqual((5, 5), (self.bag.quantity("meat"), self.bag.quantity("venison")))
        self.assertEqual([], self.fire.queue)

    def test_other_stations_still_make_one_product_at_a_time(self):
        kiln = Production("kiln")
        bag = Inventory()
        first, second = RECIPES["kiln"][:2]
        for item, n in (*first.costs.items(), *second.costs.items()):
            bag.add(item, n)
        self.assertEqual("", kiln.start(first, bag, 0.))
        self.assertEqual("Libere a saída primeiro.", kiln.start(second, bag, 0.))

    def test_the_bubble_shows_one_icon_per_kind_and_the_panel_draws_the_queue(self):
        session = flat_session()
        cell = session.player.position + EAST
        obj = WorldObject.create(cell, ObjectKind.CAMPFIRE, elevation=session.world.elevation_at(cell))
        session.world.objects[cell] = obj
        session.world.placed_stations.add(cell)
        obj.production = self.fire
        self.start("cooked_meat")
        self.start("cooked_venison")
        self.start("cooked_snake_meat")
        origin = camera_origin(session, DEFAULT_CONFIG)
        session.production_seconds = 6.
        [(_, (_, _, two, _))] = station_outputs(session, origin, DEFAULT_CONFIG)
        session.production_seconds = 100.
        [(_, (_, _, three, _))] = station_outputs(session, origin, DEFAULT_CONFIG)
        self.assertGreater(three, two)
        pygame.font.init()
        PlaceholderRenderer(pygame.Surface((960, 540)), DEFAULT_CONFIG).draw_gameplay(session, debug=False)
        fresh = Production("campfire")
        fresh.start(recipe("cooked_meat"), self.bag, 0.)
        fresh.start(recipe("cooked_venison"), self.bag, 0.)
        surface = pygame.Surface((960, 540), pygame.SRCALPHA)
        InventoryHUD(PixelFont())._recipe_panel(surface, self.bag, CraftPanel("campfire", fresh),
                                                recipe_layout(DEFAULT_CONFIG, "campfire"))


class TurnTests(unittest.TestCase):
    def test_the_bed_the_chest_and_the_composter_turn(self):
        for item in ("bed", "chest", "composter"):
            self.assertEqual(("left", "right"), TURNABLE[item])
            self.assertIn(item, MIRRORED)

    def test_a_turned_piece_is_placed_with_its_side(self):
        session = flat_session()
        bag = session.player.inventory
        bag.add("chest")
        bag.selected = next(i for i, s in enumerate(bag.slots) if s and s.item == "chest")
        target = session.player.position + EAST
        self.assertTrue(session.place_furniture(target, "chest", "right").success)
        self.assertEqual("right", session.world.objects[target].variant)

    def test_drawn_and_clicked_as_its_mirror_image(self):
        pygame.font.init()
        renderer = PlaceholderRenderer(pygame.Surface((960, 540)), DEFAULT_CONFIG)
        for kind in (ObjectKind.BED, ObjectKind.CHEST, ObjectKind.COMPOSTER):
            with self.subTest(kind=kind):
                left = WorldObject.create(GridPos(5, 5), kind, variant="left")
                right = WorldObject.create(GridPos(5, 5), kind, variant="right")
                body, (fx, _) = renderer._caster_image("object", left)
                mirror, (mx, _) = renderer._caster_image("object", right)
                area, flipped = body.get_bounding_rect(), mirror.get_bounding_rect()
                self.assertEqual(area.width, flipped.width)
                self.assertNotEqual(pygame.image.tobytes(body, "RGBA"), pygame.image.tobytes(mirror, "RGBA"))
                spots = [(dx, dy) for dx in range(-16, 17, 2) for dy in range(-30, 4, 2)
                         if object_contains(left, dx, dy)]
                self.assertTrue(spots)
                self.assertTrue(all(object_contains(right, -dx, dy) for dx, dy in spots))

    def test_the_art_pack_chest_turns_too(self):
        art = PrototypeArtRenderer(pygame.Surface((960, 540)), DEFAULT_CONFIG, MANIFEST)
        left = WorldObject.create(GridPos(5, 5), ObjectKind.CHEST, variant="left")
        right = WorldObject.create(GridPos(5, 5), ObjectKind.CHEST, variant="right")
        self.assertEqual("chest_right", art.object_name(right))
        if "chest" in art.art.images:
            image, mirror = art.art.images["chest"], art.art.images["chest_right"]
            self.assertEqual(pygame.image.tobytes(pygame.transform.flip(image, True, False), "RGBA"),
                             pygame.image.tobytes(mirror, "RGBA"))
        body, mirror = art._caster_image("object", left)[0], art._caster_image("object", right)[0]
        self.assertNotEqual(pygame.image.tobytes(body, "RGBA"), pygame.image.tobytes(mirror, "RGBA"))


if __name__ == "__main__":
    unittest.main()
