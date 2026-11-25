from __future__ import annotations

import math
from functools import lru_cache

import pygame

from spawnbound.domain.coordinates import GridPos
from spawnbound.domain.daylight import DayPhase
from spawnbound.domain.model import Biome, ObjectKind, SpaceKind, TileKind
from spawnbound.pplay_ui import show
from spawnbound.view import screen_center

RADIUS = 10
BLOCK = 16
PREFETCH = 8  # Blocos além do raio visível, preparados um por quadro.
LIMITS = {"butterfly": 4, "bee": 4, "firefly": 12, "frog": 3}
# O brilho dos vaga-lumes pode aparecer entre as folhas.
BEHIND_COVER = frozenset(("firefly",))
TALL = frozenset((ObjectKind.TREE, ObjectKind.ROCK, ObjectKind.FALLEN_LOG))
NEIGHBOURS = tuple(GridPos(dx, dy) for dx in (-1, 0, 1) for dy in (-1, 0, 1) if dx or dy)
CARDINAL = (GridPos(1, 0), GridPos(-1, 0), GridPos(0, 1), GridPos(0, -1))
WINGS = ((240, 236, 222), (236, 146, 58), (108, 152, 232), (242, 214, 96))
FROG_SCARE = 2.2


def _hash(x, y, seed):
    return ((x * 73856093) ^ (y * 19349663) ^ (seed * 83492791)) & 0xffffffff


def _clear_in_front(world, cell, z):
    tile_at, objects = world.tile_map.tile_at, world.objects
    for i in range(4):
        for j in range(4):
            if not (i or j):
                continue
            q = GridPos(cell.x + i, cell.y + j)
            obj = objects.get(q)
            if obj is not None and obj.kind in TALL and i + j <= 5:
                return False
            if q in world.portals and i + j <= 4:
                return False
            tile = tile_at(q)
            if tile is not None and tile.kind is not TileKind.WATER and (tile.elevation - z) * 10 > (i + j) * 8:
                return False
    return True


def block_candidates(world, bx, by):
    tile_at, objects, seed = world.tile_map.tile_at, world.objects, world.seed
    found = []
    for x in range(bx * BLOCK, bx * BLOCK + BLOCK):
        for y in range(by * BLOCK, by * BLOCK + BLOCK):
            roll = _hash(x, y, seed) >> 4
            q = GridPos(x, y)
            if roll % 3 and roll % 10 and (roll % 2 or q not in objects):
                continue
            tile = tile_at(q)
            if tile is None or tile.kind is not TileKind.GRASS:
                continue
            obj = objects.get(q)
            if obj is not None:
                if obj.kind is ObjectKind.BERRY_BUSH and roll % 2 == 0:
                    found.append(("bee", q, roll, None))
                continue
            water = next((d for d in CARDINAL if (w := tile_at(q + d)) is not None and w.kind is TileKind.WATER
                          and not w.deep_water and q + d not in world.sea_cells), None)
            if water is not None and roll % 3 == 0:
                found.append(("frog", q, roll, water))
            if roll % 3 == 0 and (tile.biome is Biome.FOREST or any(
                    (o := objects.get(q + d)) is not None and o.kind is ObjectKind.TREE for d in NEIGHBOURS)):
                found.append(("firefly", q, roll, None))
            if roll % 10 == 0 and tile.biome is not Biome.FOREST:
                found.append(("butterfly", q, roll, None))
    return found


def find_anchors(world, centre):
    return AmbientLife().anchors(world, centre)


@lru_cache(maxsize=16)
def _butterfly(color, open_wings, flip):
    art = pygame.Surface((9, 7), pygame.SRCALPHA)
    dark = tuple(round(c * .62) for c in color)
    if open_wings:
        for x in (0, 5):
            art.fill(color, (x, 0, 4, 3))
            art.fill(dark, (x + (1 if x == 0 else 0), 3, 3, 2))
        art.set_at((0, 0), (0, 0, 0, 0))
        art.set_at((8, 0), (0, 0, 0, 0))
    else:
        art.fill(color, (3, 0, 1, 4))
        art.fill(color, (5, 0, 1, 4))
        art.fill(dark, (3, 4, 1, 1))
        art.fill(dark, (5, 4, 1, 1))
    art.fill((44, 36, 34), (4, 1, 1, 5))
    return pygame.transform.flip(art, True, False) if flip else art


@lru_cache(maxsize=4)
def _bee(wing_up):
    art = pygame.Surface((4, 4), pygame.SRCALPHA)
    art.fill((240, 196, 58), (0, 2, 4, 2))
    art.fill((46, 36, 30), (2, 2, 1, 2))
    art.fill((228, 236, 240), (1, 0 if wing_up else 1, 2, 1))
    return art


