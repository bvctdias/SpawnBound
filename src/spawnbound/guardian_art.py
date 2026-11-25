from __future__ import annotations

import math
from functools import lru_cache

import pygame

SIZE = (84, 100)
FOOT = (42, 96)
INK = (38, 29, 44)
STONE = ((62, 68, 88), (100, 109, 130), (146, 155, 174), (196, 203, 216))
MOSS = ((70, 108, 48), (128, 170, 72))
RUNE, RUNE_DIM = (127, 240, 255), (74, 112, 132)
EMBER, EMBER_LIGHT = (255, 132, 40), (255, 214, 110)
WARN, WARN_LIGHT = (232, 70, 46), (255, 196, 92)
DUST = ((178, 160, 132), (214, 200, 172))

POSES = {
    "idle": dict(sit=0, lean=0, front=(15, -22), back=(-15, -24)),
    "walk": dict(sit=1, lean=1, front=(16, -24), back=(-15, -22)),
    "sleep": dict(sit=12, lean=2, front=(17, -3), back=(-17, -3), dim=True),
    "punch_ready": dict(sit=2, lean=-4, front=(4, -80), back=(-8, -34)),
    "stuck": dict(sit=7, lean=7, front=(31, -2), back=(-12, -26), buried=True),
    "crouch": dict(sit=10, lean=0, front=(16, -70), back=(-12, -72)),
    "air": dict(sit=3, lean=0, front=(17, -73), back=(-13, -75), tucked=True),
    "landed": dict(sit=11, lean=3, front=(26, -2), back=(-22, -2)),
    "lift": dict(sit=3, lean=-1, front=(7, -74), back=(-7, -74), rock=True),
    "throw": dict(sit=1, lean=5, front=(32, -60), back=(-14, -24)),
}


def _canvas() -> pygame.Surface:
    return pygame.Surface(SIZE, pygame.SRCALPHA)


def _p(point) -> tuple[int, int]:
    return round(FOOT[0] + point[0]), round(FOOT[1] + point[1])


