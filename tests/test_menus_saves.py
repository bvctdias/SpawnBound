import json
import os
import shutil
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "dependencias")]
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame

pygame.init()
from spawnbound import menus, savegame
from spawnbound.config import DEFAULT_CONFIG
from spawnbound.domain.coordinates import GridPos
from spawnbound.domain.model import ObjectKind, SpaceKind
from spawnbound.domain.session import GameSession
from spawnbound.input import InputFrame
from spawnbound.renderer import PlaceholderRenderer
from spawnbound.states import GameplayState, StateStack, TransitionKind

SIZE = 48


def small_session(seed=1234):
    session = GameSession.create(seed, DEFAULT_CONFIG, chunk_preview_size=SIZE)
    session.wildlife.mobs.clear()
    return session


def center(state, key):
    rects = menus.layout(state.items(), DEFAULT_CONFIG, state.top)
    return next(rect.center for item, rect in zip(state.items(), rects) if item.key == key)


def click(state, key):
    return InputFrame(destination_click=center(state, key))


def finish(menu, limit=30.):
    deadline = time.perf_counter() + limit
    transition = menu.step(InputFrame(), 1 / 60)
    while transition.kind is TransitionKind.NONE and menu.screen == "busy" and time.perf_counter() < deadline:
        time.sleep(.01)
        transition = menu.step(InputFrame(), 1 / 60)
    return transition


class FakeScene:
    ready, session, elapsed, veil, cover, clock = False, None, 0., 1., 0., 0.
    built, view_ready = None, None

    def update(self, seconds):
        self.elapsed += seconds

    def backdrop(self, renderer):
        return None

    def capture(self):
        return None


class TempFolder(unittest.TestCase):
    def setUp(self):
        self.folder = Path(tempfile.mkdtemp(prefix="spawnbound-saves-"))
        self.addCleanup(shutil.rmtree, self.folder, ignore_errors=True)


