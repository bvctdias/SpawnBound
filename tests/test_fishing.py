import os
import random
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "dependencias")]

import pygame

from spawnbound.animation import MotionKind, PlayerPose
from spawnbound.config import DEFAULT_CONFIG
from spawnbound.domain.coordinates import GridPos
from spawnbound.domain.crafting import RECIPES
from spawnbound.domain.fish import FISH
from spawnbound.domain.fishing import (BAR, BITE_WINDOW, CHARGE_SECONDS, REACH, SHOW_SECONDS, START, Minigame,
                                       bite_delay, landing, power_at)
from spawnbound.domain.inventory import Stack, stack_limit
from spawnbound.domain.model import Biome, TileKind
from spawnbound.domain.session import ActionCode, GameSession
from spawnbound.domain.tools import TOOLS
from spawnbound.fishing_ui import rod_tip
from spawnbound.input import InputFrame
from spawnbound.pplay_host import PPlayHost
from spawnbound.renderer import PlaceholderRenderer
from spawnbound.states import GameplayState
from spawnbound.view import camera_origin, screen_center

HOLD, FREE = True, False


class MinigameTests(unittest.TestCase):
    def game(self, item="lambari", seed=1):
        return Minigame(FISH[item], random.Random(seed))

    def test_holding_lifts_the_bar_and_letting_go_lets_it_fall(self):
        game = self.game()
        for _ in range(30):
            game.step(1 / 60, HOLD)
        high = game.bar
        self.assertGreater(high, .1)
        self.assertGreater(game.bar_speed, 0)
        for _ in range(20):
            game.step(1 / 60, FREE)
        self.assertLess(game.bar_speed, 0, "gravity turns it around")
        for _ in range(200):
            game.step(1 / 60, HOLD)
        self.assertAlmostEqual(1 - BAR, game.bar, msg="it stops at the top")

    def test_the_bar_bounces_on_the_bottom(self):
        game = self.game()
        game.bar, game.bar_speed = .02, -1.2
        game.step(1 / 30, FREE)
        self.assertEqual(0, game.bar)
        self.assertGreater(game.bar_speed, 0)

    def test_the_meter_fills_inside_the_bar_and_drains_outside(self):
        game = self.game()
        game.fish_y, game.target, game.bar = .15, .15, 0.
        game.rng = SimpleNamespace(random=lambda: 1., uniform=lambda a, b: 0.)
        game.step(.05, FREE)
        self.assertGreater(game.progress, START)
        game.fish_y = game.target = .9
        before = game.progress
        game.step(.05, FREE)
        self.assertLess(game.progress, before)

    def test_a_full_meter_catches_and_an_empty_one_lets_go(self):
        game = self.game()
        game.rng = SimpleNamespace(random=lambda: 1., uniform=lambda a, b: 0.)
        game.fish_y = game.target = .1
        game.progress = .99
        self.assertEqual("caught", game.step(.05, FREE))
        game = self.game()
        game.rng = SimpleNamespace(random=lambda: 1., uniform=lambda a, b: 0.)
        game.fish_y = game.target = .9
        game.progress = .005
        self.assertEqual("escaped", game.step(.05, FREE))

    def test_the_fish_stays_on_the_track_and_harder_fish_swim_harder(self):
        def restless(item):
            total = 0.
            for seed in range(6):
                game = self.game(item, seed)
                game.progress = .5
                for _ in range(600):
                    game.step(1 / 60, FREE)
                    game.progress = .5
                    self.assertTrue(0 <= game.fish_y <= 1)
                    total += abs(game.fish_speed)
            return total
        self.assertGreater(restless("atum"), 1.5 * restless("lambari"))

    def test_sinkers_keep_low_and_floaters_keep_high(self):
        def mean_height(item):
            heights = []
            for seed in range(8):
                game = self.game(item, seed)
                for _ in range(900):
                    game.step(1 / 60, FREE)
                    game.progress = .5
                    heights.append(game.fish_y)
            return sum(heights) / len(heights)
        self.assertLess(mean_height("garoupa"), .4)
        self.assertGreater(mean_height("baiacu"), .6)


