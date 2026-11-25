from __future__ import annotations

import pygame

from spawnbound.config import GameConfig
from spawnbound.inventory_hud import CREAM, EDGE, GOLD, MUTED
from spawnbound.pixel_font import PixelFont
from spawnbound.pplay_ui import GameButton, draw_on, pointed, show
from spawnbound.view import HUD_HEADROOM, hotbar_rect

PANEL = (22, 16, 16, 214)
DONE_PANEL = (18, 44, 26, 226)
DONE = (150, 226, 140)
SHADOW = (12, 8, 8)
FADE = .4
OBJECTIVE_FADE = .25
ENDING_TITLE = "FIM DA JORNADA"
ENDING_BUTTON = "Continuar explorando"


def _rgb(color) -> tuple[int, int, int]:
    return tuple(pygame.Color(color))[:3]


def _plate(surface: pygame.Surface, rect: pygame.Rect, fill, edge) -> None:
    plate = pygame.Surface(rect.size, pygame.SRCALPHA)
    pygame.draw.rect(plate, fill, plate.get_rect(), border_radius=6)
    surface.blit(plate, rect)
    pygame.draw.rect(surface, edge, rect, 1, border_radius=6)


def draw_objective(surface: pygame.Surface, font: PixelFont, step: int, total: int, text: str, how: str,
                   done: bool = False, transparency: float = 255) -> pygame.Rect:
    header = "OBJETIVO CONCLUÍDO" if done else f"OBJETIVO {step}/{total}"
    lines = [(header, 1, DONE if done else _rgb(GOLD)), (text, 2, DONE if done else _rgb(CREAM))]
    if how and not done:
        lines.append((how, 1, _rgb(MUTED)))
    labels = [(font.render(line, color, scale, shadow=SHADOW), gap)
              for (line, scale, color), gap in zip(lines, (0, 6, 6))]
    width = max(label.get_width() for label, _ in labels) + 20
    height = sum(label.get_height() + gap for label, gap in labels) + 18
    panel = pygame.Surface((width, height), pygame.SRCALPHA)
    pygame.draw.rect(panel, DONE_PANEL if done else PANEL, panel.get_rect(), border_radius=6)
    pygame.draw.rect(panel, DONE if done else _rgb(EDGE), panel.get_rect(), 1, border_radius=6)
    y = 9
    for label, gap in labels:
        y += gap
        panel.blit(label, (10, y))
        y += label.get_height()
    return show(surface, panel, transparency, topleft=(12, 12))


def draw_tip(surface: pygame.Surface, config: GameConfig, font: PixelFont, text: str,
             transparency: float = 255) -> pygame.Rect:
    tag = font.render("DICA", _rgb(GOLD), 1, shadow=SHADOW)
    label = font.render(text, _rgb(CREAM), 1, shadow=SHADOW)
    box = pygame.Surface((tag.get_width() + label.get_width() + 30, label.get_height() + 14), pygame.SRCALPHA)
    pygame.draw.rect(box, PANEL, box.get_rect(), border_radius=5)
    pygame.draw.rect(box, _rgb(EDGE), box.get_rect(), 1, border_radius=5)
    box.blit(tag, (10, 7))
    box.blit(label, (tag.get_width() + 20, 7))
    _, top, _, _ = hotbar_rect(config)
    return show(surface, box, transparency, midbottom=(config.virtual_width // 2, top - HUD_HEADROOM - 10))


def ending_layout(config: GameConfig, lines: int) -> tuple[pygame.Rect, pygame.Rect]:
    panel = pygame.Rect(0, 0, 460, 96 + 18 * lines + 58)
    panel.center = (config.virtual_width // 2, round(config.virtual_height * .44))
    button = pygame.Rect(0, 0, 300, 38)
    button.midbottom = (panel.centerx, panel.bottom - 16)
    return panel, button


def ending_button_at(config: GameConfig, lines: int, point) -> bool:
    return pointed(ending_layout(config, lines)[1], point)


def draw_ending(surface: pygame.Surface, config: GameConfig, font: PixelFont, lines: list[str],
                hover: bool = False) -> pygame.Rect:
    panel, button = ending_layout(config, len(lines))
    _plate(surface, panel, (21, 16, 15, 230), _rgb(GOLD))
    title = font.render(ENDING_TITLE, _rgb(GOLD), 3, shadow=SHADOW)
    surface.blit(title, title.get_rect(midtop=(panel.centerx, panel.top + 22)))
    y = panel.top + 70
    for index, line in enumerate(lines):
        label = font.render(line, _rgb(CREAM if index == 0 else MUTED), 1, shadow=SHADOW)
        surface.blit(label, label.get_rect(midtop=(panel.centerx, y)))
        y += 18
    go_on = GameButton(button, ENDING_BUTTON, font, color=_rgb(CREAM))
    go_on.hovered = hover
    draw_on(surface, go_on)
    return panel


__all__ = ["draw_ending", "draw_objective", "draw_tip", "ending_button_at", "ending_layout"]
