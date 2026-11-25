from __future__ import annotations

import math

import pygame

from spawnbound.domain.model import TileKind
from spawnbound.inventory_hud import CREAM, EDGE, GOLD, MUTED

TITLE = "CARTA NÁUTICA"
HINT = "clique numa ilha para navegar   esc fecha"
HERE = "você está aqui"
UNKNOWN = "ilha desconhecida"
PANEL = (460, 310)
ENTRY = (132, 96)
REACH = 170
GAP = 48
SEA = (30, 66, 96, 240)
WAVE = (48, 92, 124)
ROUTE = (222, 204, 156)
LAND = (124, 166, 94)
SAND = (214, 196, 138)
SHORE = (26, 44, 52)
HAZE = (84, 118, 142)
HOVER = (64, 108, 140)
SHADOW = (12, 20, 28)


def layout(config, islands) -> tuple[pygame.Rect, dict[str, pygame.Rect]]:
    panel = pygame.Rect((0, 0), PANEL)
    panel.center = (config.virtual_width // 2, round(config.virtual_height * .47))
    points = {}
    for spec in islands:
        angle = math.radians(spec.bearing)
        x, y = (0., 0.) if spec.home else (math.cos(angle) * REACH, math.sin(angle) * REACH * .55)
        room = min((ENTRY[0] + GAP) / abs(x) if abs(x) > 1e-6 else math.inf,
                   (ENTRY[1] + GAP) / abs(y) if abs(y) > 1e-6 else math.inf)
        if 1 < room < math.inf:
            x, y = x * room, y * room
        points[spec.space_id] = (x, y)
    if not points:
        return panel, {}
    xs, ys = [x for x, _ in points.values()], [y for _, y in points.values()]
    mid = ((min(xs) + max(xs)) / 2, (min(ys) + max(ys)) / 2)
    centre = (panel.centerx, panel.top + 34 + (panel.height - 34 - 28) // 2)
    entries = {}
    for space_id, (x, y) in points.items():
        rect = pygame.Rect((0, 0), ENTRY)
        rect.center = (round(centre[0] + x - mid[0]), round(centre[1] + y - mid[1]))
        rect.clamp_ip(panel.inflate(-12, -64).move(0, 4))
        entries[space_id] = rect
    return panel, entries


def island_at(config, islands, point) -> str | None:
    if point is None:
        return None
    _, entries = layout(config, islands)
    from spawnbound.pplay_ui import pointed
    return next((space_id for space_id, rect in entries.items() if pointed(rect, point)), None)


def outline(world, width: int = 104) -> pygame.Surface:
    size = world.chunk_preview_size or 1 + max(max(p.x, p.y) for p in world.tile_map.tiles)
    land = set()
    for p, tile in world.tile_map.tiles.items():
        if tile.kind is not TileKind.WATER and 0 <= p.x < size and 0 <= p.y < size:
            land.add((p.x, p.y))
    pixels = bytearray(size * size * 4)
    for x, y in land:
        coast = any((x + dx, y + dy) not in land for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)))
        r, g, b = SAND if coast else LAND
        i = (y * size + x) * 4
        pixels[i:i + 4] = bytes((r, g, b, 255))
    top = pygame.image.frombytes(bytes(pixels), (size, size), "RGBA")
    side = max(1, round(width / math.sqrt(2)))
    turned = pygame.transform.rotate(pygame.transform.scale(top, (side, side)), -45)
    flat = pygame.transform.scale(turned, (turned.get_width(), max(1, turned.get_height() // 2)))
    mask = pygame.mask.from_surface(flat, 1)
    ring = pygame.Surface(flat.get_size(), pygame.SRCALPHA)
    shore = mask.to_surface(setcolor=(*SHORE, 255), unsetcolor=(0, 0, 0, 0))
    for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
        ring.blit(shore, (dx, dy))
    ring.blit(flat, (0, 0))
    return ring


class SeaChart:
    def __init__(self, font):
        self.font = font
        self._outlines: dict[str, tuple[object, int, pygame.Surface]] = {}

    def _outline(self, world) -> pygame.Surface:
        cached = self._outlines.get(world.space_id)
        revision = world.tile_map.revision
        if cached is None or cached[0] is not world or cached[1] != revision:
            cached = self._outlines[world.space_id] = (world, revision, outline(world))
        return cached[2]

    def _text(self, surface, text, centre, color=CREAM, scale=1) -> pygame.Rect:
        glyphs = self.font.render(text, pygame.Color(color)[:3], scale, shadow=SHADOW)
        place = glyphs.get_rect(center=centre)
        surface.blit(glyphs, place)
        return place

    def draw(self, surface, config, session, hover: str | None = None) -> pygame.Rect:
        panel, entries = layout(config, session.islands)
        plate = pygame.Surface(panel.size, pygame.SRCALPHA)
        pygame.draw.rect(plate, SEA, plate.get_rect(), border_radius=8)
        for row, y in enumerate(range(44, panel.height - 30, 20)):
            for x in range(14 + (row % 2) * 23, panel.width - 20, 46):
                pygame.draw.lines(plate, WAVE, False, ((x, y + 1), (x + 3, y - 1), (x + 6, y + 1), (x + 9, y - 1)))
        surface.blit(plate, panel)
        pygame.draw.rect(surface, EDGE, panel, 2, border_radius=8)
        self._text(surface, TITLE, (panel.centerx, panel.top + 18), scale=2)
        self._compass(surface, (panel.right - 26, panel.top + 26))
        here = session.island
        start = entries.get(here.space_id) if here is not None else None
        for spec in session.islands:
            rect = entries[spec.space_id]
            if start is not None and rect is not start:
                self._route(surface, start, rect)
        for spec in session.islands:
            rect = entries[spec.space_id]
            world = session.spaces.worlds.get(spec.space_id)
            picture = (rect.centerx, rect.top + 36)
            if spec is not here and hover == spec.space_id:
                glow = pygame.Surface(rect.size, pygame.SRCALPHA)
                pygame.draw.rect(glow, (*HOVER, 200), glow.get_rect(), border_radius=6)
                surface.blit(glow, rect)
                pygame.draw.rect(surface, GOLD, rect, 1, border_radius=6)
            if world is not None and spec.space_id in session.visited:
                image = self._outline(world)
                surface.blit(image, image.get_rect(center=picture))
                name = spec.name
            else:
                self._unknown(surface, picture)
                name = UNKNOWN
            self._text(surface, name, (rect.centerx, rect.bottom - 18))
            if spec is here:
                self._text(surface, HERE, (rect.centerx, rect.bottom - 7), GOLD)
                pygame.draw.circle(surface, GOLD, picture, 3)
                pygame.draw.circle(surface, SHADOW, picture, 3, 1)
        self._text(surface, HINT, (panel.centerx, panel.bottom - 14), MUTED)
        return panel

    def _route(self, surface, start, end):
        a, b = start.move(0, -8).center, end.move(0, -8).center
        length = math.dist(a, b)
        if length < 1:
            return
        ux, uy = (b[0] - a[0]) / length, (b[1] - a[1]) / length
        boxes = (start.inflate(4, 4), end.inflate(4, 4))
        d = 0.
        while d < length:
            p = (round(a[0] + ux * d), round(a[1] + uy * d))
            q = (round(a[0] + ux * min(length, d + 6)), round(a[1] + uy * min(length, d + 6)))
            if not any(box.collidepoint(p) or box.collidepoint(q) for box in boxes):
                pygame.draw.line(surface, ROUTE, p, q, 2)
            d += 11

    def _unknown(self, surface, centre):
        haze = pygame.Surface((84, 40), pygame.SRCALPHA)
        pygame.draw.ellipse(haze, (*HAZE, 150), haze.get_rect())
        pygame.draw.ellipse(haze, (*HAZE, 200), haze.get_rect().inflate(-26, -14))
        surface.blit(haze, haze.get_rect(center=centre))
        self._text(surface, "?", centre, CREAM, 3)

    def _compass(self, surface, centre):
        x, y = centre
        for dx, dy, color in ((0, -1, GOLD), (0, 1, MUTED), (-1, 0, MUTED), (1, 0, MUTED)):
            tip = (x + dx * 11, y + dy * 11)
            side = (dy * 3, dx * 3)
            pygame.draw.polygon(surface, color, (tip, (x + side[0], y + side[1]), (x - side[0], y - side[1])))
        self._text(surface, "N", (x, y - 18), GOLD)
