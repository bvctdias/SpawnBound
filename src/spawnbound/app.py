from __future__ import annotations

import secrets
from pathlib import Path

from spawnbound.paths import resource_dir
from spawnbound.config import GameConfig
from spawnbound.domain.session import GameSession
from spawnbound.domain.model import SpaceKind
from spawnbound.input import InputFrame
from spawnbound.states import GameplayState, StateStack, TransitionKind


class GameApplication:
    def __init__(
        self,
        config: GameConfig,
        seed: int,
        *,
        chunk_preview_size: int | None = None,
        art_pack: Path | None = None,
        fullscreen: bool = False,
        start_at_estuary: bool = False,
        start_in_menu: bool = False,
    ) -> None:
        from spawnbound.audio import AudioManager
        from spawnbound.pplay_host import PPlayHost
        from spawnbound.renderer import PlaceholderRenderer

        self.config = config
        self.seed = seed
        self.chunk_preview_size = chunk_preview_size
        self.start_at_estuary = start_at_estuary
        self.host = PPlayHost(config)
        self.audio = AudioManager()
        if fullscreen:
            self.host.toggle_fullscreen()
        if art_pack is not None:
            from spawnbound.prototype_art import PrototypeArtRenderer
            self.renderer = PrototypeArtRenderer(self.host.screen, config, art_pack)
        else:
            from spawnbound.sprites import PlayerSprites

            atlas = resource_dir() / "assets/native_32/player/animation.json"
            sprites = PlayerSprites.from_atlas(atlas) if atlas.is_file() else None
            self.renderer = PlaceholderRenderer(self.host.screen, config, player_sprites=sprites)
        self.renderer.direct_presentation = True
        self.host.bind_presenter(self.renderer.present_to)
        self.host.use_canvas(self.renderer.interface_layer)
        self.art_hit_test = getattr(self.renderer, 'hit_test', None)
        self.sync_presentation_scale()
        self.menu_scene = None
        self.frame, self.delta_time, self.closing = InputFrame(), 0., False
        self.change_scene(self._menu_stack() if start_in_menu else self._create_state_stack(seed))

    @property
    def states(self) -> StateStack:
        return self.scene.states

    def change_scene(self, states: StateStack) -> None:
        from spawnbound import scenes
        self.scene = scenes.StackScene(self, states)
        scenes.show(self.scene)
        self.audio.enter(states)

    def states_after(self, transition) -> StateStack | None:
        if transition.kind is TransitionKind.START:
            session = transition.session
            self.seed = session.home_world.seed
            return self._game_stack(session, transition.slot)
        if transition.kind is TransitionKind.TO_MENU:
            return self._menu_stack()
        if transition.kind is TransitionKind.RESTART:
            return self._create_state_stack(self.seed)
        if transition.kind is TransitionKind.NEW_SEED:
            self.seed = secrets.randbelow(2_147_483_647)
            return self._create_state_stack(self.seed)
        return None

    def sync_presentation_scale(self) -> None:
        states = getattr(self, 'states', None)
        gameplay = states.gameplay if states is not None else None
        indoors = gameplay is not None and gameplay.session.world.space_kind is SpaceKind.INTERIOR
        _scale, zoom = self.config.presentation_scale(self.host.window.real_screen.get_size(), interior=indoors)
        if zoom == self.renderer.config.camera_zoom:
            return
        self.renderer.set_camera_zoom(zoom)
        if gameplay is not None:
            gameplay.config = self.renderer.config

    def _create_state_stack(self, seed: int) -> StateStack:
        session = GameSession.create(
            seed,
            self.config,
            chunk_preview_size=self.chunk_preview_size,
        )
        if self.start_at_estuary:
            mouth = session.world.river_mouth
            if mouth is not None:
                session.player.place(session.world.surface_position(mouth))
                session.last_message = "Foz: clique na agua para nadar ou numa margem baixa para sair."
            else:
                session.last_message = "Sem foz neste mapa. Inicio no acampamento."
        session.spaces.prepare(session.world)
        session.navigation
        return self._game_stack(session)

    def _game_stack(self, session: GameSession, slot: int | None = None) -> StateStack:
        state = GameplayState(session=session, config=self.renderer.config, art_hit_test=self.art_hit_test,
                              play_sound=self.audio.play)
        if slot is not None:
            state.mark_saved(slot)
        return StateStack(state)

    def _menu_stack(self) -> StateStack:
        from spawnbound.menus import CACHE_DIR, MainMenuState, MenuScene
        if self.menu_scene is None:
            self.menu_scene = MenuScene(self.config, cache=CACHE_DIR)
        else:
            self.menu_scene.hide()
        return StateStack(MainMenuState(self.renderer.config, self.menu_scene, island_size=self.chunk_preview_size,
                                        ahead=True, play_sound=self.audio.play))

    def run(self) -> None:
        from spawnbound import scenes
        self.scene.draw()
        while not self.closing:
            self.frame, self.delta_time = self.host.next_frame()
            self.sync_presentation_scale()
            scenes.run()
            if not self.closing:
                self.audio.update(self.states, self.delta_time)
        self.audio.close()
        self.host.close()
