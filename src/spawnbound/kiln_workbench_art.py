from functools import lru_cache
from math import asin, cos, sin, sqrt

import pygame

CLAY = [(104, 58, 52), (128, 76, 66), (152, 94, 80), (174, 112, 94), (196, 132, 110), (220, 160, 134)]
OUTLINE = (92, 52, 46)
HOLE = (46, 30, 30)
HOLE_WALL = (82, 50, 44)
KILN_SIZE = (29, 52)
CX = 14
K = .36
LIGHT = (-.66, .55, .5)
PROFILE = ((0, 4.6), (5, 5.0), (11, 6.9), (18, 8.8), (25, 10.5), (31, 11.6), (36, 11.8), (39.5, 11.2), (42, 10.2))
COURSES = (0, 4.5, 11, 18, 25, 32, 38.5)
BOTTOM = 42.0
TOP = 4.0
KILN_FOOT = (CX, round(TOP + BOTTOM))


def radius(t):
    for (t0, r0), (t1, r1) in zip(PROFILE, PROFILE[1:]):
        if t <= t1:
            f = (t - t0) / (t1 - t0)
            f = f * f * (3 - 2 * f)
            return r0 + (r1 - r0) * f
    return PROFILE[-1][1]


def tone(t, theta):
    nx, ny, nz = sin(theta), (radius(t + .5) - radius(t - .5)) * 1.1, cos(theta)
    n = sqrt(nx * nx + ny * ny + nz * nz)
    lx, ly, lz = LIGHT
    l = sqrt(lx * lx + ly * ly + lz * lz)
    b = (nx * lx + ny * ly + nz * lz) / (n * l)
    return 1 if b < -.12 else 2 if b < .18 else 3 if b < .5 else 4


def course_of(t):
    return max(i for i, c in enumerate(COURSES) if t >= c)


def _shell(w, h):
    cells = {}
    t = 0.0
    while t <= BOTTOM:
        r = radius(t)
        for i in range(-int(r * 8), int(r * 8) + 1):
            u = i / (r * 8)
            theta = asin(max(-1., min(1., u)))
            x, y = round(CX + r * u), round(TOP + t + K * r * cos(theta))
            if 0 <= x < w and 0 <= y < h:
                cells[x, y] = (t, theta, r)
        t += .1
    return cells


def _arch(x, y, mx, spring, bottom):
    dx, dy = x - mx, y - spring
    inner = sqrt(dx * dx + (dy * .78) ** 2) if dy < 0 else abs(dx)
    outer = sqrt(dx * dx + (dy * .72) ** 2) if dy < 0 else sqrt(dx * dx + (dy * .34) ** 2)
    if y > bottom + 1:
        return None, outer
    if inner < 3.4 and y <= bottom:
        return "in", inner
    if outer < 6.2:
        return "lip", outer
    return None, outer


