from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class InputFrame:
    destination_click: tuple[float, float] | None = None
    cancel_path_pressed: bool = False
    interact_pressed: bool = False
    craft_pressed: bool = False
    rest_pressed: bool = False
    pause_pressed: bool = False
    restart_pressed: bool = False
    new_seed_pressed: bool = False
    debug_pressed: bool = False
    quit_requested: bool = False
    close_requested: bool = False
    jump_pressed: bool = False
    eat_pressed: bool = False
    inventory_pressed: bool = False
    map_pressed: bool = False
    hotbar_index: int | None = None
    wheel_steps: int = 0
    pointer: tuple[float, float] | None = None
    left_release: tuple[float, float] | None = None
    right_click: tuple[float, float] | None = None
    primary_held: bool = False
    secondary_held: bool = False
    upgrade_pressed: bool = False
    pack_furniture_pressed: bool = False
    typed: str = ""
    backspace_pressed: bool = False
    enter_pressed: bool = False
