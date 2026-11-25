from __future__ import annotations

import math
from functools import lru_cache

Pixels = dict[tuple[int, int], tuple[int, int, int]]
INK = (43, 32, 44)

FUR = {"1": (96, 48, 42), "2": (146, 78, 50), "3": (190, 110, 62), "4": (222, 148, 88), "5": (244, 186, 122)}
DEER_COLORS = {"c": (246, 226, 190), "C": (214, 184, 144), "w": (252, 248, 236), "e": (29, 22, 33),
               "g": (255, 255, 255), "n": (52, 34, 38), "p": (238, 170, 152), "P": (204, 128, 118),
               "a": (248, 236, 204), "A": (212, 186, 142), "B": (152, 118, 86), "h": (64, 42, 44),
               "r": (206, 124, 70)}
LEG_TONES = {"L": "3", "l": "2", "F": "2", "f": "1"}
PAD = 3
GRID = (39, 28)
ORIGIN = (16, 27)
SHOULDER = 17

HEAD_UP = {
    0: "...............B...B.a...a",
    1: "...............B.B.B.a.a.a",
    2: "................BBB...aAa.",
    3: ".................B....A...",
    4: "...........rr....B...A....",
    5: "..........rppr...bbbbbb...",
    6: "...........rpPr.bbbbbbbb..",
    7: "............rrrbbbbbbbbb4.",
    8: "..............bbbbbgebbbb4",
    9: "..............bbbbbeebbbbbn",
    10: "...............bbbbbbbbb4cc",
    11: "...............2bbbbbbbbcC.",
    12: "...............2bbbbbb....",
    13: "...............2bbbbbw....",
    14: "...............2bbbbww....",
}
BODY = {
    13: "..w.......................",
    14: ".www..bbbbb...............",
    15: "..wwbbbbbbbbbbbbbbbbbbb...",
    16: "...wbbbbbbbbbbbbbbbbbbb...",
    17: "...bbbbbbbbbbbbbbbbbbbb...",
    18: "...bbbbbbbbbbbbbbbbbbb....",
    19: "....bbbbbbbbbbbbbbbbbb....",
    20: ".....bbbb2CccccC2bbbb.....",
}
HEAD_GRAZE = {
    15: "................bbbbbb.........",
    16: "................bbbbbbb.rr.....",
    17: ".................bbbbbbrppr....",
    18: "..................bbbbbbrpPr.a.a",
    19: "...................bbbbbbrrxBaa.",
    20: "....................bbbbbbxxBa..",
    21: ".....................bbbbxxxxx..",
    22: "......................bxxxxxx...",
    23: "......................xxxgexx...",
    24: ".......................xxeexx...",
    25: "........................xxxcc...",
    26: ".........................xCcn...",
}
HEAD_CHARGE = {
    12: "...................rr.........a.",
    13: "..................rppr......aa..",
    14: "................bbbrpPr...aa....",
    15: "................bbbbbrrxxaaaaaa.",
    16: "................bbbbbbxxxx......",
    17: "................bbbbbxxxxxBBBBB.",
    18: ".................bbbxgexxx..BB..",
    19: "..................bbxeexxx......",
    20: "....................xxxxx4......",
    21: ".....................xxxcc......",
    22: "......................xCcn......",
}
HEAD_DOWN = {
    10: "..............................a.",
    11: "..........................a..a..",
    12: "...........................a.a..",
    13: "....................rr.....aa.B.",
    14: "................bbbbrppr..a..B..",
    15: "................bbbbbrpPxxa.BB..",
    16: "................bbbbbbrrxxxBB...",
    17: "................bbbbbbbxxxxx....",
    18: ".................bbbbbxgexx.....",
    19: "..................bbbbxeexxx....",
    20: "...................bbbxxxxxx....",
    21: ".....................xxxxxcc....",
    22: "......................xxxCcn....",
}
LEGS = {
    "far_hind": ("F", ((7, 2), (9, 1), (9, 1), (9, 1), (10, 1), (10, 1), (10, 1))),
    "far_front": ("F", ((17, 2), (17, 1), (17, 1), (17, 1), (17, 1), (17, 1), (17, 1))),
    "near_hind": ("L", ((5, 2), (6, 2), (5, 2), (5, 1), (6, 1), (6, 1), (6, 1))),
    "near_front": ("L", ((19, 1), (19, 1), (20, 1), (20, 1), (20, 1), (20, 1), (20, 1))),
}
WALK = {"near_hind": -2, "far_hind": 2, "far_front": -2, "near_front": 2}
GALLOP = ({"near_hind": -4, "far_hind": -3, "far_front": 4, "near_front": 5},
          {"near_hind": 1, "far_hind": -1, "far_front": 1, "near_front": -1})
