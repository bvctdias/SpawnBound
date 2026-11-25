from __future__ import annotations

import math
import random

import pygame

from spawnbound.domain.model import ObjectKind

SHAKE_SECONDS = .24
FLASH_SECONDS = .06
TREE_LANDING_SECONDS = .30
TOPPLE_SECONDS = .42
BURST_SECONDS = .45

INK = (34, 24, 38, 235)
GLINT = (255, 255, 246, 120)
WOOD = ((246, 206, 132), (204, 138, 74), (110, 68, 48))
STONE = ((206, 218, 222), (138, 157, 176), (90, 106, 130))
CAVE_STONE = ((198, 178, 200), (147, 127, 160), (102, 86, 120))
SANDSTONE = ((247, 226, 182), (214, 176, 124), (150, 104, 70))
CACTUS = ((184, 236, 118), (82, 176, 90), (47, 124, 76))
COAL_GLINTS = ((120, 122, 150), (58, 56, 80), (22, 20, 32))
ORE_GLINTS = {"copper_ore": ((255, 216, 184), (232, 136, 96), (170, 80, 62)),
              "quartz_ore": ((255, 255, 255), (246, 200, 226), (226, 150, 192)),
              "coal_ore": COAL_GLINTS, "sandstone_coal": COAL_GLINTS}
PALM_LEAVES = ((112, 206, 80), (52, 124, 60))
LEAVES = {"palm_small": PALM_LEAVES, "palm_medium": PALM_LEAVES, "palm_tall": PALM_LEAVES,
          "pine_dark": ((122, 184, 78), (54, 137, 76)), "pine_light": ((165, 214, 106), (83, 169, 90)),
          "broadleaf": ((180, 218, 88), (101, 174, 68)), "autumn_gold": ((255, 215, 90), (240, 157, 48)),
          "autumn_red": ((255, 160, 90), (220, 85, 56))}
SPARK = ((255, 255, 236), (255, 214, 102))


def shake(t: float) -> float:
    if t >= SHAKE_SECONDS:
        return 0.
    return 2.2 * (1 - t / SHAKE_SECONDS) * math.cos(t / SHAKE_SECONDS * 3 * math.pi)


def materials(kind: ObjectKind | None, variant: str = "", cave: bool = False):
    if kind in (ObjectKind.TREE, ObjectKind.FALLEN_LOG, ObjectKind.CHEST, ObjectKind.BED, ObjectKind.TORCH,
                ObjectKind.BENCH, ObjectKind.COMPOSTER):
        return WOOD
    if kind is ObjectKind.CACTUS:
        return CACTUS
    if kind is None:
        return CAVE_STONE
    if variant.startswith("sandstone"):
        return SANDSTONE
    return CAVE_STONE if variant == "copper_ore" else STONE


def struck(body: pygame.Surface, foot: tuple[int, int], kind: ObjectKind, t: float,
           push: int, px: int) -> pygame.Surface:
    amount = shake(t) * push
    tall = kind in (ObjectKind.TREE, ObjectKind.CACTUS)
    rect = body.get_bounding_rect()
    if not tall:
        out = pygame.Surface(body.get_size(), pygame.SRCALPHA)
        out.blit(body, (round(amount / 2) * px, 0))
    else:
        out = pygame.Surface(body.get_size(), pygame.SRCALPHA)
        span = max(1, foot[1] - rect.top)
        band = 2 * px
        for top in range(rect.top, rect.bottom, band):
            lift = max(0., (foot[1] - top) / span)
            out.blit(body, (round(amount * lift) * px, top), (0, top, body.get_width(), band))
    if t < FLASH_SECONDS:
        flash = pygame.mask.from_surface(out).to_surface(setcolor=(255, 252, 238, 120),
                                                         unsetcolor=(0, 0, 0, 0))
        out.blit(flash, (0, 0))
    return out


def _interior(mask: pygame.mask.Mask, x: int, y: int, px: int) -> bool:
    w, h = mask.get_size()
    for nx, ny in ((x, y), (x + px, y), (x - px, y), (x, y + px), (x, y - px)):
        if not (0 <= nx < w and 0 <= ny < h) or not mask.get_at((nx, ny)):
            return False
    return True


def _crack(mask, rng, start, steps, drift, px):
    x, y = start
    path = []
    for _ in range(steps):
        if not _interior(mask, x, y, px):
            break
        path.append((x, y))
        y += px
        x += px * rng.choice((drift, drift, 0, -drift, drift))
    return path


def _paint_crack(overlay, mask, path, px):
    taken = set(path)
    for x, y in path:
        overlay.fill(INK, (x, y, px, px))
    for x, y in path:
        for gx, gy in ((x + px, y), (x, y + px)):
            if (gx, gy) not in taken and _interior(mask, gx, gy, px):
                overlay.fill(GLINT, (gx, gy, px, px))


