from __future__ import annotations

import random
from functools import lru_cache
from math import atan2, sin, sqrt

import pygame

SIZE = (48, 36)
FOOT = (24, 30)
LIGHT = (-.55, -.72, .52)

PALETTES = {
    "stone": ((74, 80, 100), (100, 110, 130), (130, 140, 156), (162, 172, 184), (198, 206, 212), (46, 48, 66)),
    "sandstone": ((160, 112, 76), (190, 144, 98), (214, 176, 124), (234, 204, 150), (247, 226, 182), (110, 74, 54)),
    "lilac": ((96, 86, 120), (124, 112, 150), (152, 142, 176), (182, 174, 202), (216, 210, 230), (60, 50, 80)),
}
PATCH = ((116, 76, 54), (134, 90, 62), (150, 104, 70), (164, 116, 78), (178, 130, 88))
COAL = ((22, 20, 32), (38, 36, 54), (58, 56, 80), (86, 86, 114), (120, 122, 150), (16, 14, 24))
COPPER = ((170, 80, 62), (232, 136, 96), (248, 176, 132), (255, 216, 184))
QUARTZ = {"pink": ((176, 92, 140), (226, 150, 192), (246, 200, 226), (255, 238, 248)),
          "white": ((150, 140, 170), (214, 208, 228), (240, 236, 248), (255, 255, 255))}
QUARTZ_INK = (110, 56, 96)

SHAPES = (
    ((-5, -9, 12, 8.5), (7, -6, 10, 7)),
    ((1, -11, 11, 8.5), (-9, -6, 9, 6.5), (9, -5, 8.5, 6)),
    ((-2, -8, 14, 8), (11, -5, 7, 5.5)),
)
SCALE = .8


def _lumps(shape: int) -> tuple[tuple[float, float, float, float], ...]:
    return tuple(tuple(v * SCALE for v in lump) for lump in SHAPES[shape])

LOOKS = {
    "default": ("stone", ("specks",)),
    "cave_stone": ("stone", ("specks",)),
    "sandstone": ("sandstone", ("patches",)),
    "sandstone_coal": ("sandstone", ("few_patches", "coal")),
    "coal_ore": ("stone", ("few_specks", "coal")),
    "copper_ore": ("lilac", ("specks", "copper")),
    "quartz_ore": ("stone", ("few_specks", "quartz")),
}


def rock_shape(position) -> int:
    return ((position.x * 73856093) ^ (position.y * 19349663)) % len(SHAPES)


def _lit(nx: float, ny: float) -> float:
    nz = sqrt(max(0., 1 - nx * nx - ny * ny))
    lx, ly, lz = LIGHT
    return (nx * lx + ny * ly + nz * lz) / sqrt(lx * lx + ly * ly + lz * lz)


def _tone(b: float) -> int:
    return 4 if b > .8 else 3 if b > .52 else 2 if b > .2 else 1 if b > -.18 else 0


class _Canvas:
    def __init__(self):
        self.color: dict[tuple[int, int], tuple[int, int, int]] = {}
        self.material: dict[tuple[int, int], str] = {}
        self.tone: dict[tuple[int, int], int] = {}

    def put(self, p, color, material, tone=2):
        if 0 <= p[0] < SIZE[0] and 0 <= p[1] < SIZE[1]:
            self.color[p], self.material[p], self.tone[p] = color, material, tone


def _dome(canvas, cx, cy, rx, ry, palette, material, owner=None, owners=None, wobble=None):
    fx, fy = FOOT[0] + cx, FOOT[1] + cy
    covered = []
    for y in range(int(fy - ry * 1.15) - 1, int(fy + ry * 1.15) + 2):
        for x in range(int(fx - rx * 1.15) - 1, int(fx + rx * 1.15) + 2):
            nx, ny = (x + .5 - fx) / rx, (y + .5 - fy) / ry
            if wobble:
                amount, p1, p2 = wobble
                angle = atan2(ny, nx)
                k = 1 + amount * sin(3 * angle + p1) + amount * .6 * sin(5 * angle + p2)
                nx, ny = nx / k, ny / k
            if nx * nx + ny * ny > 1:
                continue
            tone = _tone(_lit(nx, ny))
            if ny > .62:
                tone = min(tone, 1)
            canvas.put((x, y), palette[tone], material, tone)
            if owners is not None:
                owners[(x, y)] = owner
            covered.append((x, y))
    return covered


