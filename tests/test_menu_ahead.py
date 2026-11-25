import os
import shutil
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "dependencias"), str(Path(__file__).resolve().parent)]
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame

pygame.init()
from spawnbound import island_apart, menus, savegame
from spawnbound.config import DEFAULT_CONFIG
from spawnbound.domain.model import SpaceKind
from spawnbound.domain.session import GameSession
from spawnbound.input import InputFrame
from spawnbound.renderer import PlaceholderRenderer
from spawnbound.states import TransitionKind
from test_menus_saves import FakeScene, click, finish, small_session  # noqa: E402

SIZE = 32


def wait_for(condition, limit=60.):
    deadline = time.perf_counter() + limit
    while not condition() and time.perf_counter() < deadline:
        time.sleep(.01)
    return condition()


class Folder(unittest.TestCase):
    def setUp(self):
        self.folder = Path(tempfile.mkdtemp(prefix="spawnbound-menu-"))
        self.addCleanup(shutil.rmtree, self.folder, ignore_errors=True)


class KeptSceneTests(Folder):
    def scene(self):
        scene = menus.MenuScene(DEFAULT_CONFIG, size=SIZE, cache=self.folder)
        scene._thread.join()
        return scene

    def show(self, scene, renderer):
        scene.backdrop(renderer)
        scene.update(1 / 60)
        self.assertTrue(scene.ready)
        return scene.capture()

    def test_the_island_is_kept_and_opened_by_the_next_run(self):
        first = self.scene()
        self.assertEqual(1, len(list(self.folder.glob("ilha-*.bin"))))
        with patch.object(GameSession, "create", side_effect=AssertionError("made again")):
            second = self.scene()
        self.assertIsNotNone(second.built)
        self.assertEqual(first.built.world.tile_map.tiles, second.built.world.tile_map.tiles)
        self.assertEqual(set(first.built.world.objects), set(second.built.world.objects))
        self.assertTrue(second.built.world.placed_fires)

    def test_the_first_view_is_saved_and_shown_by_the_next_run_with_the_window(self):
        renderer = PlaceholderRenderer(pygame.Surface((960, 540)), DEFAULT_CONFIG)
        first = self.scene()
        self.assertIsNone(first.backdrop(renderer))
        save = self.show(first, renderer)
        self.assertIsNotNone(save, "the first live frame is saved when no picture exists")
        view = pygame.Surface(renderer._world_screen.get_size())
        view.fill((40, 90, 50))
        save(view)
        picture = self.folder / f"vista-{renderer.picture_key()}.png"
        self.assertTrue(wait_for(lambda: picture.with_suffix(".chave").exists()))
        first.update(1 / 60)
        self.assertIsNone(first.capture(), "saved once")

        second = self.scene()
        shown = second.backdrop(renderer)
        self.assertIsNotNone(shown)
        self.assertEqual((40, 90, 50), tuple(shown.get_at((10, 10)))[:3])
        self.assertEqual(1., second.cover, "the picture stands for the island until it shows")
        second.update(menus.INTRO_SECONDS)
        self.assertTrue(second.ready)
        self.assertEqual(0., second.veil, "out of the dark right after the window opens")
        self.assertEqual(1., second.cover, "its first frame lies under the whole picture")
        self.assertIsNone(second.capture(), "a picture of this code is not saved again")
        second.update(menus.COVER_SECONDS / 2)
        self.assertAlmostEqual(.5, second.cover)
        second.update(menus.COVER_SECONDS)
        self.assertEqual(0., second.cover)
        self.assertEqual(0., second.veil, "no dark fade under the picture")

    def test_the_menu_draws_the_picture_until_the_island_shows(self):
        renderer = PlaceholderRenderer(pygame.Surface((960, 540)), DEFAULT_CONFIG)
        picture = pygame.Surface(renderer._world_screen.get_size())
        picture.fill((200, 40, 40))
        renderer.draw_menu(None, None, lambda surface, config, font: surface.get_rect(), 0., backdrop=picture, cover=1.)
        self.assertEqual((200, 40, 40), tuple(renderer._world_screen.get_at((5, 5)))[:3])

    def test_a_picture_from_other_code_shows_and_is_saved_again(self):
        renderer = PlaceholderRenderer(pygame.Surface((960, 540)), DEFAULT_CONFIG)
        old = pygame.Surface(renderer._world_screen.get_size())
        old.fill((10, 20, 200))
        path = self.folder / f"vista-{renderer.picture_key()}.png"
        pygame.image.save(old, str(path))
        path.with_suffix(".chave").write_text("codigo antigo", "ascii")
        scene = self.scene()
        self.assertEqual((10, 20, 200), tuple(scene.backdrop(renderer).get_at((3, 3)))[:3])
        save = self.show(scene, renderer)
        self.assertIsNotNone(save)
        fresh = pygame.Surface(renderer._world_screen.get_size())
        fresh.fill((90, 90, 10))
        save(fresh)
        self.assertEqual((10, 20, 200), tuple(scene.picture.get_at((3, 3)))[:3], "the old one fades out first")
        scene.update(menus.COVER_SECONDS + .1)
        self.assertEqual((90, 90, 10), tuple(scene.picture.get_at((3, 3)))[:3])
        self.assertTrue(wait_for(lambda: path.with_suffix(".chave").read_text("ascii") == scene._keys[1]))

    def test_each_showing_starts_from_the_saved_view(self):
        scene = self.scene()
        world = scene.built.world
        before = scene.camera_over(world)
        scene.update(1 / 60)
        scene.update(20.)
        self.assertNotEqual(before, scene.camera)
        scene.hide()
        self.assertEqual(before, scene.camera_over(world))
        self.assertEqual(menus.SCENE_START, scene.built.cycle_seconds)


