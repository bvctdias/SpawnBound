from __future__ import annotations

from functools import lru_cache
from math import sqrt

import pygame

SIZE = (56, 84)
FOOT = (30, 80)
SIZES = {"palm_small": 30, "palm_medium": 38, "palm_tall": 46}
INK = (16, 58, 38)
DEEP = (36, 86, 56)
SHADE = (52, 124, 60)
MOSS = (68, 148, 62)
MID = (86, 172, 64)
LIGHT = (112, 206, 80)
HIGH = (150, 238, 100)
LIT_SIDE = (SHADE, MID, LIGHT, HIGH)
SHADED_SIDE = (DEEP, SHADE, MOSS, MID)
BARK = {"lit": (182, 102, 76), "top": (156, 84, 62), "mid": (124, 62, 46), "shade": (94, 46, 36),
        "deep": (70, 34, 30)}
BARK_INK = (52, 26, 24)
SEGMENT = 7
LEAN = 4


def _bezier(p0, p1, p2, steps=80):
    out = []
    for i in range(steps + 1):
        t = i / steps
        a, b, c = (1 - t) ** 2, 2 * t * (1 - t), t * t
        tx = 2 * (1 - t) * (p1[0] - p0[0]) + 2 * t * (p2[0] - p1[0])
        ty = 2 * (1 - t) * (p1[1] - p0[1]) + 2 * t * (p2[1] - p1[1])
        n = sqrt(tx * tx + ty * ty) or 1
        out.append((a * p0[0] + b * p1[0] + c * p2[0], a * p0[1] + b * p1[1] + c * p2[1], t, tx / n, ty / n))
    return out


def _frond(p0, p1, p2, width, tones):
    under, body, top, fleck = tones
    curve = _bezier(p0, p1, p2)
    bx, by = p0[0] - 2 * p1[0] + p2[0], p0[1] - 2 * p1[1] + p2[1]
    length = sum(sqrt((b[0] - a[0]) ** 2 + (b[1] - a[1]) ** 2) for a, b in zip(curve, curve[1:]))
    xs = [c[0] for c in curve]
    ys = [c[1] for c in curve]
    cells = {}
    for y in range(int(min(ys) - width) - 1, int(max(ys) + width) + 2):
        for x in range(int(min(xs) - width) - 1, int(max(xs) + width) + 2):
            px, py = x + .5, y + .5
            cx, cy, t, tx, ty = min(curve, key=lambda c: (c[0] - px) ** 2 + (c[1] - py) ** 2)
            if t >= 1:
                continue
            half = width / 2 * ((.75 + .25 * t / .2) if t < .2 else 1. if t < .55 else ((1 - t) / .45) ** .8)
            dx, dy = px - cx, py - cy
            nx, ny = (ty, -tx) if ty * bx - tx * by < 0 else (-ty, tx)
            across = dx * nx + dy * ny
            run = t * length
            saw = (run % 4) / 4
            reach = half * (1 - .4 * saw) if across < 0 and 5 < run < length - 4 else half
            if dx * dx + dy * dy > reach * reach or half < .45:
                continue
            side = max(-1., min(1., across / max(half, .5)))
            wave = abs(run % 4 - 2) / 2
            if run < 4:
                color = DEEP
            elif side < -.4 + .3 * saw:
                color = under
            elif side > .05 + .45 * wave:
                color = fleck if wave < .3 and side > .5 and t < .8 else top
            else:
                color = body
            cells[(x, y)] = color
    return cells


def _front(cx, top, length, width):
    cells = {}
    for r in range(length + 1):
        v = r / length
        half = width / 2 * ((.55 + 1.8 * v) if v < .25 else ((1 - v) / .75) ** .75)
        half = max(half, .6)
        y = top + r
        for x in range(int(cx - half - 1), int(cx + half + 2)):
            d = x + .5 - cx
            if abs(d) > half:
                continue
            s = d / half
            notch = 1.5 * (round(d) % 2) - .6 * abs(d)
            if r < 1 + (round(d) % 3 == 0):
                color = DEEP
            elif v > .78 or s > .55:
                color = SHADE
            elif r < length * .48 + notch or abs(d) < .8 and v < .72:
                color = HIGH if v < .4 and s < .1 and (x * 5 + y * 3) % 9 == 0 else LIGHT
            else:
                color = MID
            cells[(x, y)] = color
    return cells