GATHERED = {"near_hind": ((5, 21, 2), (6, 22, 2), (7, 23, 1), (8, 24, 1), (8, 25, 1), (8, 26, 1), (8, 27, 1)),
            "far_hind": ((7, 21, 2), (9, 22, 1), (10, 23, 1), (11, 24, 1), (11, 25, 1), (11, 26, 1), (11, 27, 1))}
THROWN_BACK = {"near_hind": ((5, 21, 2), (4, 21, 1), (3, 21, 1), (2, 20, 1), (1, 20, 1), (0, 20, 1), (-1, 19, 1),
                             (-2, 19, 1)),
               "far_hind": ((7, 21, 2), (6, 22, 1), (5, 22, 1), (4, 22, 1), (3, 22, 1), (2, 21, 1), (1, 21, 1))}
PAWING = {"near_front": ((19, 21, 1), (19, 22, 1), (20, 23, 1), (21, 23, 1), (22, 24, 1))}


def _legs(swing=None, moved=None) -> dict[tuple[int, int], str]:
    out = {}
    for name in ("far_hind", "far_front", "near_hind", "near_front"):
        letter, columns = LEGS[name]
        if moved and name in moved:
            cells = moved[name]
        else:
            dx = (swing or {}).get(name, 0)
            cells = tuple((x + round(dx * max(0, i - 1) / 5), 21 + i, width) for i, (x, width) in enumerate(columns))
        for i, (x, y, width) in enumerate(cells):
            for k in range(width):
                out[x + k, y] = "h" if i == len(cells) - 1 else letter if i < 2 else letter.lower()
    return out


def _compose(head, legs, lift=0, rump=0.) -> tuple[str, ...]:
    rows = [["."] * GRID[0] for _ in range(GRID[1])]

    def put(x, y, c, raised=True):
        dy = round(max(0, SHOULDER - x) * rump) if raised else 0
        if 0 <= y - dy < GRID[1] and 0 <= x + PAD < GRID[0]:
            rows[y - dy][x + PAD] = c

    for (x, y), c in legs.items():
        put(x, y, c)
    for part, raised in ((BODY, True), (head, False)):
        for y, row in part.items():
            for x, c in enumerate(row):
                if c != ".":
                    put(x, y, c, raised)
    out = ["".join(r) for r in rows]
    return tuple(out[lift:] + ["." * GRID[0]] * lift)


DEER_POSES = {
    ("idle", 0): _compose(HEAD_UP, _legs()),
    ("walk", 0): _compose(HEAD_UP, _legs(WALK)),
    ("walk", 1): _compose(HEAD_UP, _legs({k: -v for k, v in WALK.items()})),
    ("rest", 0): _compose(HEAD_GRAZE, _legs()),
    ("kick_ready", 0): _compose(HEAD_UP, _legs(moved=GATHERED)),
    ("kick", 0): _compose(HEAD_DOWN, _legs(moved=THROWN_BACK), rump=.18),
    ("charge_ready", 0): _compose(HEAD_CHARGE, _legs(moved=PAWING)),
    ("charge", 0): _compose(HEAD_CHARGE, _legs(GALLOP[0])),
    ("charge", 1): _compose(HEAD_CHARGE, _legs(GALLOP[1]), lift=1),
    ("dazed", 0): _compose(HEAD_DOWN, _legs()),
}


