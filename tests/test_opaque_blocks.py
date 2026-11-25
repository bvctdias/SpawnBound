import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "dependencias")]
import pygame

from spawnbound import renderer as renderer_module
from spawnbound.config import DEFAULT_CONFIG
from spawnbound.domain.session import GameSession
from spawnbound.renderer import RGB_MASKS, PlaceholderRenderer, opaque_surface

HIDDEN = (76, 105, 113)
GRASS = (140, 200, 90)


class OpaqueBlockTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pygame.init()

    def test_an_opaque_surface_keeps_the_scenery_under_transparent_pixels(self):
        surface = opaque_surface((4, 4))
        self.assertEqual(RGB_MASKS, surface.get_masks())
        surface.fill(GRASS)
        hidden = pygame.Surface((1, 1), pygame.SRCALPHA)
        hidden.fill((*HIDDEN, 0))
        for _ in range(2):
            surface.blit(hidden, (1, 1))
        self.assertEqual(GRASS, tuple(surface.get_at((1, 1)))[:3])

    def test_the_bundled_building_sprites_hide_a_colour_under_their_transparency(self):
        image = pygame.image.load(str(ROOT / "assets/buildings/windmill_ruined.png"))
        self.assertEqual((*HIDDEN, 0), tuple(image.get_at((0, 0))))

    def test_the_scenery_blocks_are_opaque_surfaces(self):
        made = []
        original = renderer_module.opaque_surface

        def recording(size):
            surface = original(size)
            made.append(surface)
            return surface

        renderer_module.opaque_surface = recording
        self.addCleanup(setattr, renderer_module, "opaque_surface", original)
        session = GameSession.create(1234, DEFAULT_CONFIG, chunk_preview_size=24)
        renderer = PlaceholderRenderer(pygame.Surface((960, 540)), DEFAULT_CONFIG)
        renderer.draw_gameplay(session, debug=False)
        self.assertTrue(renderer._chunks)
        for block in renderer._chunks.values():
            self.assertTrue(any(block is surface for surface in made))
            self.assertEqual(0, block.get_masks()[3])


if __name__ == "__main__":
    unittest.main()
