from __future__ import annotations

import json
import math
from functools import lru_cache

import pygame

from spawnbound.paths import resource_dir
from spawnbound.animation import MotionKind, PlayerPose
from spawnbound.domain.coordinates import WorldPos
from spawnbound.domain.fishing import BAR, FLIGHT_SECONDS, SWING_SECONDS, FishingRun
from spawnbound.item_icons import ROD_TIP, icon
from spawnbound.pplay_media import load_image
from spawnbound.pplay_ui import GameMeter, draw_on, show
from spawnbound.view import camera_origin, screen_center
from spawnbound.world_effects import Splash

_SPLASH = Splash()

ATLAS = resource_dir() / "assets" / "native_32" / "player"
INK = (38, 29, 44)
LINE = (232, 236, 228)
WATER_TOP, WATER_DEEP = (92, 182, 200), (28, 70, 116)
WOOD, WOOD_LIGHT, WOOD_DARK = (176, 112, 58), (226, 164, 96), (116, 66, 32)
GREEN, GREEN_EDGE = (112, 222, 84), (206, 255, 160)
METER_BACK = (42, 26, 18)
BOBBER_RED, BOBBER_WHITE = (226, 58, 42), (246, 244, 236)
RIPPLE = (214, 238, 236)
TEXT, SHADOW = (255, 247, 222), (38, 29, 44)

PANEL = (58, 250)
TRACK = pygame.Rect(9, 12, 22, 200)
METER = pygame.Rect(37, 12, 9, 200)
REEL = (20, 230)


@lru_cache(maxsize=1)
def _atlas() -> tuple[dict, dict]:
    spec = json.loads((ATLAS / "animation.json").read_text(encoding="utf-8"))
    sheet = load_image(ATLAS / spec["upgrades"]["fishing_rod"])
    width, height = spec["frame_size"]
    pivot = spec["pivot"]
    red = pygame.Color(ROD_TIP)
    tips = {}
    for row, direction in enumerate(spec["directions"]):
        for name in ("idle", "strike"):
            clip = spec["clips"][name]
            for index in range(clip["count"]):
                frame = sheet.subsurface(((clip["start"] + index) * width, row * height, width, height))
                mask = pygame.mask.from_threshold(frame, red, (2, 2, 2, 255))
                points = [(x, y) for box in mask.get_bounding_rects()
                          for x in range(box.left, box.right) for y in range(box.top, box.bottom)
                          if mask.get_at((x, y))]
                if points:
                    x, y = max(points, key=lambda p: (p[0] - pivot[0]) ** 2 + (p[1] - pivot[1]) ** 2)
                    tips[name, tuple(direction), index] = (x - pivot[0], y - pivot[1])
    return spec, tips


def rod_tip(pose: PlayerPose) -> tuple[int, int]:
    spec, tips = _atlas()
    name = "strike" if pose.motion is MotionKind.STRIKE else "idle"
    clip = spec["clips"][name]
    count = clip["count"]
    if name == "strike":
        index = min(count - 1, int(max(0., min(1., pose.progress)) * count))
    else:
        index = int(max(0., pose.elapsed) * clip["fps"]) % count
    facing = (pose.facing.x, pose.facing.y)
    for step in range(count):
        for near in (index + step, index - step):
            tip = tips.get((name, facing, near % count))
            if tip is not None:
                return tip
    return tips.get(("idle", facing, 0), (5, -9))


