import os
import sys
import unittest
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import pygame

from spawnbound.config import DEFAULT_CONFIG
from spawnbound.domain.coordinates import GridPos
from spawnbound.domain.crafting import RECIPES
from spawnbound.domain.model import ObjectKind, SpaceKind, WorldObject
from spawnbound.domain.session import GameSession
from spawnbound.input import InputFrame
from spawnbound.renderer import PlaceholderRenderer
from spawnbound.states import GameplayState
from spawnbound.view import camera_origin, object_contains, screen_center


class PlacedBenchTests(unittest.TestCase):
    def setUp(self):
        session = GameSession.create(1234, DEFAULT_CONFIG, chunk_preview_size=32)
        entrance = next(p for p in session.world.portals.values() if p.target_kind is SpaceKind.INTERIOR)
        session.player.place(session.world.surface_position(entrance.approach))
        session.player.facing = entrance.position - entrance.approach
        self.assertTrue(session.interact().success)
        self.session, self.room = session, session.world
        self.state = GameplayState(session, DEFAULT_CONFIG)
        self.bag = session.player.inventory

    def select(self, item):
        self.bag.selected = next(i for i, slot in enumerate(self.bag.slots) if slot and slot.item == item)

    def click(self, target):
        origin = camera_origin(self.session, DEFAULT_CONFIG)
        self.state.step(InputFrame(destination_click=screen_center(self.room.surface_position(target), origin,
                                                                   DEFAULT_CONFIG)), 0)
        for _ in range(100):
            self.state.step(InputFrame(), .05)
            if self.state.inventory_open or (target in self.room.objects and self.state._pending_target is None):
                return

    def test_crafted_at_the_bag_placed_turned_and_opened(self):
        recipe = next(r for r in RECIPES["bench"] if r.product == "bench")
        self.assertEqual({"wood": 6, "stone": 2}, recipe.costs)
        for item, qty in recipe.costs.items():
            self.bag.add(item, qty)
        self.assertTrue(self.session.craft_at_bench(recipe).success)
        self.select("bench")
        target = GridPos(7, 6)
        origin = camera_origin(self.session, DEFAULT_CONFIG)
        pointer = screen_center(self.room.surface_position(target), origin, DEFAULT_CONFIG)
        self.state.step(InputFrame(pointer=pointer, wheel_steps=1), 0)
        self.assertEqual("Bancada girada.", self.session.last_message)
        self.click(target)
        bench = self.room.objects[target]
        self.assertIs(ObjectKind.BENCH, bench.kind)
        self.assertEqual("right", bench.variant)
        self.assertEqual(0, self.bag.quantity("bench"))
        self.click(target)
        self.assertTrue(self.state.inventory_open)
        self.assertEqual("bench", self.state.craft_panel.equipment)
        self.assertIsNone(self.state.craft_panel.production)
        torch = next(r for r in RECIPES["bench"] if r.product == "torch")
        self.bag.add("wood", 2)
        self.assertTrue(self.session.craft_at_bench(torch).success)
        self.state.step(InputFrame(inventory_pressed=True), 0)
        self.assertFalse(self.state.inventory_open)
        player = self.session.player
        player.facing = target - player.position
        self.state.step(InputFrame(pack_furniture_pressed=True), 0)
        self.assertNotIn(target, self.room.objects)
        self.assertEqual(1, self.bag.quantity("bench"))

    def test_each_side_is_drawn_and_clicked_on_its_own_pixels(self):
        left = WorldObject.create(GridPos(7, 7), ObjectKind.BENCH, variant="left")
        right = WorldObject.create(GridPos(7, 7), ObjectKind.BENCH, variant="right")
        self.assertTrue(object_contains(left, 0, -8))
        self.assertTrue(object_contains(left, 0, 7))
        self.assertFalse(object_contains(left, 0, -20))
        pygame.font.init()
        renderer = PlaceholderRenderer(pygame.Surface((960, 540)), DEFAULT_CONFIG)
        a, _ = renderer._caster_image("object", left)
        b, _ = renderer._caster_image("object", right)
        self.assertNotEqual(pygame.image.tobytes(a, "RGBA"), pygame.image.tobytes(b, "RGBA"))
        renderer.draw_gameplay(self.session, debug=False)

    def test_the_native_art_pack_draws_the_bench_not_a_rock(self):
        from spawnbound.prototype_art import PrototypeArtRenderer
        manifest = Path(__file__).resolve().parents[1] / "assets/native_32/manifest.json"
        renderer = PrototypeArtRenderer(pygame.Surface((960, 540)), DEFAULT_CONFIG, manifest)
        bench = WorldObject.create(GridPos(7, 7), ObjectKind.BENCH, variant="right")
        self.assertEqual("bench", renderer.object_name(bench))
        self.assertNotIn("bench", renderer.art.images)
        self.assertIsNone(renderer.hit_test("object", bench, 0, -8))


if __name__ == "__main__":
    unittest.main()
