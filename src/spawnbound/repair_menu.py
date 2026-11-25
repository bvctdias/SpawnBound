from __future__ import annotations

import pygame

from spawnbound.config import GameConfig
from spawnbound.item_icons import ITEMS, icon
from spawnbound.pixel_font import PixelFont
from spawnbound.pplay_ui import GameButton, draw_on, pointed, show

TITLES = {"dock": "CONSERTAR O CAIS", "windmill": "CONSERTAR O MOINHO"}
BUTTON = "consertar"
SHORT_NOTE = "faltam materiais"
PLATE = (30, 18, 14, 222)
PLATE_HOVER = (64, 38, 26, 236)
TEXT = (244, 238, 226)
DIM = (150, 136, 122)
SHORT = (244, 123, 120)
SHADOW = (12, 8, 8)
ITEM_WIDTH, ITEM_GAP = 112, 10


def layout(config: GameConfig, count: int) -> tuple[pygame.Rect, list[pygame.Rect], pygame.Rect]:
    cx, cy = config.virtual_width // 2, round(config.virtual_height * .4)
    title = pygame.Rect(0, 0, 340, 46)
    title.center = (cx, cy)
    total = count * ITEM_WIDTH + max(0, count - 1) * ITEM_GAP
    items = [pygame.Rect(cx - total // 2 + i * (ITEM_WIDTH + ITEM_GAP), title.bottom + 10, ITEM_WIDTH, 50)
             for i in range(count)]
    button = pygame.Rect(0, 0, 340, 40)
    button.midtop = (cx, title.bottom + 70)
    return title, items, button


def button_at(config: GameConfig, count: int, point: tuple[float, float] | None) -> bool:
    return pointed(layout(config, count)[2], point)


def draw(surface: pygame.Surface, config: GameConfig, font: PixelFont, kind: str,
         needs: dict[str, int], have: dict[str, int], hover: bool = False) -> pygame.Rect:
    title, items, button = layout(config, len(needs))
    ready = all(have.get(item, 0) >= n for item, n in needs.items())
    for rect in (title, *items):
        plate = pygame.Surface(rect.size, pygame.SRCALPHA)
        pygame.draw.rect(plate, PLATE, plate.get_rect(), border_radius=8)
        surface.blit(plate, rect)
    label = font.render(TITLES[kind], TEXT, 3, shadow=SHADOW)
    surface.blit(label, label.get_rect(center=title.center))
    for rect, (item, n) in zip(items, needs.items()):
        show(surface, icon(item), midleft=(rect.left + 8, rect.centery))
        count = font.render(f"{have.get(item, 0)}/{n}", TEXT if have.get(item, 0) >= n else SHORT, 2, shadow=SHADOW)
        surface.blit(count, count.get_rect(midright=(rect.right - 8, rect.top + 18)))
        name = font.render(ITEMS[item][0], DIM, 1, shadow=SHADOW)
        surface.blit(name, name.get_rect(midright=(rect.right - 8, rect.bottom - 11)))
    repair = GameButton(button, BUTTON, font, enabled=ready, edge=False, color=TEXT, dim=DIM)
    repair.hovered = hover and ready
    draw_on(surface, repair)
    covered = title.union(button)
    for rect in items:
        covered.union_ip(rect)
    if not ready:
        note = font.render(SHORT_NOTE, TEXT, 1, shadow=SHADOW)
        place = note.get_rect(midtop=(button.centerx, button.bottom + 8))
        surface.blit(note, place)
        covered.union_ip(place)
    return covered