def _fur_tone(grid, x, y) -> str:
    c = grid[x, y]
    up = down = 0
    while grid.get((x, y - up - 1)) == c:
        up += 1
    while grid.get((x, y + down + 1)) == c:
        down += 1
    run = up + down + 1
    if up == 0:
        return "5" if grid.get((x - 1, y)) != c else "4"
    if up == 1 and run >= 6:
        return "4"
    if down == 0 and run >= 3:
        return "2"
    if run >= 5 and up / (run - 1) >= .6:
        return "2"
    return "3"


def _shade(rows) -> Pixels:
    grid = {(x, y): c for y, row in enumerate(rows) for x, c in enumerate(row) if c != "."}
    out: Pixels = {}
    for (x, y), c in grid.items():
        if c in "bx":
            out[x, y] = FUR[_fur_tone(grid, x, y)]
        elif c in FUR:
            out[x, y] = FUR[c]
        elif c in LEG_TONES:
            out[x, y] = FUR[LEG_TONES[c]]
        else:
            out[x, y] = DEER_COLORS[c]
    result = dict(out)
    for x, y in grid:
        for n in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
            if n not in grid:
                result.setdefault(n, INK)
    for (x, y), c in grid.items():
        if c == "r":
            for n in ((x + 1, y), (x, y + 1), (x + 1, y + 1)):
                if grid.get(n) not in (None, "r", "p", "P"):
                    result[n] = INK
        elif c == "x" and grid.get((x - 1, y)) == "b":
            result[x - 1, y] = INK
    return result


@lru_cache(maxsize=None)
def _deer(stance: str, stride: int) -> tuple:
    rows = DEER_POSES.get((stance, stride)) or DEER_POSES.get((stance, 0)) or DEER_POSES["idle", 0]
    return tuple(((x - ORIGIN[0], y - ORIGIN[1]), c) for (x, y), c in _shade(rows).items())


def deer(stride: int, stance: str) -> Pixels:
    return dict(_deer(stance, stride if stance in ("walk", "charge") else 0))


GREEN = {"light": (128, 198, 82), "mid": (78, 160, 70), "dark": (44, 108, 62), "pattern": (30, 72, 52)}
BELLY = (246, 226, 148)
BELLY_EDGE = (214, 180, 104)
SNAKE_COLORS = {"g": GREEN["light"], "h": GREEN["mid"], "d": GREEN["dark"], "e": (255, 214, 70),
                "p": (20, 14, 24), "v": BELLY, "r": (186, 44, 66), "f": (252, 246, 232), "+": GREEN["mid"]}
TONGUE = (234, 52, 74)
RADIUS = 1.6
DIAMONDS = 5.0
HEADS = {
    "rest": ("..ggggg...",
             ".ghhhhhgg.",
             "+hhheephhh",
             "+hhhhhhhhd",
             ".vvvvvvdd."),
    "open": ("..gggggg...",
             ".ghhhhhhggg",
             "+hhheephhhh",
             "+hhhhhrrff.",
             "+hhhhrr....",
             "+hhhvrr.f..",
             ".vvvvvvvv.."),
    "dazed": ("..ggggg...",
              ".ghhhhhgg.",
              "+hhhddhhhh",
              "+hhhhhhhhd",
              ".vvvvvvdd."),
}
COIL = ((3, -6.8), (0, -8), (-4, -8.4), (-8, -7.6), (-10, -5.4), (-8.6, -3), (-4.5, -2), (0, -2.1), (3.6, -3))
SNAKE_POSES = {
    "idle": COIL + ((4.8, -5.6), (3.8, -8), (4.6, -10.2)),
    "alert": COIL + ((5, -5.6), (5.4, -9), (4.6, -12), (5.6, -14)),
    "strike_ready": COIL + ((5, -5.6), (6, -9), (3.6, -12), (2.2, -14.4), (4, -16.6)),
    "walk0": ((-14, -3.4), (-11, -2.2), (-7, -2.2), (-4, -3.6), (0, -3.6), (3, -2.2), (6, -2.6)),
    "walk1": ((-14, -2.2), (-11, -3.4), (-7, -3.6), (-4, -2.2), (0, -2.2), (3, -3.4), (6, -3.4)),
    "strike": ((-13, -2.2), (-9, -3.5), (-5, -2.2), (-1, -2.6), (3, -3.6), (8, -4.4)),
    "dazed": ((-13, -3), (-10, -3.8), (-6, -3.6), (-3, -2.2), (0, -2), (3, -2.4), (6, -2)),
}