def _rock_wear(body, foot, stage, salt, px):
    overlay = pygame.Surface(body.get_size(), pygame.SRCALPHA)
    mask = pygame.mask.from_surface(body, 127)
    rect = mask.get_bounding_rects()[0] if mask.count() else body.get_rect()
    rng = random.Random(salt)
    x = rect.left + round(rect.width * (.38 + .24 * rng.random()) / px) * px
    top = next((y for y in range(rect.top, rect.bottom, px) if _interior(mask, x, y, px)), rect.top)
    drift = rng.choice((-px, px))
    main = _crack(mask, rng, (x, top), 16, drift, px)
    branch = _crack(mask, rng, main[min(3, len(main) - 1)] if main else (x, top), 8, -drift, px)[1:]
    side_y = rect.top + round(rect.height * .45 / px) * px
    side_x = next((x for x in range(rect.left, rect.right, px) if _interior(mask, x, side_y, px)), rect.left)
    second = _crack(mask, rng, (side_x + px, side_y), 7, px, px)
    length = {1: 4, 2: 8, 3: 12, 4: 16}[min(stage, 4)]
    _paint_crack(overlay, mask, main[:length], px)
    if stage >= 2:
        _paint_crack(overlay, mask, branch[:2 + 2 * stage], px)
    if stage >= 3:
        _paint_crack(overlay, mask, second[:3 + 2 * (stage - 3)], px)
        fx = rect.left + round(rect.width * .66 / px) * px
        fy = next((y for y in range(rect.top, rect.bottom, px) if mask.get_at((fx, y))), rect.top)
        width, height = mask.get_size()
        for color, row in ((INK, fy + px), (GLINT, fy + 2 * px)):
            for x in range(fx, fx + 2 * px, px):
                if 0 <= x < width and 0 <= row < height and mask.get_at((x, row)):
                    overlay.fill(color, (x, row, px, px))
    return overlay


