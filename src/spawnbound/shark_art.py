from __future__ import annotations

from functools import lru_cache
from math import pi, sin

Pixels = dict[tuple[int, int], tuple[int, int, int]]
INK = (43, 32, 44)
WATER = (64, 136, 150)
SEEN_THROUGH = .3
BACK = ((54, 58, 70), (78, 84, 98), (108, 116, 130))
BELLY = ((168, 174, 182), (214, 218, 222))
FIN = ((52, 56, 68), (80, 86, 100), (122, 130, 144))
FOAM = (242, 250, 250)
SPRAY = (198, 232, 238)
HEAD = {"d": BACK[0], "m": BACK[1], "M": BACK[2], "l": BELLY[1], "L": BELLY[0],
        "r": (150, 46, 56), "R": (98, 26, 40), "w": (250, 248, 240), "e": (20, 16, 24)}
NOSE, TAIL = 17, -19
CENTRE = 6.

OPEN_JAWS = (
    "..............ddd.....",
    "............ddmmmd....",
    "..........ddmmmmmmd...",
    "........ddmMMmmmmmmd..",
    ".......dmMMmmmmmmmmmd.",
    "......dmMMmmmmmmemmmmd",
    ".....dmmmmmmmmmmmmwwwd",
    "....dmmmmmmmmmmmRwwww.",
    "...dmmmmmmmmmmRRr.w...",
    "..dmmmmmmmmmmRRrr.....",
    "..dmmmmmmmmmRRrrr.....",
    "..dmmmmmmmmmRRrrw.w...",
    "..dLlllllllllwwwww....",
    "...LLllllllllllll.....",
    "....LLLllllllll.......",
)
CLOSED_JAWS = (
    "............ddd.......",
    "..........ddmmmd......",
    "........ddmMMmmmd.....",
    "......ddmMMmmmmmmd....",
    ".....dmMMmmmmmmemmd...",
    "....dmmmmmmmmmmmmmmd..",
    "...dmmmmmmmmmmmmmmmmd.",
    "..dmmmmmmmmmmmwwwwwwww",
    "..dLllllllllllllllll..",
    "...LLlllllllllllll....",
    "....LLLllllllll.......",
)


def _seen(color):
    return tuple(round(c * (1 - SEEN_THROUGH) + w * SEEN_THROUGH) for c, w in zip(color, WATER))


def _body(sway: int, front: int = NOSE) -> dict:
    cells = {}
    for x in range(TAIL, NOSE + 1):
        t = (x - TAIL) / (NOSE - TAIL)
        half = 5.6 * sin(pi * min(.95, .05 + t * .92)) ** .6
        top, bottom = round(CENTRE - half), round(CENTRE + half * .8)
        if x > front:
            bottom = min(bottom, round(CENTRE + half * .8 - (x - front) * 1.4))
            if bottom < 0:
                break
        for y in range(top, bottom + 1):
            if y == top:
                color = BACK[0]
            elif y < round(CENTRE):
                color = BACK[1]
            elif y == round(CENTRE):
                color = BACK[2]
            elif y < bottom:
                color = BELLY[1]
            else:
                color = BELLY[0]
            cells[(x, y)] = color
    if front >= NOSE:
        cells[(NOSE - 3, round(CENTRE) - 1)] = HEAD["e"]
    for i, (x, y) in enumerate(((4, 10), (3, 11), (2, 12), (1, 12), (0, 13), (-1, 13))):
        cells[(x, y)] = BACK[1] if i < 3 else BACK[0]
        cells.setdefault((x + 1, y), BACK[1])
        cells.setdefault((x + 2, y), BACK[1])
    for y in range(-2, 14):
        bend = abs(y - 5) / 8
        x = TAIL - 1 - round(5 * bend) + (sway if y < 5 else -sway)
        cells[(x, y)] = BACK[1] if y < 5 else BACK[0]
        cells[(x + 1, y)] = BACK[1]
        cells[(x + 2, y)] = BACK[0]
    return {p: _seen(c) for p, c in cells.items() if p[1] >= 0}


