from __future__ import annotations

import math
from functools import lru_cache

import pygame

from spawnbound.domain.model import Biome, ObjectKind, SpaceKind, TileKind
from spawnbound.inventory_hud import CREAM, EDGE, GOLD, INK, MUTED

FOG = (37, 33, 38)
FOG_SPECK = (46, 41, 46)
FOG_EDGE = (58, 52, 56)
FOG_INDEX = bytes((0, 1, 2, 1)) + bytes(252)
DEEP_SEA = (31, 70, 110)
WATER = ((86, 150, 172), (62, 128, 160), (46, 106, 146))
RIVER = (88, 154, 176)
GROUND = {Biome.MEADOW: (138, 180, 96), Biome.FOREST: (112, 160, 84), Biome.DRY: (186, 172, 114)}
BRIDGE = (158, 118, 74)
TREES = {"palm_small": (72, 140, 66), "palm_medium": (72, 140, 66), "palm_tall": (72, 140, 66),
         "pine_dark": (44, 90, 62), "pine_light": (66, 116, 70), "broadleaf": (58, 110, 58),
         "autumn_gold": (186, 136, 58), "autumn_red": (162, 82, 60)}
OBJECTS = {ObjectKind.CACTUS: (67, 109, 80), ObjectKind.ROCK: (150, 150, 140), ObjectKind.FALLEN_LOG: (122, 94, 64),
           ObjectKind.BERRY_BUSH: (168, 92, 118), ObjectKind.CHEST: (196, 156, 82), ObjectKind.DOCK: (158, 118, 74)}
CELL = 4
PANEL = (21, 16, 15, 232)


def island_pixels(world, survey) -> bytes:
    side, m = survey.side, survey.margin
    n = side * side
    objects, rivers = world.objects, world.river_cells
    level = [-1] * n
    base = [None] * n
    for p, tile in world.tile_map.tiles.items():
        x, y = p.x + m, p.y + m
        if not (0 <= x < side and 0 <= y < side):
            continue
        i = y * side + x
        if tile.kind is TileKind.WATER:
            if tile.deep_water:
                base[i] = DEEP_SEA
            elif p in rivers:
                base[i] = RIVER
            continue
        level[i] = tile.elevation
        obj = objects.get(p)
        if obj is not None and obj.kind is ObjectKind.TREE:
            base[i] = TREES.get(obj.variant, TREES["broadleaf"])
        elif obj is not None and obj.kind in OBJECTS:
            base[i] = OBJECTS[obj.kind]
        elif tile.kind is TileKind.BRIDGE:
            base[i] = BRIDGE
        else:
            base[i] = GROUND.get(tile.biome, GROUND[Biome.MEADOW])
    depth = [0 if h >= 0 else len(WATER) for h in level]
    water = [i for i in range(n) if level[i] < 0]
    for ring in range(1, len(WATER)):
        for i in water:
            if depth[i] <= ring:
                continue
            x, y = i % side, i // side
            for j in (i - side - 1, i - side, i - side + 1, i - 1, i + 1, i + side - 1, i + side, i + side + 1):
                if 0 <= j < n and abs(j % side - x) <= 1 and depth[j] == ring - 1:
                    depth[i] = ring
                    break
    shaded = {}
    out = []
    for i in range(n):
        h = level[i]
        if h < 0:
            color = base[i] or WATER[depth[i] - 1]
            out.append(shaded.get(color) or shaded.setdefault(color, bytes(color)))
            continue
        above = level[i - side - 1] if i > side else -1
        rise = h - above if above >= 0 else 0
        key = (base[i], h, max(-2, min(1, rise)))
        pixel = shaded.get(key)
        if pixel is None:
            factor = (.84 + .045 * h) * {1: 1.12, 0: 1, -1: .8, -2: .66}[key[2]]
            pixel = shaded[key] = bytes(max(0, min(255, round(c * factor))) for c in base[i])
        out.append(pixel)
    return b"".join(out)


@lru_cache(maxsize=4)
def _speckle(side) -> bytes:
    return bytes(2 if ((x * 37 + y * 91) ^ (x * y * 7)) % 13 == 0 else 0
                 for y in range(side) for x in range(side))


