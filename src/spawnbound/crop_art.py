from __future__ import annotations

import math
from dataclasses import dataclass
from functools import lru_cache

import pygame

from spawnbound.domain.coordinates import WorldPos

INK = (38, 29, 44)
COLORS = {
    "G": (62, 128, 52), "L": (118, 184, 76), "D": (40, 88, 40),
    "s": (104, 70, 46), "S": (142, 100, 64),
    "o": (232, 122, 40), "O": (255, 170, 80),
    "w": (238, 232, 214), "p": (152, 74, 150), "P": (196, 120, 190),
    "k": (226, 120, 32), "K": (255, 168, 72), "r": (176, 84, 24), "t": (110, 84, 40),
    "y": (226, 210, 120),
}
SIZE = (18, 20)
FOOT = (9, 17)
WIND = (-1, 0, 1, 0)


@dataclass(frozen=True, slots=True)
class CropView:
    location: WorldPos
    kind: str
    stage: int
    phase: float


def _leaf(grid, x0, y0, dx, length, light=True):
    for i in range(length):
        x, y = x0 + (dx * i) // 2, y0 - i
        if 0 <= x < SIZE[0] and 0 <= y < SIZE[1]:
            grid[y][x] = "L" if light and i == length - 1 else ("D" if i == 0 else "G")


def _mound(grid, width=3):
    fx, fy = FOOT
    for x in range(fx - width, fx + width + 1):
        grid[fy][x] = "s"
    for x in range(fx - width + 1, fx + width):
        grid[fy - 1][x] = "S" if (x + fy) % 3 else "s"


def _blob(grid, cx, cy, rx, ry, fill, light, dark=None):
    for y in range(cy - ry, cy + ry + 1):
        for x in range(cx - rx, cx + rx + 1):
            if ((x - cx) / (rx + .5)) ** 2 + ((y - cy) / (ry + .5)) ** 2 <= 1 and 0 <= x < SIZE[0] and 0 <= y < SIZE[1]:
                key = light if (y - cy) < -ry * .3 and (x - cx) < 0 else fill
                if dark and (x - cx) % 3 == 0 and abs(x - cx) < rx:
                    key = dark
                grid[y][x] = key


def drawing(kind: str, stage: int) -> list[list[str]]:
    grid = [["."] * SIZE[0] for _ in range(SIZE[1])]
    fx, fy = FOOT
    _mound(grid, 3 if kind != "pumpkin" or stage < 3 else 4)
    if stage == 0:
        grid[fy - 2][fx - 1] = grid[fy - 2][fx + 1] = "y"
        return grid
    if stage == 1:
        _leaf(grid, fx, fy - 2, -2, 3)
        _leaf(grid, fx, fy - 2, 2, 3)
        return grid
    if kind == "carrot":
        lengths = (6, 8, 7) if stage == 2 else (9, 12, 10)
        for dx, length in zip((-2, 0, 2), lengths):
            _leaf(grid, fx, fy - 2, dx, length)
            if stage == 3:
                _leaf(grid, fx + dx // 2, fy - 2, dx * 2, length - 3)
        if stage == 3:
            for x in range(fx - 1, fx + 2):
                grid[fy - 1][x] = "o"
                grid[fy - 2][x] = "O" if x < fx + 1 else "o"
    elif kind == "turnip":
        lengths = (5, 6, 5) if stage == 2 else (7, 9, 7)
        for dx, length in zip((-3, 0, 3), lengths):
            _leaf(grid, fx, fy - 3, dx, length)
            _leaf(grid, fx + (1 if dx > 0 else -1 if dx < 0 else 1), fy - 3, dx, length - 1, light=False)
        if stage == 3:
            _blob(grid, fx, fy - 2, 2, 2, "w", "w")
            for x in range(fx - 2, fx + 3):
                grid[fy - 4][x] = "p" if abs(x - fx) < 2 else grid[fy - 4][x]
                grid[fy - 3][x] = "P" if abs(x - fx) < 2 else "p"
    elif kind == "pumpkin":
        if stage == 2:
            for cx, cy in ((fx - 3, fy - 4), (fx + 3, fy - 5), (fx, fy - 7)):
                _blob(grid, cx, cy, 2, 2, "G", "L")
            _leaf(grid, fx, fy - 2, 0, 5, light=False)
        else:
            for cx, cy in ((fx - 6, fy - 5), (fx + 6, fy - 6)):
                _blob(grid, cx, cy, 2, 2, "G", "L")
            _blob(grid, fx, fy - 4, 5, 3, "k", "K", "r")
            grid[fy - 8][fx] = grid[fy - 9][fx] = "t"
            grid[fy - 9][fx + 1] = "G"
    return grid


def _wind(grid, lean):
    if lean == 0:
        return grid
    fx, fy = FOOT
    out = [["."] * SIZE[0] for _ in range(SIZE[1])]
    for y, row in enumerate(grid):
        for x, key in enumerate(row):
            if key == ".":
                continue
            shift = lean if key in "GLD" and y < fy - 6 else 0
            nx = x + shift
            if 0 <= nx < SIZE[0] and out[y][nx] == ".":
                out[y][nx] = key
            elif out[y][x] == ".":
                out[y][x] = key
    return out


def _paint(grid) -> pygame.Surface:
    surface = pygame.Surface(SIZE, pygame.SRCALPHA)
    filled = {(x, y) for y, row in enumerate(grid) for x, key in enumerate(row) if key != "."}
    for x, y in filled:
        surface.set_at((x, y), COLORS[grid[y][x]])
    for x, y in filled:
        for nx, ny in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
            if (nx, ny) not in filled and 0 <= nx < SIZE[0] and 0 <= ny < SIZE[1]:
                surface.set_at((nx, ny), INK)
    return surface


@lru_cache(maxsize=None)
def crop_sprite(kind: str, stage: int, frame: int, scale: float) -> tuple[pygame.Surface, tuple[int, int]]:
    image = _paint(_wind(drawing(kind, stage), WIND[frame % len(WIND)] if stage else 0))
    if scale != 1:
        image = pygame.transform.scale(image, (round(SIZE[0] * scale), round(SIZE[1] * scale)))
    return image, (round(FOOT[0] * scale), round(FOOT[1] * scale))


def wind_frame(seconds: float, phase: float) -> int:
    return int((seconds / .38 + phase * len(WIND)) % len(WIND))


def phase_of(cell) -> float:
    return (math.sin(cell.x * 12.9898 + cell.y * 78.233) * 43758.5453) % 1
