import os
import sys
import unittest
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import pygame

from spawnbound.config import DEFAULT_CONFIG
from spawnbound.domain.coordinates import GridPos
from spawnbound.domain.model import ObjectKind, SpaceKind, WorldObject
from spawnbound.domain.session import GameSession
from spawnbound.input import InputFrame
from spawnbound.renderer import PlaceholderRenderer
from spawnbound.states import GameplayState
from spawnbound.view import camera_origin, object_contains, screen_center


class KilnTurnTests(unittest.TestCase):
    def setUp(self):
        session = GameSession.create(1234, DEFAULT_CONFIG, chunk_preview_size=32)
        entrance = next(p for p in session.world.portals.values() if p.target_kind is SpaceKind.INTERIOR)
        session.player.place(session.world.surface_position(entrance.approach))
        session.player.facing = entrance.position - entrance.approach
        self.assertTrue(session.interact().success)
        self.session, self.room = session, session.world
        self.state = GameplayState(session, DEFAULT_CONFIG)
        bag = session.player.inventory
        bag.add("kiln", 2)
        bag.selected = next(i for i, slot in enumerate(bag.slots) if slot and slot.item == "kiln")

    def point(self, target):
        return screen_center(self.room.surface_position(target), camera_origin(self.session, DEFAULT_CONFIG),
                             DEFAULT_CONFIG)

    def place(self, target):
        self.state.step(InputFrame(destination_click=self.point(target)), 0)
        for _ in range(100):
            self.state.step(InputFrame(), .05)
            if target in self.room.objects:
                return self.room.objects[target]
        self.fail("the kiln was not placed")

    def test_the_wheel_turns_the_mouth_before_placing(self):
        target = GridPos(7, 7)
        pointer = self.point(target)
        slot = self.session.player.inventory.selected
        self.state.step(InputFrame(pointer=pointer), 0)
        self.assertEqual("left", self.state._placement_preview[3])
        self.state.step(InputFrame(pointer=pointer, wheel_steps=1), 0)
        self.assertIn("direita", self.session.last_message)
        self.assertEqual(slot, self.session.player.inventory.selected)
        self.state.step(InputFrame(pointer=pointer), 0)
        self.assertEqual("right", self.state._placement_preview[3])
        self.assertEqual("right", self.place(target).variant)
        self.assertEqual("right", self.place(GridPos(4, 7)).variant)

    def test_turning_back_and_the_wheel_elsewhere_changes_the_slot(self):
        pointer = self.point(GridPos(7, 7))
        self.state.step(InputFrame(pointer=pointer, wheel_steps=1), 0)
        self.state.step(InputFrame(pointer=pointer, wheel_steps=-1), 0)
        self.assertIn("esquerda", self.session.last_message)
        self.assertEqual("left", self.place(GridPos(7, 7)).variant)
        bag = self.session.player.inventory
        from spawnbound.view import hotbar_rect
        left, top, width, height = hotbar_rect(DEFAULT_CONFIG)
        slot = bag.selected
        self.state.step(InputFrame(pointer=(left + width // 2, top + height // 2), wheel_steps=1), 0)
        self.assertNotEqual(slot, bag.selected)
        bag.add("torch", 1)
        bag.selected = next(i for i, slot in enumerate(bag.slots) if slot and slot.item == "torch")
        message, slot = self.session.last_message, bag.selected
        self.state.step(InputFrame(pointer=pointer, wheel_steps=1), 0)
        self.assertEqual(message, self.session.last_message)
        self.assertNotEqual(slot, bag.selected)
        bag.selected = slot
        self.session.player.place(self.room.surface_position(GridPos(4, 5)))
        result = self.session.place_furniture(GridPos(4, 4), "torch", "right")
        self.assertTrue(result.success, result.message)
        self.assertEqual("default", self.room.objects[GridPos(4, 4)].variant)

    def test_each_side_is_drawn_and_clicked_on_its_own_pixels(self):
        left = WorldObject.create(GridPos(7, 7), ObjectKind.KILN, variant="left")
        right = WorldObject.create(GridPos(7, 7), ObjectKind.KILN, variant="right")
        self.assertTrue(object_contains(left, -14, -13))
        self.assertFalse(object_contains(right, -14, -13))
        self.assertTrue(object_contains(right, 14, -13))
        self.assertFalse(object_contains(left, 14, -13))
        pygame.font.init()
        renderer = PlaceholderRenderer(pygame.Surface((960, 540)), DEFAULT_CONFIG)
        a, _ = renderer._caster_image("object", left)
        b, _ = renderer._caster_image("object", right)
        self.assertNotEqual(pygame.image.tobytes(a, "RGBA"), pygame.image.tobytes(b, "RGBA"))
        self.assertGreater(a.get_bounding_rect().h, 45)


if __name__ == "__main__":
    unittest.main()
