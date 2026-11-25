import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "dependencias")]
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame

from spawnbound import item_icons, rest_menu
from spawnbound.campfire_art import FOOT, FRAMES, SIZE, campfire, flame, flame_frame, placed_campfire
from spawnbound.config import DEFAULT_CONFIG
from spawnbound.domain.coordinates import GridPos
from spawnbound.domain.crafting import FURNITURE, RECIPES
from spawnbound.domain.daylight import DayPhase
from spawnbound.domain.model import ObjectKind, WorldObject
from spawnbound.domain.mobs import MobKind
from spawnbound.domain.session import REST_HEARTS, ActionCode, GameSession
from spawnbound.input import InputFrame
from spawnbound.renderer import PlaceholderRenderer
from spawnbound.states import GameplayState
from spawnbound.view import camera_origin, object_contains, screen_center

DAY, AFTERNOON, NIGHT = DEFAULT_CONFIG.phase_durations
SIDES = (GridPos(1, 0), GridPos(0, 1), GridPos(-1, 0), GridPos(0, -1))


def _hot(image):
    return sum(1 for x in range(SIZE[0]) for y in range(SIZE[1])
               if image.get_at((x, y)).a and image.get_at((x, y)).r > 200 and image.get_at((x, y)).b < 120)


class CampfireArtTests(unittest.TestCase):
    def test_stones_and_logs_without_fire_and_a_flame_that_moves(self):
        body = campfire()
        self.assertLess(_hot(body), 10)
        lavender = sum(1 for x in range(SIZE[0]) for y in range(SIZE[1])
                       if body.get_at((x, y)).a and body.get_at((x, y)).b > body.get_at((x, y)).g + 15)
        self.assertGreater(lavender, 150)
        pictures = {pygame.image.tobytes(flame(k), "RGBA") for k in range(FRAMES)}
        self.assertEqual(FRAMES, len(pictures))
        for k in range(FRAMES):
            with self.subTest(frame=k):
                box = flame(k).get_bounding_rect()
                self.assertTrue(box.top > 0 and box.left > 0 and box.right < SIZE[0])
                self.assertLess(box.bottom, FOOT[1])
                self.assertGreater(_hot(flame(k)), 120)
                colours = {flame(k).get_at((x, y))[:3] for x in range(SIZE[0]) for y in range(SIZE[1])
                           if flame(k).get_at((x, y)).a}
                self.assertIn((255, 250, 210), colours)
        self.assertGreater(body.get_bounding_rect().bottom, FOOT[1])
        self.assertEqual({flame_frame(t / 10) for t in range(20)}, set(range(FRAMES)))
        self.assertNotEqual(flame_frame(.5, 0), flame_frame(.5, 1))

    def test_icon_name_and_click_area(self):
        self.assertEqual("Fogueira", item_icons.ITEMS["campfire"][0])
        self.assertEqual((32, 32), item_icons.icon("campfire").get_size())
        obj = WorldObject.create(GridPos(4, 4), ObjectKind.CAMPFIRE)
        self.assertTrue(object_contains(obj, 0, -18))
        self.assertTrue(object_contains(obj, -10, 0))
        self.assertFalse(object_contains(obj, 0, -40))
        self.assertFalse(object_contains(obj, 22, 0))


