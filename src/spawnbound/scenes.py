from __future__ import annotations

import spawnbound.pplay_media  # noqa: F401
from PPlay.scenemanager import Scene, SceneManager
from spawnbound.pplay_ui import window
from spawnbound.states import StateStack, TransitionKind


def _world(states: StateStack):
    gameplay = states.gameplay
    return gameplay.session.world if gameplay is not None else None


class StackScene(Scene):
    def __init__(self, app, states: StateStack) -> None:
        window()
        super().__init__()
        self.app, self.states = app, states

    def loop(self) -> None:
        app = self.app
        before = _world(self.states)
        transition = self.states.step(app.frame, app.delta_time)
        if transition.kind is TransitionKind.QUIT:
            app.closing = True
            return
        following = app.states_after(transition)
        if following is not None:
            app.change_scene(following)
        if _world(following or self.states) is not before:
            app.sync_presentation_scale()
        app.renderer.frame_spare = app.host.spare_seconds

    def draw(self) -> None:
        app = self.app
        if app.closing:
            return
        self.states.draw(app.renderer)
        app.host.elastic_seconds = getattr(app.renderer, "last_prefetch_seconds", 0.0)


def show(scene: StackScene) -> None:
    SceneManager.change_scene(scene)


def run() -> None:
    SceneManager.run()


__all__ = ["StackScene", "run", "show"]
