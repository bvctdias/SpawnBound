from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from enum import Enum
from typing import Protocol, Callable

from spawnbound.audio import quiet
from spawnbound.combat_audio import hit_sound
from spawnbound.config import GameConfig
from spawnbound.crafting_view import CraftPanel, bench_button, contains, recipe_layout
from spawnbound.domain.crafting import FURNITURE, RECIPES, TURNABLE, shown_recipes
from spawnbound.domain.farming import SEEDS
from spawnbound.domain import fishing
from spawnbound.domain.fish import pick_fish, water_of
from spawnbound.domain.tools import SICKLES
from spawnbound.animation import MotionKind, PlayerPose
from spawnbound.domain.coordinates import GridPos, WorldPos, NEIGHBOR_DIRECTIONS
from spawnbound.domain.movement import segment_allowed, segment_cells, walking_waypoints
from spawnbound.domain.session import FOOD, HURT_SECONDS, ActionCode, GameSession
from spawnbound.domain.model import OBJECT_SPECS, ObjectKind, SpaceKind, TileKind
from spawnbound.input import InputFrame
from spawnbound.domain.inventory import HOTBAR_SIZE, SLOT_COUNT, Inventory
from spawnbound.view import slot_at
from spawnbound import fishing_ui, guide_hud, repair_menu, rest_menu, sea_chart
from spawnbound.domain import guide
from spawnbound.pplay_ui import Fade
from spawnbound.domain.archipelago import dock_restored
from spawnbound.domain.daylight import DayPhase
from spawnbound.view import camera_origin, grid_cell_at_view_point, is_world_view_point, pick_world_point, project_grid_point, walk_point_from_hit

LANDING_WAIT = 4.
TURNED = {"bench": "Bancada girada.", "bed": "Cama girada.", "chest": "Baú girado.", "composter": "Composteira girada."}
PACK_SECONDS = .8
GUIDE_LOOK = .3
PASSED_SECONDS = 2.5
PACK_SHAKE = .2


class RendererPort(Protocol):
    def draw_gameplay(
        self,
        session: GameSession,
        *,
        debug: bool,
        path: tuple[GridPos, ...] = (),
        player_position: tuple[float, float, float] | None = None,
        action_target: GridPos | None = None,
        player_pose: PlayerPose | None = None,
        inventory_view: tuple[int | None, int | None, Inventory | None, CraftPanel] | None = None,
        map_view: bool = False,
        placement_preview: tuple[GridPos, str, bool] | None = None,
        rest_view: tuple[bool, str | None] | None = None,
        chart_view: tuple[str | None] | None = None,
        overlay: Callable | None = None,
        hud_overlay: Callable | None = None,
    ) -> None: ...

    def draw_pause(self) -> None: ...

    def draw_menu(self, session, camera, paint, veil: float = 0.) -> None: ...


class TransitionKind(str, Enum):
    NONE = "none"
    PUSH_PAUSE = "push_pause"
    POP = "pop"
    RESTART = "restart"
    NEW_SEED = "new_seed"
    QUIT = "quit"
    START = "start"
    TO_MENU = "to_menu"


@dataclass(frozen=True, slots=True)
class Transition:
    kind: TransitionKind = TransitionKind.NONE
    session: object | None = None
    slot: int | None = None


NO_TRANSITION = Transition()

ACTION_DURATION = {MotionKind.JUMP: .48, MotionKind.STRIKE: .36}
HOP_SECONDS = ACTION_DURATION[MotionKind.JUMP]
HOP_PLANTED = .125


class ClickIntent(str, Enum):
    TILL = "till"
    PLANT = "plant"
    HARVEST = "harvest"
    PLACE = "place"
    PRIMARY_ACTION = "primary_action"
    CONTEXT_INTERACTION = "context_interaction"


class AppState(Protocol):
    transparent: bool

    def step(self, frame: InputFrame, delta_time: float) -> Transition: ...

    def draw(self, renderer: RendererPort) -> None: ...


