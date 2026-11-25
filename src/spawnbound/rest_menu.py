from __future__ import annotations

import pygame

from spawnbound.config import GameConfig
from spawnbound.pixel_font import PixelFont
from spawnbound.pplay_ui import GameButton, draw_on, pointed

TITLE = "PONTO DE DESCANSO"
COOK = "cozinhar carnes"
BUTTON = "descansar até de manhã"
DAYTIME = "de dia, não dá para dormir"
PLATE = (30, 18, 14, 222)
PLATE_HOVER = (64, 38, 26, 236)
TEXT = (244, 238, 226)
DIM = (150, 136, 122)
SHADOW = (12, 8, 8)


def layout(config: GameConfig) -> tuple[pygame.Rect, pygame.Rect, pygame.Rect]:
    cx, cy = config.virtual_width // 2, round(config.virtual_height * .4)
    title = pygame.Rect(0, 0, 340, 46)
    title.center = (cx, cy)
    cook = pygame.Rect(0, 0, 340, 40)
    cook.midtop = (cx, title.bottom + 10)
    rest = pygame.Rect(0, 0, 340, 40)
    rest.midtop = (cx, cook.bottom + 8)
    return title, cook, rest


def button_at(config: GameConfig, point: tuple[int, int] | None) -> str | None:
    if point is None:
        return None
    _, cook, rest = layout(config)
    return "cook" if pointed(cook, point) else "rest" if pointed(rest, point) else None


def draw(surface: pygame.Surface, config: GameConfig, font: PixelFont, available: bool,
         hover: str | None = None) -> pygame.Rect:
    title, cook, rest = layout(config)
    plate = pygame.Surface(title.size, pygame.SRCALPHA)
    pygame.draw.rect(plate, PLATE, plate.get_rect(), border_radius=8)
    surface.blit(plate, title)
    label = font.render(TITLE, TEXT, 3, shadow=SHADOW)
    surface.blit(label, label.get_rect(center=title.center))
    buttons = (GameButton(cook, COOK, font, edge=False, color=TEXT, dim=DIM),
               GameButton(rest, BUTTON, font, enabled=available, edge=False, color=TEXT, dim=DIM))
    for button, key in zip(buttons, ("cook", "rest")):
        button.hovered = button.enabled and hover == key
    draw_on(surface, *buttons)
    covered = title.union(rest)
    if not available:
        note = font.render(DAYTIME, TEXT, 1, shadow=SHADOW)
        place = note.get_rect(midtop=(rest.centerx, rest.bottom + 8))
        surface.blit(note, place)
        covered.union_ip(place)
    return covered
