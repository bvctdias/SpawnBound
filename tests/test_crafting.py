import sys
import unittest
from pathlib import Path
import pygame

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from spawnbound.config import DEFAULT_CONFIG
from spawnbound.domain.coordinates import GridPos
from spawnbound.crafting_view import CraftPanel, bench_button, recipe_layout
from spawnbound.domain.crafting import Production, RECIPES, shown_recipes
from spawnbound.domain.inventory import Inventory, Stack
from spawnbound.domain.model import ObjectKind, SpaceKind
from spawnbound.domain.session import GameSession
from spawnbound.input import InputFrame
from spawnbound.inventory_hud import InventoryHUD, SHORT
from spawnbound.pixel_font import PixelFont
from spawnbound.states import GameplayState
from spawnbound.view import camera_origin, pick_world_point, screen_center, station_outputs


def center(box):
    x, y, w, h = box
    return x + w // 2, y + h // 2


class StationTests(unittest.TestCase):
    def test_empty_deck_and_player_placed_torch_and_bed(self):
        session = GameSession.create(1234, DEFAULT_CONFIG, chunk_preview_size=32)
        entrance = next(p for p in session.world.portals.values() if p.target_kind is SpaceKind.INTERIOR)
        session.player.place(session.world.surface_position(entrance.approach))
        session.player.facing = entrance.position - entrance.approach
        self.assertTrue(session.interact().success)
        room = session.world
        self.assertIsNone(room.camp)
        self.assertFalse(room.objects or room.placed_torches)
        deck = {GridPos(x, y) for x in range(1, 11) for y in range(1, 11)}
        landing = {GridPos(x, y) for x in (5, 6) for y in (11, 12)}
        self.assertEqual(deck | landing, set(room.tile_map.tiles))
        self.assertFalse(session.rest().success)
        state = GameplayState(session, DEFAULT_CONFIG)
        bag = session.player.inventory
        for name in ("torch", "bed"):
            recipe = next(r for r in RECIPES["bench"] if r.product == name)
            for item, qty in recipe.costs.items():
                bag.add(item, qty)
            self.assertTrue(session.craft_at_bench(recipe).success)
            bag.selected = next(i for i, slot in enumerate(bag.slots) if slot and slot.item == name)
            self.assertFalse(session.place_furniture(next(iter(room.portals)), name).success)
            self.assertEqual(1, bag.quantity(name))
            target = GridPos(7, 7)
            pos = screen_center(room.surface_position(target), camera_origin(session, DEFAULT_CONFIG), DEFAULT_CONFIG)
            state.step(InputFrame(destination_click=pos), 0)
            for _ in range(100):
                state.step(InputFrame(), .05)
                if target in room.objects:
                    break
            self.assertEqual(name, room.objects[target].kind.value)
            self.assertEqual(0, bag.quantity(name))
            if name == "torch":
                self.assertEqual({target}, room.placed_torches)
            else:
                session.player.energy = 1
                self.assertTrue(session.rest().success)
                self.assertGreater(session.player.energy, 1)
            state.step(InputFrame(pack_furniture_pressed=True), 0)
            self.assertFalse(room.placed_torches or room.objects)
            self.assertEqual(1, bag.quantity(name))

    def test_every_displayed_recipe_matches_the_costs_in_the_bag(self):
        hud = InventoryHUD(PixelFont())
        surface = pygame.Surface((960, 540), pygame.SRCALPHA)
        for kind, recipes in RECIPES.items():
            bag = Inventory()
            panel = CraftPanel(kind, None if kind == "bench" else Production(kind))
            layout = recipe_layout(DEFAULT_CONFIG, kind, bag)
            self.assertEqual(len(shown_recipes(kind, bag)), len(layout.rows))
            hud.draw_pack(surface, DEFAULT_CONFIG, bag, None, None, None, panel)
            for box in layout.rows:
                row = surface.subsurface(box)
                self.assertIn(bytes(pygame.Color(SHORT)), pygame.image.tobytes(row, "RGBA"))
            for recipe in recipes:
                for item, n in recipe.costs.items():
                    bag.add(item, n)
            layout = recipe_layout(DEFAULT_CONFIG, kind, bag)
            self.assertEqual(len(recipes), len(layout.rows))
            hud.draw_pack(surface, DEFAULT_CONFIG, bag, None, None, None, panel)
            for box in layout.rows:
                row = surface.subsurface(box)
                self.assertNotIn(bytes(pygame.Color(SHORT)), pygame.image.tobytes(row, "RGBA"))

    def test_partial_batch_collect_cancel_and_full_bag_are_atomic(self):
        bag = Inventory([Stack("carrot", 3), None])
        station = Production("composter")
        recipe = RECIPES["composter"][0]
        for _ in range(3):
            self.assertEqual("", station.start(recipe, bag, 0))
        bag.add("stone", 128)
        self.assertTrue(station.collect(bag, recipe.seconds))
        self.assertTrue(station.cancel(bag, recipe.seconds))
        self.assertEqual((1, 2), (station.ready, station.pending))
        bag.remove({"stone": 128})
        self.assertEqual("", station.cancel(bag, recipe.seconds))
        self.assertEqual("", station.collect(bag, 30))
        self.assertEqual({"carrot": 2, "carrot_seed": 1}, bag.snapshot())
        self.assertIsNone(station.recipe)
        self.assertTrue(station.collect(bag, 30))

    def test_foreign_recipes_insufficient_costs_and_mixed_batches(self):
        bag = Inventory()
        station = Production("kiln")
        recipe = RECIPES["kiln"][0]
        bag.add("coal", 9)
        self.assertTrue(station.start(recipe, bag, 0))
        self.assertEqual(9, bag.quantity("coal"))
        bag.add("copper", 6)
        self.assertTrue(station.start(RECIPES["bench"][0], bag, 0))
        self.assertEqual("", station.start(recipe, bag, 0))
        self.assertTrue(station.start(RECIPES["kiln"][1], bag, 4))
        self.assertEqual("", station.collect(bag, 4))
        self.assertEqual(1, bag.quantity("copper_bar"))

    def test_bench_clicks_upgrade_the_stored_tool_in_place(self):
        session = GameSession.create(7, DEFAULT_CONFIG)
        state = GameplayState(session, DEFAULT_CONFIG)
        bag = session.player.inventory
        bag.transfer(0, 12)
        state.step(InputFrame(inventory_pressed=True), 0)
        state.step(InputFrame(destination_click=center(bench_button(DEFAULT_CONFIG))), 0)
        boxes = recipe_layout(DEFAULT_CONFIG, "bench", bag).rows
        state.step(InputFrame(destination_click=center(boxes[1])), 0)
        self.assertEqual("pickaxe", bag.slots[12].item)
        bag.add("wood", 5)
        bag.add("stone", 5)
        for index in (1, 0):
            state.step(InputFrame(destination_click=center(boxes[index])), 0)
        self.assertEqual("stone_pickaxe", bag.slots[12].item)
        self.assertEqual(1, bag.quantity("bridge_kit"))
        self.assertEqual(0, bag.selected)
        state.step(InputFrame(pause_pressed=True), 0)
        self.assertTrue(state.inventory_open)
        self.assertIsNone(state.craft_panel.equipment)

    def test_shelter_station_click_process_return_and_collect(self):
        session = GameSession.create(1234, DEFAULT_CONFIG, chunk_preview_size=32)
        door = next(p for p in session.world.portals.values() if p.target_kind is SpaceKind.INTERIOR)
        def enter(portal):
            session.player.place(session.world.surface_position(portal.approach))
            session.player.facing = portal.position - portal.approach
            self.assertTrue(session.interact().success)

        enter(door)
        bag = session.player.inventory
        for kind, offset in ((ObjectKind.KILN, GridPos(1, 0)), (ObjectKind.COMPOSTER, GridPos(-1, 0))):
            build = next(r for r in RECIPES["bench"] if r.product == kind.value)
            for item, qty in build.costs.items():
                bag.add(item, qty)
            self.assertTrue(session.craft_at_bench(build).success)
            bag.selected = next(i for i, slot in enumerate(bag.slots) if slot and slot.item == kind.value)
            position = session.world.spawn + offset
            session.player.place(session.world.surface_position(session.world.spawn))
            self.assertTrue(session.place_furniture(position, kind.value).success)
            station = session.world.objects[position]
            recipe = RECIPES[kind.value][1]
            for item, qty in recipe.costs.items():
                bag.add(item, qty)
            state = GameplayState(session, DEFAULT_CONFIG)
            x, y = screen_center(station.position3d, camera_origin(session, DEFAULT_CONFIG), DEFAULT_CONFIG)
            state.step(InputFrame(destination_click=(x, y - 8)), 0)
            for _ in range(100):
                if state.inventory_open:
                    break
                state.step(InputFrame(), .1)
            self.assertIs(state.craft_panel.production, station.production)
            layout = recipe_layout(DEFAULT_CONFIG, kind.value)
            state.step(InputFrame(destination_click=center(layout.rows[1])), 0)
            state.step(InputFrame(pause_pressed=True), 0)
            enter(next(iter(session.world.portals.values())))
            session.advance_time(5.)
            enter(door)
            origin = camera_origin(session, DEFAULT_CONFIG)
            [(marked, box)] = station_outputs(session, origin, DEFAULT_CONFIG)
            self.assertIs(station, marked)
            self.assertEqual(station.position, pick_world_point(session, center(box), origin, DEFAULT_CONFIG).position)
            session.player.place(session.world.surface_position(station.position - session.player.facing))
            state = GameplayState(session, DEFAULT_CONFIG)
            state.step(InputFrame(interact_pressed=True), 0)
            self.assertIs(station.production, state.craft_panel.production)
            state.step(InputFrame(destination_click=center(layout.collect)), 0)
            self.assertEqual(1, bag.quantity(recipe.product))
            self.assertFalse(list(station_outputs(session, origin, DEFAULT_CONFIG)))