@dataclass(slots=True)
class GameplayState:
    session: GameSession
    config: GameConfig
    transparent: bool = False
    debug: bool = False
    play_sound: Callable[[str], None] = field(default=quiet, kw_only=True)
    inventory_open: bool = field(default=False, init=False)
    map_open: bool = field(default=False, init=False)
    rest_open: bool = field(default=False, init=False)
    _rest_pointer: tuple[int, int] | None = field(default=None, init=False)
    chart_open: bool = field(default=False, init=False)
    save_slot: int | None = field(default=None, init=False)
    _saved_played: float = field(default=0., init=False)
    _chart_pointer: tuple[int, int] | None = field(default=None, init=False)
    repair_open: GridPos | None = field(default=None, init=False)
    _repair_pointer: tuple[int, int] | None = field(default=None, init=False)
    fishing: fishing.FishingRun | None = field(default=None, init=False)
    fishing_rng: random.Random = field(default_factory=random.Random, init=False)
    _fishing_holding: bool = field(default=False, init=False)
    ending_open: bool = field(default=False, init=False)
    _ending_pointer: tuple[int, int] | None = field(default=None, init=False)
    _guide_wait: float = field(default=0., init=False)
    _passed: tuple[str, float] | None = field(default=None, init=False)
    _tip: tuple[str, float] | None = field(default=None, init=False)
    _tip_quiet: float = field(default=guide.FIRST_TIP_DELAY, init=False)
    _tip_fade: Fade = field(default_factory=lambda: Fade(0.), init=False)
    _tip_leaving: bool = field(default=False, init=False)
    _objective_fade: Fade = field(default_factory=Fade, init=False)
    _held: bool = field(default=False, init=False)
    _packing: GridPos | None = field(default=None, init=False)
    _pack_held: float = field(default=0., init=False)
    _pack_shake: float = field(default=0., init=False)
    _packing_intent: ClickIntent = field(default=ClickIntent.PRIMARY_ACTION, init=False)
    _chest: Inventory | None = field(default=None, init=False)
    craft_panel: CraftPanel = field(default_factory=CraftPanel, init=False)
    _source_slot: int | None = field(default=None, init=False)
    _hover_slot: int | None = field(default=None, init=False)
    art_hit_test: Callable[[str, object, float, float], bool | None] | None = None
    _path: tuple[GridPos, ...] = ()
    _destination: GridPos | None = None
    _destination_point: WorldPos | None = None
    _waypoints: tuple[WorldPos, ...] = ()
    _pending_target: GridPos | None = None
    _mob_id: int | None = None
    _harvest_again: GridPos | None = None
    _harvest_wait: float = 0.0
    _strike_duration: float = ACTION_DURATION[MotionKind.STRIKE]
    _pending_intent: ClickIntent | None = None
    _placing: str | None = None
    _placing_variant: str = "default"
    _turns: dict = field(default_factory=dict, init=False)
    _placement_preview: tuple | None = None
    _landing_held: float = field(default=0., init=False)
    _visual_position: tuple[float, float, float] = field(init=False)
    _animation_from: tuple[float, float, float] = field(init=False)
    _animation_to: tuple[float, float, float] | None = field(default=None, init=False)
    _animation_elapsed: float = field(default=0.0, init=False)
    _animation_duration: float = field(default=0.0, init=False)
    _walking_elapsed: float = field(default=0.0, init=False)
    _idle_elapsed: float = field(default=0.0, init=False)
    _action_motion: MotionKind | None = field(default=None, init=False)
    _action_elapsed: float = field(default=0.0, init=False)
    _hopping: bool = field(default=False, init=False)

    def __post_init__(self) -> None:
        self._saved_played = self.session.played_seconds
        position = self.session.player.position3d
        self._visual_position = (position.x, position.y, position.z)
        self._animation_from = self._visual_position
        session = self.session
        for life in (session.wildlife, session.island_life, *session.island_lives.values(), *session.mine_life.values()):
            life.in_view = self._in_camera_view

    def _in_camera_view(self, player: WorldPos, position: WorldPos) -> bool:
        config = self.config.world_view_config
        origin = camera_origin(self.session, config, player)
        x, y = project_grid_point(position, config)
        x, y = origin[0] + x, origin[1] + y
        margin = config.tile_width * 2
        return (-margin <= x <= config.virtual_width + margin
                and -margin <= y <= config.virtual_height + margin + config.world_sprite_padding)

    @property
    def visual_position(self) -> tuple[float, float]:
        return self._visual_position[:2]

    @property
    def visual_position3d(self) -> tuple[float, float, float]:
        return self._visual_position

    @property
    def player_pose(self) -> PlayerPose:
        if self.fishing is not None:
            return self._fishing_pose()
        if self._animation_to is not None and self._hopping:
            progress = self._animation_elapsed / self._animation_duration
            return PlayerPose(MotionKind.JUMP, self.session.player.facing, self._animation_elapsed, progress)
        if self.session.world.tile_map.kind_at(self.session.player.position) is TileKind.WATER:
            elapsed = self._walking_elapsed if self._animation_to is not None else self._idle_elapsed * .45
            return PlayerPose(MotionKind.SWIM, self.session.player.facing, elapsed)
        if self.session.hurt_time > 0:
            spent = HURT_SECONDS - self.session.hurt_time
            return PlayerPose(MotionKind.HURT, self.session.player.facing, spent, spent / HURT_SECONDS)
        if self._action_motion is not None:
            return PlayerPose(self._action_motion, self.session.player.facing, self._action_elapsed,
                              self._action_elapsed / self._action_duration)
        if self._animation_to is None:
            return PlayerPose(MotionKind.IDLE, self.session.player.facing, self._idle_elapsed)
        dz = self._animation_to[2] - self._animation_from[2]
        motion = MotionKind.STEP_UP if dz > 0 else MotionKind.STEP_DOWN if dz < 0 else MotionKind.WALK
        progress = self._animation_elapsed / self._animation_duration
        return PlayerPose(motion, self.session.player.facing, self._walking_elapsed, progress)

    def _sync_space(self) -> None:
        self._cancel_path(self.session.last_message)
        self.session.navigation
        p = self.session.player.position
        self._visual_position = (float(p.x), float(p.y), float(self.session.world.elevation_at(p)))
        self._animation_from = self._visual_position
        self._animation_to = None
        self._animation_elapsed = 0
        self._walking_elapsed = self._idle_elapsed = 0
        self._action_motion = None
        self._harvest_wait = 0.0

    @property
    def _action_duration(self):
        return self._strike_duration if self._action_motion is MotionKind.STRIKE else ACTION_DURATION[self._action_motion]

    @property
    def unsaved(self) -> bool:
        from spawnbound.menus import UNSAVED_SECONDS
        return self.session.played_seconds - self._saved_played > UNSAVED_SECONDS

    def mark_saved(self, slot: int) -> None:
        self.save_slot, self._saved_played = slot, self.session.played_seconds

    def step(self, frame: InputFrame, delta_time: float) -> Transition:
        self.session.played_seconds += max(0., delta_time)
        if (not frame.primary_held or frame.destination_click is not None or frame.cancel_path_pressed
                or frame.map_pressed or frame.pause_pressed or frame.inventory_pressed
                or frame.interact_pressed or frame.upgrade_pressed or frame.wheel_steps or frame.hotbar_index is not None):
            self._harvest_again = None
        self._held = frame.primary_held
        if (frame.destination_click is not None or frame.cancel_path_pressed or frame.map_pressed
                or frame.pause_pressed or frame.inventory_pressed or frame.interact_pressed):
            self._packing = None
        if frame.quit_requested:
            return Transition(TransitionKind.QUIT)
        if self.session.voyage is not None:
            if self.session.voyage.built and not self.session.voyage.landing_ready:
                self._landing_held += max(0., delta_time)
            self.session.advance_time(delta_time)
            if self.session.update_mobs(delta_time):
                self._sync_space()
            return NO_TRANSITION
        if self.fishing is not None:
            taken = self._step_fishing(frame, delta_time)
            if taken is not None:
                return taken
        if self.ending_open:
            self._ending_pointer = frame.pointer
            if (frame.pause_pressed or frame.interact_pressed
                    or guide_hud.ending_button_at(self.config, len(self._ending_lines()), frame.destination_click)):
                self.ending_open = False
            return NO_TRANSITION
        if self.map_open:
            if frame.map_pressed or frame.pause_pressed or frame.inventory_pressed:
                self.map_open = False
            return NO_TRANSITION
        if self.rest_open:
            self._rest_pointer = frame.pointer
            choice = rest_menu.button_at(self.config, frame.destination_click)
            if frame.pause_pressed or frame.interact_pressed or frame.inventory_pressed or frame.map_pressed:
                self.rest_open = False
            elif frame.craft_pressed or choice == "cook":
                self.rest_open = False
                self._open_cooking()
            elif frame.rest_pressed or choice == "rest":
                if self.session.rest_until_morning().success:
                    self.rest_open = False
            return NO_TRANSITION
        if self.chart_open:
            self._chart_pointer = frame.pointer
            choice = sea_chart.island_at(self.config, self.session.islands, frame.destination_click)
            if frame.pause_pressed or frame.interact_pressed or frame.inventory_pressed or frame.map_pressed:
                self.chart_open = False
            elif choice is not None and self.session.sail_to(choice).success:
                self.chart_open = False
                self._cancel_path(self.session.last_message)
            return NO_TRANSITION
        if self.repair_open is not None:
            self._repair_pointer = frame.pointer
            needs = self.session.repair_needs(self.repair_open)
            ready = needs is not None and self.session.player.inventory.has(needs)
            clicked = needs is not None and repair_menu.button_at(self.config, len(needs), frame.destination_click)
            if needs is None or frame.pause_pressed or frame.inventory_pressed or frame.map_pressed:
                self.repair_open = None
            elif ready and (frame.interact_pressed or clicked):
                self._repair()
            elif frame.interact_pressed:
                self.repair_open = None
            return NO_TRANSITION
        if frame.map_pressed and not self.inventory_open and self.session.survey is not None:
            self.map_open = True
            return NO_TRANSITION
        if frame.inventory_pressed or (self.inventory_open and frame.pause_pressed):
            back_to_bag = frame.pause_pressed and self.craft_panel.equipment == "bench"
            self.inventory_open = back_to_bag or not self.inventory_open
            self.craft_panel = CraftPanel()
            self._chest = None
            self._source_slot = self._hover_slot = None
            return NO_TRANSITION
        if self.inventory_open:
            self.craft_panel.pointer = frame.pointer or frame.destination_click
            if not self._handle_crafting(frame, delta_time):
                self._organize_inventory(frame)
            return NO_TRANSITION
        if frame.pause_pressed:
            self.play_sound("click")
            return Transition(TransitionKind.PUSH_PAUSE)
        if frame.restart_pressed:
            return Transition(TransitionKind.RESTART)
        if frame.new_seed_pressed:
            return Transition(TransitionKind.NEW_SEED)
        if self.session.drag_time > 0:
            self._action_motion = None
            self._cancel_path(self.session.last_message)
            self.session.advance_time(delta_time)
            if self.session.update_mobs(delta_time):
                self._sync_space()
            return NO_TRANSITION

        inventory = self.session.player.inventory
        if frame.hotbar_index is not None:
            inventory.selected = frame.hotbar_index
        elif frame.wheel_steps:
            if (inventory.equipped in TURNABLE and frame.pointer
                    and is_world_view_point(frame.pointer, self.config)):
                self._turn_equipped(inventory.equipped, frame.wheel_steps)
            else:
                inventory.selected = (inventory.selected - frame.wheel_steps) % HOTBAR_SIZE
        if self._pending_intent is ClickIntent.PLACE and inventory.equipped != self._placing:
            self._cancel_path("")
        if self._pending_intent is ClickIntent.TILL and inventory.equipped not in SICKLES:
            self._cancel_path("")
        if self._pending_intent is ClickIntent.PLANT and inventory.equipped not in SEEDS:
            self._cancel_path("")
        self._placement_preview = None
        if inventory.equipped in FURNITURE and frame.pointer and is_world_view_point(frame.pointer, self.config):
            origin = camera_origin(self.session, self.config, self._visual_position)
            hit = pick_world_point(self.session, frame.pointer, origin, self.config, self.art_hit_test)
            if hit is not None:
                self._placement_preview = (hit.position, inventory.equipped, self.session.can_place(hit.position),
                                           self._turn_of(inventory.equipped))
        self.session.advance_time(delta_time)
        elapsed = max(0., delta_time)
        if self._harvest_again is None:
            self._harvest_wait = max(0., self._harvest_wait - elapsed)
        else:
            self._harvest_wait -= elapsed
        if frame.debug_pressed:
            self.debug = not self.debug
        if self._action_motion is not None:
            self._action_elapsed += max(0.0, delta_time)
            if self._action_elapsed >= self._action_duration:
                self._action_motion = None
        if frame.cancel_path_pressed:
            self._cancel_path("Movimento cancelado.")
        if frame.right_click is not None:
            ripe = self._ripe_crop_at(frame.right_click)
            if ripe is not None:
                self._mob_id = self._harvest_again = None
                self._plan_target(ripe, ClickIntent.HARVEST)
            elif inventory.equipped in FOOD and not frame.eat_pressed:
                self.session.eat()
            elif is_world_view_point(frame.right_click, self.config, debug=self.debug):
                self._select_soil(frame.right_click)
        if frame.destination_click is not None:
            slot = slot_at(self.config, frame.destination_click, False)
            if slot is None:
                if not self._start_fishing(frame.destination_click):
                    self._set_destination(frame.destination_click)
            else:
                inventory.selected = slot
        if (frame.jump_pressed and self._action_motion is None and self._animation_to is None
                and self.session.world.tile_map.kind_at(self.session.player.position) is not TileKind.WATER):
            self._action_motion = MotionKind.JUMP
            self._action_elapsed = 0.0
        if frame.interact_pressed and self._animation_to is None:
            player = self.session.player
            ahead = player.position + player.facing
            if (self.session.repair_needs(ahead) is not None
                    and self.session.world.can_reach(player.position, ahead, self.config.max_step_height)):
                self._open_repair(ahead)
                return NO_TRANSITION
            previous_space = self.session.world.space_id
            result = self.session.interact()
            if result.code is ActionCode.CAMPFIRE_OPENED:
                self._open_rest()
                return NO_TRANSITION
            if result.code is ActionCode.DOCK_OPENED:
                self._open_chart()
                return NO_TRANSITION
            if result.code is ActionCode.STATION_OPENED:
                self._open_station()
                return NO_TRANSITION
            if result.code is ActionCode.CHEST_OPENED:
                player = self.session.player
                self._chest = self.session.world.objects[player.position + player.facing].storage
                self.inventory_open = True
                self._source_slot = self._hover_slot = None
                return NO_TRANSITION
            if result.code is ActionCode.WAYSTONE_TRAVEL or self.session.world.space_id != previous_space:
                self._sync_space()
        if frame.craft_pressed:
            self.session.craft_bridge_kit()
        if frame.upgrade_pressed:
            self.session.upgrade_pickaxe()
        if frame.rest_pressed and self.session.rest().code is ActionCode.CAMPFIRE_OPENED:
            self._open_rest()
            return NO_TRANSITION
        if frame.pack_furniture_pressed and self._animation_to is None:
            self.session.take_furniture()
        if frame.eat_pressed:
            self.session.eat()

        if self._mob_id is not None:
            mob = self.session.wildlife.mobs.get(self._mob_id)
            if mob is None:
                self._cancel_path("O alvo saiu de vista.")
            elif mob.location.grid != self._pending_target:
                self._plan_target(mob.location.grid, ClickIntent.PRIMARY_ACTION)
        self._advance_movement(delta_time)
        if self._packing is not None:
            self._update_packing(frame, delta_time)
        while (frame.primary_held and self._harvest_again is not None and
               self._animation_to is None and self._harvest_wait <= 1e-9):
            self._pending_target = self._harvest_again
            self._pending_intent = ClickIntent.PRIMARY_ACTION
            self._complete_pending_target()
        self.session.airborne = (self._action_motion is MotionKind.JUMP
                                 or (self._animation_to is not None and self._hopping))
        if self.session.update_mobs(delta_time):
            self._sync_space()
        self._follow_guide(delta_time)
        return NO_TRANSITION

    def _follow_guide(self, seconds: float) -> None:
        seconds = max(0., seconds)
        session = self.session
        if self._passed is not None:
            text, left = self._passed
            self._passed = (text, left - seconds) if left > seconds else None
            if self._passed is None:
                self._show_objective()
        if self._tip is not None:
            text, shown = self._tip
            self._tip = (text, shown + seconds) if shown + seconds < guide.TIP_SECONDS else None
            if self._tip is None:
                self._tip_quiet = guide.TIP_GAP
            elif shown + seconds >= guide.TIP_SECONDS - guide_hud.FADE and not self._tip_leaving:
                self._tip_leaving = True
                self._tip_fade.to(0, guide_hud.FADE, "ease_in")
        else:
            self._tip_quiet -= seconds
        self._guide_wait -= seconds
        if self._guide_wait > 0:
            return
        self._guide_wait = GUIDE_LOOK
        passed = guide.advance(session)
        if passed:
            self._passed = (passed[-1].text, PASSED_SECONDS)
            self._show_objective()
            if guide.finished(session) and not session.ending_seen:
                session.ending_seen = True
                self.ending_open = True
                self._cancel_path("")
        if self._tip is None and self._tip_quiet <= 0:
            tip = guide.next_tip(session)
            if tip is not None:
                session.tips_seen.add(tip.key)
                self._tip = (tip.text, 0.)
                self._tip_leaving = False
                self._tip_fade.transparency = 0
                self._tip_fade.to(255, guide_hud.FADE, "ease_out")

    def _show_objective(self) -> None:
        self._objective_fade.transparency = 0
        self._objective_fade.to(255, guide_hud.OBJECTIVE_FADE, "ease_out")

    def _ending_lines(self) -> list[str]:
        session = self.session
        minutes = int(session.played_seconds // 60)
        played = f"{minutes // 60} h {minutes % 60:02d} min" if minutes >= 60 else f"{minutes} min"
        return ["Você venceu o Guardião de Pedra.",
                f"Tempo de jogo: {played}   Ilhas visitadas: {len(session.visited)}   Corações: {session.max_hearts}",
                "A ilha continua aberta para explorar.", "Obrigado por jogar!"]

    def _ending_overlay(self) -> Callable | None:
        if not self.ending_open:
            return None
        lines = self._ending_lines()
        hover = guide_hud.ending_button_at(self.config, len(lines), self._ending_pointer)
        return lambda surface, config, font: guide_hud.draw_ending(surface, config, font, lines, hover)

    def _hud_overlay(self) -> Callable | None:
        cast = self._fishing_overlay()
        session = self.session
        objective = None if self.debug else guide.current(session)
        passed = None if self.debug else self._passed
        tip = None if self.debug else self._tip
        if cast is None and objective is None and passed is None and tip is None:
            return None
        step, total = session.objective + 1, len(guide.OBJECTIVES)
        shown, faded = self._objective_fade.transparency, self._tip_fade.transparency

        def paint(surface, config, font):
            covered = []
            if cast is not None:
                covered.append(cast(surface, config, font))
            if passed is not None:
                covered.append(guide_hud.draw_objective(surface, font, step - 1, total, passed[0], "", done=True,
                                                        transparency=shown))
            elif objective is not None:
                covered.append(guide_hud.draw_objective(surface, font, step, total, objective.text, objective.how,
                                                        transparency=shown))
            if tip is not None:
                covered.append(guide_hud.draw_tip(surface, config, font, tip[0], faded))
            return covered[0].unionall(covered[1:])
        return paint

    def _start_fishing(self, click: tuple[float, float]) -> bool:
        session = self.session
        if (session.player.inventory.equipped != "fishing_rod"
                or not is_world_view_point(click, self.config, debug=self.debug)):
            return False
        origin = camera_origin(session, self.config, self._visual_position)
        hit = pick_world_point(session, click, origin, self.config, self.art_hit_test)
        if hit is None or hit.kind not in ("tile", "water") or water_of(session.world, hit.position) is None:
            return False
        player = session.player
        if session.world.tile_map.kind_at(player.position) is TileKind.WATER:
            session.warn("Saia da água para pescar.")
            return True
        self._cancel_path("")
        self._action_motion = None
        step = hit.position - player.position
        if step.x or step.y:
            player.facing = GridPos((step.x > 0) - (step.x < 0), (step.y > 0) - (step.y < 0))
        self.fishing = fishing.FishingRun(hit.position, self.fishing_rng)
        return True

    def _stop_fishing(self, message: str = "Linha recolhida.", *, warn: bool = False) -> None:
        self.fishing = None
        if warn:
            self.session.warn(message)
        else:
            self.session.last_message = message

    def _step_fishing(self, frame: InputFrame, delta_time: float) -> Transition | None:
        run, session = self.fishing, self.session
        seconds = max(0., delta_time)
        self._fishing_holding = frame.primary_held or frame.secondary_held
        if run.phase != "caught":
            if frame.pause_pressed or frame.cancel_path_pressed:
                self._stop_fishing()
                return NO_TRANSITION
            if (frame.inventory_pressed or frame.map_pressed or frame.interact_pressed
                    or frame.hotbar_index is not None or frame.wheel_steps
                    or session.player.inventory.equipped != "fishing_rod"):
                self._stop_fishing()
                return None
        if run.phase == "minigame":
            run.clock += seconds
            result = run.game.step(seconds, self._fishing_holding)
            if result == "caught":
                if session.catch_fish(run.fish.item).success:
                    self.play_sound("pickup")
                    run.enter("caught")
                else:
                    self.fishing = None
            elif result == "escaped":
                fish = run.fish
                self._stop_fishing(f"{'A' if fish.feminine else 'O'} {fish.name.lower()} escapou.", warn=True)
            return NO_TRANSITION
        session.advance_time(delta_time)
        run.clock += seconds
        clicked = frame.destination_click is not None or frame.right_click is not None
        if run.phase == "charging":
            if frame.primary_held:
                run.held += seconds
                run.power = fishing.power_at(run.held)
            else:
                run.bobber = fishing.landing(session.player.position, run.aim, run.power)
                run.water = water_of(session.world, run.bobber)
                run.enter("casting")
        elif run.phase == "casting":
            if run.clock >= fishing.SWING_SECONDS + fishing.FLIGHT_SECONDS:
                if run.water is None:
                    self._stop_fishing("A boia caiu fora da água. Segure o clique por mais tempo.", warn=True)
                    return NO_TRANSITION
                run.bite_at = fishing.bite_delay(run.rng, fishing.near_shelter(session.world, run.bobber))
                run.enter("waiting")
        elif run.phase == "waiting":
            if clicked:
                self._stop_fishing()
                return NO_TRANSITION
            if run.clock >= run.bite_at:
                night = session.daylight.phase is DayPhase.NIGHT
                run.fish = pick_fish(run.rng, run.water, night)
                self.play_sound("splash")
                run.enter("bite")
        elif run.phase == "bite":
            if clicked:
                run.game = fishing.Minigame(run.fish, run.rng)
                run.enter("minigame")
                return NO_TRANSITION
            if run.clock >= fishing.BITE_WINDOW:
                run.fish = None
                run.bite_at = fishing.bite_delay(run.rng, fishing.near_shelter(session.world, run.bobber))
                run.enter("waiting")
                session.last_message = "O peixe soltou a isca."
        elif run.phase == "caught" and run.clock >= fishing.SHOW_SECONDS:
            self.fishing = None
        before = session.hurt_time
        if session.update_mobs(delta_time):
            self.fishing = None
            self._sync_space()
        elif (self.fishing is not None and self.fishing.phase != "caught"
              and (session.hurt_time > before or session.drag_time > 0)):
            self._stop_fishing("Você soltou a linha.", warn=True)
        return NO_TRANSITION

    def _fishing_pose(self) -> PlayerPose:
        run, facing, strike = self.fishing, self.session.player.facing, MotionKind.STRIKE
        if run.phase == "charging":
            return PlayerPose(strike, facing, 0., .13 + .2 * run.power)
        if run.phase == "casting" and run.clock < fishing.SWING_SECONDS:
            return PlayerPose(strike, facing, run.clock, .33 + .67 * run.clock / fishing.SWING_SECONDS)
        if run.phase == "minigame":
            if run.clock < fishing.HOOK_SECONDS:
                return PlayerPose(strike, facing, run.clock, .25 * run.clock / fishing.HOOK_SECONDS)
            return PlayerPose(strike, facing, run.clock, .13 if self._fishing_holding else .01)
        return PlayerPose(MotionKind.IDLE, facing, run.clock)

    def _fishing_overlay(self) -> Callable | None:
        run = self.fishing
        if run is None:
            return None
        pose, visual, holding = self.player_pose, self._visual_position, self._fishing_holding
        clock = self.session.played_seconds
        return lambda surface, config, font: fishing_ui.draw(surface, config, font, self.session, run, pose,
                                                              visual, holding, clock)

    def _slot_owner(self, index: int) -> tuple[Inventory, int]:
        if self._chest is not None and index >= SLOT_COUNT:
            return self._chest, index - SLOT_COUNT
        return self.session.player.inventory, index

    def _open_station(self) -> None:
        player = self.session.player
        obj = self.session.world.object_at(player.position + player.facing)
        self._open_recipes(None if obj.kind is ObjectKind.BENCH else obj.production)

    def _open_cooking(self) -> None:
        cell = self.session.campfire_beside()
        if cell is not None:
            self._open_recipes(self.session.world.objects[cell].production)

    def _open_recipes(self, station) -> None:
        if station is None:
            self.craft_panel = CraftPanel("bench")
        else:
            station.refresh(self.session.production_seconds)
            self.craft_panel = CraftPanel(station.equipment, station)
        self.inventory_open = True
        self._chest = self._source_slot = self._hover_slot = None
        self._cancel_path("")

    def _handle_crafting(self, frame: InputFrame, seconds: float) -> bool:
        if self._chest is not None:
            return False
        panel = self.craft_panel
        click = frame.destination_click
        if panel.production is None and contains(bench_button(self.config), click) and (
                panel.equipment is None or recipe_layout(self.config, "bench").beside_bag):
            self.play_sound("click")
            panel.equipment = None if panel.equipment else "bench"
            panel.message = ""
            self._source_slot = self._hover_slot = None
            return True
        if panel.equipment is None:
            return False
        bag = self.session.player.inventory
        layout = recipe_layout(self.config, panel.equipment, bag)
        station = panel.production
        if station is not None:
            self.session.production_seconds += max(0., seconds)
            now = self.session.production_seconds
            station.refresh(now)
            if contains(layout.collect, click):
                self.play_sound("click")
                panel.message = station.collect(bag, now)
            elif station.recipe and contains(layout.cancel, click):
                self.play_sound("click")
                panel.message = station.cancel(bag, now)
        for row, recipe in zip(layout.rows, shown_recipes(panel.equipment, bag)):
            if contains(row, click):
                self.play_sound("click")
                if station is None:
                    panel.message = self.session.craft_at_bench(recipe).message
                else:
                    panel.message = station.start(recipe, bag, now)
                return True
        return not layout.beside_bag

    def _move_stack(self, source: int, target: int, *, single: bool = False) -> None:
        origin, i = self._slot_owner(source)
        destination, j = self._slot_owner(target)
        before = origin.slots[i]
        origin.transfer(i, j, destination=destination, single=single)
        if before != origin.slots[i]:
            self.play_sound("slot")

    def _organize_inventory(self, frame: InputFrame) -> None:
        inventory = self.session.player.inventory
        def locate(point):
            return slot_at(self.config, point, True, self._chest is not None) if point is not None else None

        self._hover_slot = locate(frame.pointer)
        if frame.hotbar_index is not None:
            if self._hover_slot is not None:
                origin, i = self._slot_owner(self._hover_slot)
                target = frame.hotbar_index
                origin.slots[i], inventory.slots[target] = inventory.slots[target], origin.slots[i]
            inventory.selected = frame.hotbar_index
            self._source_slot = None
            return
        if frame.destination_click is not None:
            target = locate(frame.destination_click)
            if target is not None:
                if self._source_slot is None:
                    owner, i = self._slot_owner(target)
                    if owner.slots[i]:
                        self.play_sound("slot")
                        self._source_slot = target
                else:
                    self._move_stack(self._source_slot, target)
                    self._source_slot = None
        if self._source_slot is not None and frame.left_release is not None:
            target = locate(frame.left_release)
            if target is not None and target != self._source_slot:
                self._move_stack(self._source_slot, target)
                self._source_slot = None
        if self._source_slot is not None and frame.right_click is not None:
            target = locate(frame.right_click)
            if target is not None:
                self._move_stack(self._source_slot, target, single=True)
                owner, i = self._slot_owner(self._source_slot)
                if owner.slots[i] is None:
                    self._source_slot = None

    def _ripe_crop_at(self, click: tuple[float, float]) -> GridPos | None:
        if not self.session.world.crops or not is_world_view_point(click, self.config, debug=self.debug):
            return None
        origin = camera_origin(self.session, self.config, self._visual_position)
        hit = pick_world_point(self.session, click, origin, self.config, self.art_hit_test)
        if hit is not None and hit.kind == "tile" and self.session.crop_ripe(hit.position):
            return hit.position
        return None

    def _select_soil(self, click: tuple[float, float]) -> None:
        equipped = self.session.player.inventory.equipped
        if equipped not in SICKLES and equipped not in SEEDS:
            self.session.warn("Equipe a foice para arar.")
            return
        origin = camera_origin(self.session, self.config, self._visual_position)
        hit = pick_world_point(self.session, click, origin, self.config, self.art_hit_test)
        if hit is None or hit.kind != "tile" or not hit.surface:
            self.session.warn("Escolha um bloco de grama livre.")
            return
        if equipped in SEEDS:
            world = self.session.world
            if hit.position in world.crops:
                self.session.warn("Já há uma planta aqui.")
            elif world.tilled_soil.get(hit.position) != 2:
                self.session.warn("Prepare a terra com a foice antes de plantar.")
            else:
                self._mob_id = self._harvest_again = None
                self._plan_target(hit.position, ClickIntent.PLANT)
            return
        obstacle = self.session.soil_obstacle(hit.position)
        if obstacle:
            self.session.warn(obstacle)
            return
        self._mob_id = self._harvest_again = None
        self._plan_target(hit.position, ClickIntent.TILL)

    def _set_destination(self, click: tuple[float, float]) -> None:
        if not is_world_view_point(click, self.config, debug=self.debug):
            return

        origin = camera_origin(self.session, self.config, self._visual_position)
        hit = pick_world_point(self.session, click, origin, self.config, self.art_hit_test)
        self._mob_id = hit.mob_id if hit is not None else None
        if self._mob_id is not None:
            self._plan_target(hit.position, ClickIntent.PRIMARY_ACTION)
            return
        destination = hit.position if hit is not None else grid_cell_at_view_point(click, origin, self.config)
        tile = self.session.world.tile_map.tile_at(destination)
        obj = self.session.world.object_at(destination)
        item = self.session.player.inventory.equipped
        if item in FURNITURE and obj is None and destination not in self.session.world.portals:
            if hit is None or not self.session.can_place(destination):
                self._cancel_path("Escolha um espaço livre.")
                return
            self._placing = item
            self._placing_variant = self._turn_of(item)
            self._plan_target(destination, ClickIntent.PLACE)
            return
        if obj and obj.kind in (ObjectKind.BED, ObjectKind.CAMPFIRE, ObjectKind.WINDMILL, ObjectKind.WAYSTONE,
                                ObjectKind.DOCK):
            self._plan_target(destination, ClickIntent.CONTEXT_INTERACTION)
            return
        if destination in self.session.world.portals or (obj and (obj.storage is not None or obj.production is not None
                                                                  or obj.kind is ObjectKind.BENCH)):
            self._plan_target(destination, ClickIntent.CONTEXT_INTERACTION)
            return
        if tile is not None and tile.kind is TileKind.CAVE_WALL:
            self._plan_target(destination, ClickIntent.PRIMARY_ACTION)
            return
        if hit is None and not self.session.world.bridge.contains(destination):
            self._cancel_path("Nao ha superficie nesse ponto.")
            return
        if obj is not None:
            self._plan_target(destination, ClickIntent.PRIMARY_ACTION)
            return
        if self.session.world.bridge.contains(destination) and not self.session.world.bridge.built:
            self._plan_target(destination, ClickIntent.CONTEXT_INTERACTION)
            return
        navigation = self.session.navigation
        start = self.session.player.position
        if not navigation.reachable(start, destination):
            notice = ("Mar aberto: a corrente e forte demais." if tile is not None and tile.deep_water
                      else "Sem caminho ate ali: indo ao ponto mais proximo.")
            self._approach_edge(destination, notice)
            return
        point = (walk_point_from_hit(hit, click, origin, self.session.world, self.config)
                 if hit is not None else self.session.world.surface_position(destination))
        path = navigation.route(start, (destination,))
        if path is None:
            self._cancel_path("Nao existe caminho ate o destino escolhido.")
            return

        self._stop_motion()
        self._pending_target = None
        self._pending_intent = None
        if not self._queue_route(path, point):
            return
        self.session.last_message = f"Destino selecionado: {destination.x},{destination.y}."
        if not self._waypoints:
            self.session.last_message = "Destino alcancado."

    def _plan_target(self, target: GridPos, intent: ClickIntent) -> None:
        candidates: list[GridPos] = []
        if self._mob_id is not None and self.session.player.position == target:
            candidates.append(target)
        for direction in NEIGHBOR_DIRECTIONS:
            approach = target - direction
            if self._mob_id is not None and not self.session.world.can_step(approach, target):
                continue
            if not self.session.world.can_reach(approach, target, self.config.max_step_height):
                continue
            if self.session.world.player_can_enter(approach):
                candidates.append(approach)

        portal = self.session.world.portals.get(target)
        if portal is not None and portal.target_kind is SpaceKind.INTERIOR:
            candidates = [portal.approach]
        path = self.session.navigation.route(self.session.player.position, candidates)
        if path is None:
            self._approach_edge(target, "Sem acesso ao alvo: indo ao ponto mais proximo.")
            return

        approach = path[-1] if path else self.session.player.position
        self._stop_motion()
        self._pending_target = target
        self._pending_intent = intent
        if not path:
            self._path = ()
            self._waypoints = ()
            self._destination = self._destination_point = None
            self._complete_pending_target()
        else:
            if not self._queue_route(path, self.session.world.surface_position(approach)):
                return
            action = "usar a ferramenta" if intent is ClickIntent.PRIMARY_ACTION else "interagir"
            self.session.last_message = f"Aproximando para {action}."

    def _queue_route(self, path: tuple[GridPos, ...], point: WorldPos) -> bool:
        self._destination = point.grid
        self._destination_point = point
        try:
            self._waypoints = walking_waypoints(self.session.world, self.session.player.position3d,
                                                path, point, self.config.max_step_height, swim=True)
        except ValueError:
            self._cancel_path("O caminho ate o destino foi bloqueado.")
            return False
        self._path = tuple(p.grid for p in self._waypoints)
        return True

    def _approach_edge(self, target: GridPos, notice: str) -> None:
        self._cancel_path(notice)
        start = self.session.player.position
        nav = self.session.navigation
        edge = nav.nearest_reachable(start, target)
        if edge is None or edge == start:
            return
        route = nav.route(start, (edge,))
        if route is not None:
            self._queue_route(route, self.session.world.surface_position(edge))

    def _advance_movement(self, delta_time: float) -> None:
        remaining = max(0.0, delta_time)
        while True:
            if self._animation_to is None:
                if not self._path:
                    self._idle_elapsed += remaining
                    self._walking_elapsed = 0.0
                    return
                started = self._update_path()
                if self._animation_to is None:
                    if started:
                        continue
                    return
            duration_left = max(0.0, self._animation_duration - self._animation_elapsed)
            consumed = min(remaining, duration_left)
            self._walking_elapsed += consumed
            self._idle_elapsed = 0.0
            self._update_visual_position(consumed)
            remaining = max(0.0, remaining - consumed)
            if self._animation_to is not None:
                return

    def _update_path(self) -> bool:
        if not self._path:
            return False
        if not self._waypoints:
            self._queue_route(self._path, self._destination_point or self.session.world.surface_position(self._path[-1]))
            if not self._waypoints:
                return False

        next_position = self._waypoints[0]
        if not segment_allowed(self.session.world, self.session.player.position3d,
                               next_position, self.config.max_step_height, swim=True):
            self.session.navigation.refresh(segment_cells(self.session.player.position3d, next_position))
            self._stop_motion()
            self._replan_path()
            return False

        dx = next_position.x - self.session.player.position3d.x
        dy = next_position.y - self.session.player.position3d.y
        angle = math.atan2(dy, dx)
        self.session.player.facing = min(NEIGHBOR_DIRECTIONS,
            key=lambda d: abs(math.atan2(math.sin(math.atan2(d.y, d.x) - angle),
                                         math.cos(math.atan2(d.y, d.x) - angle))))
        self._start_visual_move(next_position)
        return True

    def _replan_path(self) -> None:
        if self._pending_target is not None and self._pending_intent is not None:
            self._plan_target(self._pending_target, self._pending_intent)
            return
        if self._destination_point is None:
            self._cancel_path("Movimento interrompido.")
            return

        path = self.session.navigation.route(self.session.player.position, (self._destination,))
        if path is not None:
            self._queue_route(path, self._destination_point)
            return
        self._cancel_path("O caminho ate o destino foi bloqueado.")

    def _start_visual_move(self, destination: WorldPos) -> None:
        if self._action_motion is MotionKind.STRIKE:
            self._action_motion = None
        target = (destination.x, destination.y, destination.z)
        if self.config.movement_seconds_per_cell <= 0.0:
            if not self.session.move_continuous(destination.x, destination.y).success:
                self._cancel_path("O caminho ate o destino foi bloqueado.")
                return
            self._visual_position = target
            self._animation_from = target
            self._animation_to = None
            self._finish_segment()
            return

        self._animation_from = self._visual_position
        self._animation_to = target
        self._animation_elapsed = 0.0
        distance = math.hypot(
            target[0] - self._animation_from[0],
            target[1] - self._animation_from[1],
        )
        self._animation_duration = self.config.movement_seconds_per_cell * distance
        if self.session.world.tile_map.kind_at(destination.grid) is TileKind.WATER:
            self._animation_duration *= 1.45
        # A rota mantém o ponto de entrada de cada degrau para sincronizar o salto com a mudança de nível.
        self._hopping = abs(target[2] - self._animation_from[2]) > .5
        if self._hopping:
            self._animation_duration = max(self._animation_duration, HOP_SECONDS)

    def _update_visual_position(self, delta_time: float) -> None:
        if self._animation_to is None:
            return

        duration = self._animation_duration
        self._animation_elapsed = min(duration, self._animation_elapsed + delta_time)
        progress = self._animation_elapsed / duration
        if self._hopping:
            progress = min(1., max(0., (progress - HOP_PLANTED) / (1 - 2 * HOP_PLANTED)))
        candidate = tuple(
            start + (target - start) * progress
            for start, target in zip(self._animation_from, self._animation_to)
        )

        if not self.session.move_continuous(candidate[0], candidate[1]).success:
            self._stop_motion()
            self._replan_path()
            return
        self._visual_position = candidate

        if self._animation_elapsed >= duration - 1e-9:
            self._visual_position = self._animation_to
            self._animation_from = self._visual_position
            self._animation_to = None
            self._finish_segment()

    def _finish_segment(self) -> None:
        self._waypoints = self._waypoints[1:]
        self._path = self._path[1:]
        if not self._waypoints:
            self._destination = self._destination_point = None
            if self._pending_target is not None:
                self._complete_pending_target()
            elif not self.session.completed:
                self.session.last_message = "Destino alcancado."

    def _stop_motion(self) -> None:
        self._animation_to = None
        self._animation_elapsed = 0.0
        p = self.session.player.position3d
        self._visual_position = (p.x, p.y, p.z)
        self._animation_from = self._visual_position

    def _complete_pending_target(self, pack: bool = True) -> None:
        if self._pending_target is None or self._pending_intent is None:
            return
        if self._animation_to is not None:
            return

        target = self._pending_target
        intent = self._pending_intent
        direction = target - self.session.player.position
        if direction not in NEIGHBOR_DIRECTIONS and not (self._mob_id is not None and target == self.session.player.position):
            self._cancel_path("O alvo deixou de estar ao alcance.")
            return

        self._pending_target = None
        self._pending_intent = None
        if direction in NEIGHBOR_DIRECTIONS:
            self.session.player.facing = direction
        if intent in (ClickIntent.PLANT, ClickIntent.HARVEST):
            act = self.session.plant if intent is ClickIntent.PLANT else self.session.harvest
            if act(target).success:
                self._action_motion = MotionKind.STRIKE
                self._strike_duration = ACTION_DURATION[MotionKind.STRIKE]
                self._action_elapsed = 0.
            return
        if intent is ClickIntent.TILL:
            if self.session.till_soil(target).success:
                self._action_motion = MotionKind.STRIKE
                self._strike_duration = ACTION_DURATION[MotionKind.STRIKE]
                self._action_elapsed = 0.
            return
        if intent is ClickIntent.PLACE:
            self.session.place_furniture(target, self._placing, self._placing_variant)
            self._placing = self._placement_preview = None
            return
        if intent in (ClickIntent.PRIMARY_ACTION, ClickIntent.CONTEXT_INTERACTION) and self._mob_id is None:
            obj = self.session.world.object_at(target)
            if self.session.repair_needs(target) is not None:
                self._open_repair(target)
                return
            if pack and self._held and obj is not None and obj.kind.value in FURNITURE:
                self._packing, self._pack_held, self._pack_shake = target, 0., 0.
                self._packing_intent = intent
                return
        if intent is ClickIntent.PRIMARY_ACTION:
            obj = self.session.world.object_at(target)
            resource = self._mob_id is None and (obj is not None or
                       self.session.world.tile_map.kind_at(target) is TileKind.CAVE_WALL)
            if resource and self._harvest_wait > 1e-9:
                self._harvest_again = target
                return
            if self._mob_id is not None:
                mob = self.session.wildlife.mobs.get(self._mob_id)
                previous_hp = mob.hp if mob is not None else 0
                result = self.session.attack_mob(self._mob_id)
                if mob is not None and result.code in (ActionCode.MOB_HIT, ActionCode.MOB_DEFEATED):
                    self.play_sound(hit_sound(mob, previous_hp))
            else:
                result = self.session.primary_action(target)
            self._mob_id = None
            self._harvest_again = target if result.code is ActionCode.RESOURCE_HIT else None
            if result.success:
                self._strike_duration = ACTION_DURATION[MotionKind.STRIKE]
                if resource:
                    spec = obj.spec if obj else OBJECT_SPECS[ObjectKind.ROCK]
                    self._strike_duration = spec.swing_seconds
                    self._harvest_wait += self._strike_duration
                self._action_motion = MotionKind.STRIKE
                self._action_elapsed = max(0., self._strike_duration - self._harvest_wait) if resource else 0.
        else:
            obj = self.session.world.object_at(target)
            if obj and obj.kind is ObjectKind.BED:
                self.session.rest()
                return
            if obj and obj.kind in (ObjectKind.WINDMILL, ObjectKind.WAYSTONE):
                self.session.primary_action(target)
                return
            if obj and obj.kind is ObjectKind.DOCK:
                if not dock_restored(obj):
                    self.session.primary_action(target)
                elif self.session.interact().code is ActionCode.DOCK_OPENED:
                    self._open_chart()
                return
            if obj and obj.kind is ObjectKind.CAMPFIRE:
                self._open_rest()
                return
            if obj and (obj.production is not None or obj.kind is ObjectKind.BENCH):
                if self.session.interact().code is ActionCode.STATION_OPENED:
                    self._open_station()
                return
            self.session.warn("Pressione E para abrir o bau." if obj and obj.kind is ObjectKind.CHEST
                              else "Pressione E para interagir.")

    def _open_rest(self) -> None:
        self.rest_open = True
        self._cancel_path("")

    def _open_repair(self, target: GridPos) -> None:
        self.repair_open = target
        self._repair_pointer = None
        self._cancel_path("")

    def _repair(self) -> None:
        target, self.repair_open = self.repair_open, None
        player = self.session.player
        if target - player.position in NEIGHBOR_DIRECTIONS:
            player.facing = target - player.position
        self.session.interact()

    def _repair_overlay(self) -> Callable | None:
        target = self.repair_open
        needs = self.session.repair_needs(target) if target is not None else None
        if needs is None:
            return None
        kind = self.session.world.object_at(target).kind.value
        have = {item: self.session.player.inventory.quantity(item) for item in needs}
        hover = repair_menu.button_at(self.config, len(needs), self._repair_pointer)
        return lambda surface, config, font: repair_menu.draw(surface, config, font, kind, needs, have, hover)

    def _update_packing(self, frame: InputFrame, seconds: float) -> None:
        target = self._packing
        if self.session.world.object_at(target) is None:
            self._packing = None
            return
        if not frame.primary_held:
            self._packing = None
            self._pending_target, self._pending_intent = target, self._packing_intent
            self._complete_pending_target(pack=False)
            return
        self._pack_held += max(0., seconds)
        self._pack_shake -= max(0., seconds)
        if self._pack_shake <= 0:
            self._pack_shake += PACK_SHAKE
            self.session.shake(target)
            if self._action_motion is None:
                self._action_motion, self._action_elapsed = MotionKind.STRIKE, 0.
                self._strike_duration = ACTION_DURATION[MotionKind.STRIKE]
        if self._pack_held >= PACK_SECONDS:
            self._packing = None
            player = self.session.player
            if target - player.position in NEIGHBOR_DIRECTIONS:
                player.facing = target - player.position
            self.session.take_furniture()

    def _open_chart(self) -> None:
        self.chart_open = True
        self._chart_pointer = None
        self._cancel_path("")

    def _turn_equipped(self, item: str, steps: int) -> None:
        sides = TURNABLE[item]
        side = sides[(sides.index(self._turn_of(item)) + steps) % len(sides)]
        self._turns[item] = side
        self.session.last_message = (("Boca da fornalha " + ("a direita." if side == "right" else "a esquerda."))
                                     if item == "kiln" else TURNED.get(item, "Girado."))

    def _turn_of(self, item: str | None) -> str:
        sides = TURNABLE.get(item)
        return self._turns.get(item, sides[0]) if sides else "default"

    def _cancel_path(self, message: str) -> None:
        self._harvest_again = None
        self._packing = None
        self._mob_id = None
        self._stop_motion()
        self._path = ()
        self._waypoints = ()
        self._destination = None
        self._destination_point = None
        self._pending_target = None
        self._pending_intent = None
        self.session.last_message = message

    def draw(self, renderer: RendererPort, overlay: Callable | None = None) -> None:
        renderer.draw_gameplay(
            self.session,
            overlay=overlay or self._ending_overlay() or self._repair_overlay(),
            hud_overlay=self._hud_overlay(),
            debug=self.debug,
            path=self._path,
            player_position=self._visual_position,
            action_target=self._pending_target,
            player_pose=self.player_pose,
            inventory_view=(self._source_slot, self._hover_slot, self._chest, self.craft_panel) if self.inventory_open else None,
            map_view=self.map_open,
            placement_preview=(self._placement_preview
                               if not (self.inventory_open or self.map_open or self.rest_open or self.chart_open
                                       or self.repair_open is not None or self.ending_open)
                               else None),
            rest_view=((self.session.daylight.phase is not DayPhase.DAY,
                        rest_menu.button_at(self.config, self._rest_pointer)) if self.rest_open else None),
            chart_view=((sea_chart.island_at(self.config, self.session.islands, self._chart_pointer),)
                        if self.chart_open else None),
        )
        self._prepare_landing(renderer)

    def _prepare_landing(self, renderer: RendererPort) -> None:
        prepare = getattr(renderer, "prepare_arrival", None)
        if prepare is None:
            return
        session = self.session
        voyage = session.voyage
        if voyage is not None:
            landing = (voyage.world, voyage.landing) if voyage.world is not None else None
        else:
            self._landing_held = 0.
            landing = door_ahead(session)
        ready = landing is None or prepare(session, *landing, veiled=voyage is not None)
        if voyage is not None:
            voyage.landing_ready = (landing is not None and ready) or self._landing_held > LANDING_WAIT


def door_ahead(session: GameSession) -> tuple[object, GridPos] | None:
    here = session.player.position
    doors = [portal for portal in session.world.portals.values() if portal.target_kind is not SpaceKind.INTERIOR]
    if not doors:
        return None
    door = min(doors, key=lambda p: abs(p.position.x - here.x) + abs(p.position.y - here.y))
    world = session.spaces.worlds.get(door.target_space_id)
    if world is None:
        return None
    return world, door.arrival or world.spawn


class StateStack:
    def __init__(self, base: AppState, save_folder=None) -> None:
        self._states: list[AppState] = [base]
        self.save_folder = save_folder

    @property
    def gameplay(self) -> GameplayState | None:
        base = self._states[0]
        return base if isinstance(base, GameplayState) else None

    @property
    def top(self) -> AppState:
        return self._states[-1]

    _LEAVING = {TransitionKind.QUIT: "quit", TransitionKind.RESTART: "restart", TransitionKind.NEW_SEED: "new_seed"}

    def step(self, frame: InputFrame, delta_time: float) -> Transition:
        gameplay = self.gameplay
        if frame.close_requested and gameplay is not None:
            return self._leave(gameplay, TransitionKind.QUIT)
        top = self._states[-1]
        transition = top.step(frame, delta_time)
        if top is gameplay and transition.kind in self._LEAVING:
            return self._leave(gameplay, transition.kind)

        if transition.kind is TransitionKind.PUSH_PAUSE:
            from spawnbound.menus import PauseMenuState
            self._states.append(PauseMenuState(gameplay, self.save_folder))
            return NO_TRANSITION
        if transition.kind is TransitionKind.POP:
            if len(self._states) > 1:
                self._states.pop()
            return NO_TRANSITION
        return transition

    def _leave(self, gameplay: GameplayState, kind: TransitionKind) -> Transition:
        if not gameplay.unsaved:
            return Transition(kind)
        from spawnbound.menus import PauseMenuState
        if not isinstance(self._states[-1], PauseMenuState):
            self._states.append(PauseMenuState(gameplay, self.save_folder))
        self._states[-1].ask_leave(self._LEAVING[kind])
        return NO_TRANSITION

    def draw(self, renderer: RendererPort) -> None:
        first_visible = len(self._states) - 1
        while first_visible > 0 and self._states[first_visible].transparent:
            first_visible -= 1
        for state in self._states[first_visible:]:
            state.draw(renderer)