class CastTests(unittest.TestCase):
    def test_the_power_bar_rises_and_falls(self):
        self.assertEqual(0, power_at(0))
        self.assertAlmostEqual(.5, power_at(CHARGE_SECONDS / 2))
        self.assertAlmostEqual(1, power_at(CHARGE_SECONDS))
        self.assertAlmostEqual(.5, power_at(1.5 * CHARGE_SECONDS))

    def test_the_bobber_falls_short_without_power(self):
        start, aim = GridPos(0, 0), GridPos(5, 0)
        self.assertEqual(aim, landing(start, aim, 1.))
        short = landing(start, aim, 0.)
        self.assertEqual(GridPos(round(REACH[0]), 0), short)
        self.assertEqual(GridPos(1, 1), landing(start, GridPos(1, 1), 0.))

    def test_bites_come_sooner_beside_a_fish_shelter(self):
        far = [bite_delay(random.Random(seed), False) for seed in range(20)]
        near = [bite_delay(random.Random(seed), True) for seed in range(20)]
        self.assertTrue(all(n < f for n, f in zip(near, far)))


class RodTests(unittest.TestCase):
    def test_the_bench_makes_the_rod_of_one_wood_and_three_silks(self):
        recipe = next(r for r in RECIPES["bench"] if r.product == "fishing_rod")
        self.assertEqual({"wood": 1, "silk": 3}, recipe.costs)
        self.assertIn("fishing_rod", TOOLS)
        self.assertEqual(1, stack_limit("fishing_rod"))
        game = GameSession.create(7, DEFAULT_CONFIG, chunk_preview_size=24)
        bag = game.player.inventory
        bag.add("wood", 1)
        bag.add("silk", 3)
        result = game.craft_at_bench(recipe)
        self.assertIs(ActionCode.CRAFTED, result.code)
        self.assertEqual(1, bag.quantity("fishing_rod"))
        self.assertEqual(0, bag.quantity("silk"))

    def test_the_rod_has_its_sheet_and_its_tip_in_every_frame_used(self):
        import json
        spec = json.loads((ROOT / "assets/native_32/player/animation.json").read_text(encoding="utf-8"))
        self.assertEqual("fishing_rod.png", spec["upgrades"]["fishing_rod"])
        pygame.init()
        right = GridPos(1, 0)
        idle = rod_tip(PlayerPose(MotionKind.IDLE, right, 0.))
        drawn_back = rod_tip(PlayerPose(MotionKind.STRIKE, right, 0., .3))
        self.assertGreater(idle[0], 6, "the tip ahead of the explorer")
        self.assertLess(idle[1], -12, "and above the waist")
        self.assertLess(drawn_back[0], idle[0], "drawn back to cast")
        left = rod_tip(PlayerPose(MotionKind.IDLE, GridPos(-1, 0), 0.))
        self.assertLess(left[0], 0, "the tip on the other side")