class GamesAheadTests(Folder):
    def menu(self):
        scene = FakeScene()
        scene.ready, scene.clock = True, menus.AHEAD_AFTER
        return menus.MainMenuState(DEFAULT_CONFIG, scene, island_size=SIZE, folder=self.folder, ahead=True)

    def made(self, menu, name):
        menu.step(InputFrame(), 1 / 60)
        game = getattr(menu, name)
        self.assertIsNotNone(game, name)
        game._thread.join()
        self.assertIsNone(game.error)
        return game.session

    def test_nothing_is_prepared_until_the_scene_has_shown_a_moment(self):
        menu = self.menu()
        menu.scene.clock = menus.AHEAD_AFTER / 2
        menu.step(InputFrame(), 1 / 60)
        self.assertIsNone(menu._spare)

    def test_a_new_game_without_a_seed_takes_the_island_made_ahead(self):
        menu = self.menu()
        spare = self.made(menu, "_spare")
        menu.step(click(menu, "new"), 1 / 60)
        menu.step(InputFrame(enter_pressed=True), 1 / 60)
        transition = finish(menu)
        self.assertEqual(TransitionKind.START, transition.kind)
        self.assertIs(spare, transition.session)
        self.assertIn(SpaceKind.CAVE, {world.space_kind for world in spare.spaces.worlds.values()},
                      "its mine came with it")

    def test_a_new_game_still_in_the_making_is_waited_for(self):
        menu = self.menu()
        menu.step(InputFrame(), 1 / 60)
        spare = menu._spare
        menu.step(click(menu, "new"), 1 / 60)
        menu.step(InputFrame(enter_pressed=True), 1 / 60)
        transition = finish(menu)
        self.assertIs(spare.session, transition.session)

    def test_a_typed_seed_makes_its_own_island(self):
        menu = self.menu()
        spare = self.made(menu, "_spare")
        menu.step(click(menu, "new"), 1 / 60)
        menu.step(InputFrame(typed="77", enter_pressed=True), 1 / 60)
        transition = finish(menu)
        self.assertEqual(77, transition.session.home_world.seed)
        self.assertIsNot(spare, transition.session)

    def test_continue_takes_the_save_opened_ahead(self):
        savegame.save_session(small_session(), 2, self.folder)
        menu = self.menu()
        self.made(menu, "_spare")
        kept = self.made(menu, "_kept")
        self.assertEqual("Jogo carregado do espaço 2.", kept.last_message)
        transition = menu.step(click(menu, "continue"), 1 / 60)
        if transition.kind is TransitionKind.NONE:
            transition = finish(menu)
        self.assertEqual((TransitionKind.START, 2), (transition.kind, transition.slot))
        self.assertIs(kept, transition.session)

    def test_a_save_written_since_is_opened_again(self):
        savegame.save_session(small_session(), 2, self.folder)
        menu = self.menu()
        self.made(menu, "_spare")
        kept = self.made(menu, "_kept")
        with patch.object(savegame.time, "time", return_value=time.time() + 60):
            savegame.save_session(small_session(77), 2, self.folder)
        menu.refresh()
        transition = menu.step(click(menu, "continue"), 1 / 60)
        transition = finish(menu)
        self.assertIsNot(kept, transition.session)
        self.assertEqual(77, transition.session.home_world.seed)

    def test_without_ahead_the_menu_prepares_nothing(self):
        menu = self.menu()
        menu.ahead = False
        menu.step(InputFrame(), 1 / 60)
        self.assertIsNone(menu._spare)


class IslandApartTests(unittest.TestCase):
    def test_an_island_made_in_another_process_is_the_one_made_here(self):
        with patch.object(island_apart, "APART_FROM", SIZE):
            data = island_apart._run_apart(5, DEFAULT_CONFIG, SIZE)
            self.assertIsNotNone(data, "the other process answered")
            apart = island_apart.make_session(5, DEFAULT_CONFIG, SIZE)
        here = island_apart._make(5, DEFAULT_CONFIG, SIZE)
        self.assertEqual(here.world.tile_map.tiles, apart.world.tile_map.tiles)
        self.assertEqual(set(here.world.objects), set(apart.world.objects))
        self.assertEqual(set(here.spaces.worlds), set(apart.spaces.worlds))
        self.assertIs(DEFAULT_CONFIG, apart.config)

    def test_without_a_process_the_island_is_made_here(self):
        with patch.object(island_apart, "APART_FROM", SIZE), \
                patch.object(island_apart.subprocess, "run", side_effect=OSError("no processes")):
            session = island_apart.make_session(5, DEFAULT_CONFIG, SIZE)
        self.assertEqual(5, session.home_world.seed)

    def test_small_islands_are_made_here(self):
        with patch.object(island_apart, "_run_apart", side_effect=AssertionError("a process for a small island")):
            island_apart.make_session(5, DEFAULT_CONFIG, SIZE)


if __name__ == "__main__":
    unittest.main()
