from __future__ import annotations

from functools import lru_cache
from math import sqrt

import pygame

LEVEL = 10
WATER_LIFT = 7
RAISE = 2
HALF = .27
START = -.38
PLANK = .2
AXES = {"x": ((16, 8), (-16, 8)), "y": ((-16, 8), (16, 8))}
WOOD = ((84, 54, 38), (122, 82, 52), (158, 112, 70), (192, 148, 96))
GREY = ((72, 66, 62), (102, 94, 84), (132, 122, 106), (160, 148, 128))
INK = (44, 28, 24)
FOAM = (206, 234, 240)
ROPE = (206, 178, 120)
STRIPE = (58, 124, 138)
CANVAS = (156, 92)
ORIGIN = (78, 30)


class _Pen:
    def __init__(self, surface, axis, water):
        self.surface = surface
        self.u, self.v = AXES[axis]
        self.water = water

    def at(self, t, s, h):
        return (round(ORIGIN[0] + t * self.u[0] + s * self.v[0]),
                round(ORIGIN[1] + t * self.u[1] + s * self.v[1] - h))

    def flat(self, color, t0, t1, s0, s1, h, h1=None):
        h1 = h if h1 is None else h1
        pygame.draw.polygon(self.surface, color, (self.at(t0, s0, h), self.at(t1, s0, h),
                                                  self.at(t1, s1, h1), self.at(t0, s1, h1)))

    def side(self, color, t0, t1, s, top, bottom):
        pygame.draw.polygon(self.surface, color, (self.at(t0, s, top), self.at(t1, s, top),
                                                  self.at(t1, s, bottom), self.at(t0, s, bottom)))

    def end(self, color, t, s0, s1, top, bottom):
        pygame.draw.polygon(self.surface, color, (self.at(t, s0, top), self.at(t, s1, top),
                                                  self.at(t, s1, bottom), self.at(t, s0, bottom)))

    def post(self, wood, t, s, top, foam):
        x, y = self.at(t, s, top)
        bottom = self.at(t, s, self.water)[1]
        for dx, shade in ((-1, 3), (0, 2), (1, 1)):
            pygame.draw.line(self.surface, wood[shade], (x + dx, y), (x + dx, bottom))
        self.surface.set_at((x, y), wood[3])
        for dx in (-4, -3, 3, 4):
            foam.set_at((x + dx, bottom), FOAM)
        for dx in (-2, 2):
            foam.set_at((x + dx, bottom + 1), FOAM)


def _beam(f):
    if f <= .45:
        return .24 * sqrt(max(0., 1 - ((.45 - f) / .62) ** 2))
    return .24 * sqrt(max(0., 1 - ((f - .45) / .55) ** 2))


def _boat(pen, foam, capsized):
    stern, bow, centre = 1.0, 2.25, .86
    fs = [k / 14 for k in range(15)]

    def point(f, side, h, narrow=1.):
        return pen.at(stern + (bow - stern) * f, centre + side * _beam(f) * narrow, h)

    if capsized:
        keel = [point(f, 0, pen.water + 4 * sqrt(_beam(f) / .24)) for f in fs]
        far = [point(f, -1, pen.water) for f in fs]
        near = [point(f, 1, pen.water) for f in fs]
        pygame.draw.polygon(pen.surface, GREY[2], far + keel[::-1])
        pygame.draw.polygon(pen.surface, GREY[1], near + keel[::-1])
        seam = [point(f, .55, pen.water + 2 * sqrt(_beam(f) / .24)) for f in fs[2:-2]]
        pygame.draw.lines(pen.surface, GREY[0], False, seam)
        pygame.draw.lines(pen.surface, GREY[3], False, keel[1:-1])
        rim = near
    else:
        def sheer(f):
            return pen.water + 4 + 2 * f * f
        far = [point(f, -1, sheer(f)) for f in fs]
        near = [point(f, 1, sheer(f)) for f in fs]
        pygame.draw.polygon(pen.surface, WOOD[1], far + near[::-1])
        pygame.draw.line(pen.surface, WOOD[3], point(.5, -1, sheer(.5) - 1, .85), point(.5, 1, sheer(.5) - 1, .85), 2)
        rim = [point(f, 1, pen.water, .86) for f in fs]
        pygame.draw.polygon(pen.surface, WOOD[2], near + rim[::-1])
        pygame.draw.lines(pen.surface, STRIPE, False, [(x, y + 1) for x, y in near[1:-3]])
        pygame.draw.lines(pen.surface, WOOD[3], False, far)
        pygame.draw.lines(pen.surface, WOOD[3], False, near)
    for x, y in rim[1:-1:3]:
        foam.set_at((x, y + 1), FOAM)
        foam.set_at((x + 1, y + 1), FOAM)
    return point(.96, 0, pen.water + 5)


