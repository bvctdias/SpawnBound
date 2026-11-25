from __future__ import annotations

from functools import lru_cache
from math import sqrt

import pygame

from spawnbound.domain.model import mushroom_caps

SIZE = (32, 26)
FOOT = (16, 20)
STEM = ((244, 236, 222), (222, 208, 190), (188, 170, 152))
CAPS = {
    "white_mushroom": {"tones": ((214, 186, 182), (234, 222, 216), (248, 242, 236), (255, 254, 250)),
                       "rim": (200, 160, 158), "ink": (104, 70, 58), "spots": None},
    "brown_mushroom": {"tones": ((112, 66, 44), (150, 96, 58), (184, 128, 78), (212, 160, 102)),
                       "rim": (96, 58, 42), "ink": (62, 36, 28), "spots": (232, 206, 160)},
}
MOREL = {"tones": ((122, 70, 36), (176, 110, 54), (214, 150, 78), (242, 196, 118)),
         "pit": (92, 48, 26), "ink": (78, 42, 24), "stem": ((236, 200, 140), (204, 160, 100), (166, 118, 70))}
LIGHT = (-.6, -.7, .4)
LAYOUTS = {
    2: (((-5, -1), "big"), ((5, 2), "small")),
    3: (((-7, -1), "big"), ((6, -3), "small"), ((0, 3), "big")),
}
MIRRORED = 2
CAP_SIZE = {"big": (4.8, 2.7, 3), "small": (4., 2.3, 3)}


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


def _stem(fx, fy, height, width=3, tones=STEM):
    cells = {}
    left = fx - width // 2
    for y in range(fy - height, fy + 1):
        for i, x in enumerate(range(left, left + width)):
            cells[(x, y)] = tones[0] if i == 0 else tones[2] if i == width - 1 or y == fy else tones[1]
    return cells


def _cap(cx, top, rx, ry, look):
    tones = look["tones"]
    cy = top + ry
    cells = {}
    for y in range(int(top) - 1, int(cy + ry) + 1):
        for x in range(int(cx - rx) - 1, int(cx + rx) + 2):
            nx, ny = (x + .5 - cx) / rx, (y + .5 - cy) / ry
            if nx * nx + ny * ny > 1 or ny > .62:
                continue
            if ny > .3:
                cells[(x, y)] = look["rim"]
                continue
            b = _lit(nx * .9, min(ny, .99) * .9)
            tone = 3 if b > .85 else 2 if b > .55 else 1 if b > .2 else 0
            cells[(x, y)] = tones[tone]
    if look["spots"]:
        for x, y in ((round(cx - rx * .4), round(top + 1)), (round(cx + rx * .35), round(top + ry * .7))):
            if (x, y) in cells:
                cells[(x, y)] = look["spots"]
    return cells


def _morel(fx, fy):
    cells = {}
    rx, ry = 5.6, 7.2
    cx, cy = fx + .5, fy - 2 - ry
    tones = MOREL["tones"]
    pits = [(round(cx) + col * 3 + (1 if row % 2 else 0), round(cy) + .5 + row * 4)
            for row in range(-2, 2) for col in range(-2, 3)]
    for y in range(int(cy - ry) - 1, int(cy + ry) + 2):
        for x in range(int(cx - rx) - 1, int(cx + rx) + 2):
            squeeze = 1 + .5 * max(0., (cy - (y + .5)) / ry) ** 1.5
            nx, ny = (x + .5 - cx) / rx * squeeze, (y + .5 - cy) / ry
            if nx * nx + ny * ny > 1:
                continue
            pit = nx * nx + ny * ny < .74 and any(
                (x + .5 - px) ** 2 + ((y + .5 - py) / 1.45) ** 2 < 1.05 for px, py in pits)
            b = _lit(nx * .9, ny * .9)
            if pit:
                cells[(x, y)] = MOREL["pit"] if b < .7 else tones[0]
            else:
                cells[(x, y)] = tones[3] if b > .8 else tones[2] if b > .4 else tones[1]
    return cells, _stem(fx, fy, 2, 5, MOREL["stem"])


def _layout(position) -> int:
    return ((position.x * 73856093) ^ (position.y * 19349663)) & 0xFF


@lru_cache(maxsize=None)
def mushroom(variant: str, caps: int, arrangement: int) -> pygame.Surface:
    grid: dict[tuple[int, int], tuple[int, int, int]] = {}
    fx, fy = FOOT
    if variant == "morel":
        cap, stem = _morel(fx, fy)
        _stamp(grid, {**stem, **cap}, MOREL["ink"])
    else:
        look = CAPS.get(variant, CAPS["white_mushroom"])
        mirror = -1 if arrangement % MIRRORED else 1
        for (dx, dy), size in LAYOUTS[caps]:
            rx, ry, height = CAP_SIZE[size]
            x, y = fx + mirror * dx, fy + dy
            stem = _stem(x, y, height)
            cap = _cap(x + .5, y - height - 1.62 * ry + .6, rx, ry, look)
            _stamp(grid, {**stem, **cap}, look["ink"])
    image = pygame.Surface(SIZE, pygame.SRCALPHA)
    for (x, y), color in grid.items():
        if 0 <= x < SIZE[0] and 0 <= y < SIZE[1]:
            image.set_at((x, y), color)
    return image


def mushroom_look(variant: str, position) -> tuple[str, int, int]:
    return variant, mushroom_caps(variant, position), _layout(position)


def placed_mushroom(variant: str, position, scale: float = 1.) -> tuple[pygame.Surface, tuple[int, int]]:
    image = mushroom(*mushroom_look(variant, position))
    if scale != 1:
        image = pygame.transform.scale(image, (round(image.get_width() * scale), round(image.get_height() * scale)))
    return image, (round(FOOT[0] * scale), round(FOOT[1] * scale))
