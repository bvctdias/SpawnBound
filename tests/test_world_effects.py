from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "dependencias")]

import pygame
from PPlay.effects import ScreenEffects
from PPlay.particles import ParticleEmitter

from spawnbound.config import DEFAULT_CONFIG
from spawnbound.domain.coordinates import GridPos, WorldPos
from spawnbound.domain.model import ObjectKind, WorldObject
from spawnbound.pplay_ui import window
from spawnbound.world_effects import WOOD, Chips, Splash, WorldFeel, chip_colours, shake_offset


class EffectsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.window = window()
        self.window._delta_time = 1 / 30
        ScreenEffects._shake_time = 0
        self.addCleanup(setattr, self.window, "_delta_time", 0.)
        self.addCleanup(setattr, ScreenEffects, "_shake_time", 0)

    def session(self, **extra):
        values = dict(world=object(), afterimages=[], hurt_time=0.,
                      wildlife=SimpleNamespace(mobs={1: SimpleNamespace(boss=SimpleNamespace(stage=""))}))
        values.update(extra)
        return SimpleNamespace(**values)

    def test_chips_are_pplay_particles_that_fly_up_fall_and_draw_as_square_pixels(self) -> None:
        chips = Chips(50, 60, WOOD, size=2)
        self.assertIsInstance(chips, ParticleEmitter)
        chips.explodir(12)
        self.assertEqual(12, len(chips.particulas))
        self.assertTrue(all(p.vy < 0 and p.cor in WOOD for p in chips.particulas))
        for _ in range(8):
            chips.update()
        self.assertTrue(any(p.vy > 0 for p in chips.particulas), "gravity brings them down")
        surface = pygame.Surface((200, 200))
        chips.origin = (10, 0)
        from spawnbound.pplay_ui import draw_on
        draw_on(surface, chips)
        lit = {tuple(surface.get_at((x, y)))[:3] for x in range(200) for y in range(200)} - {(0, 0, 0)}
        self.assertTrue(lit, "the chips were drawn")
        for _ in range(60):
            chips.update()
        self.assertEqual([], chips.particulas, "PPlay ages them away")

    def test_the_screen_shakes_when_the_guardian_lands_or_punches_and_when_hurt(self) -> None:
        feel, session = WorldFeel(), self.session()
        surface = pygame.Surface((10, 10))
        feel.follow(session, (0, 0), surface, DEFAULT_CONFIG)
        self.assertEqual((0, 0), shake_offset())
        session.wildlife.mobs[1].boss.stage = "landed"
        feel.follow(session, (0, 0), surface, DEFAULT_CONFIG)
        self.assertEqual((2, .3), (ScreenEffects._shake_intensity, ScreenEffects._shake_time))
        ScreenEffects._shake_time = 0
        feel.follow(session, (0, 0), surface, DEFAULT_CONFIG)
        self.assertEqual(0, ScreenEffects._shake_time, "once per landing")
        session.hurt_time = .38
        feel.follow(session, (0, 0), surface, DEFAULT_CONFIG)
        self.assertEqual((1, .15), (ScreenEffects._shake_intensity, ScreenEffects._shake_time))
        offset = shake_offset()
        self.assertTrue(all(abs(v) <= 1 for v in offset))

    def test_a_broken_tree_throws_chips_in_its_colours_once(self) -> None:
        feel, session = WorldFeel(), self.session()
        surface = pygame.Surface((960, 540))
        feel.follow(session, (480, 100), surface, DEFAULT_CONFIG)
        tree = WorldObject("t", GridPos(3, 4), ObjectKind.TREE, 3, variant="autumn_red")
        self.assertIn((196, 76, 52), chip_colours(tree), "its leaves")
        session.afterimages.append(SimpleNamespace(destroyed=True, subject=tree, location=WorldPos(3, 4, 0)))
        session.afterimages.append(SimpleNamespace(destroyed=False, subject=tree, location=WorldPos(3, 4, 0)))
        feel.follow(session, (480, 100), surface, DEFAULT_CONFIG)
        self.assertEqual(1, len(feel.emitters))
        self.assertTrue({p.cor for p in feel.emitters[0].particulas} <= set(chip_colours(tree)))
        feel.follow(session, (480, 100), surface, DEFAULT_CONFIG)
        self.assertEqual(1, len(feel.emitters), "the same break throws chips once")

    def test_rocks_with_ore_add_its_colour(self) -> None:
        rock = WorldObject("r", GridPos(0, 0), ObjectKind.ROCK, 3, variant="copper_ore")
        self.assertIn((206, 116, 62), chip_colours(rock))

    def test_a_bite_splashes_drops_at_the_bobber(self) -> None:
        splash, surface = Splash(), pygame.Surface((300, 300))
        run = SimpleNamespace(phase="waiting")
        self.assertIsNone(splash.follow(surface, run, (100, 100), (0, 0), 2))
        run.phase = "bite"
        bounds = splash.follow(surface, run, (100, 100), (0, 0), 2)
        self.assertIsNotNone(bounds)
        self.assertLessEqual(abs(bounds.centerx - 100), 60)


if __name__ == "__main__":
    unittest.main()