def _trunk_wear(body, foot, stage, salt, px):
    overlay = pygame.Surface(body.get_size(), pygame.SRCALPHA)
    mask = pygame.mask.from_surface(body, 127)
    fx, fy = foot
    y = fy - 9 * px
    w, h = mask.get_size()
    if not (0 <= y < h and 0 <= fx < w) or not mask.get_at((fx, y)):
        return _rock_wear(body, foot, stage, salt, px)
    left = fx
    while left - px >= 0 and mask.get_at((left - px, y)):
        left -= px
    right = fx
    while right + px < w and mask.get_at((right + px, y)):
        right += px
    width = (right - left) // px + 1
    depth = min({1: 2, 2: 3, 3: 4, 4: 5}[min(stage, 4)], max(1, width - 2))
    half = {1: 1, 2: 2, 3: 2, 4: 3}[min(stage, 4)]

    def paint(color, x, ry):
        if 0 <= x < w and 0 <= ry < h and mask.get_at((x, ry)):
            overlay.fill(color, (x, ry, px, px))

    for row in range(-half, half + 1):
        reach = max(1, depth - abs(row))
        ry = y + row * px
        for column in range(reach):
            paint((176, 112, 58) if column == reach - 1 else (246, 210, 140), left + column * px, ry)
        paint(INK, left + reach * px, ry)
    for row in (-half - 1, half + 1):
        for column in range(max(1, depth - abs(row) + 1)):
            paint(INK, left + column * px, y + row * px)
    if stage >= 3:
        tip = left + depth * px
        for k in range(1, 2 + stage):
            paint(INK, tip + (k // 2) * px, y - (half + k) * px)
    return overlay


def _slash_wear(body, foot, stage, salt, px, light, dark):
    overlay = pygame.Surface(body.get_size(), pygame.SRCALPHA)
    mask = pygame.mask.from_surface(body, 127)
    rect = mask.get_bounding_rects()[0] if mask.count() else body.get_rect()
    rng = random.Random(salt)
    spots = [(rect.left + round(rect.width * (.3 + .4 * rng.random()) / px) * px,
              rect.top + round(rect.height * (.35 + .4 * rng.random()) / px) * px) for _ in range(4)]
    for sx, sy in spots[:min(stage, 4)]:
        for k in range(4):
            x, y = sx + k * px, sy - k * px
            if _interior(mask, x, y, px) and _interior(mask, x, y + px, px):
                overlay.fill(dark, (x, y, px, px))
                overlay.fill(light, (x, y + px, px, px))
                if _interior(mask, x + px, y + px, px):
                    overlay.fill(light, (x + px, y + px, px, px))
    return overlay


def wear_overlay(body: pygame.Surface, foot: tuple[int, int], kind: ObjectKind,
                 stage: int, salt: int, px: int) -> pygame.Surface:
    if kind is ObjectKind.TREE:
        return _trunk_wear(body, foot, stage, salt, px)
    if kind is ObjectKind.CACTUS:
        return _slash_wear(body, foot, stage, salt, px, (224, 248, 168, 255), (29, 74, 62, 255))
    if kind is ObjectKind.FALLEN_LOG:
        return _slash_wear(body, foot, stage, salt, px, (246, 210, 140, 255), INK)
    return _rock_wear(body, foot, stage, salt, px)


def wall_cracks(screen: pygame.Surface, center: tuple[int, int], stage: int, px: int) -> None:
    x, y = center
    paths = (((-6, 7), (-4, 10), (-5, 13), (-2, 16), (-3, 19), (0, 23)),
             ((3, 9), (5, 12), (4, 15), (7, 18)),
             ((-11, 12), (-9, 15), (-10, 18), (-7, 21)))
    for path in paths[:min(3, max(1, stage))]:
        points = [(x + dx * px, y + dy * px) for dx, dy in path[:2 + stage]]
        if len(points) > 1:
            pygame.draw.lines(screen, INK[:3], False, points, px)
            pygame.draw.lines(screen, (176, 160, 184), False, [(a + px, b) for a, b in points], max(1, px // 2))


def _particles(seed: int, count: int):
    rng = random.Random(seed)
    return [(rng.uniform(.6, 1.), rng.uniform(.55, 1.), rng.random(), rng.randrange(3), rng.random() < .35)
            for _ in range(count)]


def draw_chips(screen, colors, t, origin, ground, push, px, seed, *, count=6, spread=1.):
    x0, y0 = origin
    for speed, rise, wobble, shade, big in _particles(seed, count):
        life = .32 + .2 * speed
        if t > life:
            continue
        vx = -push * (14 + 46 * speed * spread) * (1 if wobble > .2 else -.6)
        vy = -(36 + 60 * rise * spread)
        x = x0 + vx * t
        y = min(ground, y0 + vy * t + 210 * t * t)
        size = (2 if big else 1) * px
        screen.fill(colors[shade][:3], (round(x / px) * px, round(y / px) * px, size, size))


def draw_leaves(screen, colors, t, canopy, ground, px, seed, *, count=3, life=.55):
    cx, cy = canopy
    rng = random.Random(seed ^ 0x1EAF)
    for i in range(count):
        dx, phase, fall = rng.uniform(-13, 13), rng.uniform(0, 6.3), rng.uniform(22, 34)
        if t > life:
            return
        x = cx + dx * px + 3 * px * math.sin(t * 9 + phase)
        y = min(ground, cy + fall * t * px)
        color = colors[i % 2]
        screen.fill(color, (round(x / px) * px, round(y / px) * px, 2 * px, px))


def draw_spark(screen, t, point, px):
    if t >= .09:
        return
    x, y = point
    reach = 2 if t < .045 else 3
    rays = ((1, 0), (-1, 0), (0, 1), (0, -1)) if t < .045 else ((1, 1), (-1, -1), (1, -1), (-1, 1))
    screen.fill(SPARK[0], (x, y, px, px))
    for dx, dy in rays:
        for k in range(1, reach + 1):
            screen.fill(SPARK[0] if k == 1 else SPARK[1], (x + dx * k * px, y + dy * k * px, px, px))


def draw_twinkles(screen, colors, t, center, px, seed, *, count=4, life=.42):
    if t >= life:
        return
    rng = random.Random(seed ^ 0x51A7)
    cx, cy = center
    for i in range(count):
        dx, dy, delay = rng.uniform(-12, 12), rng.uniform(-18, 0), rng.uniform(0, .2)
        local = t - delay
        if not 0 <= local < .16:
            continue
        x, y = round(cx + dx * px), round(cy + dy * px - local * 18 * px)
        arm = 1 if local < .05 or local > .11 else 2
        color = colors[i % 2][:3]
        screen.fill(color, (x, y, px, px))
        for ax, ay in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            screen.fill(color, (x + ax * arm * px, y + ay * arm * px, px, px))


def burst_pieces(body: pygame.Surface, foot, t: float, push: int, px: int):
    rect = body.get_bounding_rect()
    if not rect.width or not rect.height:
        return []
    half_w = max(px, (rect.width // 2) // px * px)
    half_h = max(px, (rect.height // 2) // px * px)
    alpha = 255 if t < .22 else max(0, round(255 * (1 - (t - .22) / (BURST_SECONDS - .22))))
    pieces = []
    for col in (0, 1):
        for row in (0, 1):
            part = pygame.Rect(rect.left + col * half_w, rect.top + row * half_h,
                               half_w if col == 0 else rect.width - half_w,
                               half_h if row == 0 else rect.height - half_h)
            if not part.width or not part.height:
                continue
            image = body.subsurface(part).copy()
            image.set_alpha(alpha)
            side = -1 if col == 0 else 1
            vx = side * (22 + 10 * row) + push * 8
            vy = -(70 if row == 0 else 38)
            x = part.x - foot[0] + vx * t * px
            y = part.y - foot[1] + (vy * t + 260 * t * t) * px
            pieces.append((image, (round(x / px) * px, round(min(y, part.y - foot[1] + 6 * px) / px) * px)))
    return pieces
