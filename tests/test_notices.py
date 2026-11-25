import sys
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "dependencias")]

import pygame

from spawnbound import savegame, torchlight
from spawnbound.config import DEFAULT_CONFIG, GameConfig
from spawnbound.craft_art import station_sprite
from spawnbound.domain.coordinates import GridPos
from spawnbound.domain.model import ObjectKind, WorldObject
from spawnbound.domain.session import ActionCode, GameSession
from spawnbound.renderer import PlaceholderRenderer

EAST = GridPos(1, 0)


def flat_session():
    session = GameSession.create(1234, DEFAULT_CONFIG, chunk_preview_size=8)
    session.world.objects.clear()
    session.wildlife.mobs.clear()
    return session


def select(session, item):
    bag = session.player.inventory
    bag.selected = next(i for i, slot in enumerate(bag.slots) if slot and slot.item == item)


class NoticeTests(unittest.TestCase):
    def setUp(self):
        self.s = flat_session()
        p = self.s.player.position
        self.tree = p + EAST
        self.s.world.objects[self.tree] = WorldObject.create(self.tree, ObjectKind.TREE)
        self.s.player.facing = EAST

    def test_a_new_game_opens_with_an_empty_corner(self):
        self.assertEqual(("", 0), (self.s.notice, self.s.notice_count))

    def test_routine_successes_stay_out_of_the_corner(self):
        select(self.s, "axe")
        self.assertTrue(self.s.primary_action(self.tree).success)
        self.assertTrue(self.s.last_message)
        self.assertEqual(("", 0), (self.s.notice, self.s.notice_count))

    def test_a_failure_that_explains_itself_shows_each_time(self):
        self.s.world.objects[self.tree] = WorldObject.create(self.tree, ObjectKind.ROCK)
        select(self.s, "axe")
        self.assertIs(ActionCode.TOOL_REQUIRED, self.s.primary_action(self.tree).code)
        self.assertEqual("Selecione a picareta na barra.", self.s.notice)
        self.s.primary_action(self.tree)
        self.assertEqual(2, self.s.notice_count)

    def test_plain_failures_stay_quiet(self):
        self.assertIs(ActionCode.NOTHING_HERE, self.s.primary_action(self.tree - EAST - EAST).code)
        self.assertEqual("Nada para atingir nessa celula.", self.s.last_message)
        self.assertEqual("", self.s.notice)

    def test_a_blow_is_a_danger_and_shows(self):
        self.s.wildlife.last_blow = "arrow"
        with patch.object(self.s.wildlife, "tick", return_value=True):
            self.s.update_mobs(.1)
        self.assertEqual("Uma flecha acertou voce!", self.s.notice)

    def test_a_game_saved_before_the_notices_gets_them(self):
        saved = savegame.schema(self.s)
        saved[savegame._key(GameSession)] = [n for n in saved[savegame._key(GameSession)]
                                             if n not in ("notice", "notice_count")]
        del self.s.notice, self.s.notice_count
        savegame.upgrade(self.s, saved)
        self.assertEqual(("", 0), (self.s.notice, self.s.notice_count))


class CornerTests(unittest.TestCase):
    def setUp(self):
        pygame.font.init()
        self.renderer = PlaceholderRenderer(pygame.Surface((960, 540)), GameConfig())
        self.s = flat_session()

    def test_only_notices_reach_the_corner(self):
        self.assertIsNone(self.renderer._draw_notice(self.s))
        self.s.last_message = "Destino alcancado."
        self.assertIsNone(self.renderer._draw_notice(self.s))
        self.s.warn("Energia insuficiente.")
        self.assertIsNotNone(self.renderer._draw_notice(self.s))

    def test_a_game_just_opened_keeps_its_old_notice_to_itself(self):
        self.s.warn("Energia insuficiente.")
        self.assertIsNone(self.renderer._draw_notice(self.s))
        self.s.warn("Energia insuficiente.")
        self.assertIsNotNone(self.renderer._draw_notice(self.s))


class TorchTests(unittest.TestCase):
    def test_the_placed_torch_is_about_sixty_percent_with_the_same_light(self):
        self.assertEqual((6, 18), station_sprite("torch").get_size())
        self.assertEqual(82, torchlight.TORCH_RADIUS)

    def test_the_light_sits_in_the_flame(self):
        sprite = station_sprite("torch")
        row = sprite.get_height() - 3 - torchlight.TORCH_FLAME
        r, g, b, a = sprite.get_at((sprite.get_width() // 2, row))
        self.assertEqual(255, a)
        self.assertGreater(r, 200)
        self.assertGreater(g, 150)


if __name__ == "__main__":
    unittest.main()
