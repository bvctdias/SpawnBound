from __future__ import annotations

from functools import lru_cache
from math import sqrt

Pixels = dict[tuple[int, int], tuple[int, int, int]]
INK = (43, 32, 44)
PURPLE = ((50, 30, 64), (74, 46, 94), (100, 64, 122), (128, 86, 148))
MAUVE = ((122, 62, 98), (158, 88, 120))
MAW, TOOTH, TOOTH_SHADE, TONGUE, GUM = (36, 20, 42), (236, 240, 238), (186, 194, 204), (148, 50, 76), (216, 184, 140)
BONE = {"w": (232, 236, 234), "s": (184, 190, 200), "g": (214, 182, 136)}
CLAW = (220, 190, 146)
EYE, PUPIL = (246, 208, 92), (28, 16, 32)
LIGHT = (-.6, -.7, .45)

GROUND = 19
ORIGIN = (13, GROUND)
HEAD = (16.5, 8.0, 8.5, 7.0, 2.3)
HAUNCH = (8.5, 11.5, 5.6, 4.5, 2.2)
MAW_BACK = 14
MAW_TOP = 8
SPLIT = 11
HORNS = ((18, ("gg", "ww", "ws", "ww.", "w..")), (11, ("gg", "ws", "ww", "w.")), (5, ("gg", "ws", "w.")))


def _lit(nx: float, ny: float) -> float:
    nz = sqrt(max(0., 1 - nx * nx - ny * ny))
    lx, ly, lz = LIGHT
    return (nx * lx + ny * ly + nz * lz) / sqrt(lx * lx + ly * ly + lz * lz)


def _tone(b: float) -> int:
    return 3 if b > .72 else 2 if b > .38 else 1 if b > .02 else 0


def _blob(cx, cy, rx, ry, power, x, y):
    nx, ny = (x + .5 - cx) / rx, (y + .5 - cy) / ry
    return nx, ny, abs(nx) ** power + abs(ny) ** power


def _body() -> dict:
    cells = {}
    for y in range(0, GROUND):
        for x in range(0, 27):
            head = _blob(*HEAD, x, y)
            haunch = _blob(*HAUNCH, x, y)
            nx, ny, depth = min(head, haunch, key=lambda b: b[2])
            if depth > 1:
                continue
            tone = _tone(_lit(nx * .92, ny * .92))
            color = PURPLE[tone]
            if head[2] <= 1 and head[1] < -.55 and -.75 < head[0] < .55:
                color = MAUVE[1] if tone >= 2 else MAUVE[0]
            cells[(x, y)] = color
    return cells


def _teeth(cells: dict, row: int, offset: int) -> None:
    for (x, y) in list(cells):
        if y in (row, row + 1) and x >= MAW_BACK + (1 if y == row and offset else 0):
            k = (x - MAW_BACK - offset) % 3
            cells[(x, y)] = MAW if k == 2 else TOOTH_SHADE if (y == row + 1 and k == 1) else TOOTH


def _head(drop: int, asleep: bool) -> dict:
    body = _body()
    if asleep:
        for (x, y) in body:
            if x >= MAW_BACK + 1 and y == SPLIT:
                body[(x, y)] = MAW
            elif x >= MAW_BACK + 1 and y in (SPLIT - 1, SPLIT + 1) and (x - MAW_BACK - (y > SPLIT)) % 3 == 0:
                body[(x, y)] = TOOTH
        return body
    jaw = {(x, y + drop): c for (x, y), c in body.items() if x >= MAW_BACK and y >= SPLIT}
    cells = {p: c for p, c in body.items() if not (p[0] >= MAW_BACK and p[1] >= SPLIT)}
    for (x, y), c in body.items():
        if x >= MAW_BACK and y == SPLIT:
            for d in range(drop):
                cells[(x, y + d)] = MAW
    cells.update(jaw)
    for (x, y) in list(cells):
        if x < MAW_BACK + (1 if y in (MAW_TOP, SPLIT + drop + 3) else 0):
            continue
        if y == MAW_TOP or SPLIT <= y <= SPLIT + drop or y == SPLIT + drop + 3:
            cells[(x, y)] = MAW
        if drop and y == SPLIT + drop - 1 and MAW_BACK + 2 <= x <= MAW_BACK + 7:
            cells[(x, y)] = TONGUE
    _teeth(cells, MAW_TOP + 1, 0)
    _teeth(cells, SPLIT + drop + 1, 1)
    for y in range(MAW_TOP, SPLIT + drop + 4):
        front = max((x for (x, yy) in cells if yy == y), default=None)
        if front is not None and front >= MAW_BACK:
            cells[(front, y)] = MAW
    for x in (MAW_BACK + 3, MAW_BACK + 6):
        if cells.get((x, MAW_TOP + 2)) is TOOTH_SHADE or cells.get((x, MAW_TOP + 2)) is TOOTH:
            cells[(x, MAW_TOP + 2)] = GUM
    return cells