class SaveTests(TempFolder):
    def test_a_save_brings_the_game_back_as_it_was(self):
        session = small_session()
        session.cycle_seconds, session.played_seconds = 47.5, 321.
        session.player.hearts = 3
        cell = next(c for c in session.world.objects if session.world.objects[c].kind is ObjectKind.TREE)
        del session.world.objects[cell]
        navigation = session._navigation
        info = savegame.save_session(session, 2, self.folder)
        self.assertIs(navigation, session._navigation)
        self.assertEqual((2, 1234, 321., True), (info.slot, info.seed, info.played_seconds, info.compatible))
        self.assertTrue(savegame.slot_path(2, self.folder).is_file())
        self.assertFalse(savegame.slot_path(2, self.folder).with_suffix(".tmp").exists())
        read = savegame.read_slot(2, self.folder)
        self.assertEqual((1234, savegame.describe_place(session), True), (read.seed, read.place, read.compatible))
        loaded = savegame.load_session(2, DEFAULT_CONFIG, self.folder)
        self.assertEqual(1234, loaded.home_world.seed)
        self.assertEqual((47.5, 321., 3), (loaded.cycle_seconds, loaded.played_seconds, loaded.player.hearts))
        self.assertNotIn(cell, loaded.world.objects)
        self.assertEqual(session.player.position, loaded.player.position)
        self.assertIs(DEFAULT_CONFIG, loaded.config)
        self.assertEqual({}, loaded._navigation)
        loaded.navigation

    def test_the_screen_never_goes_into_the_save(self):
        session = small_session()
        game = GameplayState(session, DEFAULT_CONFIG, art_hit_test=lambda *args: None)
        self.assertIsNotNone(session.wildlife.in_view)
        savegame.save_session(session, 1, self.folder)
        self.assertIsNotNone(session.wildlife.in_view)
        data = savegame.slot_path(1, self.folder).read_bytes()
        body = savegame.zlib.decompress(data[data.index(b"\n", len(savegame.MAGIC)) + 1:])
        for name in (b"GameplayState", b"pygame", b"renderer"):
            self.assertNotIn(name, body)
        loaded = savegame.load_session(1, DEFAULT_CONFIG, self.folder)
        self.assertIsNone(loaded.wildlife.in_view)
        game = GameplayState(loaded, DEFAULT_CONFIG)
        lives = (loaded.wildlife, loaded.island_life, *loaded.island_lives.values(), *loaded.mine_life.values())
        self.assertTrue(all(life.in_view == game._in_camera_view for life in lives))

    def test_slots_list_and_the_last_saved_is_continued(self):
        self.assertEqual([None, None, None], savegame.list_slots(self.folder))
        self.assertIsNone(savegame.latest_slot(self.folder))
        session = small_session()
        with patch.object(savegame.time, "time", return_value=2000.):
            savegame.save_session(session, 3, self.folder)
        with patch.object(savegame.time, "time", return_value=3000.):
            savegame.save_session(session, 1, self.folder)
        slots = savegame.list_slots(self.folder)
        self.assertEqual([1, None, 3], [info.slot if info else None for info in slots])
        self.assertEqual(1, savegame.latest_slot(self.folder))
        with patch.object(savegame.time, "time", return_value=4000.):
            savegame.save_session(session, 3, self.folder)
        self.assertEqual(3, savegame.latest_slot(self.folder))

    def test_saves_of_another_version_or_damaged_are_shown_but_never_opened(self):
        savegame.save_session(small_session(), 1, self.folder)
        path = savegame.slot_path(1, self.folder)
        data = path.read_bytes()
        end = data.index(b"\n", len(savegame.MAGIC))
        header = json.loads(data[len(savegame.MAGIC):end])
        header["version"] = savegame.SAVE_VERSION + 1
        path.write_bytes(savegame.MAGIC + json.dumps(header).encode() + data[end:])
        info = savegame.read_slot(1, self.folder)
        self.assertFalse(info.compatible)
        self.assertEqual(1234, info.seed)
        self.assertEqual("save de outra versão do jogo", menus.slot_detail(info))
        self.assertIsNone(savegame.latest_slot(self.folder))
        with self.assertRaisesRegex(savegame.SaveError, "outra versão"):
            savegame.load_session(1, DEFAULT_CONFIG, self.folder)

        savegame.slot_path(2, self.folder).write_bytes(b"not a save at all")
        info = savegame.read_slot(2, self.folder)
        self.assertFalse(info.compatible)
        self.assertEqual("save danificado", menus.slot_detail(info))
        with self.assertRaises(savegame.SaveError):
            savegame.load_session(2, DEFAULT_CONFIG, self.folder)

        savegame.save_session(small_session(), 3, self.folder)
        path = savegame.slot_path(3, self.folder)
        path.write_bytes(path.read_bytes()[:-200])
        self.assertTrue(savegame.read_slot(3, self.folder).compatible)
        with self.assertRaisesRegex(savegame.SaveError, "não abre"):
            savegame.load_session(3, DEFAULT_CONFIG, self.folder)
        with self.assertRaisesRegex(savegame.SaveError, "vazio"):
            savegame.load_session(1, DEFAULT_CONFIG, self.folder / "elsewhere")

    def test_nothing_is_saved_during_a_crossing(self):
        session = small_session()
        session.voyage = object()
        with self.assertRaisesRegex(savegame.SaveError, "travessia"):
            savegame.save_session(session, 1, self.folder)
        self.assertEqual([None, None, None], savegame.list_slots(self.folder))

    def test_slots_seeds_and_play_time(self):
        with self.assertRaises(ValueError):
            savegame.slot_path(0, self.folder)
        with self.assertRaises(ValueError):
            savegame.slot_path(savegame.SLOTS + 1, self.folder)
        self.assertEqual(self.folder / "espaco2.sav", savegame.slot_path(2, self.folder))
        self.assertIsNone(savegame.parse_seed(""))
        self.assertIsNone(savegame.parse_seed("   "))
        self.assertEqual(1234, savegame.parse_seed(" 1234 "))
        self.assertEqual(int("9" * 16) % savegame.SEED_LIMIT, savegame.parse_seed("9" * 16))
        word = savegame.parse_seed("ilha")
        self.assertEqual(word, savegame.parse_seed("ilha"))
        self.assertTrue(0 <= word < savegame.SEED_LIMIT)
        info = savegame.SlotInfo(1, 7, "Ilha principal", 59., time.time(), True)
        self.assertEqual("0 min", info.played)
        self.assertEqual("1 h 01 min", savegame.SlotInfo(1, 7, "x", 3700., 0., True).played)
        self.assertTrue(menus.slot_detail(info).startswith("Ilha principal - seed 7 - 0 min - "))
        self.assertEqual("vazio", menus.slot_detail(None))