def _catmull(points, steps=16):
    pts = (points[0],) + tuple(points) + (points[-1],)
    out = []
    for i in range(1, len(pts) - 2):
        p0, p1, p2, p3 = pts[i - 1], pts[i], pts[i + 1], pts[i + 2]
        for k in range(steps):
            t = k / steps
            out.append(tuple(.5 * (2 * p1[j] + (-p0[j] + p2[j]) * t + (2 * p0[j] - 5 * p1[j] + 4 * p2[j] - p3[j]) * t * t
                                   + (-p0[j] + 3 * p1[j] - 3 * p2[j] + p3[j]) * t ** 3) for j in (0, 1)))
    out.append(tuple(points[-1]))
    return out


def _body_color(side: float, along: float, at: float):
    if side >= .55:
        color = BELLY if side < .95 else BELLY_EDGE
    elif side <= -.6:
        color = GREEN["light"]
    else:
        color = GREEN["mid"]
    if at > .1:
        phase = along % DIAMONDS
        width = .75 * (1 - abs(phase - 1.5) / 1.5)
        if abs(side + .15) < width:
            color = GREEN["pattern"]
        elif abs(side + .15) < width + .35 and phase < 3 and side < .55:
            color = GREEN["dark"]
    return color


@lru_cache(maxsize=None)
def _snake(spine: tuple, head: str, tongue: bool) -> tuple:
    line = _catmull(spine)
    walked = [0.]
    for a, b in zip(line, line[1:]):
        walked.append(walked[-1] + math.dist(a, b))
    total = walked[-1]
    cells: dict[tuple[int, int], tuple[float, float, float, float]] = {}
    for i, ((cx, cy), along) in enumerate(zip(line, walked)):
        at = along / total
        a, b = line[max(0, i - 1)], line[min(len(line) - 1, i + 1)]
        length = math.dist(a, b) or 1.
        nx, ny = (a[1] - b[1]) / length, (b[0] - a[0]) / length
        if ny < -.3:
            nx, ny = -nx, -ny
        radius = RADIUS * min(1., .3 + at / .35)
        for y in range(math.floor(cy - radius), math.ceil(cy + radius) + 1):
            for x in range(math.floor(cx - radius), math.ceil(cx + radius) + 1):
                d = math.hypot(x - cx, y - cy)
                if d > radius:
                    continue
                before = cells.get((x, y))
                if before is None or at - before[0] >= .08 or d < before[2]:
                    side = ((x - cx) * nx + (y - cy) * ny) / max(radius, .5)
                    cells[x, y] = (at, side, d, along)
    out: Pixels = {(x, y): _body_color(side, along, at) for (x, y), (at, side, _, along) in cells.items()}
    rows = HEADS[head]
    jx, jy = next((x, y) for y, r in enumerate(rows) for x, c in enumerate(r) if c == "+")
    nx, ny = round(line[-1][0]), round(line[-1][1])
    head_cells = set()
    for y, row in enumerate(rows):
        for x, c in enumerate(row):
            if c != ".":
                cell = (nx + x - jx, ny + y - jy)
                out[cell] = SNAKE_COLORS[c]
                if c != "+":
                    head_cells.add(cell)
    result = dict(out)
    for x, y in out:
        for n in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
            if n not in out:
                result.setdefault(n, INK)
    for (x, y), (at, *_) in cells.items():
        if (x, y) not in head_cells and any(
                n in cells and n not in head_cells and cells[n][0] > at + .25
                for n in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1))):
            result[x, y] = INK
    for x, y in head_cells:
        if (x, y + 1) in cells and (x, y + 1) not in head_cells:
            result[x, y + 1] = INK
    if tongue:
        tx, ty = nx - jx + len(rows[3]) + 1, ny - jy + 3
        for p in ((tx, ty), (tx + 1, ty), (tx + 2, ty - 1), (tx + 2, ty + 1)):
            result[p] = TONGUE
    return tuple(result.items())


