from __future__ import annotations

import pygame

from spawnbound.config import GameConfig
from spawnbound.inventory_hud import CREAM, EDGE, GOLD, MUTED
from spawnbound.pixel_font import PixelFont
from spawnbound.pplay_ui import GameButton, draw_on, pointed

TITLE = "CONTROLES"
BACK = "Voltar"
NOTE = "Esc para voltar"
LEFT = (
    ("MOUSE", (
        ("Clique", "andar, coletar, atacar, colocar móvel"),
        ("Segurar o clique", "seguir coletando; recolher o móvel"),
        ("Clique direito", "comer, arar com a foice, plantar, colher"),
        ("Roda", "trocar o espaço da barra; girar o móvel"),
    )),
    ("PESCA, COM A VARA NA BARRA", (
        ("Segurar na água", "encher a força; soltar lança a linha"),
        ("Clique no !", "fisgar o peixe"),
        ("Segurar o clique", "subir a barra verde no minigame"),
    )),
)
RIGHT = (
    ("TECLADO", (
        ("1 a 5", "escolher o espaço da barra"),
        ("Espaço", "pular; passa por cima da onda"),
        ("E", "entrar, sair, baú, estações, cais, consertar"),
        ("I ou Tab", "mochila e bancada"),
        ("M", "mapa da ilha"),
        ("Q", "comer"),
        ("R", "descansar na cama ou na fogueira"),
        ("U", "melhorar a ferramenta selecionada"),
        ("C", "kit de ponte"),
        ("G", "recolher o móvel da frente"),
        ("Esc", "pausa; fecha os painéis"),
        ("F", "tela cheia ou janela"),
        ("F1", "diagnóstico"),
        ("F5 / F6", "reiniciar / outra ilha"),
        ("F10", "sair do jogo"),
    )),
)
ROW = 15
HEADER_GAP = 6
SECTION_GAP = 14
COLUMN_GAP = 34
TITLE_SPACE = 16 + 21 + 20
KEY_GAP = 12
PANEL = (21, 16, 15, 222)
PLATE = (30, 18, 14, 222)
PLATE_HOVER = (64, 38, 26, 236)
SHADOW = (12, 8, 8)
_MEASURE = PixelFont()


def _rgb(color) -> tuple[int, int, int]:
    return tuple(pygame.Color(color))[:3]


def _column_size(font: PixelFont, sections) -> tuple[int, int, int]:
    keys = max(font.size(key)[0] for _, rows in sections for key, _ in rows)
    actions = max(font.size(action)[0] for _, rows in sections for _, action in rows)
    headers = max(font.size(header)[0] for header, _ in sections)
    height = sum(7 + HEADER_GAP + ROW * len(rows) for _, rows in sections) + SECTION_GAP * (len(sections) - 1)
    return keys, max(headers, keys + KEY_GAP + actions), height


def layout(config: GameConfig) -> tuple[pygame.Rect, pygame.Rect, pygame.Rect]:
    _, left, left_height = _column_size(_MEASURE, LEFT)
    _, right, right_height = _column_size(_MEASURE, RIGHT)
    body = pygame.Rect(0, 0, left + COLUMN_GAP + right, max(left_height, right_height))
    panel = pygame.Rect(0, 0, body.width + 48, TITLE_SPACE + body.height + 20 + 38 + 10 + 7 + 24)
    panel.center = (config.virtual_width // 2, config.virtual_height // 2)
    body.midtop = (panel.centerx, panel.top + TITLE_SPACE)
    button = pygame.Rect(0, 0, 220, 38)
    button.midtop = (panel.centerx, body.bottom + 20)
    return panel, body, button


def button_at(config: GameConfig, point) -> str | None:
    return "back" if pointed(layout(config)[2], point) else None


def _draw_column(surface: pygame.Surface, font: PixelFont, sections, left: int, top: int) -> None:
    keys, _, _ = _column_size(font, sections)
    y = top
    for index, (header, rows) in enumerate(sections):
        if index:
            y += SECTION_GAP
        surface.blit(font.render(header, _rgb(MUTED), 1, shadow=SHADOW), (left, y))
        y += 7 + HEADER_GAP
        for key, action in rows:
            surface.blit(font.render(key, _rgb(GOLD), 1, shadow=SHADOW), (left, y))
            surface.blit(font.render(action, _rgb(CREAM), 1, shadow=SHADOW), (left + keys + KEY_GAP, y))
            y += ROW


def draw(surface: pygame.Surface, config: GameConfig, font: PixelFont, hover: str | None = None) -> pygame.Rect:
    panel, body, button = layout(config)
    plate = pygame.Surface(panel.size, pygame.SRCALPHA)
    pygame.draw.rect(plate, PANEL, plate.get_rect(), border_radius=10)
    surface.blit(plate, panel)
    pygame.draw.rect(surface, _rgb(EDGE), panel, 2, border_radius=10)
    title = font.render(TITLE, _rgb(CREAM), 3, shadow=SHADOW)
    surface.blit(title, title.get_rect(midtop=(panel.centerx, panel.top + 16)))
    _, left_width, _ = _column_size(font, LEFT)
    _draw_column(surface, font, LEFT, body.left, body.top)
    _draw_column(surface, font, RIGHT, body.left + left_width + COLUMN_GAP, body.top)
    back = GameButton(button, BACK, font, color=_rgb(CREAM))
    back.hovered = hover == "back"
    draw_on(surface, back)
    note = font.render(NOTE, _rgb(MUTED), 1, shadow=SHADOW)
    surface.blit(note, note.get_rect(midtop=(panel.centerx, button.bottom + 10)))
    return panel


__all__ = ["LEFT", "RIGHT", "button_at", "draw", "layout"]