def _deck(pen, wood, length, holes, loose):
    lit_side = pen.v[0] < 0
    lit_end = pen.u[0] < 0
    pen.side(wood[1] if lit_side else wood[0], START, length, HALF, RAISE, RAISE - 2)
    pen.end(wood[1] if lit_end else wood[0], length, -HALF, HALF, RAISE, RAISE - 2)
    for s0, s1 in ((-HALF, -HALF + .07), (HALF - .07, HALF)):
        pen.flat(wood[0], START, length, s0, s1, RAISE)
    count = round((length - START) / PLANK)
    for index in range(count):
        if index in holes:
            continue
        t0 = START + index * PLANK
        t1 = min(length, t0 + PLANK)
        tone = wood[3] if (index * 5 + 2) % 3 == 0 else wood[2]
        if index == loose:
            pen.flat(tone, t0 + .02, t1 + .04, -HALF - .04, HALF + .02, RAISE + 1, RAISE - 2)
            continue
        pen.flat(tone, t0, t1, -HALF, HALF, RAISE)
        if index + 1 < count and index + 1 not in holes and index + 1 != loose:
            pygame.draw.line(pen.surface, wood[1], pen.at(t1, -HALF, RAISE), pen.at(t1, HALF, RAISE))


def _outline(surface):
    mask = pygame.mask.from_surface(surface, 1)
    grown = mask.copy()
    for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        grown.draw(mask, (dx, dy))
    grown.erase(mask, (0, 0))
    ink = grown.to_surface(setcolor=(*INK, 255), unsetcolor=(0, 0, 0, 0))
    ink.blit(surface, (0, 0))
    return ink


def _draw(variant, elevation):
    restored = variant.startswith("restored")
    axis = variant.rsplit("-", 1)[1]
    water = min(-3, WATER_LIFT - elevation * LEVEL)
    body = pygame.Surface(CANVAS, pygame.SRCALPHA)
    foam = pygame.Surface(CANVAS, pygame.SRCALPHA)
    pen = _Pen(body, axis, water)
    wood = WOOD if restored else GREY
    if restored:
        length, holes, loose = 2.45, (), None
        posts = ((.75, 0), (1.5, 0), (2.32, 4))
    else:
        length, holes, loose = 1.65, (5, 8, 9), 6
        posts = ((.75, 0), (1.5, 0))
    for t, rise in posts:
        pen.post(wood, t, -HALF + .04, RAISE + rise, foam)
    _deck(pen, wood, length, holes, loose)
    for t, rise in posts:
        pen.post(wood, t, HALF - .04, RAISE + rise, foam)
    if restored:
        pen.flat(ROPE, 1.98, 2.16, -.12, .08, RAISE + 1)
        pen.flat(WOOD[1], 2.03, 2.11, -.06, .02, RAISE + 1)
    else:
        pen.post(wood, 2.28, -HALF + .04, water + 4, foam)
        pen.post(wood, 2.3, HALF - .04, water + 2, foam)
        pen.side(GREY[1], 2.0, 2.38, .62, water + 2, water)
        pen.flat(GREY[3], 2.0, 2.38, .44, .62, water + 2)
    bow = _boat(pen, foam, capsized=not restored)
    image = _outline(body)
    if restored:
        top = pen.at(2.32, HALF - .04, RAISE + 4)
        points = [(round(top[0] + (bow[0] - top[0]) * k / 8),
                   round(top[1] + (bow[1] - top[1]) * k / 8 + 2.5 * (1 - (2 * k / 8 - 1) ** 2))) for k in range(9)]
        pygame.draw.lines(image, ROPE, False, points)
    out = pygame.Surface(CANVAS, pygame.SRCALPHA)
    out.blit(foam, (0, 0))
    out.blit(image, (0, 0))
    box = out.get_bounding_rect()
    return out.subsurface(box).copy(), (ORIGIN[0] - box.x, ORIGIN[1] - box.y)


@lru_cache(maxsize=32)
def dock_sprite(variant: str, elevation: int, scale: float = 1.0):
    if scale != 1:
        image, (fx, fy) = dock_sprite(variant, elevation)
        return pygame.transform.scale_by(image, scale), (round(fx * scale), round(fy * scale))
    return _draw(variant, elevation)