def snake(stride: int, stance: str) -> Pixels:
    if stance in ("walk", "run"):
        return dict(_snake(SNAKE_POSES[f"walk{stride}"], "rest", False))
    if stance in ("alert", "strike_ready"):
        return dict(_snake(SNAKE_POSES[stance], "rest", bool(stride)))
    if stance == "strike":
        return dict(_snake(SNAKE_POSES["strike"], "open", False))
    if stance == "dazed":
        return dict(_snake(SNAKE_POSES["dazed"], "dazed", False))
    return dict(_snake(SNAKE_POSES["idle"], "rest", False))


SPIDER_COLORS = {"1": (62, 36, 32), "2": (102, 60, 44), "3": (146, 92, 58), "4": (190, 128, 76),
                 "5": (224, 170, 104), "m": (236, 132, 48), "M": (255, 186, 92), "e": (255, 64, 56),
                 "g": (255, 230, 210), "f": (238, 220, 190), "L": (120, 72, 50), "l": (170, 110, 66),
                 "F": (70, 42, 36), "j": (236, 132, 48)}
SPIDER_EYE = SPIDER_COLORS["e"]
SPIDER_ORIGIN = (15, 15)
SPIDER_BODY = {
    2: "........344443",
    3: "......34455544.3",
    4: ".....3445mMm5443",
    5: "....334455m54443",
    6: "....3344444444433",
    7: "...23344m444m4433334e",
    8: "...2233344444333334eg4",
    9: "....222333333332234444",
    10: "....1122223322211.2f2f",
    11: "......11111111....f..f",
}
SPIDER_BITE_HEAD = {
    9: "....222333333332234444",
    10: "....1122223322211.2f22f",
    11: "......11111111...f....f",
}
NEAR_LEGS = (((21, 8), (26, 5), (30, 15)), ((20, 10), (23, 11), (24, 15)),
             ((16, 10), (14, 12), (13, 15)), ((14, 10), (8, 12), (5, 15)))
