import sys
import unittest
from pathlib import Path

import pygame

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from spawnbound.cottage_art import PIVOT, cottage
from spawnbound.domain.coordinates import GridPos
from spawnbound.domain.model import Portal, SpaceKind
from spawnbound.house_art import light_room
from spawnbound.view import portal_contains


class HouseArtTests(unittest.TestCase):
    def test_bundled_cottage_and_clicks_follow_generated_pixels(self):
        portal = Portal("house", GridPos(1, 1), GridPos(1, 2), "inside", SpaceKind.INTERIOR, "ABRIGO")
        shipped = pygame.image.load(ROOT / "assets/native_32/sprites/shelter.png")
        self.assertEqual(pygame.image.tobytes(cottage(), "RGBA"), pygame.image.tobytes(shipped, "RGBA"))
        for y in range(shipped.get_height()):
            for x in range(shipped.get_width()):
                self.assertEqual(bool(shipped.get_at((x, y)).a), portal_contains(portal, x-PIVOT[0], y-PIVOT[1]))

    def test_light_reaches_the_planks_and_leaves_the_void_black(self):
        scene = pygame.Surface((320, 160))
        pygame.draw.rect(scene, (227, 113, 61), (40, 20, 250, 110))
        dark = scene.copy()
        light_room(dark, [], 1)
        light_room(scene, [(70, 45)], 1)
        for p in ((0, 0), (68, 15), (8, 44), (319, 159)):
            self.assertEqual((0, 0, 0), scene.get_at(p)[:3])
        self.assertGreater(scene.get_at((70, 45)).r, scene.get_at((270, 45)).r)
        self.assertGreater(scene.get_at((70, 45)).r, dark.get_at((70, 45)).r)