class OlderSaveTests(TempFolder):
    GAME = "spawnbound.domain.session.GameSession"
    LIFE = "spawnbound.domain.mobs.Wildlife"

    def write(self, session, schema):
        header = {"version": savegame.SAVE_VERSION, "seed": 1234, "place": "Ilha", "played_seconds": 0.,
                  "saved_at": 0.}
        if schema is not None:
            header["schema"] = schema
        config, session.config = session.config, None
        body = savegame.zlib.compress(savegame.pickle.dumps(session))
        session.config = config
        savegame.slot_path(1, self.folder).write_bytes(savegame.MAGIC + json.dumps(header).encode() + b"\n" + body)

    def older(self, session, removed):
        schema = savegame.schema(session)
        for key, names in removed.items():
            for name in names:
                schema[key].remove(name)
        return schema

    def test_fields_added_since_get_their_defaults(self):
        session = small_session()
        session.cycle_seconds = 33.
        schema = self.older(session, {self.GAME: ["played_seconds"], self.LIFE: ["grace"]})
        del session.played_seconds
        lives = (session.wildlife, *session.island_lives.values())
        for life in lives:
            if hasattr(life, "grace"):
                del life.grace
        self.write(session, schema)
        loaded = savegame.load_session(1, DEFAULT_CONFIG, self.folder)
        self.assertEqual((0., 33.), (loaded.played_seconds, loaded.cycle_seconds))
        self.assertEqual(0., loaded.wildlife.grace)
        self.assertIs(DEFAULT_CONFIG, loaded.config)
        state = GameplayState(loaded, DEFAULT_CONFIG)
        state.step(InputFrame(), .5)
        self.assertAlmostEqual(.5, loaded.played_seconds)

    def test_the_first_saves_without_the_list_are_checked_whole(self):
        session = small_session()
        del session.played_seconds
        self.write(session, None)
        self.assertEqual(0., savegame.load_session(1, DEFAULT_CONFIG, self.folder).played_seconds)

    def test_changes_a_save_cannot_follow_refuse_to_open(self):
        session = small_session()
        schema = self.older(session, {self.GAME: ["island_life"]})
        life = session.island_life
        del session.island_life
        self.write(session, schema)
        with self.assertRaisesRegex(savegame.SaveError, "não abre"):
            savegame.load_session(1, DEFAULT_CONFIG, self.folder)
        session.island_life = life
        schema = savegame.schema(session)
        tile = schema["spawnbound.domain.model.Tile"]
        tile[0], tile[1] = tile[1], tile[0]
        self.write(session, schema)
        with self.assertRaisesRegex(savegame.SaveError, "não abre"):
            savegame.load_session(1, DEFAULT_CONFIG, self.folder)

    def test_a_save_of_the_same_code_opens_without_walking_the_game(self):
        session = small_session()
        savegame.save_session(session, 1, self.folder)
        self.assertIs(DEFAULT_CONFIG, session.config)
        data = savegame.slot_path(1, self.folder).read_bytes()
        self.assertNotIn(b"GameConfig", savegame.zlib.decompress(data[data.index(b"\n", len(savegame.MAGIC)) + 1:]))
        with patch.object(savegame, "_fill_missing", side_effect=AssertionError("walked")):
            loaded = savegame.load_session(1, DEFAULT_CONFIG, self.folder)
        self.assertIs(DEFAULT_CONFIG, loaded.config)


