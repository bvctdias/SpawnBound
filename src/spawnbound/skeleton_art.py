from __future__ import annotations

from functools import lru_cache

Pixels = dict[tuple[int, int], tuple[int, int, int]]
INK = (43, 32, 44)
BONE = {"W": (250, 242, 240), "l": (226, 212, 214), "m": (186, 166, 176), "d": (130, 110, 126),
        "e": (30, 22, 40), "k": INK}
WOOD = {"g": (110, 66, 40), "G": (166, 108, 52), "h": (220, 158, 86)}
STRING = (236, 226, 204)
ARROW = {"a": (170, 116, 60), "t": (200, 206, 214), "f": (236, 236, 236)}

BODY = (
    "...mmlllmm...",
    "..mlWWWWWlm..",
    ".mlWWWWWWWlm.",
    ".mllWWWWWllm.",
    ".mllWWWWWllm.",
    ".mlllWWWlllm.",
    ".mlelWlWlelm.",
    ".dleellleeld.",
    ".dleeleleeld.",
    ".dllllllllld.",
    "..kkWdWdWkk..",
    "..mdkkkkkdm..",
    "....mlllm....",
    "....dmlmd....",
    "....mlllm....",
    "....dmdmd....",
)
LEGS = {
    "stand": ("....lm.ml....", "....ld.dl...."),
    "walk0": ("....lm.ml....", ".......dl...."),
    "walk1": ("....lm.ml....", "....ld......."),
}
ORIGIN = (6, 17)


def _line(a, b):
    (x0, y0), (x1, y1) = a, b
    n = max(abs(x1 - x0), abs(y1 - y0)) or 1
    return [(round(x0 + (x1 - x0) * i / n), round(y0 + (y1 - y0) * i / n)) for i in range(n + 1)]


def _arm(path, thick=True) -> dict[tuple[int, int], tuple[int, int, int]]:
    cells = {}
    points = [p for a, b in zip(path, path[1:]) for p in _line(a, b)]
    for x, y in points:
        cells[(x, y)] = BONE["l"]
        if thick and (x, y + 1) not in cells:
            cells[(x, y + 1)] = BONE["m"]
    cells[path[-1]] = BONE["W"]
    return cells


def _bow(tip_x, top, bottom, bulge, pull=None) -> dict[tuple[int, int], tuple[int, int, int]]:
    cells = {}
    mid, half = (top + bottom) / 2, (bottom - top) / 2
    for y in range(top, bottom + 1):
        x = tip_x + round(bulge * (1 - ((y - mid) / half) ** 2))
        cells[(x, y)] = WOOD["h"] if y < mid - 1 else WOOD["G"]
        cells[(x + 1, y)] = WOOD["g"] if abs(y - mid) <= 1 or y > mid else WOOD["G"]
    string = (_line((tip_x, top), pull) + _line(pull, (tip_x, bottom))) if pull else _line((tip_x, top), (tip_x, bottom))
    for p in string:
        cells.setdefault(p, STRING)
    return cells


def _arrow(tail, head) -> dict[tuple[int, int], tuple[int, int, int]]:
    cells = {p: ARROW["a"] for p in _line(tail, head)}
    cells[head] = ARROW["t"]
    cells[(head[0] + 1, head[1])] = ARROW["t"]
    cells[tail] = ARROW["f"]
    return cells


WEAPONS = {
    "bow": {
        "idle": lambda: (_arm([(2, 12), (2, 14), (1, 15)]), "body",
                         _bow(13, 8, 18, 3), _arm([(10, 12), (12, 13), (15, 13)])),
        "draw": lambda: (_arm([(2, 12), (6, 12), (10, 12)]), "body",
                         _bow(15, 7, 17, 3, pull=(10, 12)), _arrow((9, 12), (20, 12)),
                         _arm([(10, 12), (13, 12), (17, 12)])),
        "release": lambda: (_arm([(2, 12), (5, 11), (8, 11)]), "body",
                            _bow(15, 7, 17, 3), _arm([(10, 12), (13, 12), (17, 12)])),
    },
}
STANCES = {"draw": "draw", "release": "release"}


def _stamp(grid: dict, cells: dict) -> None:
    for x, y in cells:
        for n in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
            if n not in cells:
                grid[n] = INK
    grid.update(cells)


def _body(legs: str, bob: int) -> dict[tuple[int, int], tuple[int, int, int]]:
    cells = {}
    for y, row in enumerate(BODY + LEGS[legs]):
        lift = bob if y < len(BODY) - 4 else 0
        for x, c in enumerate(row):
            if c != ".":
                cells[(x, y + lift)] = BONE[c]
    return cells


@lru_cache(maxsize=None)
def _skeleton(weapon: str, pose: str, legs: str, bob: int) -> tuple:
    grid: dict[tuple[int, int], tuple[int, int, int]] = {}
    for layer in WEAPONS[weapon][pose]():
        _stamp(grid, _body(legs, bob) if layer == "body" else layer)
    return tuple(((x - ORIGIN[0], y - ORIGIN[1]), c) for (x, y), c in grid.items())


def skeleton(weapon: str, stride: int, stance: str) -> Pixels:
    pose = STANCES.get(stance, "idle")
    legs = f"walk{stride}" if stance in ("walk", "run") else "stand"
    bob = 1 if stance == "rest" else 0
    return dict(_skeleton(weapon, pose, legs, bob))


def archer(stride: int, stance: str) -> Pixels:
    return skeleton("bow", stride, stance)