def draw(surface: pygame.Surface, config, font, session, run: FishingRun, pose: PlayerPose,
         visual: tuple[float, float, float], holding: bool, clock: float) -> pygame.Rect:
    origin = camera_origin(session, config, visual)
    zoom = config.camera_zoom
    feet = screen_center(WorldPos(*visual), origin, config)
    dx, dy = rod_tip(pose)
    tip = (feet[0] + dx * zoom, feet[1] + dy * zoom)
    bounds = pygame.Rect(feet[0], feet[1], 1, 1)
    water = None
    if run.bobber is not None and run.phase != "caught":
        lift = config.world_view_config.water_lift * zoom
        center = screen_center(session.world.surface_position(run.bobber), origin, config)
        water = (center[0], center[1] - lift)
        bounds.union_ip(_line_and_bobber(surface, run, tip, water, clock))
    splash = _SPLASH.follow(surface, run, water, origin, zoom)
    if splash is not None:
        bounds.union_ip(splash)
    if run.phase == "charging":
        bounds.union_ip(_power_bar(surface, feet, zoom, run.power))
    elif run.phase == "bite":
        bounds.union_ip(_alert(surface, feet, zoom, run.clock))
    elif run.phase == "minigame":
        bounds.union_ip(_panel(surface, feet, zoom, run, holding))
    elif run.phase == "caught":
        bounds.union_ip(_trophy(surface, font, feet, zoom, run))
    return bounds


def _line_and_bobber(surface, run, tip, water, clock) -> pygame.Rect:
    phase = run.phase
    if phase == "charging":
        return pygame.Rect(tip, (1, 1))
    if phase == "casting":
        flight = (run.clock - SWING_SECONDS) / FLIGHT_SECONDS
        if flight <= 0:
            return pygame.Rect(tip, (1, 1))
        t = min(1., flight)
        arc = math.sin(math.pi * t) * (34 + .25 * math.dist(tip, water))
        bobber = (tip[0] + (water[0] - tip[0]) * t, tip[1] + (water[1] - tip[1]) * t - arc)
        _curve(surface, tip, bobber, 0)
        _bobber(surface, bobber, under=False)
        return pygame.Rect(min(tip[0], bobber[0]) - 4, min(tip[1], bobber[1]) - 4,
                           abs(tip[0] - bobber[0]) + 9, abs(tip[1] - bobber[1]) + 9)
    sink = 0
    if phase == "waiting":
        bob = math.sin(clock * 3.1) * 1.2
        ripple_age = (clock % 1.8) / 1.8
    elif phase == "bite":
        bob, sink = 2 + math.sin(run.clock * 40), 1
        ripple_age = (run.clock * 2.5) % 1
    else:
        game = run.game
        bob = 1 + math.sin(game.elapsed * 23) * 1.5
        ripple_age = (game.elapsed * 1.7) % 1
        sink = 1
    _ripple(surface, water, ripple_age)
    if phase == "bite":
        _splash(surface, water, run.clock)
    bobber = (water[0], water[1] + bob)
    _curve(surface, tip, bobber, 16 if phase == "waiting" else 4 if phase == "bite" else 0)
    _bobber(surface, bobber, under=True, sink=sink)
    return pygame.Rect(min(tip[0], water[0]) - 14, min(tip[1], water[1]) - 14,
                       abs(tip[0] - water[0]) + 29, abs(tip[1] - water[1]) + 29)


def _curve(surface, start, end, sag) -> None:
    middle = ((start[0] + end[0]) / 2, (start[1] + end[1]) / 2 + sag)
    points = []
    for i in range(13):
        t = i / 12
        points.append(((1 - t) ** 2 * start[0] + 2 * (1 - t) * t * middle[0] + t * t * end[0],
                       (1 - t) ** 2 * start[1] + 2 * (1 - t) * t * middle[1] + t * t * end[1]))
    pygame.draw.lines(surface, LINE, False, points, 1)


def _bobber(surface, at, under: bool, sink: int = 0) -> None:
    x, y = round(at[0]), round(at[1])
    pygame.draw.circle(surface, INK, (x, y - 1 + sink), 4)
    pygame.draw.circle(surface, BOBBER_WHITE, (x, y - 1 + sink), 3)
    pygame.draw.rect(surface, BOBBER_RED, (x - 3, y - 4 + sink, 7, 3))
    surface.set_at((x - 1, y - 3 + sink), (255, 160, 140))
    if under:
        pygame.draw.ellipse(surface, WATER_TOP, (x - 5, y + 1, 11, 4))
        pygame.draw.ellipse(surface, RIPPLE, (x - 5, y + 1, 11, 4), 1)


