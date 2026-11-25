import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "dependencias")]
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame

from spawnbound import skeleton_art
from spawnbound.domain.mobs import MobKind
from spawnbound.mob_art import ANCHOR, CANVAS, posed_pixels, sprite
from spawnbound.skeleton_art import ARROW, BONE, INK, STRING, WOOD, archer, skeleton

POSES = [(0, "idle"), (0, "walk"), (1, "walk"), (0, "draw"), (0, "release"), (0, "rest")]


def skull(pixels):
    return {p: c for p, c in pixels.items() if p[1] <= -8 and abs(p[0]) <= 5}


class SkeletonArtTests(unittest.TestCase):
    def test_every_pose_is_its_own_drawing_and_fits_the_creature_canvas(self):
        drawings = set()
        for stride, stance in POSES:
            pixels = archer(stride, stance)
            with self.subTest(stance=stance, stride=stride):
                xs, ys = [x for x, _ in pixels], [y for _, y in pixels]
                self.assertTrue(-ANCHOR[0] <= min(xs) and max(xs) < CANVAS[0] - ANCHOR[0])
                self.assertTrue(-ANCHOR[1] <= min(ys) and max(ys) < CANVAS[1] - ANCHOR[1])
                self.assertTrue(any((x, 1) in pixels for x in (-2, -1, 1, 2)))
                self.assertLessEqual(max(ys), 2)
                self.assertTrue(18 <= 1 - min(ys) <= 22)
            drawings.add(frozenset(pixels.items()))
        self.assertEqual(len(POSES), len(drawings))

    def test_the_skull_has_slanted_sockets_a_nose_and_teeth(self):
        pixels = archer(0, "idle")
        socket = BONE["e"]
        eyes = sorted(p for p, c in pixels.items() if c == socket)
        self.assertGreaterEqual(len(eyes), 10)
        top = min(y for _, y in eyes)
        self.assertEqual(2, sum(1 for _, y in eyes if y == top))
        self.assertTrue(any(c == BONE["W"] for (x, y), c in pixels.items() if y == top + 4))

    def test_every_part_has_an_ink_outline(self):
        for stride, stance in POSES:
            pixels = archer(stride, stance)
            for (x, y), color in pixels.items():
                if color == INK:
                    continue
                for n in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
                    with self.subTest(stance=stance, pixel=(x, y)):
                        self.assertIn(n, pixels)

    def test_the_bow_is_drawn_back_with_an_arrow_and_snaps_on_release(self):
        draw, release, idle = archer(0, "draw"), archer(0, "release"), archer(0, "idle")
        wood = set(WOOD.values())
        for pixels in (draw, release, idle):
            self.assertGreater(sum(c in wood for c in pixels.values()), 12)
            self.assertTrue(all(x > 0 for (x, y), c in pixels.items() if c in wood))
        self.assertIn(ARROW["t"], draw.values())
        self.assertNotIn(ARROW["t"], release.values())
        self.assertNotIn(ARROW["t"], idle.values())
        reach = lambda pixels: min(x for (x, y), c in pixels.items() if c == STRING)
        self.assertLessEqual(reach(draw), reach(release) - 2)

    def test_the_base_body_is_shared_so_other_weapons_can_come(self):
        bare = {"idle": lambda: ("body",), "draw": lambda: ("body",), "release": lambda: ("body",)}
        skeleton_art.WEAPONS["bare"] = bare
        try:
            for stride, stance in POSES:
                with self.subTest(stance=stance):
                    body = skeleton("bare", stride, stance)
                    self.assertFalse(set(WOOD.values()) & set(body.values()))
                    self.assertEqual(skull(body), skull(archer(stride, stance)))
        finally:
            del skeleton_art.WEAPONS["bare"]
            skeleton_art._skeleton.cache_clear()

    def test_the_game_draws_it_facing_both_ways_and_flashes_when_hurt(self):
        right = posed_pixels(MobKind.SKELETON, False, 0, "draw")
        left = posed_pixels(MobKind.SKELETON, True, 0, "draw")
        self.assertEqual({(-x, y): c for (x, y), c in right.items()}, left)
        hurt = posed_pixels(MobKind.SKELETON, False, 0, "hurt")
        self.assertNotEqual(set(hurt.values()), set(right.values()))
        self.assertTrue(all(r >= g and r >= b for r, g, b in hurt.values()))
        image = sprite(MobKind.SKELETON, False, 0, "idle", 2.)
        self.assertEqual((CANVAS[0] * 2, CANVAS[1] * 2), image.get_size())
        self.assertGreater(pygame.mask.from_surface(image).count(), 600)


if __name__ == "__main__":
    unittest.main()