def _body(canvas, shape, palette):
    owners: dict[tuple[int, int], int] = {}
    lumps = random.Random(f"shape/{shape}")
    for i, lump in enumerate(_lumps(shape)):
        wobble = (.07, lumps.uniform(0, 6.3), lumps.uniform(0, 6.3))
        _dome(canvas, *lump, palette, "rock", i, owners, wobble)
    for (x, y), owner in list(owners.items()):
        if any(owners.get((x + dx, y + dy), -1) > owner for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))):
            tone = max(0, canvas.tone[(x, y)] - 2)
            canvas.put((x, y), palette[tone], "rock", tone)
    return owners


def _inside(canvas, p, margin=1):
    x, y = p
    return all(canvas.material.get((x + dx, y + dy)) == "rock"
               for dx in range(-margin, margin + 1) for dy in range(-margin, margin + 1))


def _specks(canvas, rng, palette, count):
    spots = [p for p in canvas.color if _inside(canvas, p) and canvas.tone[p] >= 2]
    for p in rng.sample(spots, min(count, len(spots))):
        tone = canvas.tone[p]
        canvas.put(p, palette[tone - 2], "rock", tone)
        if rng.random() < .5:
            q = (p[0] + 1, p[1])
            if q in canvas.color and canvas.material[q] == "rock":
                canvas.put(q, palette[max(0, canvas.tone[q] - 1)], "rock", canvas.tone[q])


def _patches(canvas, rng, count):
    rows = [p[1] for p in canvas.color]
    top, bottom = min(rows), max(rows)
    spots = [p for p in canvas.color if _inside(canvas, p, 2) and p[1] < top + (bottom - top) * .75]
    for cx, cy in rng.sample(spots, min(count, len(spots))):
        radius, phase, lobes = rng.uniform(2.3, 3.4), rng.uniform(0, 6.3), rng.choice((2, 3))
        for y in range(cy - 5, cy + 6):
            for x in range(cx - 6, cx + 7):
                dx, dy = x - cx, (y - cy) * 1.4
                d = sqrt(dx * dx + dy * dy)
                angle = 0. if d == 0 else (dy / d if dx >= 0 else -dy / d)
                if d <= radius + .9 * sin(lobes * angle * 3.14 + phase) and _inside(canvas, (x, y)):
                    tone = canvas.tone[(x, y)]
                    canvas.put((x, y), PATCH[tone], "rock", tone)


def _coal(canvas, rng, shape):
    lumps = _lumps(shape)
    back = lumps[0]
    seats = [(back[0] - 3, back[1] - back[3] * .55), (back[0] + 4, back[1] - back[3] * .35)]
    front = lumps[-1]
    seats.append((front[0] + 1, front[1] - front[3] * .3))
    for sx, sy in seats:
        r = rng.uniform(3.1, 3.6)
        covered = _dome(canvas, sx + rng.uniform(-1, 1), sy, r, r * .85, COAL, "coal",
                        wobble=(.1, rng.uniform(0, 6.3), rng.uniform(0, 6.3)))
        for x, y in covered:
            below = (x, y + 1)
            if below in canvas.color and canvas.material[below] == "rock":
                canvas.put(below, COAL[1], "coal", 1)


