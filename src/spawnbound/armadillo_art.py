from __future__ import annotations

from functools import lru_cache
from math import asin, pi, sqrt

Pixels = dict[tuple[int, int], tuple[int, int, int]]
INK = (43, 32, 44)
SHELL = ((92, 44, 34), (124, 66, 48), (156, 92, 66), (186, 118, 84), (214, 150, 108))
SKIN = {"H": (168, 102, 76), "h": (132, 76, 58), "R": (150, 90, 68), "N": (244, 224, 214),
        "P": (218, 166, 156), "e": (30, 22, 33)}
LEG = {"near": (112, 62, 46), "far": (80, 42, 34)}
LIGHT = (-.6, -.7, .45)

CX, RIM, RX, RY = 11.5, 11, 7.2, 10.4
ROUND = 2.5
GROUND = RIM + 3
ORIGIN = (12, GROUND)
BANDS = 6.3
HEAD = (
    ".RR.......",
    "RhhR......",
    "hhhhhhh...",
    "HHHHHHHHh.",
    "HHNeNNNHHP",
    "HNNNNNNPPP",
    ".HNNNPPP..",
)
HIND, FRONT = 6, 15


def _lit(nx: float, ny: float) -> float:
    nz = sqrt(max(0., 1 - nx * nx - ny * ny))
    lx, ly, lz = LIGHT
    return (nx * lx + ny * ly + nz * lz) / sqrt(lx * lx + ly * ly + lz * lz)


def _tone(b: float) -> int:
    return 4 if b > .78 else 3 if b > .48 else 2 if b > .12 else 1


def _ridge(nx: float, turn: float = 0.) -> int:
    band = ((asin(max(-1., min(1., nx))) / (pi / 2) + 1) * BANDS / 2 + turn) % 1
    return -2 if band < .26 else 1 if band < .52 else 0


def _shell(lift: int) -> dict:
    cells = {}
    for y in range(int(RIM - RY), RIM + 1):
        for x in range(int(CX - RX) - 1, int(CX + RX) + 2):
            nx, ny = (x + .5 - CX) / RX, (y - RIM) / RY
            if abs(nx) ** ROUND + abs(ny) ** ROUND > 1:
                continue
            ridge = _ridge(nx)
            tone = _tone(_lit(nx * .9, ny * .9)) + ridge
            if -.42 < ny < -.2:
                tone -= 1
            if y == RIM:
                tone = 0 if ridge < 0 else 1
            cells[(x, y - lift)] = SHELL[max(0, min(4, tone))]
    return cells


def _tail(lift: int, swing: int) -> dict:
    cells = {}
    base = (int(CX - RX) + 2, RIM - 4 - lift)
    tip = (base[0] - 6, GROUND - 1 + swing)
    steps = 18
    for i in range(steps + 1):
        t = i / steps
        x, y = round(base[0] + (tip[0] - base[0]) * t), round(base[1] + (tip[1] - base[1]) * t)
        tone = 2 if (i // 4) % 2 else 3
        for d in range(round(3 - 2.2 * t)):
            cells.setdefault((x, y + d), SHELL[tone - (d > 0)])
    return cells


def _head(lift: int, low: int) -> dict:
    cells = {}
    for y, row in enumerate(HEAD):
        for x, c in enumerate(row):
            if c != ".":
                cells[(16 + x, RIM - 7 + y - lift + low)] = SKIN[c]
    return cells


def _leg(x: int, foot: int, near: bool, lift: int) -> dict:
    color = LEG["near" if near else "far"]
    top = RIM + 1 - lift
    cells = {(x, y): color for y in range(top, GROUND)}
    cells.update({(x + 1, y): color for y in range(top, GROUND - 1)})
    cells[(x + foot, GROUND)] = cells[(x + foot + 1, GROUND)] = color
    return cells


def _stamp(grid: dict, cells: dict) -> None:
    for x, y in cells:
        for n in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
            if n not in cells:
                grid[n] = INK
    grid.update(cells)


POSES = {
    "idle": (0, 0, 0, (0, 0, 0, 0)),
    "rest": (0, 1, 0, (0, 0, 0, 0)),
    "walk0": (0, 0, 0, (1, -1, 1, -1)),
    "walk1": (0, 0, 1, (-1, 1, -1, 1)),
    "run0": (1, 0, 0, (-2, -1, 2, 3)),
    "run1": (0, 0, 1, (1, 2, -2, -1)),
}


@lru_cache(maxsize=None)
def _walker(pose: str) -> tuple:
    lift, low, swing, (nh, fh, ff, nf) = POSES[pose]
    grid: dict = {}
    _stamp(grid, _tail(lift, swing))
    _stamp(grid, _leg(HIND + 1, fh, False, lift))
    _stamp(grid, _leg(FRONT - 1, ff, False, lift))
    _stamp(grid, _shell(lift))
    _stamp(grid, _leg(HIND, nh, True, lift))
    _stamp(grid, _leg(FRONT, nf, True, lift))
    _stamp(grid, _head(lift, low))
    return tuple(((x - ORIGIN[0], y - ORIGIN[1]), c) for (x, y), c in grid.items())


BALL = 6.4


@lru_cache(maxsize=None)
def _ball(turn: int) -> tuple:
    cx, cy = ORIGIN[0] + .5, GROUND - BALL + .5
    cells = {}
    for y in range(int(cy - BALL) - 1, int(cy + BALL) + 2):
        for x in range(int(cx - BALL) - 1, int(cx + BALL) + 2):
            nx, ny = (x + .5 - cx) / BALL, (y + .5 - cy) / BALL
            if nx * nx + ny * ny > 1:
                continue
            tone = _tone(_lit(nx * .95, ny * .95))
            tone += _ridge(nx / max(.35, sqrt(max(0., 1 - ny * ny))), turn * .5)
            cells[(x, y)] = SHELL[max(0, min(4, tone))]
    grid: dict = {}
    _stamp(grid, cells)
    front = round(cx + BALL) - 1
    tucked = {(front, GROUND - 2): SKIN["N"], (front - 1, GROUND - 2): SKIN["P"],
              (front - 1, GROUND - 3): SKIN["h"], (front, GROUND - 3): SKIN["H"]}
    _stamp(grid, tucked)
    return tuple(((x - ORIGIN[0], y - ORIGIN[1]), c) for (x, y), c in grid.items())


def armadillo(stride: int, stance: str) -> Pixels:
    if stance == "ball":
        return dict(_ball(stride))
    if stance in ("walk", "run"):
        return dict(_walker(f"{stance}{stride}"))
    return dict(_walker("rest" if stance == "rest" else "idle"))
