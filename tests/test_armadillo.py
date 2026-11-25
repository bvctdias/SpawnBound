import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "dependencias")]
import pygame

from spawnbound.config import DEFAULT_CONFIG
from spawnbound.domain.coordinates import GridPos
from spawnbound.domain.generation import WorldGenerator
from spawnbound.domain.mobs import (SWORD_DAMAGE, ARMADILLO_AREA, ARMADILLO_SPACING, ARMADILLO_WARY, BOLT_SECONDS, CURL_SECONDS,
                                    HEALTH, SAFE_START, Mob, MobKind, Wildlife, chebyshev, distance)
from spawnbound.domain.model import Biome
from spawnbound.mob_art import ANCHOR, CANVAS, mob_pose, pick_pixels, posed_pixels
from spawnbound.renderer import PlaceholderRenderer

sys.path.insert(0, str(ROOT / "tests"))
from test_wild_fauna import flat_session, put, run  # noqa: E402


class ArmadilloPlacementTests(unittest.TestCase):
    def test_each_desert_gets_armadillos_by_its_size(self):
        for seed in (1234, 7, 39658298):
            world = WorldGenerator().generate_chunk_preview(seed, 128)
            life = Wildlife(world)
            armadillos = [m for m in life.mobs.values() if m.kind is MobKind.ARMADILLO]
            with self.subTest(seed=seed):
                self.assertGreaterEqual(len(armadillos), 5)
                for index, target in enumerate(life._armadillo_target):
                    region = sum(1 for d in life._desert_of.values() if d == index)
                    self.assertEqual(-(-region // ARMADILLO_AREA), target)
                    self.assertLessEqual(life.armadillos_in(index), target)
                for a in armadillos:
                    self.assertIs(Biome.DRY, world.tile_map.tile_at(a.end.grid).biome)
                    self.assertGreaterEqual(chebyshev(a.end, world.spawn), SAFE_START)
                    self.assertTrue(all(chebyshev(a.end, b.end) >= ARMADILLO_SPACING
                                        for b in armadillos if b is not a))
                    self.assertFalse(a.hostile)

    def test_a_hunted_armadillo_comes_back_out_of_sight(self):
        world = WorldGenerator().generate_chunk_preview(1234, 128)
        life = Wildlife(world)
        life.mobs = {uid: m for uid, m in life.mobs.items() if m.kind is not MobKind.ARMADILLO}
        life.in_view = lambda player, cell: False
        life._replenish_wild(world.surface_position(world.spawn))
        for index, target in enumerate(life._armadillo_target):
            self.assertEqual(min(1, target), life.armadillos_in(index))


class ArmadilloBehaviourTests(unittest.TestCase):
    def setUp(self):
        self.session = flat_session()
        self.player = self.session.player
        self.here = self.player.position

    def test_it_walks_away_from_a_close_player_at_its_own_pace(self):
        mob = put(self.session, MobKind.ARMADILLO, self.here + GridPos(2, 0))
        mob.wait = 5.
        self.assertFalse(run(self.session.wildlife, 4., self.player.position3d))
        self.assertGreater(chebyshev(mob.end, self.player.position3d), ARMADILLO_WARY)
        self.assertAlmostEqual(.46 * distance(mob.start, mob.end), mob.duration)
        for _ in range(60):
            run(self.session.wildlife, .1, self.player.position3d)
            self.assertGreater(chebyshev(mob.end, self.player.position3d), ARMADILLO_WARY)
        far = put(self.session, MobKind.ARMADILLO, self.here + GridPos(9, 9), uid=2)
        far.wait = 5.
        run(self.session.wildlife, 1., self.player.position3d)
        self.assertEqual(self.here + GridPos(9, 9), far.end.grid)

    def test_struck_it_curls_and_further_blows_bounce_off(self):
        session = self.session
        mob = put(session, MobKind.ARMADILLO, self.here + GridPos(1, 0))
        mob.wait = 5.
        result = session.attack_mob(mob.id)
        self.assertIn("enrolou", result.message)
        self.assertEqual((HEALTH[MobKind.ARMADILLO] - SWORD_DAMAGE, CURL_SECONDS), (mob.hp, mob.curled))
        self.assertEqual("ball_hurt", mob_pose(mob)[3])
        energy = self.player.energy
        result = session.attack_mob(mob.id)
        self.assertTrue(result.success)
        self.assertIn("não entra", result.message)
        self.assertEqual((HEALTH[MobKind.ARMADILLO] - SWORD_DAMAGE, energy - 5), (mob.hp, self.player.energy))
        cell = mob.end.grid
        run(session.wildlife, CURL_SECONDS - .2, self.player.position3d)
        self.assertEqual((cell, "ball"), (mob.end.grid, mob_pose(mob)[3]))
        run(session.wildlife, .4, self.player.position3d)
        self.assertEqual(0., mob.curled)
        self.assertGreater(mob.flee_time, BOLT_SECONDS - .5)
        run(session.wildlife, 1., self.player.position3d)
        self.assertGreaterEqual(chebyshev(mob.end, self.player.position3d), 3)

    def test_three_blows_that_land_give_meat_and_hide(self):
        session = self.session
        mob = put(session, MobKind.ARMADILLO, self.here + GridPos(1, 0))
        for blow in range(3):
            mob.wait = 5.
            mob.start = mob.end = session.world.surface_position(self.here + GridPos(1, 0))
            mob.curled = mob.flee_time = 0.
            result = session.attack_mob(mob.id)
        self.assertNotIn(mob.id, session.wildlife.mobs)
        bag = self.player.inventory
        self.assertEqual((1, 1), (bag.quantity("meat"), bag.quantity("hide")))
        self.assertIn("fogueira", result.message)

    def test_it_never_hurts_the_player(self):
        mob = put(self.session, MobKind.ARMADILLO, self.here + GridPos(1, 0))
        self.session.attack_mob(mob.id)
        self.assertFalse(mob.hostile)
        self.assertFalse(run(self.session.wildlife, 8., self.player.position3d))


class ArmadilloArtTests(unittest.TestCase):
    def test_poses_fit_the_canvas_and_the_ball_is_round(self):
        pictures = {}
        for stance, stride in (("idle", 0), ("walk", 0), ("walk", 1), ("run", 0), ("run", 1), ("rest", 0),
                               ("ball", 0), ("ball", 1)):
            pixels = posed_pixels(MobKind.ARMADILLO, False, stride, stance)
            pictures[stance, stride] = frozenset(pixels.items())
            with self.subTest(stance=stance, stride=stride):
                for x, y in pixels:
                    self.assertTrue(0 <= ANCHOR[0] + x < CANVAS[0] and 0 <= ANCHOR[1] + y < CANVAS[1])
                self.assertEqual(1, max(y for _, y in pixels))
        self.assertEqual(8, len(set(pictures.values())))
        body = posed_pixels(MobKind.ARMADILLO, False, 0, "idle")
        ball = posed_pixels(MobKind.ARMADILLO, False, 0, "ball")
        width = lambda p: max(x for x, _ in p) - min(x for x, _ in p) + 1
        height = lambda p: max(y for _, y in p) - min(y for _, y in p) + 1
        self.assertGreater(width(body), 1.5 * height(body))
        self.assertLessEqual(abs(width(ball) - height(ball)), 2)
        self.assertLess(width(ball), width(body))
        left = posed_pixels(MobKind.ARMADILLO, True, 0, "idle")
        self.assertEqual({(-x, y) for x, y in body}, set(left))
        colours = set(body.values())
        self.assertGreaterEqual(len([c for c in colours if c[0] > c[1] > c[2] and c[0] < 230]), 4)
        self.assertIn((244, 224, 214), colours)

    def test_picked_and_drawn_in_both_renderers(self):
        from spawnbound.prototype_art import PrototypeArtRenderer
        pygame.font.init()
        session = flat_session()
        here = session.player.position
        walker = put(session, MobKind.ARMADILLO, here + GridPos(2, 1))
        ball = put(session, MobKind.ARMADILLO, here + GridPos(1, 0), uid=2)
        session.attack_mob(ball.id)
        self.assertTrue(pick_pixels(walker) and pick_pixels(ball))
        art = PrototypeArtRenderer(pygame.Surface((960, 540)), DEFAULT_CONFIG, ROOT / "assets/native_32/manifest.json")
        plain = PlaceholderRenderer(pygame.Surface((960, 540)), DEFAULT_CONFIG)
        for renderer in (art, plain):
            renderer.draw_gameplay(session, debug=False)


if __name__ == "__main__":
    unittest.main()