def _copper(canvas, rng):
    chunk = (".HHO.", "HOOOd", "OOOdd", ".Odd.")
    colors = {"H": COPPER[3], "O": COPPER[1], "d": COPPER[0]}
    rows = [p[1] for p in canvas.color]
    top, bottom = min(rows), max(rows)
    spots = [p for p in canvas.color if _inside(canvas, p, 2) and canvas.tone[p] >= 1
             and p[1] < top + (bottom - top) * .62]
    placed = []
    for p in rng.sample(spots, len(spots)):
        if len(placed) == 3:
            break
        if any(abs(p[0] - q[0]) < 7 and abs(p[1] - q[1]) < 6 for q in placed):
            continue
        placed.append(p)
        for y, row in enumerate(chunk):
            for x, cell in enumerate(row):
                if cell != ".":
                    canvas.put((p[0] + x - 1, p[1] + y - 1), colors[cell], "copper")
        canvas.put((p[0] + 1, p[1]), COPPER[2], "copper")


def _quartz(canvas, rng, shape):
    lumps = _lumps(shape)
    back = lumps[0]
    base_y = FOOT[1] + back[1] - back[3] * .2
    for i, (dx, height, lean, kind) in enumerate(((-4, 9, -1, "pink"), (0, 12, 0, "white"), (4, 8, 1, "pink"))):
        cx = round(FOOT[0] + back[0] + dx) + rng.choice((-1, 0, 1))
        h = height + rng.choice((-1, 0, 1))
        light, mid, lit, glint = QUARTZ[kind][1], QUARTZ[kind][0], QUARTZ[kind][2], QUARTZ[kind][3]
        for step in range(h):
            y = round(base_y) - step
            shift = round(lean * step / h * 2)
            half = 2 if step < h - 3 else 1 if step < h - 1 else 0
            for x in range(cx - half + shift, cx + half + 1 + shift):
                color = lit if x < cx + shift else light if x == cx + shift else mid
                canvas.put((x, y), color, "crystal")
        canvas.put((cx + round(lean * 2) - 1 + (0 if lean <= 0 else 1), round(base_y) - h + 3), glint, "crystal")


def _outline(canvas, palette):
    inks = {"rock": palette[5], "coal": COAL[5], "copper": palette[5], "crystal": QUARTZ_INK}
    rim = {}
    for (x, y), material in canvas.material.items():
        for p in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
            if p not in canvas.color and 0 <= p[0] < SIZE[0] and 0 <= p[1] < SIZE[1]:
                if rim.get(p) != QUARTZ_INK:
                    rim[p] = inks[material]
    for p, color in rim.items():
        canvas.put(p, color, "ink")


@lru_cache(maxsize=None)
def rock(variant: str, shape: int) -> pygame.Surface:
    palette_name, marks = LOOKS.get(variant, LOOKS["default"])
    palette = PALETTES[palette_name]
    rng = random.Random(f"{palette_name}/{'+'.join(marks)}/{shape}")
    canvas = _Canvas()
    _body(canvas, shape, palette)
    for mark in marks:
        if mark in ("specks", "few_specks"):
            _specks(canvas, rng, palette, 5 if mark == "specks" else 2)
        elif mark in ("patches", "few_patches"):
            _patches(canvas, rng, 3 if mark == "patches" else 2)
        elif mark == "coal":
            _coal(canvas, rng, shape)
        elif mark == "copper":
            _copper(canvas, rng)
        elif mark == "quartz":
            _quartz(canvas, rng, shape)
    _outline(canvas, palette)
    image = pygame.Surface(SIZE, pygame.SRCALPHA)
    for p, color in canvas.color.items():
        image.set_at(p, color)
    return image


def placed_rock(variant: str, shape: int, scale: float = 1.) -> tuple[pygame.Surface, tuple[int, int]]:
    image = rock(variant, shape)
    if scale != 1:
        image = pygame.transform.scale(image, (round(image.get_width() * scale), round(image.get_height() * scale)))
    return image, (round(FOOT[0] * scale), round(FOOT[1] * scale))