def _ripple(surface, at, age: float) -> None:
    radius = 3 + age * 11
    layer = pygame.Surface((40, 20), pygame.SRCALPHA)
    alpha = round(200 * (1 - age))
    pygame.draw.ellipse(layer, (*RIPPLE, alpha), pygame.Rect(0, 0, radius * 2, radius).move(20 - radius, 10 - radius / 2 + 2), 1)
    surface.blit(layer, (at[0] - 20, at[1] - 10))


def _splash(surface, at, clock) -> None:
    for i, side in enumerate((-1, 0, 1)):
        t = (clock * 2.2 + i * .3) % 1
        x = at[0] + side * (3 + 6 * t)
        y = at[1] - 2 - 9 * math.sin(math.pi * t)
        pygame.draw.rect(surface, RIPPLE, (round(x), round(y), 2, 2))


class PowerMeter(GameMeter):
    def paint(self, screen) -> None:
        box = self.rect
        pygame.draw.rect(screen, INK, box)
        pygame.draw.rect(screen, WOOD_LIGHT, box.inflate(-2, -2))
        inner = box.inflate(-4, -4)
        pygame.draw.rect(screen, METER_BACK, inner)
        height = round(inner.height * self.fraction)
        if height:
            pygame.draw.rect(screen, _meter_colour(self.fraction), (inner.left, inner.bottom - height, inner.width, height))
            pygame.draw.line(screen, (255, 255, 255), (inner.left, inner.bottom - height),
                             (inner.right - 1, inner.bottom - height))


class CatchMeter(GameMeter):
    def paint(self, screen) -> None:
        meter = self.rect
        pygame.draw.rect(screen, INK, meter.inflate(4, 4))
        pygame.draw.rect(screen, METER_BACK, meter)
        filled = round(meter.height * self.fraction)
        if filled:
            pygame.draw.rect(screen, _meter_colour(self.fraction), (meter.left, meter.bottom - filled, meter.width, filled))
            pygame.draw.line(screen, (255, 255, 255), (meter.left, meter.bottom - filled),
                             (meter.right - 1, meter.bottom - filled))


def _power_bar(surface, feet, zoom, power) -> pygame.Rect:
    box = pygame.Rect(0, 0, 10, 48)
    box.midbottom = (feet[0] + round(16 * zoom), feet[1] - round(6 * zoom))
    draw_on(surface, PowerMeter(box, power))
    return box


def _alert(surface, feet, zoom, clock) -> pygame.Rect:
    pop = 1 + .35 * max(0., 1 - clock * 6)
    w, h = round(14 * pop), round(18 * pop)
    box = pygame.Rect(0, 0, w, h)
    box.midbottom = (feet[0], feet[1] - round(46 * zoom) - round(2 * math.sin(clock * 18)))
    pygame.draw.rect(surface, INK, box.inflate(2, 2), border_radius=4)
    pygame.draw.rect(surface, (255, 252, 236), box, border_radius=4)
    pygame.draw.polygon(surface, INK, (box.midbottom, (box.centerx - 3, box.bottom), (box.centerx, box.bottom + 4)))
    bar = pygame.Rect(0, 0, max(2, round(4 * pop)), round(9 * pop))
    bar.midtop = (box.centerx, box.top + round(3 * pop))
    pygame.draw.rect(surface, BOBBER_RED, bar)
    pygame.draw.rect(surface, BOBBER_RED, (bar.left, bar.bottom + round(2 * pop), bar.width, bar.width))
    return box.inflate(4, 8)


