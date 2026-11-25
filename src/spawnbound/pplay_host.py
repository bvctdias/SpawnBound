from __future__ import annotations

import math
import os
import time

# O SDL lê a opção de sincronização vertical ao criar a janela.
os.environ.setdefault("SDL_FRAMEBUFFER_ACCELERATION", "1")
os.environ.setdefault("SDL_RENDER_VSYNC", "1")

import pygame
from PPlay.input_manager import InputManager
from PPlay.window import Window

from spawnbound.config import GameConfig
from spawnbound.input import InputFrame
from spawnbound.domain.inventory import HOTBAR_SIZE
from spawnbound.pacing import FramePacer
from spawnbound.pplay_ui import advance_fades
from spawnbound.world_effects import advance_shake

ACTIONS = {
    "inventario": ["I", "TAB"],
    "mapa": ["M"],
    "interagir": ["E"],
    "fabricar": ["C"],
    "melhorar": ["U"],
    "comer": ["Q"],
    "descansar": ["R"],
    "recolher_movel": ["G"],
    "pular": ["SPACE"],
    "pausa": ["ESC"],
    "recomecar": ["F5"],
    "nova_seed": ["F6"],
    "depurar": ["F1"],
    "sair": ["F10"],
    "apagar": ["BACKSPACE"],
    "confirmar": ["ENTER", pygame.K_KP_ENTER],
    **{f"barra_{n}": [str(n)] for n in range(1, HOTBAR_SIZE + 1)},
}
for _action, _keys in ACTIONS.items():
    InputManager.define_action(_action, _keys)


def pressed(action: str) -> bool:
    return bool(InputManager.action_pressed(action))


