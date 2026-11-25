import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import pygame
from spawnbound.config import GameConfig
from spawnbound.domain.daylight import DayPhase, Daylight
from spawnbound.domain.model import SpaceKind
from spawnbound.domain.session import GameSession
from spawnbound.input import InputFrame
from spawnbound.renderer import AmbientLighting
from spawnbound.states import GameplayState, StateStack
from spawnbound.animation import MotionKind, PlayerPose
from spawnbound.torchlight import carried_strength, draw_lighting, hand_center
from spawnbound.view import camera_origin, screen_center


class DaylightTests(unittest.TestCase):
    def test_lantern_fades_at_dusk_and_dawn_and_lights_only_its_patch(self):
        cfg = GameConfig()
        session = GameSession.create(42, cfg, chunk_preview_size=24)
        pose = PlayerPose(MotionKind.IDLE, session.player.facing)
        player = session.player.position3d
        origin = camera_origin(session, cfg, player)
        x, y = hand_center(screen_center(player, origin, cfg), cfg.world_art_scale, pose)
        for t, expected in ((0, 0), (30, 0), (57, .5), (60, 1), (87, .5), (0, 0)):
            session.cycle_seconds = t
            self.assertAlmostEqual(expected, carried_strength(session))
            target = pygame.Surface((960, 540), depth=32)
            target.fill((175, 165, 150))
            draw_lighting(target, session, AmbientLighting(), cfg, origin, player, pose)
            center, far = target.get_at((x, y)), target.get_at((x+120, y))
            if expected:
                self.assertGreater(center.r, far.r)
                self.assertGreater(center.r-center.b, far.r-far.b)
            else:
                self.assertEqual(center, far)
    def test_period_boundaries_and_wrap(self):
        for seconds, phase in ((0, DayPhase.DAY), (29.99, DayPhase.DAY), (30, DayPhase.AFTERNOON),
                               (59.99, DayPhase.AFTERNOON), (60, DayPhase.NIGHT), (90, DayPhase.DAY)):
            self.assertEqual(phase, Daylight.at(seconds, (30, 30, 30)).phase)
        self.assertAlmostEqual(0.5, Daylight.at(27, (30, 30, 30)).blend)
        cfg = GameConfig(day_seconds=2, afternoon_seconds=3, night_seconds=4)
        self.assertEqual(DayPhase.NIGHT, Daylight.at(14, cfg.phase_durations).phase)
        with self.assertRaises(ValueError):
            GameConfig(night_seconds=0)

    def test_pause_freezes_clock_and_indoor_time_reaches_exterior(self):
        cfg = GameConfig()
        session = GameSession.create(1234, cfg, chunk_preview_size=24)
        stack = StateStack(GameplayState(session, cfg))
        stack.step(InputFrame(), 28)
        stack.step(InputFrame(pause_pressed=True), 0)
        stack.step(InputFrame(), 90)
        self.assertEqual(28, session.cycle_seconds)
        stack.step(InputFrame(pause_pressed=True), 0)
        outdoors = session.world
        light = AmbientLighting()
        for kind in (SpaceKind.CAVE, SpaceKind.INTERIOR):
            portal = next(p for p in outdoors.portals.values() if p.target_kind is kind)
            session.world, _ = session.spaces.resolve(outdoors, portal)
            stack.step(InputFrame(), 17)
            target = pygame.Surface((1, 1))
            target.fill((150, 150, 150))
            light.draw(target, session)
            pixel = target.get_at((0, 0))
            if kind is SpaceKind.CAVE:
                self.assertTrue(0 < pixel.r < pixel.b < 50)
            else:
                self.assertEqual((150, 150, 150), pixel[:3])
        session.world = outdoors
        self.assertEqual(DayPhase.NIGHT, session.daylight.phase)
        light.draw(target, session)
        red, green, blue, _ = target.get_at((0, 0))
        self.assertTrue(red < green < blue < 150)