@lru_cache(maxsize=8)
def _glow(level):
    art = pygame.Surface((11, 11))
    k = level / 3
    for radius, color in ((5, (26, 32, 8)), (3, (60, 76, 18)), (1, (140, 170, 50))):
        pygame.draw.circle(art, tuple(round(c * k) for c in color), (5, 5), radius)
    art.set_at((5, 5), (255, 255, 190))
    return art


@lru_cache(maxsize=8)
def _frog(hop, flip):
    art = pygame.Surface((7, 5), pygame.SRCALPHA)
    body, back, belly = (92, 152, 72), (60, 112, 56), (176, 196, 120)
    if hop:
        art.fill(body, (1, 0, 5, 3))
        art.fill(back, (2, 0, 3, 1))
        art.fill(body, (0, 3, 2, 1))
        art.fill(body, (5, 3, 2, 2))
    else:
        art.fill(body, (1, 1, 5, 3))
        art.fill(back, (2, 1, 3, 1))
        art.fill(belly, (2, 3, 3, 1))
        art.fill(body, (0, 3, 1, 2))
        art.fill(body, (6, 3, 1, 2))
    eye_y = 0 if hop else 1
    art.fill((236, 232, 200), (4, eye_y, 2, 1))
    art.set_at((5, eye_y), (24, 22, 20))
    framed = pygame.Surface((9, 7), pygame.SRCALPHA)
    edge = pygame.mask.from_surface(art).to_surface(setcolor=(30, 52, 34, 255), unsetcolor=(0, 0, 0, 0))
    for dx, dy in ((0, 1), (2, 1), (1, 0), (1, 2)):
        framed.blit(edge, (dx, dy))
    framed.blit(art, (1, 1))
    return pygame.transform.flip(framed, True, False) if flip else framed