@lru_cache(maxsize=2)
def kiln(right: bool = False) -> pygame.Surface:
    side = 1 if right else -1
    w, h = KILN_SIZE
    cells = _shell(w, h)
    image = pygame.Surface((w, h), pygame.SRCALPHA)
    grid = {}
    for (x, y), (t, theta, r) in cells.items():
        c = course_of(t)
        local = t - COURSES[c]
        size = (COURSES[c + 1] if c + 1 < len(COURSES) else BOTTOM) - COURSES[c]
        level = tone(t, theta)
        if c and local < .8:
            level -= 1
        elif c and local < 1.8 and level >= 2:
            level += 1
        elif local > size - 1.0:
            level -= 1
        if t > BOTTOM - 1.6:
            level = min(level, 1)
        brick = int((theta * r + (c % 2) * 3.4 + 60) / (6.8 if c > 1 else 5.6))
        grid[x, y] = (c, brick, max(0, min(5, level)))
    for (x, y), (c, brick, level) in grid.items():
        left = grid.get((x - 1, y))
        t, theta, r = cells[x, y]
        if left and left[0] == c and left[1] != brick and abs(theta) < 1.05 and t - COURSES[c] >= .8:
            level = max(0, level - 1)
        r0, g0, b0 = CLAY[level]
        shift = ((brick * 7 + c * 3) % 5 - 2) * 2
        image.set_at((x, y), (r0 + shift, g0 + shift // 2, b0))
    mx, spring, bottom = CX + 8 * side, 33, 44
    for x in range(w):
        for y in range(24, h):
            kind, d = _arch(x, y, mx, spring, bottom)
            if kind == "in":
                floor = y >= bottom - 1
                far = (x - mx) * side < 0 and y > spring
                image.set_at((x, y), HOLE_WALL if floor or (far and d > 2.2) else HOLE)
            elif kind == "lip":
                if not image.get_at((x, y)).a and y > bottom - 3:
                    continue
                dx, dy = x - mx, y - spring
                n = sqrt(dx * dx + min(dy, 0) ** 2) or 1
                b = (-dx * .66 - min(dy, 0) * .75) / n
                level = 5 if b > .45 else 4 if b > -.05 else 3 if b > -.55 else 2
                if d < 4.2 and (dx * side > 0 or dy > 0):
                    level = min(level, 2)
                if d > 5.4:
                    level = max(1, level - 1)
                image.set_at((x, y), CLAY[level])
    for x in range(w):
        for y in range(24, h):
            kind, d = _arch(x, y, mx, spring, bottom)
            if kind is None and 6.2 <= d < 7.2 and y <= bottom and image.get_at((x, y)).a:
                away = (x - mx) > 0 or y > spring
                image.set_at((x, y), CLAY[0] if away else CLAY[1])
    for dx, dy in ((-2, 2), (1, 3), (3, 1)):
        image.set_at((mx + dx * side, bottom + dy - 1), CLAY[0])
    vx = CX - 7 * side
    for dx in (-1, 0, 1):
        image.set_at((vx + dx, 40), CLAY[1])
        image.set_at((vx + dx, 41), HOLE)
    for dx in (-2, -1, 0, 1):
        image.set_at((vx + dx, 42), HOLE)
    for dx in (-1, 0):
        image.set_at((vx + dx, 43), CLAY[4])
    rim = pygame.Rect(0, 0, 12, 7)
    rim.center = (CX, round(TOP))
    pygame.draw.ellipse(image, CLAY[2], rim.move(0, 2))
    pygame.draw.ellipse(image, CLAY[3], rim.move(0, 1))
    pygame.draw.ellipse(image, CLAY[5], rim)
    pygame.draw.ellipse(image, CLAY[4], pygame.Rect(rim.x + 6, rim.y + 2, 6, 4))
    ty = round(TOP)
    for dx in range(-2, 3):
        image.set_at((CX + dx, ty - 1), HOLE_WALL)
    for dx in range(-3, 4):
        image.set_at((CX + dx, ty), HOLE)
    for dx in range(-2, 3):
        image.set_at((CX + dx, ty + 1), HOLE)
    mask = {(x, y) for x in range(w) for y in range(h) if image.get_at((x, y)).a}
    for x, y in mask:
        for n in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
            if n not in mask and 0 <= n[0] < w and 0 <= n[1] < h:
                image.set_at(n, OUTLINE)
    return image


@lru_cache(maxsize=8)
def placed_kiln(right: bool, scale: float = 1.) -> tuple[pygame.Surface, tuple[int, int]]:
    image = kiln(right)
    if scale != 1:
        image = pygame.transform.scale(image, (round(image.get_width() * scale), round(image.get_height() * scale)))
    return image, (round(KILN_FOOT[0] * scale), round(KILN_FOOT[1] * scale))


WOOD = {"frame_hi": (228, 170, 146), "frame": (204, 140, 118), "frame_lo": (168, 106, 88),
        "panel": (160, 96, 78), "panel_hi": (176, 110, 90), "panel_lo": (124, 70, 58), "seam": (132, 78, 64),
        "left": (150, 90, 72), "left_lo": (124, 72, 58), "right": (112, 64, 52), "right_lo": (92, 52, 44),
        "leg_l": (134, 80, 64), "leg_r": (100, 58, 48), "ink": (78, 44, 40)}
IRON = ((96, 92, 108), (150, 146, 162), (198, 196, 210), (226, 224, 236))
TOOL = ((176, 150, 132), (236, 216, 196), (252, 244, 232))
BENCH_SIZE = (34, 28)
APEX = (17, 1)
BENCH_FOOT = (17, 16)
THICK = 3
LEG = 4


def _grid(x, y):
    sx, sy = x - APEX[0], y - APEX[1]
    return (sx / 16 + sy / 8) / 2, (sy / 8 - sx / 16) / 2


@lru_cache(maxsize=2)
def workbench(right: bool = False) -> pygame.Surface:
    w, h = BENCH_SIZE
    image = pygame.Surface((w, h), pygame.SRCALPHA)
    top = {}
    for y in range(h):
        for x in range(w):
            gx, gy = _grid(x + .5, y + .5)
            if 0 <= gx <= 1 and 0 <= gy <= 1:
                top[x, y] = (gx, gy)
    low = {}
    for (x, y) in top:
        low[x] = max(low.get(x, -1), y)
    for cx, cy in ((3, 9), (30, 9), (17, 17)):
        for x in range(cx - 2, cx + 2):
            for y in range(cy + THICK, cy + THICK + LEG + 1):
                image.set_at((x, y), WOOD["leg_l"] if x < cx else WOOD["leg_r"])
        image.set_at((cx - 2, cy + THICK + LEG), WOOD["left_lo"])
    for x, y in low.items():
        face = "left" if x < 17 else "right"
        for dy in range(1, THICK + 1):
            image.set_at((x, y + dy), WOOD[face] if dy < THICK else WOOD[face + "_lo"])
    for (x, y), (gx, gy) in top.items():
        edge = min(gx, gy, 1 - gx, 1 - gy)
        far = min(gx, gy) <= min(1 - gx, 1 - gy)
        if edge < .16:
            color = WOOD["frame_hi"] if far and edge < .08 else WOOD["frame_lo"] if not far and edge < .06 else WOOD["frame"]
        elif edge < .22:
            color = WOOD["panel_lo"] if far else WOOD["panel_hi"]
        else:
            along = (gy if right else gx - .02) * 3
            color = WOOD["seam"] if along % 1 < .1 else WOOD["panel"]
        image.set_at((x, y), color)
    for cx, cy in ((17, 2), (2, 9), (31, 9), (17, 16)):
        for dx, dy, c in ((-1, -1, 2), (0, -1, 2), (1, -1, 1), (-2, 0, 2), (-1, 0, 3), (0, 0, 2), (1, 0, 1),
                          (2, 0, 1), (-1, 1, 1), (0, 1, 1), (1, 1, 0), (-2, 1, 1), (2, 1, 0), (0, 2, 0),
                          (-1, 2, 0), (1, 2, 0)):
            if 0 <= cx + dx < w:
                image.set_at((cx + dx, cy + dy), IRON[c])
    def put(x, y, c):
        image.set_at((w - 1 - x if right else x, y), c)
    handle = ((10, 13), (11, 13), (12, 12), (13, 12), (14, 11), (15, 11), (16, 10), (17, 10))
    for x, y in handle:
        put(x, y + 2, WOOD["panel_lo"])
    for x, y in handle:
        put(x, y, TOOL[2])
        put(x, y + 1, TOOL[1])
    put(10, 14, TOOL[0])
    put(11, 14, TOOL[0])
    head = ((17, 6, 3), (18, 6, 3), (19, 6, 2), (16, 7, 3), (17, 7, 2), (18, 7, 2), (19, 7, 2), (20, 7, 1),
            (16, 8, 2), (17, 8, 1), (18, 8, 1), (19, 8, 1), (20, 8, 1), (21, 8, 0), (17, 9, 0), (18, 9, 0),
            (19, 9, 0), (20, 9, 0), (21, 9, 0))
    for x, y, c in head:
        put(x, y, IRON[c])
    for x in range(18, 23):
        put(x, 10, WOOD["panel_lo"])
    mask = {(x, y) for x in range(w) for y in range(h) if image.get_at((x, y)).a}
    for x, y in mask:
        for n in ((x + 1, y), (x - 1, y), (x, y + 1), (x, y - 1)):
            if n not in mask and 0 <= n[0] < w and 0 <= n[1] < h:
                image.set_at(n, WOOD["ink"])
    return image


@lru_cache(maxsize=8)
def placed_workbench(right: bool, scale: float = 1.) -> tuple[pygame.Surface, tuple[int, int]]:
    image = workbench(right)
    if scale != 1:
        image = pygame.transform.scale(image, (round(image.get_width() * scale), round(image.get_height() * scale)))
    return image, (round(BENCH_FOOT[0] * scale), round(BENCH_FOOT[1] * scale))