class MainMenuTests(TempFolder):
    def menu(self):
        return menus.MainMenuState(DEFAULT_CONFIG, FakeScene(), island_size=SIZE, folder=self.folder)

    def test_without_saves_there_is_no_continue_and_loading_is_off(self):
        menu = self.menu()
        items = {item.key: item for item in menu.items() if item.key}
        self.assertEqual(["new", "load", "quit"], list(items))
        self.assertFalse(items["load"].enabled)
        self.assertEqual(TransitionKind.NONE, menu.step(click(menu, "load"), 1 / 60).kind)
        self.assertEqual("main", menu.screen)
        self.assertEqual(TransitionKind.QUIT, menu.step(click(menu, "quit"), 1 / 60).kind)
        self.assertEqual(TransitionKind.QUIT, menu.step(InputFrame(close_requested=True), 1 / 60).kind)

    def test_continue_opens_the_last_save(self):
        session = small_session()
        session.played_seconds = 90.
        with patch.object(savegame.time, "time", return_value=1000.):
            savegame.save_session(session, 2, self.folder)
        with patch.object(savegame.time, "time", return_value=500.):
            savegame.save_session(small_session(77), 3, self.folder)
        menu = self.menu()
        self.assertEqual(["new", "continue", "load", "quit"], [item.key for item in menu.items() if item.key])
        place = savegame.describe_place(session)
        self.assertTrue(menu.items()[-1].label.startswith(f"Continuar: espaço 2 - {place} - seed 1234 - 1 min"))
        self.assertEqual(TransitionKind.NONE, menu.step(click(menu, "continue"), 1 / 60).kind)
        self.assertEqual([], menu.items())
        menu._busy_time = menus.BUSY_QUIET
        self.assertEqual(["CARREGAR JOGO", "Abrindo o espaço 2..."], [item.label for item in menu.items()])
        transition = finish(menu)
        self.assertEqual((TransitionKind.START, 2), (transition.kind, transition.slot))
        self.assertEqual(1234, transition.session.home_world.seed)
        self.assertEqual(90., transition.session.played_seconds)

    def test_a_save_in_the_mine_opens_with_both_route_maps(self):
        session = small_session()
        portal = next(p for p in session.world.portals.values() if p.target_kind is SpaceKind.CAVE)
        session.player.place(session.world.surface_position(portal.position))
        session.interact()
        self.assertIs(SpaceKind.CAVE, session.world.space_kind)
        savegame.save_session(session, 1, self.folder)
        menu = self.menu()
        menu.step(click(menu, "continue"), 1 / 60)
        loaded = finish(menu).session
        self.assertIs(SpaceKind.CAVE, loaded.world.space_kind)
        self.assertEqual({loaded.world.space_id, loaded.island_life.world.space_id}, set(loaded._navigation))
        self.assertEqual("Jogo carregado do espaço 1.", loaded.last_message)

    def test_load_screen_lists_the_three_slots(self):
        savegame.save_session(small_session(77), 3, self.folder)
        savegame.slot_path(1, self.folder).write_bytes(b"broken")
        menu = self.menu()
        menu.step(click(menu, "load"), 1 / 60)
        self.assertEqual("load", menu.screen)
        slots = [item for item in menu.items() if item.kind == "slot"]
        self.assertEqual([False, False, True], [item.enabled for item in slots])
        self.assertEqual(["save danificado", "vazio"], [item.detail for item in slots[:2]])
        damaged = InputFrame(destination_click=center(menu, "slot1"))
        self.assertEqual(TransitionKind.NONE, menu.step(damaged, 1 / 60).kind)
        savegame.slot_path(3, self.folder).write_bytes(b"broken since the list was read")
        self.assertEqual(TransitionKind.NONE, menu.step(click(menu, "slot3"), 1 / 60).kind)
        self.assertEqual(TransitionKind.NONE, finish(menu).kind)
        self.assertEqual("load", menu.screen)
        self.assertIn("SpawnBound", menu.message)
        self.assertFalse(any(item.enabled for item in menu.items() if item.kind == "slot"))
        menu.step(InputFrame(pause_pressed=True), 1 / 60)
        self.assertEqual(("main", ""), (menu.screen, menu.message))

    def test_a_new_game_takes_a_typed_seed(self):
        menu = self.menu()
        menu.step(click(menu, "new"), 1 / 60)
        self.assertEqual("new", menu.screen)
        for typed in ("12", "a", "3"):
            menu.step(InputFrame(typed=typed), 1 / 60)
        self.assertEqual("123", menu.seed_text)
        menu.step(InputFrame(backspace_pressed=True), 1 / 60)
        self.assertEqual("12", menu.seed_text)
        menu.step(InputFrame(typed="9" * 20), 1 / 60)
        self.assertEqual(menus.SEED_DIGITS, len(menu.seed_text))
        menu.step(InputFrame(pause_pressed=True), 1 / 60)
        self.assertEqual("main", menu.screen)
        menu.step(click(menu, "new"), 1 / 60)
        self.assertEqual("", menu.seed_text)
        menu.step(InputFrame(typed="4321"), 1 / 60)
        menu.step(InputFrame(enter_pressed=True), 1 / 60)
        self.assertEqual("busy", menu.screen)
        transition = finish(menu)
        self.assertEqual((TransitionKind.START, None), (transition.kind, transition.slot))
        self.assertEqual(4321, transition.session.home_world.seed)
        self.assertEqual(0., transition.session.played_seconds)

    def test_a_failed_island_returns_to_the_seed_screen(self):
        menu = self.menu()
        menu.step(click(menu, "new"), 1 / 60)
        with patch.object(menus.GameSession, "create", side_effect=RuntimeError("sem terra")):
            menu.step(click(menu, "start"), 1 / 60)
            menu._builder.join(10)
        menu.step(InputFrame(), 1 / 60)
        self.assertEqual("new", menu.screen)
        self.assertIn("sem terra", menu.message)