class AmbientLife:
    def __init__(self):
        self._world = None  # Guardar o mundo evita reutilizar o id de uma ilha já descartada.
        self._seen = 0
        self._blocks: dict[tuple[int, int], list] = {}
        self._clear: dict[GridPos, bool] = {}
        self._cell = None
        self._anchors: dict = {}

    def _forget_changes(self, world):
        changes = world.tile_map.changes
        if world is not self._world:
            self._world, self._seen = world, len(changes)
            self._blocks.clear()
        elif len(changes) == self._seen:
            return
        for p in changes[self._seen:]:
            # Uma célula alterada também pode invalidar os blocos vizinhos.
            for dx in (-1, 0, 1):
                for dy in (-1, 0, 1):
                    self._blocks.pop(((p.x + dx) // BLOCK, (p.y + dy) // BLOCK), None)
        self._seen = len(changes)
        self._clear.clear()
        self._cell = None

    def _block(self, world, key):
        block = self._blocks.get(key)
        if block is None:
            block = self._blocks[key] = block_candidates(world, *key)
        return block

    def _prefetch(self, world, cell):
        reach = RADIUS + PREFETCH
        for bx in range((cell.x - reach) // BLOCK, (cell.x + reach) // BLOCK + 1):
            for by in range((cell.y - reach) // BLOCK, (cell.y + reach) // BLOCK + 1):
                if (bx, by) not in self._blocks:
                    self._block(world, (bx, by))
                    return

    def anchors(self, world, cell):
        self._forget_changes(world)
        if cell == self._cell:
            self._prefetch(world, cell)
            return self._anchors
        found = {kind: [] for kind in LIMITS}
        for bx in range((cell.x - RADIUS) // BLOCK, (cell.x + RADIUS) // BLOCK + 1):
            for by in range((cell.y - RADIUS) // BLOCK, (cell.y + RADIUS) // BLOCK + 1):
                for kind, q, roll, extra in self._block(world, (bx, by)):
                    dx, dy = q.x - cell.x, q.y - cell.y
                    if -RADIUS <= dx <= RADIUS and -RADIUS <= dy <= RADIUS:
                        found[kind].append((dx * dx + dy * dy, q, roll, extra))
        anchors = {}
        for kind, candidates in found.items():
            candidates.sort(key=lambda c: (c[0], c[1]))
            chosen = []
            for _, q, roll, extra in candidates:
                if len(chosen) == LIMITS[kind]:
                    break
                if kind not in BEHIND_COVER:
                    clear = self._clear.get(q)
                    if clear is None:
                        clear = self._clear[q] = _clear_in_front(world, q, world.elevation_at(q))
                    if not clear:
                        continue
                chosen.append((q, roll, extra) if kind == "frog" else (q, roll))
            anchors[kind] = tuple(chosen)
        self._cell, self._anchors = cell, anchors
        return anchors

    def draw_ground(self, screen, session, origin, config) -> int:
        world = session.world
        if world.space_kind is not SpaceKind.OUTDOOR:
            return 0
        anchors = self.anchors(world, session.player.position)
        light, t, scale = session.daylight, session.cycle_seconds, config.pixel_scale
        drawn = 0
        presence = {DayPhase.DAY: 1.0, DayPhase.AFTERNOON: 1 - light.blend}.get(light.phase, 0.0)
        flyers = [("butterfly", a) for a in anchors["butterfly"]] + [("bee", a) for a in anchors["bee"]]
        for n, (kind, (cell, roll)) in enumerate(flyers):
            if (n + .5) / max(1, len(flyers)) > presence:
                continue
            if kind == "bee" and not getattr(world.objects.get(cell), "available", False):
                continue
            phase = (roll % 628) / 100
            z = world.elevation_at(cell)
            if kind == "butterfly":
                x = cell.x + .55 * math.sin(t * .7 + phase) + .2 * math.sin(t * 1.9 + 2 * phase)
                y = cell.y + .55 * math.cos(t * .6 + 1.3 * phase) + .2 * math.cos(t * 1.7 + phase)
                vx = .7 * math.cos(t * .7 + phase) - .6 * math.sin(t * .6 + 1.3 * phase)
                sprite = _butterfly(WINGS[roll % len(WINGS)], int(t * 9 + phase) % 2 == 0, vx < 0)
                height = 11 + 4 * math.sin(t * 2.3 + phase)
            else:
                for offset in (0, math.pi):
                    angle = t * 4.5 + phase + offset
                    x = cell.x + .3 * math.cos(angle)
                    y = cell.y + .3 * math.sin(angle)
                    sx, sy = screen_center((x, y, z), origin, config)
                    sprite = _bee(int(t * 24 + offset) % 2 == 0)
                    if scale != 1:
                        sprite = pygame.transform.scale_by(sprite, scale)
                    show(screen, sprite, center=(sx, sy - (9 + 2 * math.sin(angle * 2)) * scale))
                    drawn += 1
                continue
            sx, sy = screen_center((x, y, z), origin, config)
            if scale != 1:
                sprite = pygame.transform.scale_by(sprite, scale)
            show(screen, sprite, center=(sx, sy - round(height * scale)))
            drawn += 1
        player = session.player.position3d
        for cell, roll, water in anchors["frog"]:
            if (cell.x - player.x) ** 2 + (cell.y - player.y) ** 2 < FROG_SCARE ** 2:
                continue
            period = 3.5 + roll % 3
            beat = (t + roll % 7) % period
            hop = beat < .35
            side = 1 if int((t + roll % 7) / period) % 2 else -1
            across = GridPos(-water.y, water.x)
            u = beat / .35 if hop else 1.0
            shift = .14 * side * (2 * u - 1) if hop else .14 * side
            x = cell.x + .28 * water.x + shift * across.x
            y = cell.y + .28 * water.y + shift * across.y
            sx, sy = screen_center((x, y, world.elevation_at(cell)), origin, config)
            height = 5 * math.sin(math.pi * u) if hop else 0
            facing_left = (across.x - across.y) * side < 0
            sprite = _frog(hop, facing_left)
            if scale != 1:
                sprite = pygame.transform.scale_by(sprite, scale)
            show(screen, sprite, midbottom=(sx, sy + 1 - round(height * scale)))
            drawn += 1
        return drawn

    def draw_glow(self, screen, session, origin, config) -> int:
        world = session.world
        if world.space_kind is not SpaceKind.OUTDOOR:
            return 0
        light = session.daylight
        presence = {DayPhase.AFTERNOON: light.blend, DayPhase.NIGHT: 1 - light.blend}.get(light.phase, 0.0)
        if presence <= 0:
            return 0
        anchors = self.anchors(world, session.player.position)["firefly"]
        t, scale = session.cycle_seconds, config.pixel_scale
        drawn = 0
        for n, (cell, roll) in enumerate(anchors):
            if (n + .5) / len(anchors) > presence:
                continue
            phase = (roll % 628) / 100
            pulse = math.sin(t * 1.7 + phase)
            if pulse <= 0:
                continue
            x = cell.x + .7 * math.sin(t * .35 + phase) + .2 * math.sin(t * 1.1 + 3 * phase)
            y = cell.y + .7 * math.cos(t * .3 + 2 * phase) + .2 * math.cos(t * .9 + phase)
            height = 7 + 9 * (.5 + .5 * math.sin(t * .5 + phase))
            sx, sy = screen_center((x, y, world.elevation_at(cell)), origin, config)
            sprite = _glow(1 + min(2, int(pulse * 3)))
            if scale != 1:
                sprite = pygame.transform.scale_by(sprite, scale)
            screen.blit(sprite, sprite.get_rect(center=(sx, sy - round(height * scale))),
                        special_flags=pygame.BLEND_ADD)
            drawn += 1
        return drawn