class PPlayHost:
    _primary_held = False
    _secondary_held = False
    _let_go = ()

    def __init__(self, config: GameConfig) -> None:
        self._primary_held = False
        self._secondary_held = False
        self.config = config
        self.window = Window(
            largura_virtual=config.virtual_width,
            altura_virtual=config.virtual_height,
            titulo=config.title,
            resizavel=True,
            pixel_art=True,
        )
        self.screen: pygame.Surface = self.window.screen
        self.keyboard = self.window.keyboard
        self.mouse = self.window.mouse
        self._last_frame_time = time.perf_counter()
        self._frame_deadline = self._last_frame_time + 1 / config.target_fps
        self._presenter = None
        self._windowed_size = self.window.real_screen.get_size()
        self._cocoa_window = (pygame.Window.from_display_module()
                              if pygame.display.get_driver() == "cocoa" else None)
        self.window.fullscreen_handler = self.toggle_fullscreen
        self.window.close_handler = lambda: None  # A cena trata o fechamento para dar ao jogador a chance de salvar.
        self._reported_hz = self._refresh_rate()
        self._pacer = FramePacer(config.max_fps, self._reported_hz)
        self._refresh_checked = self._last_frame_time
        self._returned_at = self._last_frame_time
        self._present_seconds = 0.0
        self.elastic_seconds = 0.0
        self._refresh_s = self._nominal_s = 1 / (self._reported_hz or 60)
        self._latch = self._last_frame_time
        self._upload = FramePacer.UPLOAD
        self._locked = False
        self._measure_in = 0
        self._measure_cost = self._refresh_s / 2
        self._last_measured = None
        self._flip_started = None
        self._probe_pending = False
        self._probe_vsync()

    @property
    def frame_period(self) -> float:
        return self._pacer.period

    @property
    def spare_seconds(self) -> float:
        return self._pacer.spare

    def next_frame(self) -> tuple[InputFrame, float]:
        entered = time.perf_counter()
        work = entered - self._returned_at - self.elastic_seconds
        pacer = self._pacer
        visible = pygame.display.get_active()
        synced = pacer.vsync and visible
        locked = synced and pacer.refreshes > 1
        if locked and not self._locked:
            self._measure_in = 0
        self._locked = locked
        if not synced:
            self._wait_until(self._frame_deadline)
        self._present_seconds = 0.0
        self._flip_started = None
        self._configure_presentation_filter()
        self.window.update()
        advance_fades()
        advance_shake()
        flipped = time.perf_counter()
        if self._flip_started is not None and (locked or not synced):
            took = flipped - self._flip_started
            if took < self._refresh_s / 2:
                self._upload += (took - self._upload) * .2
                pacer.upload = self._upload
        if locked:
            self._follow_display()
        if self.keyboard.key_down("F"):
            self.toggle_fullscreen()
        now = time.perf_counter()
        if now - self._refresh_checked > 1.0:
            self._refresh_checked = now
            hz = self._refresh_rate()
            if hz > 0 and hz != self._reported_hz:
                self._reported_hz = hz
                self._probe_pending = True
            pacer.update()
        if self._probe_pending:
            self._probe_vsync()
        # O intervalo parte da apresentação do quadro para descontar a espera das medições.
        interval = flipped - self._last_frame_time
        if visible:
            pacer.record(work + self._present_seconds, interval)
        delta_time = min(pacer.frame_time(interval), self.config.max_frame_delta)
        self._last_frame_time = flipped
        period = pacer.period
        self._frame_deadline += period
        if self._frame_deadline < flipped:
            self._frame_deadline = flipped + period
        self._returned_at = time.perf_counter()
        return self._snapshot_input(), delta_time

    SPIN = .001
    REPEAT_RECT = (0, 0, 1, 1)
    LATE_GUARD = .1
    PHASE_GAIN = .5
    RATE_GAIN = .005
    RATE_RANGE = .005

    @classmethod
    def _wait_until(cls, deadline: float) -> None:
        remaining = deadline - time.perf_counter()
        if remaining > cls.SPIN:
            time.sleep(remaining - cls.SPIN)
        while time.perf_counter() < deadline:
            pass

    def _wait_for_present(self) -> None:
        refresh = self._refresh_s
        now = time.perf_counter()
        if now + self._upload > self._latch - self.LATE_GUARD * refresh:
            missed = math.ceil((now + self._upload + self.LATE_GUARD * refresh - self._latch) / refresh)
            self._latch += missed * refresh
            return
        self._wait_until(self._latch - refresh / 2 - self._upload)

    def _follow_display(self) -> None:
        refresh = self._refresh_s
        self._measure_in -= 1
        if self._measure_in <= 0:
            start = time.perf_counter()
            pygame.display.update(self.REPEAT_RECT)
            taken = time.perf_counter()
            # Medir a sincronização consome parte de uma atualização da tela. Medir com folga preserva o ritmo.
            self._measure_cost += (taken - start - self._measure_cost) * .2
            roomy = self._pacer.spare > self._measure_cost + self._upload
            self._measure_in = 4 if roomy else 64
            if taken - start > .15 * refresh:
                error = taken - self._latch
                residual = error - round(error / refresh) * refresh
                last = self._last_measured
                if last is not None and (span := round((taken - last) / refresh)) > 0:
                    nominal = self._nominal_s
                    self._refresh_s = min(max(refresh + self.RATE_GAIN * residual / span,
                                              (1 - self.RATE_RANGE) * nominal), (1 + self.RATE_RANGE) * nominal)
                self._latch += self.PHASE_GAIN * residual
                self._last_measured = taken
        self._latch += self._pacer.refreshes * self._refresh_s

    def _probe_vsync(self) -> None:
        self._probe_pending = False
        refresh = self._refresh_rate()
        if refresh <= 0 or pygame.display.get_driver() == "dummy":
            self._pacer.vsync = False
            return
        stamps = [time.perf_counter()]
        for _ in range(24):
            pygame.display.update(self.REPEAT_RECT)
            stamps.append(time.perf_counter())
        intervals = sorted(b - a for a, b in zip(stamps, stamps[1:]))
        self._reported_hz = refresh
        self._pacer.set_refresh(refresh)
        self._pacer.vsync = intervals[len(intervals) // 2] >= .6 / refresh
        self._refresh_s = self._nominal_s = self._estimate_refresh(stamps[4:], refresh)
        self._latch = stamps[-1] + self._pacer.refreshes * self._refresh_s
        self._last_measured = None
        self._measure_in = 0
        self._frame_deadline = time.perf_counter() + self._pacer.period

    @staticmethod
    def _estimate_refresh(stamps: list[float], reported: int) -> float:
        nominal = 1 / reported
        slopes = sorted((stamps[j] - stamps[i]) / (j - i)
                        for i in range(len(stamps)) for j in range(i + 8, len(stamps)))
        if not slopes:
            return nominal
        estimate = slopes[len(slopes) // 2]
        off = abs(estimate / nominal - 1)
        return nominal if off < .005 or off > .05 else estimate

    @staticmethod
    def _refresh_rate() -> int:
        try:
            return int(pygame.display.get_current_refresh_rate() or 0)
        except (AttributeError, pygame.error):
            return 0

    def use_canvas(self, surface) -> None:
        self.window.screen = surface
        self.window.cor_fundo = (0, 0, 0, 0)

    def bind_presenter(self, presenter) -> None:
        self._presenter = presenter

        def timed(target) -> None:
            start = time.perf_counter()
            presenter(target)
            self._present_seconds += time.perf_counter() - start
            if self._locked:
                self._wait_for_present()
            self._flip_started = time.perf_counter()

        self.window.frame_presenter = timed

    def toggle_fullscreen(self) -> None:
        if self._cocoa_window is not None:
            if pygame.display.is_fullscreen():
                self._cocoa_window.set_windowed()
            else:
                self._cocoa_window.set_fullscreen(desktop=True)
            return
        if self.window.real_screen.get_flags() & pygame.FULLSCREEN:
            self.window.real_screen = pygame.display.set_mode(self._windowed_size, pygame.RESIZABLE)
        else:
            self._windowed_size = self.window.real_screen.get_size()
            desktop = pygame.display.get_desktop_sizes()[0]
            self.window.real_screen = pygame.display.set_mode(desktop, pygame.FULLSCREEN)
        self._probe_pending = True

    def _configure_presentation_filter(self) -> None:
        # Na escala inteira, cada pixel mantém suas bordas. A escala fracionária precisa de filtragem.
        width, height = self.window.real_screen.get_size()
        ratio = min(width / self.config.virtual_width, height / self.config.virtual_height)
        scaled_width = max(1, int(self.config.virtual_width * ratio))
        scaled_height = max(1, int(self.config.virtual_height * ratio))
        self.window.pixel_art = (
            scaled_width % self.config.virtual_width == 0
            and scaled_height % self.config.virtual_height == 0
            and scaled_width // self.config.virtual_width == scaled_height // self.config.virtual_height
        )

    def _button(self, button: int, held_before: bool, focus_lost: bool) -> tuple[bool, bool, bool]:
        down = self.mouse.button_down(button)
        if down:
            self._let_go = tuple(b for b in self._let_go if b != button)
        if focus_lost:
            self._let_go = (*self._let_go, button)
        held = bool(self.mouse.button_pressed(button)) and button not in self._let_go
        return down, held, (held_before or down) and not held and not focus_lost

    def _snapshot_input(self) -> InputFrame:
        mouse = self.mouse
        wheel_steps, typed, close, focus_lost = 0, "", False, False
        for event in self.window.eventos:
            if event.type == pygame.QUIT:
                close = True
            elif event.type == pygame.MOUSEWHEEL:
                wheel_steps += event.y
            elif event.type == pygame.KEYDOWN and getattr(event, "unicode", "").isdigit():
                typed += event.unicode
            elif event.type == pygame.WINDOWFOCUSLOST:
                focus_lost = True
        pointer = mouse.get_position()
        left_down, self._primary_held, left_up = self._button(mouse.LEFT, self._primary_held, focus_lost)
        right_down, self._secondary_held, _ = self._button(mouse.RIGHT, self._secondary_held, focus_lost)
        hotbar_index = next((n for n in range(HOTBAR_SIZE) if pressed(f"barra_{n + 1}")), None)
        return InputFrame(
            destination_click=pointer if left_down else None,
            inventory_pressed=pressed("inventario"),
            map_pressed=pressed("mapa"),
            hotbar_index=hotbar_index,
            wheel_steps=wheel_steps,
            pointer=pointer,
            left_release=pointer if left_up else None,
            primary_held=self._primary_held,
            secondary_held=self._secondary_held,
            right_click=pointer if right_down else None,
            interact_pressed=pressed("interagir"),
            craft_pressed=pressed("fabricar"),
            upgrade_pressed=pressed("melhorar"),
            eat_pressed=pressed("comer"),
            rest_pressed=pressed("descansar"),
            pack_furniture_pressed=pressed("recolher_movel"),
            jump_pressed=pressed("pular"),
            pause_pressed=pressed("pausa"),
            restart_pressed=pressed("recomecar"),
            new_seed_pressed=pressed("nova_seed"),
            debug_pressed=pressed("depurar"),
            quit_requested=pressed("sair"),
            close_requested=close,
            typed=typed,
            backspace_pressed=pressed("apagar"),
            enter_pressed=pressed("confirmar"),
        )

    def close(self) -> None:
        self.window.close()