class PauseMenuTests(TempFolder):
    @classmethod
    def setUpClass(cls):
        cls.session = small_session()

    def setUp(self):
        super().setUp()
        self.session.played_seconds = self.session.cycle_seconds = 0.
        self.session.voyage = None
        self.game = GameplayState(self.session, DEFAULT_CONFIG)
        self.stack = StateStack(self.game, save_folder=self.folder)

    def pause(self):
        self.stack.step(InputFrame(pause_pressed=True), 0)
        self.assertIsInstance(self.stack.top, menus.PauseMenuState)
        return self.stack.top

    def press(self, key):
        return self.stack.step(click(self.stack.top, key), 0)

    def test_escape_pauses_and_resumes_and_play_time_counts_only_while_playing(self):
        self.stack.step(InputFrame(), 2.)
        self.assertAlmostEqual(2., self.session.played_seconds)
        pause = self.pause()
        self.assertEqual(["resume", "save", "controls", "menu", "quit"],
                         [item.key for item in pause.items() if item.key])
        self.stack.step(InputFrame(), 5.)
        self.assertAlmostEqual(2., self.session.played_seconds)
        self.stack.step(InputFrame(pause_pressed=True), 0)
        self.assertIs(self.game, self.stack.top)
        self.pause()
        self.press("resume")
        self.assertIs(self.game, self.stack.top)

    def test_saving_asks_for_the_slot_and_confirms_before_overwriting(self):
        savegame.save_session(small_session(77), 2, self.folder)
        self.stack.step(InputFrame(), 8.)
        self.assertTrue(self.game.unsaved)
        pause = self.pause()
        self.press("save")
        self.assertEqual("slots", pause.screen)
        self.press("slot1")
        self.assertEqual(("main", "Jogo salvo no espaço 1."), (pause.screen, pause.message))
        self.assertEqual((1, False), (self.game.save_slot, self.game.unsaved))
        self.press("save")
        self.assertTrue(any(item.label == "Espaço 1 (esta partida)" for item in pause.items()))
        self.press("slot1")
        self.assertEqual("main", pause.screen)
        self.press("save")
        self.press("slot2")
        self.assertEqual(("overwrite", 2), (pause.screen, pause.target))
        self.assertIn("seed 77", " ".join(item.label for item in pause.items()))
        self.press("no")
        self.assertEqual("slots", pause.screen)
        self.assertEqual(77, savegame.read_slot(2, self.folder).seed)
        self.press("slot2")
        self.press("yes")
        self.assertEqual((1234, 2), (savegame.read_slot(2, self.folder).seed, self.game.save_slot))
        self.press("save")
        self.stack.step(InputFrame(pause_pressed=True), 0)
        self.assertEqual("main", pause.screen)

    def test_leaving_with_nothing_unsaved_does_not_ask(self):
        self.pause()
        self.assertEqual(TransitionKind.TO_MENU, self.press("menu").kind)
        self.stack = StateStack(self.game, save_folder=self.folder)
        self.pause()
        self.assertEqual(TransitionKind.QUIT, self.press("quit").kind)
        self.assertEqual([None, None, None], savegame.list_slots(self.folder))

    def test_leaving_with_unsaved_progress_asks_first(self):
        self.stack.step(InputFrame(), menus.UNSAVED_SECONDS + 1)
        pause = self.pause()
        self.assertEqual(TransitionKind.NONE, self.press("menu").kind)
        self.assertEqual("leave", pause.screen)
        self.press("cancel")
        self.assertEqual(("main", None), (pause.screen, pause.pending))
        self.press("quit")
        self.assertEqual(TransitionKind.QUIT, self.press("leave").kind)
        self.assertEqual([None, None, None], savegame.list_slots(self.folder))

    def test_save_and_leave_picks_a_slot_or_uses_this_games_own(self):
        self.stack.step(InputFrame(), menus.UNSAVED_SECONDS + 1)
        pause = self.pause()
        self.press("menu")
        self.press("save_leave")
        self.assertEqual(("slots", "menu"), (pause.screen, pause.pending))
        self.assertEqual(TransitionKind.TO_MENU, self.press("slot3").kind)
        self.assertEqual(3, savegame.latest_slot(self.folder))
        saved = savegame.read_slot(3, self.folder).played_seconds
        self.stack = StateStack(self.game, save_folder=self.folder)
        self.stack.step(InputFrame(), menus.UNSAVED_SECONDS + 1)
        self.pause()
        self.press("quit")
        self.assertEqual(TransitionKind.QUIT, self.press("save_leave").kind)
        self.assertGreater(savegame.read_slot(3, self.folder).played_seconds, saved)

    def test_the_window_x_asks_only_with_unsaved_progress(self):
        close = InputFrame(close_requested=True)
        self.assertEqual(TransitionKind.QUIT, self.stack.step(close, 0).kind)
        self.stack.step(InputFrame(), menus.UNSAVED_SECONDS + 1)
        self.assertEqual(TransitionKind.NONE, self.stack.step(close, 0).kind)
        pause = self.stack.top
        self.assertIsInstance(pause, menus.PauseMenuState)
        self.assertEqual(("leave", "quit"), (pause.screen, pause.pending))
        self.stack.step(close, 0)
        self.assertEqual(2, len(self.stack._states))
        self.press("cancel")
        self.assertEqual("main", pause.screen)
        self.press("save")
        self.stack.step(close, 0)
        self.assertEqual(("leave", "quit"), (pause.screen, pause.pending))
        self.assertEqual(TransitionKind.QUIT, self.press("leave").kind)

    def test_f10_f5_and_f6_ask_like_leaving(self):
        self.assertEqual(TransitionKind.RESTART, self.stack.step(InputFrame(restart_pressed=True), 0).kind)
        self.stack.step(InputFrame(), menus.UNSAVED_SECONDS + 1)
        for frame, action, kind in ((InputFrame(restart_pressed=True), "restart", TransitionKind.RESTART),
                                    (InputFrame(new_seed_pressed=True), "new_seed", TransitionKind.NEW_SEED),
                                    (InputFrame(quit_requested=True), "quit", TransitionKind.QUIT)):
            self.assertEqual(TransitionKind.NONE, self.stack.step(frame, 0).kind)
            pause = self.stack.top
            self.assertEqual(("leave", action), (pause.screen, pause.pending))
            self.assertEqual(kind, self.press("leave").kind)
            self.stack = StateStack(self.game, save_folder=self.folder)
        pause = self.pause()
        self.assertEqual(TransitionKind.NONE, self.stack.step(InputFrame(quit_requested=True), 0).kind)
        self.assertEqual(("leave", "quit"), (pause.screen, pause.pending))

    def test_pplay_knows_the_function_keys(self):
        from PPlay.keyboard import Keyboard
        keyboard = Keyboard()
        self.assertEqual([pygame.K_F1, pygame.K_F5, pygame.K_F10, pygame.K_f, pygame.K_ESCAPE, pygame.K_i],
                         [keyboard._get_code(name) for name in ("F1", "F5", "F10", "F", "ESC", "I")])

    def test_the_host_turns_the_window_x_into_a_request(self):
        from types import SimpleNamespace
        from spawnbound.pplay_host import PPlayHost
        host = PPlayHost.__new__(PPlayHost)
        host.window = SimpleNamespace(eventos=[pygame.event.Event(pygame.QUIT)],
                                      screen_to_virtual_coords=lambda x, y: (x, y))
        host.mouse = SimpleNamespace(LEFT=1, RIGHT=3, get_position=lambda: (0, 0),
                                     button_down=lambda button: False, button_pressed=lambda button: False)
        host.keyboard = SimpleNamespace(key_down=lambda key: False)
        self.assertTrue(host._snapshot_input().close_requested)
        host.window.eventos = []
        self.assertFalse(host._snapshot_input().close_requested)

    def test_a_save_that_fails_says_why(self):
        pause = self.pause()
        self.session.voyage = object()
        self.press("save")
        self.press("slot1")
        self.assertEqual("main", pause.screen)
        self.assertIn("travessia", pause.message)
        self.assertEqual([None, None, None], savegame.list_slots(self.folder))
        self.session.voyage = None