class IslandMap:
    def __init__(self, font):
        self.font = font
        self._world = None
        self._survey = None
        self._base_key = None
        self._base: pygame.Surface | None = None
        self._image_key = None
        self._image: pygame.Surface | None = None

    def _text(self, surface, text, position, color=CREAM, scale=1):
        glyphs = self.font.render(text, pygame.Color(color)[:3], scale, shadow=(31, 24, 27))
        surface.blit(glyphs, position)

    def _top_down(self, world, survey):
        changes = world.tile_map.changes
        key = (world.tile_map.revision, len(changes), len(world.objects))
        if world is not self._world or key != self._base_key:
            side = survey.side
            self._base = pygame.image.frombytes(island_pixels(world, survey), (side, side), "RGB")
            self._world, self._base_key, self._image_key = world, key, None
        return self._base

    def image(self, world, survey) -> pygame.Surface:
        base = self._top_down(world, survey)
        key = (self._base_key, survey.version)
        if survey is self._survey and key == self._image_key:
            return self._image
        side = survey.side
        n = side * side
        cells = int.from_bytes(survey.cells, "big") | int.from_bytes(_speckle(side), "big")
        fog = pygame.image.frombytes(cells.to_bytes(n, "big").translate(FOG_INDEX), (side, side), "P")
        fog.set_palette([FOG, (0, 0, 0), FOG_SPECK] + [(0, 0, 0)] * 253)
        fog.set_colorkey(1)
        edge = fog.copy()
        edge.set_palette([FOG_EDGE, (0, 0, 0), FOG_EDGE] + [(0, 0, 0)] * 253)
        top = pygame.Surface((side, side), pygame.SRCALPHA)
        top.blit(base, (0, 0))
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            top.blit(edge, (dx, dy))
        top.blit(fog, (0, 0))
        big = pygame.transform.scale(top, (side * CELL, side * CELL))
        turned = pygame.transform.rotate(big, -45)
        w = turned.get_width()
        self._image = pygame.transform.scale(turned, (w, w // 2))
        self._survey, self._image_key = survey, key
        return self._image

    @staticmethod
    def project(survey, position, centre=(0, 0)):
        half = survey.side / 2
        a = (position.x + survey.margin + .5 - half) * CELL
        b = (position.y + survey.margin + .5 - half) * CELL
        c = math.sqrt(.5)
        return round(centre[0] + (a - b) * c), round(centre[1] + (a + b) * c * .5)

    def draw(self, screen, config, session) -> pygame.Rect:
        survey = session.survey
        if survey is None:
            return pygame.Rect(0, 0, 0, 0)
        world = session.spaces.worlds[survey.space_id]
        image = self.image(world, survey)
        panel = pygame.Rect(0, 0, image.get_width() + 28, image.get_height() + 76)
        panel.center = screen.get_rect().center
        pygame.draw.rect(screen, PANEL, panel, border_radius=8)
        pygame.draw.rect(screen, EDGE, panel, 2, border_radius=8)
        title = "Mapa da ilha"
        w, _ = self.font.size(title, 2)
        self._text(screen, title, (panel.centerx - w // 2, panel.top + 10), scale=2)
        centre = (panel.centerx, panel.top + 34 + image.get_height() // 2)
        screen.blit(image, image.get_rect(center=centre))

        def at(position):
            return self.project(survey, position, centre)

        for portal in world.portals.values():
            if survey.seen(portal.position):
                self._portal_icon(screen, at(portal.position), portal.target_kind)
        if world.camp is not None:
            self._camp_icon(screen, at(world.camp))
        here = session.player.position
        if session.world is not world:
            here = next((p.position for p in world.portals.values()
                         if p.target_space_id == session.world.space_id), None)
        if here is not None:
            self._player_icon(screen, at(here))

        footer = panel.bottom - 22
        x = panel.left + 16
        legend = (("Você", lambda p: self._player_icon(screen, p, pulse=False)),
                  ("Base", lambda p: self._camp_icon(screen, p)),
                  ("Caverna", lambda p: self._portal_icon(screen, p, SpaceKind.CAVE)))
        for label, icon in legend:
            icon((x + 5, footer + 4))
            self._text(screen, label, (x + 14, footer), MUTED)
            x += 24 + self.font.size(label)[0]
        share = f"Explorado {round(survey.explored_share * 100)}%   M fecha"
        w, _ = self.font.size(share)
        self._text(screen, share, (panel.right - 16 - w, footer), MUTED)
        return panel

    @staticmethod
    def _camp_icon(screen, point):
        x, y = point
        tent = [(x - 5, y + 3), (x, y - 5), (x + 5, y + 3)]
        pygame.draw.polygon(screen, GOLD, tent)
        pygame.draw.polygon(screen, INK, tent, 1)
        pygame.draw.line(screen, INK, (x, y - 1), (x, y + 3))

    @staticmethod
    def _portal_icon(screen, point, kind):
        x, y = point
        if kind is SpaceKind.INTERIOR:
            house = [(x - 4, y + 3), (x - 4, y - 1), (x, y - 5), (x + 4, y - 1), (x + 4, y + 3)]
            pygame.draw.polygon(screen, (164, 104, 70), house)
            pygame.draw.polygon(screen, INK, house, 1)
            return
        hill = [(x - 6, y + 3), (x - 2, y - 4), (x + 2, y - 4), (x + 6, y + 3)]
        pygame.draw.polygon(screen, (120, 116, 110), hill)
        pygame.draw.polygon(screen, INK, hill, 1)
        pygame.draw.rect(screen, INK, (x - 2, y - 1, 4, 4))

    @staticmethod
    def _player_icon(screen, point, pulse=True):
        x, y = point
        if pulse:
            ring = 5 + (pygame.time.get_ticks() // 120) % 4
            pygame.draw.ellipse(screen, CREAM, (x - ring, y - ring // 2, ring * 2, ring), 1)
        dot = [(x, y - 3), (x + 4, y), (x, y + 3), (x - 4, y)]
        pygame.draw.polygon(screen, CREAM, dot)
        pygame.draw.polygon(screen, INK, dot, 1)