class FishingFlowTests(unittest.TestCase):
    def setUp(self):
        self.game = GameSession.create(7, DEFAULT_CONFIG, chunk_preview_size=24)
        self.game.wildlife.mobs.clear()
        world = self.world = self.game.world
        world.objects.clear()
        world.portals.clear()
        world.crops.clear()
        world.fish_refuges.clear()
        self.home = self.game.player.position
        level = self.game.player.elevation
        for p in tuple(world.tile_map.tiles):
            water = p.x >= self.home.x + 2
            world.tile_map.add(p, TileKind.WATER if water else TileKind.GRASS, biome=Biome.MEADOW,
                               elevation=level - 1 if water else level)
        self.bag = self.game.player.inventory
        self.bag.slots[4] = Stack("fishing_rod", 1)
        self.bag.selected = 4
        self.state = GameplayState(self.game, DEFAULT_CONFIG)
        self.state.fishing_rng = random.Random(5)
        self.water = self.home + GridPos(4, 0)

    def click(self, cell, water=True):
        origin = camera_origin(self.game, DEFAULT_CONFIG, self.state.visual_position3d)
        x, y = screen_center(self.world.surface_position(cell), origin, DEFAULT_CONFIG)
        return x, y - (DEFAULT_CONFIG.water_lift if water else 0)

    def step(self, frame=None, seconds=1 / 30):
        self.state.step(frame or InputFrame(), seconds)

    def cast(self, hold_seconds=CHARGE_SECONDS):
        self.step(InputFrame(destination_click=self.click(self.water), primary_held=True), 0)
        self.assertIsNotNone(self.state.fishing, self.game.last_message)
        self.assertEqual("charging", self.state.fishing.phase)
        held = 0.
        while held < hold_seconds - 1e-9:
            self.step(InputFrame(primary_held=True), min(1 / 30, hold_seconds - held))
            held += 1 / 30
        self.step()
        self.assertEqual("casting", self.state.fishing.phase)
        for _ in range(40):
            self.step()

    def wait_for_bite(self):
        for _ in range(400):
            if self.state.fishing.phase == "bite":
                return
            self.step()
        self.fail("no bite")

    def test_a_click_on_water_with_the_rod_casts_and_on_land_walks(self):
        self.step(InputFrame(destination_click=self.click(self.home + GridPos(0, 2), water=False)), 0)
        self.assertIsNone(self.state.fishing)
        self.cast()
        self.assertEqual("waiting", self.state.fishing.phase)
        self.assertEqual(self.water, self.state.fishing.bobber)
        self.assertEqual(GridPos(1, 0), self.game.player.facing)

    def test_without_the_rod_a_click_on_water_does_not_fish(self):
        self.bag.selected = 0
        self.step(InputFrame(destination_click=self.click(self.water)), 0)
        self.assertIsNone(self.state.fishing)

    def test_too_little_power_drops_the_bobber_on_land(self):
        self.water = self.home + GridPos(6, 0)
        for p in tuple(self.world.tile_map.tiles):
            if p.x in (self.home.x + 2, self.home.x + 3):
                self.world.tile_map.add(p, TileKind.GRASS, biome=Biome.MEADOW, elevation=self.game.player.elevation)
        self.step(InputFrame(destination_click=self.click(self.water), primary_held=True), 0)
        self.step()
        for _ in range(40):
            self.step()
        self.assertIsNone(self.state.fishing)
        self.assertIn("fora da água", self.game.notice)

    def test_the_world_runs_while_waiting_and_stops_in_the_minigame(self):
        self.cast()
        clock = self.game.production_seconds
        self.step()
        self.assertGreater(self.game.production_seconds, clock)
        self.wait_for_bite()
        self.step(InputFrame(destination_click=(5, 5), primary_held=True))
        self.assertEqual("minigame", self.state.fishing.phase)
        clock = self.game.production_seconds
        for _ in range(10):
            self.step(InputFrame(primary_held=True))
        self.assertEqual(clock, self.game.production_seconds)

    def test_either_button_lifts_the_bar(self):
        self.cast()
        self.wait_for_bite()
        self.step(InputFrame(destination_click=(5, 5)))
        game = self.state.fishing.game
        game.progress = .5
        for _ in range(15):
            self.step(InputFrame(secondary_held=True))
            game.progress = .5
        self.assertGreater(game.bar, .1)
        self.assertGreater(game.bar_speed, 0)

    def test_a_full_meter_puts_the_fish_in_the_bag_and_shows_it(self):
        self.cast()
        self.wait_for_bite()
        self.step(InputFrame(destination_click=(5, 5)))
        run = self.state.fishing
        run.game.fish_y = run.game.target = .1
        run.game.rng = SimpleNamespace(random=lambda: 1., uniform=lambda a, b: 0.)
        run.game.progress = .999
        self.step()
        self.assertEqual("caught", run.phase)
        self.assertEqual(1, self.bag.quantity(run.fish.item))
        self.assertIn("Você pescou", self.game.last_message)
        for _ in range(round(SHOW_SECONDS * 30) + 2):
            self.step()
        self.assertIsNone(self.state.fishing)

    def test_an_empty_meter_lets_it_go(self):
        self.cast()
        self.wait_for_bite()
        self.step(InputFrame(destination_click=(5, 5)))
        run = self.state.fishing
        run.game.fish_y = run.game.target = .9
        run.game.rng = SimpleNamespace(random=lambda: 1., uniform=lambda a, b: 0.)
        run.game.progress = .005
        self.step()
        self.assertIsNone(self.state.fishing)
        self.assertIn("escapou", self.game.notice)
        self.assertEqual(0, sum(self.bag.quantity(item) for item in FISH))

    def test_a_missed_bite_goes_back_to_waiting(self):
        self.cast()
        self.wait_for_bite()
        for _ in range(round(BITE_WINDOW * 30) + 2):
            self.step()
        self.assertEqual("waiting", self.state.fishing.phase)
        self.assertEqual("O peixe soltou a isca.", self.game.last_message)

    def test_esc_another_slot_or_a_click_while_waiting_reels_in(self):
        self.cast()
        self.step(InputFrame(pause_pressed=True))
        self.assertIsNone(self.state.fishing)
        self.cast()
        self.step(InputFrame(destination_click=(400, 300)))
        self.assertIsNone(self.state.fishing)
        self.cast()
        self.step(InputFrame(hotbar_index=0))
        self.assertIsNone(self.state.fishing)
        self.assertEqual(0, self.bag.selected)

    def test_the_cast_is_drawn_back_then_swung(self):
        self.step(InputFrame(destination_click=self.click(self.water), primary_held=True), 0)
        self.assertIs(MotionKind.STRIKE, self.state.player_pose.motion)
        self.assertLess(self.state.player_pose.progress, .35)
        self.step(InputFrame(primary_held=True), .2)
        self.step()
        self.step(InputFrame(), .15)
        self.assertIs(MotionKind.STRIKE, self.state.player_pose.motion)
        self.assertGreater(self.state.player_pose.progress, .6)

    def test_every_phase_is_drawn(self):
        pygame.init()
        renderer = PlaceholderRenderer(pygame.Surface((960, 540)), DEFAULT_CONFIG)
        seen = set()
        self.step(InputFrame(destination_click=self.click(self.water), primary_held=True), 0)
        for _ in range(600):
            run = self.state.fishing
            if run is None:
                break
            seen.add(run.phase)
            before = pygame.image.tobytes(renderer._ui_screen, "RGBA") if run.phase == "minigame" else None
            self.state.draw(renderer)
            if run.phase == "charging":
                frame = InputFrame(primary_held=len(seen) and run.held < .5)
            elif run.phase == "bite":
                frame = InputFrame(destination_click=(5, 5))
            elif run.phase == "minigame":
                game = run.game
                frame = InputFrame(primary_held=game.bar + BAR / 2 < game.fish_y)
                game.progress = min(1., game.progress + .02)
            else:
                frame = InputFrame()
            self.step(frame)
        self.assertEqual({"charging", "casting", "waiting", "bite", "minigame", "caught"}, seen)