class MenuDrawingTests(TempFolder):
    def test_every_screen_fits_and_the_title_clears_the_buttons(self):
        saved = small_session()
        for slot in range(1, savegame.SLOTS + 1):
            savegame.save_session(saved, slot, self.folder)
        menu = menus.MainMenuState(DEFAULT_CONFIG, FakeScene(), island_size=SIZE, folder=self.folder)
        game = GameplayState(saved, DEFAULT_CONFIG)
        game.mark_saved(1)
        pause = menus.PauseMenuState(game, self.folder)
        pause.slots = savegame.list_slots(self.folder)
        pause.target = 2
        screen = pygame.Rect(0, 0, DEFAULT_CONFIG.virtual_width, DEFAULT_CONFIG.virtual_height)
        for state, screens in ((menu, ("main", "new", "busy", "load")), (pause, ("main", "slots", "overwrite", "leave"))):
            for name in screens:
                state.screen, state.message = name, "Uma mensagem de erro bem comprida para caber."
                rects = menus.layout(state.items(), DEFAULT_CONFIG, state.top)
                for rect in rects:
                    self.assertTrue(screen.contains(rect.inflate(48, 32)), (type(state).__name__, name, rect))
                for a, b in zip(rects, rects[1:]):
                    self.assertLessEqual(a.bottom, b.top)
        menu.screen = "main"
        title_bottom = 128 + 7 * 7 // 2 + 8
        self.assertLess(title_bottom, menus.layout(menu.items(), DEFAULT_CONFIG, menu.top)[0].top)

    def test_the_menu_draws_over_the_scene_and_the_pause_over_the_game(self):
        renderer = PlaceholderRenderer(pygame.Surface((960, 540)), DEFAULT_CONFIG)
        menu = menus.MainMenuState(DEFAULT_CONFIG, FakeScene(), island_size=SIZE, folder=self.folder)
        menu.draw(renderer)
        self.assertEqual((10, 14, 26), renderer._world_screen.get_at((5, 5))[:3])
        self.assertEqual(renderer.screen.get_rect(), renderer._ui_bounds)
        session = small_session()
        drawn = []

        def paint(surface, config, font):
            drawn.append(surface.get_size())
            return pygame.Rect(1, 2, 3, 4)

        renderer.draw_menu(session, (session.world.spawn.x, session.world.spawn.y, 0.), paint, .5)
        self.assertEqual([(960, 540)], drawn)
        self.assertEqual(pygame.Rect(1, 2, 3, 4), renderer._ui_bounds)
        self.assertFalse(renderer.scenery)
        self.assertFalse(renderer.direct_presentation)
        game = GameplayState(session, DEFAULT_CONFIG)
        pause = menus.PauseMenuState(game, self.folder)
        game.draw(renderer, overlay=pause.paint)
        bounds = renderer._ui_bounds
        self.assertTrue(renderer.screen.get_rect().contains(bounds))
        self.assertTrue(bounds.collidepoint(center(pause, "save")))
        pause.draw(renderer)


