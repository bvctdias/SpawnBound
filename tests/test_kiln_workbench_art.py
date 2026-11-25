import os
import sys
import unittest
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import pygame

from spawnbound.kiln_workbench_art import BENCH_SIZE, CX, HOLE, KILN_SIZE, kiln, workbench


def rows(image, last=None):
    w, h = image.get_size()
    found = {}
    for y in range(h if last is None else last + 1):
        xs = [x for x in range(w) if image.get_at((x, y)).a]
        if xs:
            found[y] = xs
    return found


def light(image, xs, ys):
    values = [sum(image.get_at((x, y))[:3]) for x in xs for y in ys if image.get_at((x, y)).a]
    return sum(values) / len(values)


class KilnArtTests(unittest.TestCase):
    def test_the_mouth_turns_with_the_kiln(self):
        for right in (False, True):
            image = kiln(right)
            self.assertEqual(KILN_SIZE, image.get_size())
            dark = [x for x in range(image.get_width()) for y in range(29, 40) if image.get_at((x, y))[:3] == HOLE]
            self.assertGreater(len(dark), 30)
            mean = sum(dark) / len(dark)
            if right:
                self.assertGreater(mean, CX + 4)
            else:
                self.assertLess(mean, CX - 4)
        self.assertNotEqual(pygame.image.tobytes(kiln(False), "RGBA"), pygame.image.tobytes(kiln(True), "RGBA"))

    def test_the_shell_has_no_holes(self):
        for right in (False, True):
            for y, xs in rows(kiln(right)).items():
                self.assertEqual(max(xs) - min(xs) + 1, len(xs), (right, y))

    def test_the_light_stays_on_the_left_in_both_turns(self):
        for right in (False, True):
            image = kiln(right)
            self.assertGreater(light(image, range(CX - 9, CX - 3), range(10, 24)),
                               light(image, range(CX + 4, CX + 10), range(10, 24)) + 40)


class WorkbenchArtTests(unittest.TestCase):
    def test_two_turns_of_the_same_size(self):
        self.assertEqual(BENCH_SIZE, workbench(False).get_size())
        self.assertEqual(BENCH_SIZE, workbench(True).get_size())
        self.assertNotEqual(pygame.image.tobytes(workbench(False), "RGBA"),
                            pygame.image.tobytes(workbench(True), "RGBA"))

    def test_the_top_is_solid_and_the_left_face_is_lit(self):
        for right in (False, True):
            image = workbench(right)
            for y, xs in rows(image, last=11).items():
                self.assertEqual(max(xs) - min(xs) + 1, len(xs), (right, y))
            self.assertGreater(light(image, range(6, 14), range(15, 19)), light(image, range(20, 28), range(15, 19)))


if __name__ == "__main__":
    unittest.main()
