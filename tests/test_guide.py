import json
import os
import re
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "dependencias")]
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame

pygame.init()
from spawnbound import controls_menu, guide_hud, menus, savegame
from spawnbound.config import DEFAULT_CONFIG
from spawnbound.domain import guide
from spawnbound.domain.coordinates import GridPos
from spawnbound.domain.inventory import Stack
from spawnbound.domain.model import ObjectKind, SpaceKind, WorldObject
from spawnbound.domain.session import GameSession
from spawnbound.input import InputFrame
from spawnbound.pixel_font import PixelFont
from spawnbound.states import GameplayState

FRAME = 1 / 60


def small_session(seed=1234):
    session = GameSession.create(seed, DEFAULT_CONFIG, chunk_preview_size=48)
    session.wildlife.mobs.clear()
    return session


def play(state, seconds, frame=None):
    for _ in range(round(seconds / FRAME)):
        state.step(frame or InputFrame(), FRAME)


class ObjectiveTests(unittest.TestCase):
    def test_the_line_goes_one_objective_at_a_time(self):
        session = small_session()
        self.assertEqual("wood", guide.current(session).key)
        self.assertEqual([], guide.advance(session))
        session.player.inventory.add("wood", 10)
        self.assertEqual(["wood"], [o.key for o in guide.advance(session)])
        self.assertEqual("stone_tool", guide.current(session).key)
        bag = session.player.inventory
        bag.slots[bag.slots.index(next(s for s in bag.slots if s and s.item == "axe"))] = Stack("stone_axe", 1)
        bag.add("coal", 3)
        self.assertEqual(["stone_tool", "coal"], [o.key for o in guide.advance(session)])
        self.assertEqual("campfire", guide.current(session).key)

    def test_a_passed_objective_stays_passed(self):
        session = small_session()
        session.player.inventory.add("wood", 10)
        guide.advance(session)
        session.player.inventory.remove({"wood": 10})
        self.assertEqual([], guide.advance(session))
        self.assertEqual(1, session.objective)

    def test_the_campfire_counts_once_it_is_on_the_ground(self):
        session = small_session()
        session.objective = [o.key for o in guide.OBJECTIVES].index("campfire")
        session.player.inventory.add("campfire", 1)
        self.assertEqual([], guide.advance(session), "in the bag it is not lit yet")
        cell = session.player.position + session.player.facing
        session.world.objects[cell] = WorldObject.create(cell, ObjectKind.CAMPFIRE,
                                                         elevation=session.world.elevation_at(cell))
        self.assertEqual(["campfire"], [o.key for o in guide.advance(session)])
        session.player.inventory.add("cooked_meat", 1)
        self.assertEqual(["roast"], [o.key for o in guide.advance(session)])

    def test_what_the_world_keeps_passes_the_objectives_before_it(self):
        session = small_session()
        session.visited.add("outra ilha")
        guide.advance(session)
        self.assertEqual("guardian", guide.current(session).key)
        session.home_world.guardian_defeated = True
        self.assertEqual(["guardian"], [o.key for o in guide.advance(session)])
        self.assertTrue(guide.finished(session))
        self.assertIsNone(guide.current(session))

    def test_every_objective_has_its_words(self):
        font = PixelFont()
        keys = [o.key for o in guide.OBJECTIVES]
        self.assertEqual(len(keys), len(set(keys)))
        self.assertEqual("guardian", keys[-1], "the Stone Guardian closes the line")
        for objective in guide.OBJECTIVES:
            self.assertTrue(objective.text and objective.how)
            self.assertLess(font.size(objective.how)[0] + 20, DEFAULT_CONFIG.virtual_width // 2)


class TipTests(unittest.TestCase):
    def test_each_tip_shows_once_in_its_moment(self):
        session = small_session()
        self.assertEqual("pause", guide.next_tip(session).key)
        session.tips_seen.add("pause")
        self.assertIsNone(guide.next_tip(session), "nothing else has happened yet")
        session.player.hearts -= 1
        self.assertEqual("hurt", guide.next_tip(session).key)
        session.tips_seen.add("hurt")
        self.assertIsNone(guide.next_tip(session))

    def test_the_tips_fit_above_the_hotbar(self):
        font = PixelFont()
        keys = [tip.key for tip in guide.TIPS]
        self.assertEqual(len(keys), len(set(keys)))
        for tip in guide.TIPS:
            self.assertLess(font.size("DICA " + tip.text)[0] + 40, DEFAULT_CONFIG.virtual_width - 40, tip.key)


class GameplayGuideTests(unittest.TestCase):
    def test_the_hud_follows_the_line_and_the_tip_comes_and_goes(self):
        session = small_session()
        state = GameplayState(session, DEFAULT_CONFIG)
        play(state, guide.FIRST_TIP_DELAY + .5)
        self.assertIn("pause", session.tips_seen)
        self.assertIsNotNone(state._tip)
        self.assertIsNotNone(state._hud_overlay())
        session.player.inventory.add("wood", 10)
        play(state, .5)
        self.assertEqual(1, session.objective)
        self.assertEqual("Colete 10 madeiras", state._passed[0])
        play(state, guide.TIP_SECONDS)
        self.assertIsNone(state._passed)
        self.assertIsNone(state._tip)
        state.debug = True
        self.assertIsNone(state._hud_overlay(), "the F1 panel takes the top of the screen")

    def test_the_end_opens_once_and_closes_with_its_button_or_esc(self):
        session = small_session()
        state = GameplayState(session, DEFAULT_CONFIG)
        session.home_world.guardian_defeated = True
        play(state, .5)
        self.assertTrue(state.ending_open)
        self.assertTrue(session.ending_seen)
        self.assertIsNotNone(state._ending_overlay())
        clock = session.cycle_seconds
        play(state, .5)
        self.assertEqual(clock, session.cycle_seconds, "the panel pauses the game")
        lines = state._ending_lines()
        _, button = guide_hud.ending_layout(DEFAULT_CONFIG, len(lines))
        state.step(InputFrame(destination_click=button.center), FRAME)
        self.assertFalse(state.ending_open)
        play(state, 1)
        self.assertFalse(state.ending_open, "it does not come back")
        state.ending_open = True
        state.step(InputFrame(pause_pressed=True), FRAME)
        self.assertFalse(state.ending_open)

    def test_the_panels_are_drawn(self):
        surface = pygame.Surface((DEFAULT_CONFIG.virtual_width, DEFAULT_CONFIG.virtual_height), pygame.SRCALPHA)
        font = PixelFont()
        screen = surface.get_rect()
        for rect in (guide_hud.draw_objective(surface, font, 1, 8, "Colete 10 madeiras", "Clique numa árvore."),
                     guide_hud.draw_objective(surface, font, 1, 8, "Colete 10 madeiras", "", done=True),
                     guide_hud.draw_tip(surface, DEFAULT_CONFIG, font, guide.TIPS[0].text, 255),
                     guide_hud.draw_ending(surface, DEFAULT_CONFIG, font, ["a", "b", "c", "d"], True)):
            self.assertTrue(screen.contains(rect), rect)


class ControlsPageTests(unittest.TestCase):
    def setUp(self):
        self.folder = Path(tempfile.mkdtemp(prefix="spawnbound-saves-"))
        self.addCleanup(shutil.rmtree, self.folder, ignore_errors=True)

    def test_controles_opens_from_the_pause_and_goes_back(self):
        game = GameplayState(small_session(), DEFAULT_CONFIG)
        pause = menus.PauseMenuState(game, self.folder)
        keys = [item.key for item in pause.items()]
        self.assertEqual(["resume", "save", "controls", "menu", "quit"], [k for k in keys if k])
        rects = menus.layout(pause.items(), DEFAULT_CONFIG, pause.top)
        button = rects[keys.index("controls")].center
        pause.step(InputFrame(destination_click=button), 0)
        self.assertEqual("controls", pause.screen)
        _, _, back = controls_menu.layout(DEFAULT_CONFIG)
        pause.step(InputFrame(destination_click=back.center), 0)
        self.assertEqual("main", pause.screen)
        pause.step(InputFrame(destination_click=button), 0)
        pause.step(InputFrame(pause_pressed=True), 0)
        self.assertEqual("main", pause.screen, "Esc goes back to the pause menu, not to the game")

    def test_the_page_fits_the_screen(self):
        panel, body, back = controls_menu.layout(DEFAULT_CONFIG)
        screen = pygame.Rect(0, 0, DEFAULT_CONFIG.virtual_width, DEFAULT_CONFIG.virtual_height)
        self.assertTrue(screen.contains(panel))
        self.assertTrue(panel.contains(body) and panel.contains(back))
        self.assertLess(body.bottom, back.top)
        surface = pygame.Surface(screen.size, pygame.SRCALPHA)
        self.assertEqual(panel, controls_menu.draw(surface, DEFAULT_CONFIG, PixelFont(), "back"))

    def test_every_key_on_the_page_is_one_the_game_reads(self):
        source = (ROOT / "src/spawnbound/pplay_host.py").read_text(encoding="utf-8")
        from spawnbound import pplay_host
        read = {key for keys in pplay_host.ACTIONS.values() for key in keys if isinstance(key, str)}
        read |= set(re.findall(r'key_down\("([A-Z0-9]+)"\)', source))
        if "K_TAB" in source:
            read.add("TAB")
        for _, rows in controls_menu.RIGHT:
            for label, _ in rows:
                for part in re.split(r"[^\w]+", label.upper()):
                    if part in ("", "A", "OU") or part.isdigit():
                        continue
                    self.assertIn({"ESPAÇO": "SPACE"}.get(part, part), read, label)


class SavedGuideTests(unittest.TestCase):
    def setUp(self):
        self.folder = Path(tempfile.mkdtemp(prefix="spawnbound-saves-"))
        self.addCleanup(shutil.rmtree, self.folder, ignore_errors=True)

    def test_the_line_and_the_tips_go_into_the_save(self):
        session = small_session()
        session.objective, session.tips_seen, session.ending_seen = 3, {"pause", "hurt"}, False
        savegame.save_session(session, 1, self.folder)
        loaded = savegame.load_session(1, DEFAULT_CONFIG, self.folder)
        self.assertEqual((3, {"pause", "hurt"}, False), (loaded.objective, loaded.tips_seen, loaded.ending_seen))

    def test_an_older_save_starts_the_line_from_the_beginning(self):
        session = small_session()
        schema = savegame.schema(session)
        game = "spawnbound.domain.session.GameSession"
        for name in ("objective", "tips_seen", "ending_seen"):
            schema[game].remove(name)
            delattr(session, name)
        header = {"version": savegame.SAVE_VERSION, "seed": 1234, "place": "Ilha", "played_seconds": 0.,
                  "saved_at": 0., "schema": schema}
        config, session.config = session.config, None
        body = savegame.zlib.compress(savegame.pickle.dumps(session))
        savegame.slot_path(1, self.folder).write_bytes(savegame.MAGIC + json.dumps(header).encode() + b"\n" + body)
        loaded = savegame.load_session(1, DEFAULT_CONFIG, self.folder)
        self.assertEqual((0, set(), False), (loaded.objective, loaded.tips_seen, loaded.ending_seen))
        state = GameplayState(loaded, DEFAULT_CONFIG)
        play(state, .5)


if __name__ == "__main__":
    unittest.main()
