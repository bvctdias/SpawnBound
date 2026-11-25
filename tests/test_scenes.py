from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "dependencias")]

from PPlay.scenemanager import Scene, SceneManager

from spawnbound import scenes
from spawnbound.input import InputFrame
from spawnbound.states import NO_TRANSITION, StateStack, Transition, TransitionKind


class Screen:
    transparent = False

    def __init__(self, name, log, then=NO_TRANSITION):
        self.name, self.log, self.then = name, log, then

    def step(self, frame, delta_time):
        self.log.append(("step", self.name, frame, delta_time))
        return self.then

    def draw(self, renderer):
        self.log.append(("draw", self.name))


class App:
    def __init__(self, log, following=None):
        self.frame, self.delta_time, self.closing = InputFrame(), 1 / 60, False
        self.renderer = SimpleNamespace(frame_spare=None, last_prefetch_seconds=.002)
        self.host = SimpleNamespace(spare_seconds=.005, elastic_seconds=0.)
        self.following, self.scene, self.synced = following, None, 0

    def states_after(self, transition):
        return self.following if transition.kind is TransitionKind.START else None

    def change_scene(self, states):
        self.scene = scenes.StackScene(self, states)
        scenes.show(self.scene)

    def sync_presentation_scale(self):
        self.synced += 1


class SceneTests(unittest.TestCase):
    def tearDown(self) -> None:
        SceneManager._current_scene = None

    def test_the_scene_is_a_pplay_scene_run_by_the_scene_manager(self) -> None:
        log = []
        app = App(log)
        app.change_scene(StateStack(Screen("menu", log)))
        self.assertIsInstance(app.scene, Scene)
        self.assertIs(SceneManager._current_scene, app.scene)
        scenes.run()
        self.assertEqual(log, [("step", "menu", app.frame, app.delta_time), ("draw", "menu")])
        self.assertEqual(app.renderer.frame_spare, .005)
        self.assertEqual(app.host.elastic_seconds, .002)

    def test_a_transition_makes_the_next_scene_current_and_it_draws_in_the_same_frame(self) -> None:
        log = []
        app = App(log, following=StateStack(Screen("game", log)))
        app.change_scene(StateStack(Screen("menu", log, then=Transition(TransitionKind.START))))
        first = app.scene
        scenes.run()
        self.assertIsNot(app.scene, first)
        self.assertIs(SceneManager._current_scene, app.scene)
        self.assertEqual([entry[:2] for entry in log], [("step", "menu"), ("draw", "game")])
        scenes.run()
        self.assertEqual([entry[:2] for entry in log[2:]], [("step", "game"), ("draw", "game")])

    def test_quitting_draws_nothing_and_closes(self) -> None:
        log = []
        app = App(log)
        app.change_scene(StateStack(Screen("menu", log, then=Transition(TransitionKind.QUIT))))
        scenes.run()
        self.assertTrue(app.closing)
        self.assertEqual([entry[:2] for entry in log], [("step", "menu")])


if __name__ == "__main__":
    unittest.main()