def _boulder(surface, center, rx, ry, shade=1) -> None:
    cx, cy = _p(center)
    pygame.draw.ellipse(surface, STONE[shade - 1], (cx - rx, cy - ry, 2 * rx, 2 * ry))
    pygame.draw.ellipse(surface, STONE[shade], (cx - rx, cy - ry, 2 * rx, 2 * ry - max(2, ry // 3)))
    pygame.draw.ellipse(surface, STONE[min(3, shade + 1)], (cx - rx + 2, cy - ry + 1, rx, max(2, ry // 2)))


def _arm(surface, shoulder, hand, shade) -> None:
    pygame.draw.line(surface, STONE[shade - 1], _p(shoulder), _p(hand), 11)
    pygame.draw.line(surface, STONE[shade], _p(shoulder), _p(hand), 6)
    for t, rx, ry in ((.38, 7, 6), (.72, 6, 5)):
        _boulder(surface, (shoulder[0] + (hand[0] - shoulder[0]) * t, shoulder[1] + (hand[1] - shoulder[1]) * t),
                 rx, ry, shade)


def _fist(surface, hand, shade, buried=False) -> None:
    x, y = _p(hand)
    rect = pygame.Rect(x - 8, y - 7, 17, 14)
    pygame.draw.rect(surface, STONE[shade - 1], rect, border_radius=4)
    pygame.draw.rect(surface, STONE[shade], rect.inflate(-2, -3).move(0, -1), border_radius=3)
    for k in range(3):
        surface.set_at((rect.left + 4 + 3 * k, rect.top + 2), STONE[min(3, shade + 1)])
    if buried:
        pygame.draw.rect(surface, (0, 0, 0, 0), (rect.left - 2, FOOT[1] + 1, rect.width + 4, 12))


def _draw(stance: str, frame: int) -> pygame.Surface:
    wrath = stance.endswith("+")
    base = stance.rstrip("+")
    pose = POSES.get(base, POSES["idle"])
    sit, lean = pose["sit"], pose["lean"]
    shake = (1 if frame else -1) if base in ("stuck", "punch_ready", "crouch") else 0
    lean += shake
    stride = (3 if frame else -3) if base == "walk" else 0
    surface = _canvas()
    hip = -20 + sit
    for side, shade, step in ((-1, 1, -stride), (1, 2, stride)):
        foot_y = -6 if pose.get("tucked") else 0
        top = (side * 8 + lean // 2, hip)
        bottom = (side * 9 + step, foot_y - (sit // 2 if base == "sleep" else 0))
        pygame.draw.line(surface, STONE[shade - 1], _p(top), _p(bottom), 10)
        pygame.draw.line(surface, STONE[shade], _p(top), _p(bottom), 6)
        fx, fy = _p(bottom)
        pygame.draw.rect(surface, STONE[shade - 1], (fx - 6, fy - 4, 13, 5), border_radius=2)
    front, back = pose["front"], pose["back"]
    shoulder_y = -48 + sit
    back_shoulder = (-12 + lean, shoulder_y)
    front_shoulder = (12 + lean, shoulder_y)
    _arm(surface, back_shoulder, back, 1)
    _fist(surface, back, 1, pose.get("buried", False) and base == "landed")
    _boulder(surface, back_shoulder, 9, 8, 1)
    _boulder(surface, (lean, -36 + sit), 18, 19, 2)
    _boulder(surface, (lean + 3, -30 + sit), 10, 9, 2)
    _boulder(surface, front_shoulder, 10, 9, 2)
    hx, hy = _p((lean + 5, -61 + sit + (4 if base == "sleep" else 0)))
    head = pygame.Rect(hx - 10, hy - 8, 21, 16)
    pygame.draw.rect(surface, STONE[0], head, border_radius=4)
    pygame.draw.rect(surface, STONE[1], head.inflate(-2, -3).move(0, -1), border_radius=3)
    pygame.draw.line(surface, STONE[2], (head.left + 2, head.top + 1), (head.right - 3, head.top + 1))
    pygame.draw.rect(surface, STONE[0], (head.left + 3, head.top + 5, head.width - 3, 2))
    eye = RUNE_DIM if pose.get("dim") else EMBER if wrath else RUNE
    if not pose.get("dim"):
        for ex in (head.right - 4, head.right - 9):
            pygame.draw.rect(surface, eye, (ex, head.top + 7, 2, 2))
            surface.set_at((ex, head.top + 7), EMBER_LIGHT if wrath else (230, 255, 255))
    else:
        for ex in (head.right - 5, head.right - 10):
            pygame.draw.line(surface, eye, (ex, head.top + 8), (ex + 2, head.top + 8))
    for mx, my, w in ((head.left + 2, head.top - 1, 8), (_p(front_shoulder)[0] - 6, _p(front_shoulder)[1] - 8, 9),
                      (_p(back_shoulder)[0] - 4, _p(back_shoulder)[1] - 8, 7)):
        pygame.draw.rect(surface, MOSS[0], (mx, my + 1, w, 2))
        pygame.draw.rect(surface, MOSS[1], (mx + 1, my, w - 3, 1))
    cx, cy = _p((lean + 1, -38 + sit))
    if wrath:
        for a, b in (((cx - 9, cy - 8), (cx - 2, cy)), ((cx - 2, cy), (cx - 6, cy + 9)),
                     ((cx - 2, cy), (cx + 8, cy + 3)), ((cx + 8, cy + 3), (cx + 11, cy - 6))):
            pygame.draw.line(surface, EMBER, a, b, 2)
            pygame.draw.line(surface, EMBER_LIGHT, a, b, 1)
    else:
        rune = RUNE_DIM if pose.get("dim") else RUNE
        pygame.draw.lines(surface, rune, False, ((cx - 4, cy - 5), (cx, cy - 1), (cx - 4, cy + 3), (cx, cy + 7)), 1)
        surface.set_at((cx + 4, cy + 1), rune)
    _arm(surface, front_shoulder, front, 2)
    _fist(surface, front, 2, pose.get("buried", False))
    if wrath:
        fx, fy = _p(front)
        pygame.draw.line(surface, EMBER, (fx - 3, fy - 3), (fx + 2, fy + 1), 1)
    if pose.get("rock"):
        _rock(surface, _p((0, -86)), 9)
    if base == "stuck":
        fx, _ = _p(front)
        for k, (dx, dy) in enumerate(((-9, -3), (8, -2), (-5, -6), (10, -6))):
            pygame.draw.rect(surface, STONE[1 + k % 2], (fx + dx, FOOT[1] + dy, 3, 3))
    return _outlined(surface)


def _rock(surface, center, radius) -> None:
    x, y = center
    pygame.draw.circle(surface, STONE[0], (x, y), radius)
    pygame.draw.circle(surface, STONE[1], (x - 1, y - 1), radius - 2)
    pygame.draw.circle(surface, STONE[2], (x - radius // 3, y - radius // 3), max(1, radius // 3))


def _outlined(surface: pygame.Surface) -> pygame.Surface:
    mask = pygame.mask.from_surface(surface)
    out = surface.copy()
    w, h = surface.get_size()
    for x in range(w):
        for y in range(h):
            if mask.get_at((x, y)):
                continue
            if any(0 <= x + dx < w and 0 <= y + dy < h and mask.get_at((x + dx, y + dy))
                   for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1))):
                out.set_at((x, y), INK)
    return out


@lru_cache(maxsize=64)
def _pixels(stance: str, frame: int) -> dict:
    surface = _draw(stance, frame)
    pixels = {}
    w, h = surface.get_size()
    for x in range(w):
        for y in range(h):
            colour = surface.get_at((x, y))
            if colour.a:
                pixels[x - FOOT[0], y - FOOT[1]] = tuple(colour)[:3]
    return pixels


def guardian(stride: int, stance: str) -> dict:
    return _pixels(stance, stride)


@lru_cache(maxsize=16)
def menhir_sprite(variant: str, scale: float) -> tuple[pygame.Surface, tuple[int, int]]:
    height = (30, 26, 34)[int(variant) % 3 if variant.isdigit() else 0]
    w = 14
    surface = pygame.Surface((w + 4, height + 6), pygame.SRCALPHA)
    body = [(2, height + 3), (3, 5), (6, 1), (w - 2, 3), (w + 1, height + 3)]
    pygame.draw.polygon(surface, STONE[0], body)
    pygame.draw.polygon(surface, STONE[1], [(4, height + 1), (5, 6), (7, 3), (w - 4, 5), (w - 2, height + 1)])
    pygame.draw.line(surface, STONE[2], (6, 5), (6, height - 2))
    rx, ry = w // 2 + 1, height // 2
    pygame.draw.lines(surface, RUNE_DIM, False, ((rx - 2, ry - 4), (rx + 1, ry - 1), (rx - 2, ry + 2), (rx + 1, ry + 5)), 1)
    pygame.draw.rect(surface, MOSS[0], (3, height, w - 1, 2))
    pygame.draw.rect(surface, MOSS[1], (4, height - 1, 4, 1))
    surface = _outlined(surface)
    foot = (surface.get_width() // 2, height + 3)
    if scale != 1:
        surface = pygame.transform.scale(surface, (round(surface.get_width() * scale), round(surface.get_height() * scale)))
        foot = (round(foot[0] * scale), round(foot[1] * scale))
    return surface, foot


def draw_mark(screen, center, tile_w, tile_h, urgency: float, clock: float) -> None:
    x, y = center
    pulse = .5 + .5 * math.sin(clock * (10 + 14 * urgency))
    points = [(x, y - tile_h // 2), (x + tile_w // 2, y), (x, y + tile_h // 2), (x - tile_w // 2, y)]
    layer = pygame.Surface((tile_w + 2, tile_h + 2), pygame.SRCALPHA)
    local = [(px - x + tile_w // 2 + 1, py - y + tile_h // 2 + 1) for px, py in points]
    pygame.draw.polygon(layer, (*WARN, round(70 + 110 * urgency * pulse)), local)
    pygame.draw.polygon(layer, (*WARN_LIGHT, round(140 + 115 * urgency)), local, 1)
    screen.blit(layer, (x - tile_w // 2 - 1, y - tile_h // 2 - 1))


def draw_ring(screen, center, semi_x: float, semi_y: float) -> None:
    x, y = center
    rect = pygame.Rect(0, 0, round(2 * semi_x), round(2 * semi_y))
    rect.center = (x, y)
    if rect.width < 4:
        return
    layer = pygame.Surface((rect.width + 8, rect.height + 8), pygame.SRCALPHA)
    inner = pygame.Rect(4, 4, rect.width, rect.height)
    pygame.draw.ellipse(layer, (*DUST[0], 170), inner, 5)
    pygame.draw.ellipse(layer, (*DUST[1], 230), inner, 2)
    pygame.draw.ellipse(layer, (255, 250, 230, 200), inner.inflate(-6, -3), 1)
    screen.blit(layer, (rect.left - 4, rect.top - 4))


def draw_falling_rock(screen, rock_at, shadow_at, progress: float, scale: float) -> None:
    sw, sh = round((6 + 14 * progress) * scale), round((3 + 6 * progress) * scale)
    layer = pygame.Surface((sw, sh), pygame.SRCALPHA)
    pygame.draw.ellipse(layer, (20, 16, 24, round(60 + 130 * progress)), layer.get_rect())
    screen.blit(layer, (shadow_at[0] - sw // 2, shadow_at[1] - sh // 2))
    radius = max(3, round(7 * scale))
    pygame.draw.circle(screen, INK, rock_at, radius + 1)
    _rock(screen, rock_at, radius)


def draw_dust(screen, center, age: float, scale: float, seed: int = 0) -> None:
    if age >= .6:
        return
    t = age / .6
    for k in range(9):
        angle = (k * 2.4 + seed) % (2 * math.pi)
        reach = (6 + 16 * t) * scale
        x = center[0] + math.cos(angle) * reach * 1.4
        y = center[1] + math.sin(angle) * reach * .5 - 10 * scale * math.sin(math.pi * t)
        size = max(1, round((3 - 2 * t) * scale))
        pygame.draw.rect(screen, DUST[k % 2], (round(x), round(y), size, size))


def draw_health(surface, font, hp: int, total: int, wrath: bool, name: str) -> pygame.Rect:
    from spawnbound.pplay_ui import draw_on
    width = 300
    box = pygame.Rect(0, 0, width, 12)
    box.midtop = (surface.get_width() // 2, 34)
    label = font.render(name.upper(), (255, 247, 222), 2, shadow=INK)
    tag = label.get_rect(midbottom=(box.centerx, box.top - 3))
    surface.blit(label, tag)
    draw_on(surface, _health_meter()(box, hp, total, wrath))
    return box.union(tag).inflate(6, 6)


@lru_cache(maxsize=1)
def _health_meter():
    from spawnbound.pplay_ui import GameMeter

    class HealthMeter(GameMeter):
        def __init__(self, box, hp, total, wrath) -> None:
            super().__init__(box, max(0, hp), total)
            self.wrath = wrath

        def paint(self, screen) -> None:
            box = self.rect
            pygame.draw.rect(screen, INK, box.inflate(4, 4))
            pygame.draw.rect(screen, (64, 40, 36), box)
            filled = round(box.width * self.fraction)
            if filled:
                colour = EMBER if self.wrath else (204, 62, 52)
                pygame.draw.rect(screen, colour, (box.left, box.top, filled, box.height))
                pygame.draw.line(screen, EMBER_LIGHT if self.wrath else (255, 150, 130), (box.left, box.top + 1),
                                 (box.left + filled - 1, box.top + 1))
            half = box.left + box.width // 2
            pygame.draw.line(screen, INK, (half, box.top), (half, box.bottom - 1))

    return HealthMeter