def _eye(cells: dict, awake: bool) -> None:
    x, y = MAW_BACK + 1, MAW_TOP - 2
    cells[(x, y)], cells[(x + 1, y)] = (EYE, PUPIL) if awake else (PURPLE[0], PURPLE[0])


def _horns(body: dict) -> dict:
    cells = {}
    for left, rows in HORNS:
        top = min(y for (x, y) in body if x in (left, left + 1))
        for i, row in enumerate(rows):
            for j, c in enumerate(row):
                if c != ".":
                    cells[(left + j - (i >= 3), top - i)] = BONE[c]
    return cells


def _leg(x: int, foot: int, near: bool, fold: int) -> dict:
    color = PURPLE[1] if near else PURPLE[0]
    bottom = GROUND - fold
    cells = {(x + dx, y): color for dx in range(3) for y in range(13, bottom)}
    for dx in range(3):
        cells[(x + dx + foot, bottom)] = color
    cells[(x + 2 + foot, bottom)] = cells[(x + 3 + foot, bottom)] = CLAW
    return cells


def _tail(swing: int, low: bool) -> dict:
    cells = {}
    base = (4, 12)
    tip = (-2, 8 + swing) if not low else (-3, GROUND - 4)
    steps = 16
    for i in range(steps + 1):
        t = i / steps
        x = round(base[0] + (tip[0] - base[0]) * t)
        y = round(base[1] + (tip[1] - base[1]) * t ** 2)
        for d in range(round(4 - 3 * t)):
            cells.setdefault((x, y + d), PURPLE[2 - (d > 1) - (t > .6)])
    cells[(tip[0], tip[1] - 1)] = PURPLE[2]
    return cells


def _stamp(grid: dict, cells: dict) -> None:
    for x, y in cells:
        for n in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
            if n not in cells:
                grid[n] = INK
    grid.update(cells)


def _moved(cells: dict, dx: int, dy: int) -> dict:
    return {(x + dx, y + dy): c for (x, y), c in cells.items()}


POSES = {
    "idle": (0, 0, 0, 0, True, False, 0, (0, 0, 0, 0)),
    "walk0": (0, 0, 0, 0, True, False, 0, (1, -1, 1, -1)),
    "walk1": (1, 0, 1, 0, True, False, 0, (-1, 1, -1, 1)),
    "sleep": (-4, 0, 0, 0, False, True, 3, (0, 0, 0, 0)),
    "strike_ready": (0, -1, 1, 2, True, False, 0, (-1, 0, 0, -1)),
    "strike": (1, 1, 0, 3, True, False, 0, (1, 0, 1, 2)),
    "charge_ready": (-1, -1, 0, 1, True, False, 0, (-1, -1, -1, -1)),
    "charge": (1, 1, 1, 3, True, False, 0, (-2, -1, 2, 3)),
    "dazed": (0, 0, 0, 2, False, False, 0, (0, 0, 0, 0)),
}
HIND, FRONT = 6, 13


@lru_cache(maxsize=None)
def _pose(name: str) -> tuple:
    lift, shift, swing, drop, awake, asleep, fold, (nh, fh, ff, nf) = POSES[name]
    grid: dict = {}
    _stamp(grid, _moved(_tail(swing, asleep), 0, -lift))
    _stamp(grid, _leg(HIND + 2, fh, False, fold))
    _stamp(grid, _leg(FRONT + 2, ff, False, fold))
    _stamp(grid, _leg(HIND, nh, True, fold))
    _stamp(grid, _leg(FRONT, nf, True, fold))
    head = _head(drop, asleep)
    _eye(head, awake)
    _stamp(grid, _moved(head, 0, -lift))
    _stamp(grid, _moved(_horns(head), 0, -lift))
    return tuple(((x - ORIGIN[0] + shift, y - ORIGIN[1]), c) for (x, y), c in grid.items())


def mine_monster(stride: int, stance: str) -> Pixels:
    if stance in ("walk", "run"):
        return dict(_pose(f"walk{stride % 2}"))
    if stance in POSES:
        return dict(_pose(stance))
    return dict(_pose("idle"))