def _cap(cx, cy, rx, ry):
    cells = {}
    for x, y in _blob(cx, cy, rx, ry):
        nx, ny = (x + .5 - cx) / rx, (y + .5 - cy) / ry
        if ny > .6:
            cells[(x, y)] = DEEP
        elif ny < -.1 and nx < .35:
            cells[(x, y)] = HIGH if (x * 3 + y) % 5 == 0 else LIGHT
        else:
            cells[(x, y)] = MID
    return cells


def _blob(cx, cy, rx, ry):
    return [(x, y) for y in range(int(cy - ry) - 1, int(cy + ry) + 2)
            for x in range(int(cx - rx) - 1, int(cx + rx) + 2)
            if ((x + .5 - cx) / rx) ** 2 + ((y + .5 - cy) / ry) ** 2 <= 1]


def _trunk(height):
    cells = {}
    fx, fy = FOOT
    for h in range(height + 1):
        y = fy - h
        lean = round(LEAN * (h / height) ** 1.5)
        width = 12 - round(2 * h / height)
        ring = h % SEGMENT
        bulge = 1 if ring in (1, 2) else 0
        left = fx - lean - width // 2 - bulge
        right = fx - lean + (width - 1) // 2 + bulge
        for x in range(left, right + 1):
            across = (x - left) / max(1, right - left)
            if ring == SEGMENT - 1:
                color = BARK["lit"] if across < .6 else BARK["top"]
            elif ring == 0:
                color = BARK["deep"]
            elif across < .22:
                color = BARK["top"]
            elif across > .68:
                color = BARK["shade"]
            else:
                color = BARK["mid"]
            cells[(x, y)] = color
    return cells


def _stamp(grid, cells, ink):
    for x, y in cells:
        for n in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
            if n not in cells:
                grid[n] = ink
    grid.update(cells)


def _layer(grid, crown, cells):
    for x, y in cells:
        for n in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
            if n not in cells:
                grid[n] = DEEP if n in crown else INK
    grid.update(cells)
    crown.update(cells)


@lru_cache(maxsize=None)
def palm(variant: str) -> pygame.Surface:
    height = SIZES.get(variant, SIZES["palm_medium"])
    grid: dict[tuple[int, int], tuple[int, int, int]] = {}
    _stamp(grid, _trunk(height), BARK_INK)
    ax, ay = FOOT[0] - LEAN, FOOT[1] - height
    at = lambda dx, dy: (ax + dx, ay + dy)
    crown: set[tuple[int, int]] = set()
    _layer(grid, crown, {c: DEEP for c in _blob(ax, ay - 15, 8, 4)})
    _layer(grid, crown, _cap(ax, ay - 20, 6, 4))
    for side, tones in ((1, SHADED_SIDE), (-1, LIT_SIDE)):
        _layer(grid, crown, _frond(at(side * 3, -15), at(side * 21, -22), at(side * 17, 2), 12, tones))
    _layer(grid, crown, _front(ax, ay - 17, 23, 15))
    image = pygame.Surface(SIZE, pygame.SRCALPHA)
    for (x, y), color in grid.items():
        if 0 <= x < SIZE[0] and 0 <= y < SIZE[1]:
            image.set_at((x, y), color)
    return image


def placed_palm(variant: str, scale: float = 1.) -> tuple[pygame.Surface, tuple[int, int]]:
    image = palm(variant)
    if scale != 1:
        image = pygame.transform.scale(image, (round(image.get_width() * scale), round(image.get_height() * scale)))
    return image, (round(FOOT[0] * scale), round(FOOT[1] * scale))