class CampfireUseTests(unittest.TestCase):
    def setUp(self):
        self.session = GameSession.create(1234, DEFAULT_CONFIG, chunk_preview_size=128)
        self.session.wildlife.mobs.clear()
        self.bag = self.session.player.inventory
        self.state = GameplayState(self.session, DEFAULT_CONFIG)

    def _place(self):
        recipe = next(r for r in RECIPES["bench"] if r.product == "campfire")
        self.assertEqual({"coal": 3, "stone": 5}, FURNITURE["campfire"])
        self.assertEqual({"coal": 3, "stone": 5}, recipe.costs)
        self.bag.add("coal", 3)
        self.bag.add("stone", 5)
        self.assertTrue(self.session.craft_at_bench(recipe).success)
        self.assertEqual((0, 0, 1), (self.bag.quantity("coal"), self.bag.quantity("stone"),
                                     self.bag.quantity("campfire")))
        self.bag.selected = next(i for i, s in enumerate(self.bag.slots) if s and s.item == "campfire")
        player = self.session.player
        side = next(d for d in SIDES if self.session.can_place(player.position + d))
        cell = player.position + side
        self.assertTrue(self.session.place_furniture(cell, "campfire").success)
        player.facing = side
        return cell

    def test_placed_and_picked_up_like_furniture(self):
        cell = self._place()
        world = self.session.world
        self.assertIs(ObjectKind.CAMPFIRE, world.objects[cell].kind)
        self.assertIn(cell, world.placed_fires)
        self.assertFalse(world.is_walkable(cell))
        self.assertEqual(cell, self.session.campfire_beside())
        self.assertTrue(self.session.take_furniture().success)
        self.assertNotIn(cell, world.placed_fires)
        self.assertEqual(1, self.bag.quantity("campfire"))

    def test_e_r_or_a_click_open_the_rest_point_and_esc_closes_it(self):
        cell = self._place()
        self.assertIs(ActionCode.CAMPFIRE_OPENED, self.session.interact().code)
        self.assertIs(ActionCode.CAMPFIRE_OPENED, self.session.rest().code)
        for opening in (InputFrame(interact_pressed=True), InputFrame(rest_pressed=True)):
            with self.subTest(opening=opening):
                self.state.step(opening, 0)
                self.assertTrue(self.state.rest_open)
                self.state.step(InputFrame(pause_pressed=True), 0)
                self.assertFalse(self.state.rest_open)
        origin = camera_origin(self.session, DEFAULT_CONFIG)
        point = screen_center(self.session.world.surface_position(cell), origin, DEFAULT_CONFIG)
        self.state.step(InputFrame(destination_click=(point[0], point[1] - 10)), 0)
        for _ in range(40):
            if self.state.rest_open:
                break
            self.state.step(InputFrame(), .05)
        self.assertTrue(self.state.rest_open)

    def test_resting_at_night_sleeps_to_morning_for_half_the_energy_and_two_hearts(self):
        self._place()
        session = self.session
        session.cycle_seconds = DAY + AFTERNOON + NIGHT * .3
        session.advance_time(0)
        self.assertTrue(session.wildlife.night_spawned)
        session.player.energy, session.player.hearts = 20, 5
        before = session.production_seconds
        self.state.step(InputFrame(interact_pressed=True), 0)
        self.state.step(InputFrame(destination_click=rest_menu.layout(DEFAULT_CONFIG)[2].center), 0)
        self.assertFalse(self.state.rest_open)
        self.assertIs(DayPhase.DAY, session.daylight.phase)
        self.assertAlmostEqual(0, session.cycle_seconds, places=3)
        self.assertEqual((20 + session.player.max_energy // 2, 5 + REST_HEARTS),
                         (session.player.energy, session.player.hearts))
        self.assertIn(f"e {REST_HEARTS} corações", session.last_message)
        self.assertAlmostEqual(before + NIGHT * .7, session.production_seconds, places=3)
        self.assertFalse(session.wildlife.night_spawned)
        self.assertFalse(any(m.kind is MobKind.SKELETON for m in session.wildlife.mobs.values()))
        session.player.energy = session.player.max_energy - 10
        session.player.hearts = DEFAULT_CONFIG.starting_hearts - 1
        session.cycle_seconds = DAY + AFTERNOON * .5
        result = session.rest_until_morning()
        self.assertTrue(result.success)
        self.assertEqual((session.player.max_energy, DEFAULT_CONFIG.starting_hearts),
                         (session.player.energy, session.player.hearts))
        self.assertIn("e 1 coração.", result.message)

    def test_by_day_or_away_from_the_fire_nothing_happens(self):
        cell = self._place()
        session = self.session
        session.cycle_seconds = DAY * .5
        session.player.energy = 20
        self.state.step(InputFrame(rest_pressed=True), 0)
        self.state.step(InputFrame(rest_pressed=True), 0)
        self.assertTrue(self.state.rest_open)
        self.assertEqual((20, DAY * .5), (session.player.energy, session.cycle_seconds))
        self.assertIn("dia", session.last_message)
        session.cycle_seconds = DAY + AFTERNOON + 1
        session.player.position = cell + GridPos(3, 3)
        self.assertIsNone(session.campfire_beside())
        self.assertFalse(session.rest_until_morning().success)
        self.assertEqual(20, session.player.energy)

    def test_both_renderers_draw_the_stones_by_code_and_the_flame_as_an_actor(self):
        from spawnbound.prototype_art import PrototypeArtRenderer
        pygame.font.init()
        cell = self._place()
        art = PrototypeArtRenderer(pygame.Surface((960, 540)), DEFAULT_CONFIG, ROOT / "assets/native_32/manifest.json")
        plain = PlaceholderRenderer(pygame.Surface((960, 540)), DEFAULT_CONFIG)
        obj = self.session.world.objects[cell]
        self.assertNotIn(art.object_name(obj), art.art.images)
        sprite, (fx, fy) = placed_campfire()
        for renderer in (art, plain):
            with self.subTest(renderer=type(renderer).__name__):
                body, foot = renderer._caster_image("object", obj)
                region = pygame.Rect(foot[0] - fx, foot[1] - fy, *sprite.get_size())
                self.assertEqual(pygame.image.tobytes(sprite, "RGBA"),
                                 pygame.image.tobytes(body.subsurface(region), "RGBA"))
                fires = [a for a in renderer._actors(self.session, self.session.player.position3d) if a.kind == "fire"]
                self.assertEqual([cell], [a.position for a in fires])
                frames = set()
                for k in range(FRAMES):
                    self.session.cycle_seconds = k / 9
                    frames.add(renderer._actor_state(self.session, fires[0], (0, 0), (0, 0))[1])
                self.assertEqual(FRAMES, len(frames))
        plain.draw_gameplay(self.session, debug=False, rest_view=(True, "rest"))
        plain.draw_gameplay(self.session, debug=False, rest_view=(False, "cook"))


if __name__ == "__main__":
    unittest.main()