FAR_LEGS = (((19, 6), (22, 0), (27, 5)), ((13, 3), (14, 0), (18, 4)), ((9, 3), (5, 1), (0, 6)))
SPIDER_POSES = {
    "idle": ((0, 0), NEAR_LEGS, FAR_LEGS, None),
    "walk0": ((0, 0), (((21, 8), (27, 5), (31, 15)), ((20, 10), (22, 11), (22, 15)),
                       ((16, 10), (15, 12), (15, 15)), ((14, 10), (7, 12), (3, 15))),
              (((19, 6), (23, 1), (28, 5)), ((13, 3), (13, 0), (17, 4)), ((9, 3), (5, 1), (0, 6))), None),
    "walk1": ((0, -1), (((21, 8), (25, 5), (28, 15)), ((20, 10), (24, 11), (26, 15)),
                        ((16, 10), (13, 12), (11, 15)), ((14, 10), (9, 12), (6, 15))),
              (((19, 6), (21, 0), (26, 5)), ((13, 3), (15, 0), (19, 4)), ((9, 3), (6, 1), (1, 6))), None),
    "crouch": ((0, 2), (((21, 8), (26, 3), (30, 15)), ((20, 10), (23, 8), (25, 15)),
                        ((16, 10), (13, 9), (12, 15)), ((14, 10), (7, 9), (4, 15))),
               (((19, 6), (22, -1), (27, 5)), ((13, 3), (14, -1), (18, 4)), ((9, 3), (5, 0), (0, 6))), None),
    "leap": ((1, -4), (((21, 8), (27, 6), (32, 8)), ((20, 10), (25, 10), (29, 12)),
                       ((16, 10), (12, 11), (8, 12)), ((14, 10), (8, 10), (2, 11))),
             (((19, 6), (24, 2), (30, 5)), ((13, 3), (15, 0), (20, 3)), ((9, 3), (4, 3), (-1, 6))), None),
    "rear": ((0, -1), (((21, 8), (25, 1), (30, 0)), ((20, 10), (25, 7), (28, 9)),
                       ((16, 10), (14, 12), (13, 15)), ((14, 10), (8, 12), (5, 15))),
             (((19, 6), (21, -1), (26, -2)), ((13, 3), (14, 0), (18, 4)), ((9, 3), (5, 1), (0, 6))), "bite"),
    "bite": ((2, 0), (((21, 8), (27, 6), (30, 15)), ((20, 10), (24, 11), (25, 15)),
                      ((16, 10), (14, 12), (13, 15)), ((14, 10), (8, 12), (5, 15))),
             (((19, 6), (23, 0), (28, 5)), ((13, 3), (14, 0), (18, 4)), ((9, 3), (5, 1), (0, 6))), "bite"),
    "dazed": ((0, 3), (((21, 8), (26, 9), (31, 15)), ((20, 10), (24, 12), (26, 15)),
                       ((16, 10), (13, 13), (11, 15)), ((14, 10), (7, 13), (2, 15))),
              (((19, 6), (23, 4), (28, 9)), ((13, 3), (15, 1), (19, 5)), ((9, 3), (5, 3), (0, 9))), None),
}
SPIDER_STANCES = {"walk": "walk", "run": "walk", "charge_ready": "crouch", "charge": "leap",
                  "strike_ready": "rear", "strike": "bite", "dazed": "dazed"}


def _line(a, b):
    (x0, y0), (x1, y1) = a, b
    n = max(abs(x1 - x0), abs(y1 - y0)) or 1
    return [(round(x0 + (x1 - x0) * i / n), round(y0 + (y1 - y0) * i / n)) for i in range(n + 1)]


@lru_cache(maxsize=None)
def _spider(pose: str) -> tuple:
    (dx, dy), near, far, head = SPIDER_POSES[pose]
    grid: dict[tuple[int, int], str] = {}
    for attach, knee, foot in far:
        for x, y in _line(attach, knee)[1:] + _line(knee, foot)[1:]:
            grid[x + dx, y + dy] = "F"
    body = dict(SPIDER_BODY)
    if head == "bite":
        body.update(SPIDER_BITE_HEAD)
    for y, row in body.items():
        for x, c in enumerate(row):
            if c != ".":
                grid[x + dx, y + dy] = c
    for attach, knee, foot in near:
        a, k = (attach[0] + dx, attach[1] + dy), (knee[0] + dx, knee[1] + dy)
        for p in _line(a, k)[1:] + _line(k, foot)[1:]:
            if grid.get(p, "F") == "F":
                grid[p] = "j" if p == k else "l" if p[1] <= k[1] + 1 else "L"
    result = {p: SPIDER_COLORS[c] for p, c in grid.items()}
    for (x, y), c in grid.items():
        if c == "F":
            continue
        for n in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
            if n not in grid:
                result.setdefault(n, INK)
    return tuple(((x - SPIDER_ORIGIN[0], y - SPIDER_ORIGIN[1]), c) for (x, y), c in result.items())


def spider(stride: int, stance: str) -> Pixels:
    pose = SPIDER_STANCES.get(stance, "idle")
    if pose == "walk":
        pose = f"walk{stride}"
    return dict(_spider(pose))