def _fin(left: int, height: int, lean: float, sink: int = 0) -> dict:
    cells = {}
    for row in range(1, height + 1):
        y = -row + sink
        if y >= 0:
            continue
        front = left + round((height - row) * lean) + 1
        back = left - (1 if row == height else 0)
        for x in range(back, max(back, front) + 1):
            cells[(x, y)] = FIN[2] if x == front else FIN[0] if x == back else FIN[1]
    return cells


def _foam(left: int, right: int, frame: int, wide: bool = False) -> dict:
    grow = frame + (1 if wide else 0)
    cells = {(x, 0): FOAM for x in range(left - grow, right + grow + 1)}
    cells[(left - grow - 1, -1)] = cells[(right + grow + 1, -1)] = FOAM
    if frame:
        cells[(right + grow + 2, 0)] = SPRAY
    return cells


def _stamp(grid: dict, cells: dict) -> None:
    for x, y in cells:
        for n in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
            if n not in cells and n[1] <= 0:
                grid[n] = INK
    grid.update(cells)


def _head(rows: tuple[str, ...]) -> dict:
    top = len(rows) - 1
    return {(1 + x, y - top): HEAD[c] for y, row in enumerate(rows) for x, c in enumerate(row) if c != "."}


def _splash(frame: int) -> dict:
    cells = {(x, 0): FOAM for x in range(-2, 23)}
    for x, y in ((-3, -1), (23, -1), (-5, -3), (24, -3), (-1, -6), (21, -8), (-4, -9), (24, -10), (9, -16)):
        cells[(x + (frame if x > 10 else -frame), y - frame)] = SPRAY if y < -5 else FOAM
    return cells


@lru_cache(maxsize=None)
def _shark(stance: str, frame: int) -> tuple:
    grid: dict = {}
    if stance in ("strike", "drag"):
        grid.update(_body(0, front=2))
        _stamp(grid, _fin(-9, 9, .6, sink=3))
        _stamp(grid, _head(OPEN_JAWS if stance == "strike" else CLOSED_JAWS))
        grid.update(_splash(frame))
    else:
        ready = stance == "strike_ready"
        grid.update(_body(frame if stance in ("walk", "run") else 0))
        _stamp(grid, _fin(-4, 12, .75, sink=2 if ready else 0))
        _stamp(grid, _fin(TAIL - 6 + (frame if stance in ("walk", "run") else 0), 7, .22))
        grid.update(_foam(-5, 6, frame, wide=ready))
        grid.update(_foam(TAIL - 6, TAIL - 3, frame))
    return tuple(grid.items())


def shark(stride: int, stance: str) -> Pixels:
    if stance not in ("walk", "run", "strike_ready", "strike", "drag"):
        stance = "idle"
    return dict(_shark(stance, stride % 2))


LAYERS = ("all", "above", "below")


@lru_cache(maxsize=128)
def placed_shark(stance: str, stride: int, left: bool, scale: float, layer: str = "all"):
    import pygame
    pixels = shark(stride, stance)
    xs = [x for x, _ in pixels]
    ys = [y for _, y in pixels]
    x0, y0 = min(xs), min(ys)
    image = pygame.Surface((max(xs) - x0 + 1, max(ys) - y0 + 1), pygame.SRCALPHA)
    for (x, y), color in pixels.items():
        if layer == "all" or (y <= 0) == (layer == "above"):
            image.set_at((x - x0, y - y0), color)
    anchor = (-x0, -y0)
    if left:
        image = pygame.transform.flip(image, True, False)
        anchor = (image.get_width() - 1 - anchor[0], anchor[1])
    if scale != 1:
        image = pygame.transform.scale(image, (round(image.get_width() * scale), round(image.get_height() * scale)))
    return image, (round(anchor[0] * scale), round(anchor[1] * scale))