class RightButtonTests(unittest.TestCase):
    def test_the_host_reports_the_right_button_held_until_let_go(self):
        from unittest.mock import patch
        from PPlay.keyboard import Keyboard
        from PPlay.mouse import Mouse
        from PPlay.window import Window
        host = PPlayHost.__new__(PPlayHost)
        window = SimpleNamespace(eventos=[], screen_to_virtual_coords=lambda x, y: (x, y), keyboard=Keyboard())
        host.window, host.keyboard, host.mouse = window, window.keyboard, Mouse()

        def snapshot(events, right):
            window.eventos = events
            with patch.object(Window, "get_instance", return_value=window), \
                    patch("pygame.mouse.get_pressed", return_value=(False, False, right)), \
                    patch("pygame.mouse.get_pos", return_value=(10, 10)):
                return host._snapshot_input()

        frame = snapshot([pygame.event.Event(pygame.MOUSEBUTTONDOWN, button=3, pos=(10, 10))], True)
        self.assertTrue(frame.secondary_held)
        self.assertEqual((10, 10), frame.right_click)
        self.assertTrue(snapshot([], True).secondary_held)
        self.assertFalse(snapshot([pygame.event.Event(pygame.MOUSEBUTTONUP, button=3, pos=(10, 10))], False).secondary_held)


if __name__ == "__main__":
    unittest.main()
