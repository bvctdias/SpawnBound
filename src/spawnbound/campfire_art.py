from __future__ import annotations

from functools import lru_cache
from math import cos, pi, sin, sqrt
from typing import NamedTuple

import pygame

SIZE = (40, 46)
FOOT = (20, 36)
FRAMES = 6
FPS = 9
STONE = ((112, 104, 142), (148, 140, 178), (184, 178, 208), (218, 214, 234))
STONE_INK = (60, 52, 82)
ASH = ((58, 48, 50), (84, 70, 66))
LOG = ((74, 42, 30), (110, 66, 42), (150, 96, 58))
LOG_END = (204, 158, 104)
LOG_INK = (46, 26, 22)
EMBER = ((176, 52, 34), (236, 112, 44), (255, 196, 84))
FLAME = ((206, 70, 40), (240, 120, 46), (255, 182, 64), (255, 226, 112), (255, 250, 210))
FLAME_INK = (124, 42, 30)
RING = (20, 31, 11.5, 7.)
STONES = 12
LIGHT = (-.6, -.7, .4)


def _lit(nx, ny):
    nz = sqrt(max(0., 1 - nx * nx - ny * ny))
    lx, ly, lz = LIGHT
    return (nx * lx + ny * ly + nz * lz) / sqrt(lx * lx + ly * ly + lz * lz)


def _stamp(grid, cells, ink):
    for x, y in cells:
        for n in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
            if n not in cells:
                grid[n] = ink
    grid.update(cells)


def _stone(cx, cy, rx, ry):
    cells = {}
    for y in range(int(cy - ry) - 1, int(cy + ry) + 2):
        for x in range(int(cx - rx) - 1, int(cx + rx) + 2):
            nx, ny = (x + .5 - cx) / rx, (y + .5 - cy) / ry
            if nx * nx + ny * ny > 1:
                continue
            b = _lit(nx * .9, ny * .9)
            cells[(x, y)] = STONE[3 if b > .85 else 2 if b > .5 else 1 if b > .1 else 0]
    return cells


def _ring():
    cx, cy, rx, ry = RING
    behind, front = [], []
    for i in range(STONES):
        a = 2 * pi * (i + .5) / STONES
        sx, sy = cx + rx * sin(a), cy - ry * cos(a)
        size = 3.7 if i % 3 else 4.2
        stone = _stone(sx, sy, size, size * .76)
        (behind if sy < cy else front).append((sy, stone))
    order = lambda pair: pair[0]
    return [s for _, s in sorted(behind, key=order)], [s for _, s in sorted(front, key=order)]


def _log(a, b, thick=2):
    cells = {}
    (ax, ay), (bx, by) = a, b
    steps = max(abs(bx - ax), abs(by - ay)) * 2
    for i in range(steps + 1):
        t = i / steps
        x, y = ax + (bx - ax) * t, ay + (by - ay) * t
        for d in range(thick + 1):
            cells[(round(x), round(y) + d)] = LOG[2] if d == 0 else LOG[1] if d < thick else LOG[0]
    cells[(round(bx), round(by))] = LOG_END
    cells[(round(bx), round(by) + 1)] = LOG_END
    return cells


@lru_cache(maxsize=None)
def campfire() -> pygame.Surface:
    grid: dict[tuple[int, int], tuple[int, int, int]] = {}
    behind, front = _ring()
    for stone in behind:
        _stamp(grid, stone, STONE_INK)
    cx, cy, rx, ry = RING
    ash = {(x, y): ASH[1] if y < cy else ASH[0]
           for y in range(int(cy - ry), int(cy + ry) + 1) for x in range(int(cx - rx), int(cx + rx) + 1)
           if ((x + .5 - cx) / (rx - 2.5)) ** 2 + ((y + .5 - cy) / (ry - 1.2)) ** 2 <= 1}
    grid.update(ash)
    _stamp(grid, _log((12, 34), (26, 28)), LOG_INK)
    _stamp(grid, _log((28, 34), (14, 28)), LOG_INK)
    for x, y, tone in ((19, 32, 2), (21, 32, 1), (17, 33, 1), (23, 33, 0), (20, 34, 1), (15, 31, 0), (25, 31, 1)):
        grid[(x, y)] = EMBER[tone]
    for stone in front:
        _stamp(grid, stone, STONE_INK)
    return _surface(grid)


def _tongue(cells, cx, base, height, width, sway, phase, hottest=4):
    for y in range(base - height, base + 1):
        v = (base - y) / height
        half = width * (1 - v) ** .7 * min(1., .72 + v * 1.4) * (.8 if y == base else 1.)
        middle = cx + sway * sin(phase + v * 2.4) * v ** 1.3
        for x in range(int(middle - half) - 1, int(middle + half) + 2):
            u = abs(x + .5 - middle) / half if half > .3 else 2
            if u > 1:
                continue
            heat = (4 if (u / .36) ** 2 + (v / .42) ** 2 < 1 else 3 if (u / .7) ** 2 + (v / .68) ** 2 < 1
                    else 2 if (u / .92) ** 2 + (v / .9) ** 2 < 1 else 1)
            heat = min(heat, hottest)
            if heat > cells.get((x, y), 0):
                cells[(x, y)] = heat


@lru_cache(maxsize=None)
def flame(frame: int) -> pygame.Surface:
    phase = 2 * pi * (frame % FRAMES) / FRAMES
    heat: dict[tuple[int, int], int] = {}
    base = 32
    _tongue(heat, 20, base, 20 + round(2 * sin(phase)), 7.4, 2.4, phase)
    _tongue(heat, 14.5, base, 12 + round(2 * sin(phase + 2.1)), 4., 1.6, phase + 1., hottest=3)
    _tongue(heat, 25.5, base, 11 + round(2 * sin(phase + 4.2)), 3.8, 1.6, phase + 2., hottest=3)
    cells = {p: FLAME[h] if h > 1 else FLAME[0] for p, h in heat.items()}
    grid: dict[tuple[int, int], tuple[int, int, int]] = {}
    _stamp(grid, cells, FLAME_INK)
    for x, y in [p for p in grid if p[1] > base]:
        del grid[(x, y)]
    if frame % 3 != 2:
        top = min(y for _, y in cells)
        sx = 20 + round(2.2 * sin(phase + 2.4)) + (1 if frame % 2 else -1)
        grid[(sx, top - 3 - frame % 3)] = FLAME[3]
    return _surface(grid)


def _surface(grid):
    image = pygame.Surface(SIZE, pygame.SRCALPHA)
    for (x, y), color in grid.items():
        if 0 <= x < SIZE[0] and 0 <= y < SIZE[1]:
            image.set_at((x, y), color)
    return image


class Flame(NamedTuple):
    location: object
    seed: int


def flame_frame(seconds: float, seed: int = 0) -> int:
    return (int(seconds * FPS) + seed) % FRAMES


def _scaled(image: pygame.Surface, scale: float) -> pygame.Surface:
    if scale == 1:
        return image
    return pygame.transform.scale(image, (round(image.get_width() * scale), round(image.get_height() * scale)))


def placed_campfire(scale: float = 1.) -> tuple[pygame.Surface, tuple[int, int]]:
    return _scaled(campfire(), scale), (round(FOOT[0] * scale), round(FOOT[1] * scale))


@lru_cache(maxsize=None)
def placed_flame(frame: int, scale: float = 1.) -> tuple[pygame.Surface, tuple[int, int]]:
    return _scaled(flame(frame), scale), (round(FOOT[0] * scale), round(FOOT[1] * scale))
