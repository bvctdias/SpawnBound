import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import pygame
from spawnbound.config import GameConfig
from spawnbound.domain.coordinates import GridPos
from spawnbound.domain.session import GameSession
from spawnbound.pixel_font import GLYPHS, HEIGHT, PixelFont, normalize
from spawnbound.renderer import PlaceholderRenderer


class PixelFontTests(unittest.TestCase):
    def test_glyphs_share_height_and_rows_have_one_width(self):
        for char, rows in GLYPHS.items():
            with self.subTest(char=char):
                self.assertEqual(HEIGHT, len(rows))
                self.assertEqual(1, len({len(row) for row in rows}))

    def test_text_is_uppercased_without_accents_and_unknown_becomes_question_mark(self):
        self.assertEqual("ACAO NIVEL", normalize("ação nível"))
        font = PixelFont()
        self.assertEqual((11, 7), font.size("ab"))
        self.assertEqual(font.size("?"), font.size("€"))

    def test_render_is_crisp_two_colour_text_with_shadow(self):
        surface = PixelFont().render("E", (250, 250, 240), shadow=(10, 10, 10))
        colours = {tuple(surface.get_at((x, y))) for x in range(surface.get_width())
                   for y in range(surface.get_height())}
        self.assertEqual({(250, 250, 240, 255), (10, 10, 10, 255), (0, 0, 0, 0)}, colours)
        scaled = PixelFont().render("E", (250, 250, 240), scale=3)
        self.assertEqual((15, 21), scaled.get_size())


class ContextualLabelTests(unittest.TestCase):
    def test_portal_label_appears_only_near_the_entrance(self):
        pygame.font.init()
        config = GameConfig(camera_zoom=1)
        session = GameSession.create(1234, config, chunk_preview_size=64)
        portal = next(iter(session.world.portals.values()))
        renderer = PlaceholderRenderer(pygame.Surface((960, 540)), config)
        origin = renderer._camera_origin(session)
        x, y = renderer._ground_center(session, portal.position, origin)
        top = y - round((78 if portal.target_kind.value == "interior" else 47) * config.world_art_scale)
        region = pygame.Rect(x - 30, top, 60, 8)

        def label_pixels(player_position):
            session.player.position = player_position
            renderer.screen = pygame.Surface((960, 540), pygame.SRCALPHA)
            renderer._draw_portal(session, portal, origin)
            return sum(renderer.screen.get_at((px, py)).a > 0 for px in range(region.left, region.right)
                       for py in range(region.top, region.bottom))

        self.assertEqual(0, label_pixels(portal.position + GridPos(12, 12)))
        self.assertGreater(label_pixels(portal.approach), 0)


if __name__ == "__main__":
    unittest.main()