def _panel(surface, feet, zoom, run: FishingRun, holding: bool) -> pygame.Rect:
    game = run.game
    w, h = PANEL
    left = feet[0] + round(24 * zoom)
    if left + w > surface.get_width() - 6:
        left = feet[0] - round(24 * zoom) - w
    top = max(6, min(surface.get_height() - h - 6, feet[1] - h + round(40 * zoom)))
    if not game.inside:
        left += round(math.sin(game.elapsed * 61))
        top += round(math.cos(game.elapsed * 47))
    panel = pygame.Rect(left, top, w, h)
    pygame.draw.rect(surface, INK, panel.inflate(2, 2), border_radius=6)
    pygame.draw.rect(surface, WOOD_DARK, panel, border_radius=6)
    pygame.draw.rect(surface, WOOD, panel.inflate(-4, -4), border_radius=5)
    for y in range(panel.top + 8, panel.bottom - 6, 9):
        pygame.draw.line(surface, WOOD_DARK, (panel.left + 3, y), (panel.left + 6, y))
        pygame.draw.line(surface, WOOD_LIGHT, (panel.right - 6, y + 4), (panel.right - 4, y + 4))
    pygame.draw.line(surface, WOOD_LIGHT, (panel.left + 4, panel.top + 3), (panel.right - 5, panel.top + 3))
    track = TRACK.move(left, top)
    meter = METER.move(left, top)
    pygame.draw.rect(surface, INK, track.inflate(4, 4))
    for y in range(track.height):
        t = y / (track.height - 1)
        colour = [round(a + (b - a) * t) for a, b in zip(WATER_TOP, WATER_DEEP)]
        pygame.draw.line(surface, colour, (track.left, track.top + y), (track.right - 1, track.top + y))
    for i in range(4):
        t = (game.elapsed * (.22 + .07 * i) + i * .29) % 1
        bx = track.left + 4 + (i * 5) % (track.width - 7) + round(math.sin(game.elapsed * 3 + i))
        pygame.draw.circle(surface, (170, 222, 230), (bx, round(track.bottom - 3 - t * (track.height - 6))), 1)
    bar_h = round(BAR * track.height)
    bar_top = round(track.bottom - (game.bar + BAR) * track.height)
    bar = pygame.Rect(track.left, bar_top, track.width, bar_h).clip(track)
    layer = pygame.Surface(bar.size, pygame.SRCALPHA)
    layer.fill((*GREEN, 205 if game.inside else 150))
    surface.blit(layer, bar.topleft)
    pygame.draw.line(surface, GREEN_EDGE, bar.topleft, (bar.right - 1, bar.top), 2)
    pygame.draw.line(surface, GREEN_EDGE, (bar.left, bar.bottom - 1), (bar.right - 1, bar.bottom - 1), 2)
    fish = pygame.transform.flip(icon(run.fish.item, 1), math.sin(game.elapsed * 9) > .6, False)
    wiggle = round(math.sin(game.elapsed * 14) * (2 if not game.inside else 1))
    fy = track.bottom - game.fish_y * track.height
    show(surface, fish, center=(track.centerx + wiggle, round(fy)))
    draw_on(surface, CatchMeter(meter, game.progress))
    centre = (left + REEL[0], top + REEL[1])
    pygame.draw.circle(surface, INK, centre, 10)
    pygame.draw.circle(surface, (108, 116, 134), centre, 9)
    pygame.draw.circle(surface, (196, 206, 216), centre, 6)
    angle = game.elapsed * (14 if holding else 2.5)
    end = (centre[0] + math.cos(angle) * 8, centre[1] + math.sin(angle) * 8)
    pygame.draw.line(surface, INK, centre, end, 3)
    pygame.draw.circle(surface, WOOD_LIGHT, (round(end[0]), round(end[1])), 2)
    pygame.draw.circle(surface, INK, centre, 2)
    return panel.inflate(6, 6)


def _trophy(surface, font, feet, zoom, run: FishingRun) -> pygame.Rect:
    rise = min(1., run.clock / .25)
    image = icon(run.fish.item, 2)
    box = show(surface, image, midbottom=(feet[0], feet[1] - round((40 + 8 * rise) * zoom)))
    label = font.render(run.fish.name, TEXT, 2, shadow=SHADOW)
    tag = label.get_rect(midbottom=(box.centerx, box.top - 2))
    surface.blit(label, tag)
    return box.union(tag)


def _meter_colour(value: float) -> tuple[int, int, int]:
    red, yellow, green = (216, 58, 42), (232, 200, 58), (90, 216, 74)
    a, b, t = (red, yellow, value / .5) if value < .5 else (yellow, green, (value - .5) / .5)
    return tuple(round(x + (y - x) * t) for x, y in zip(a, b))