class MenuSceneTests(unittest.TestCase):
    def test_the_scene_has_a_lit_camp_no_hunters_and_turns_day_to_night(self):
        scene = menus.MenuScene(DEFAULT_CONFIG, size=SIZE)
        self.assertFalse(scene.ready)
        self.assertEqual(1., scene.veil)
        scene._thread.join(30)
        scene.update(.5)
        self.assertTrue(scene.ready)
        session = scene.session
        world = session.world
        self.assertEqual(1, len(world.placed_fires))
        self.assertIs(ObjectKind.CAMPFIRE, world.objects[next(iter(world.placed_fires))].kind)
        self.assertFalse(any(mob.hostile for mob in session.wildlife.mobs.values()))
        self.assertAlmostEqual(menus.SCENE_START, session.cycle_seconds)
        self.assertAlmostEqual(1., scene.veil)
        scene.update(menus.FADE_SECONDS)
        self.assertAlmostEqual(0., scene.veil)
        self.assertAlmostEqual(menus.SCENE_START + menus.FADE_SECONDS * menus.SCENE_SPEED, session.cycle_seconds)
        camp = world.camp or world.spawn
        camera = scene.camera
        self.assertEqual(float(world.elevation_at(camp)), camera.z)
        self.assertAlmostEqual(2 * menus.CAMERA_OFFSET, (camera.x - camp.x) + (camera.y - camp.y))
        scene.update(sum(DEFAULT_CONFIG.phase_durations) / menus.SCENE_SPEED * .6)
        self.assertGreaterEqual(session.cycle_seconds, sum(DEFAULT_CONFIG.phase_durations[:2]))


if __name__ == "__main__":
    unittest.main()
