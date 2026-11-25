import os
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "dependencias")]

import pygame

from spawnbound import cli
from spawnbound.config import DEFAULT_CONFIG
from spawnbound.renderer import PlaceholderRenderer

RED, GREEN = (200, 40, 40), (40, 200, 60)


def no_menu(surface, config, font):
    return surface.get_rect()


class PictureFitTests(unittest.TestCase):
    def setUp(self):
        pygame.init()
        self.renderer = PlaceholderRenderer(pygame.Surface((960, 540)), DEFAULT_CONFIG)
        self.picture = pygame.Surface(self.renderer._world_screen.get_size())
        self.picture.fill(RED)
        self.picture.fill(GREEN, (478, 268, 5, 5))

    def resize(self, window):
        self.renderer.set_camera_zoom(DEFAULT_CONFIG.presentation_scale(window)[1])
        return self.renderer._world_screen

    def test_a_maximised_window_shows_the_middle_of_the_picture(self):
        canvas = self.resize((1920, 1009))
        self.assertLess(canvas.get_width(), self.picture.get_width())
        self.renderer.draw_menu(None, None, no_menu, 0., backdrop=self.picture, cover=1.)
        middle = (canvas.get_width() // 2, canvas.get_height() // 2)
        self.assertEqual(GREEN, tuple(canvas.get_at(middle))[:3], "the same view, around the camera")
        for corner in ((0, 0), (canvas.get_width() - 1, canvas.get_height() - 1)):
            self.assertEqual(RED, tuple(canvas.get_at(corner))[:3], "no dark behind the menu")

    def test_a_larger_canvas_gets_the_picture_enlarged_to_cover_it(self):
        canvas = self.resize((1366, 768))
        self.assertGreater(canvas.get_width(), self.picture.get_width())
        self.renderer.draw_menu(None, None, no_menu, 0., backdrop=self.picture, cover=1.)
        for corner in ((0, 0), (canvas.get_width() - 1, 0), (0, canvas.get_height() - 1)):
            self.assertEqual(RED, tuple(canvas.get_at(corner))[:3])
        middle = (canvas.get_width() // 2, canvas.get_height() // 2)
        self.assertEqual(GREEN, tuple(canvas.get_at(middle))[:3])

    def test_the_fitted_picture_is_made_once_per_size(self):
        self.resize((1920, 1009))
        first = self.renderer._fit_picture(self.picture)
        self.assertIs(first, self.renderer._fit_picture(self.picture))
        self.resize((1366, 768))
        self.assertIsNot(first, self.renderer._fit_picture(self.picture))

    def test_the_live_scene_still_fades_out_the_fitted_picture(self):
        self.resize((1920, 1009))
        self.renderer.draw_menu(None, None, no_menu, 0., backdrop=self.picture, cover=1.)
        fitted = self.renderer._fit_picture(self.picture)
        self.assertIsNone(fitted.get_alpha(), "the cover's opacity is set only while it is drawn")


class StartTests(unittest.TestCase):
    def test_the_game_always_opens_fullscreen(self):
        for argv in ([], ["--seed", "5"], ["--fullscreen"]):
            with self.subTest(argv=argv), patch("spawnbound.app.GameApplication") as app:
                app.return_value = MagicMock()
                self.assertEqual(0, cli.main(argv))
                self.assertIs(True, app.call_args.kwargs["fullscreen"])


if __name__ == "__main__":
    unittest.main()
