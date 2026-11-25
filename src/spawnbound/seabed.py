import math
from functools import lru_cache
from typing import NamedTuple

import pygame

from spawnbound.domain.coordinates import GridPos
from spawnbound.domain.model import Tile, TileKind, World
from spawnbound.domain.terrain import CARDINAL


class Sandbank(NamedTuple):
    level: int
    left_drop: int
    right_drop: int
    detail: int


SAND = ((68, 134, 148, 190), (99, 159, 157, 196), (147, 181, 159, 204))


def shore_depth(world, pos, limit=3):
    tile_at = world.tile_map.tile_at
    for ring in range(1, limit):
        for d in range(-ring, ring + 1):
            for q in ((pos.x + d, pos.y - ring), (pos.x + d, pos.y + ring),
                      (pos.x - ring, pos.y + d), (pos.x + ring, pos.y + d)):
                tile = tile_at(GridPos(*q))
                if tile is not None and tile.kind is not TileKind.WATER:
                    return ring
    return limit


def water_decoration(world, pos, tile):
    size = world.tile_map.ocean_island_size
    if not size or tile.deep_water:
        return None
    if pos in world.fish_refuges:
        return "thicket"
    for step in CARDINAL:
        lane = world.fish_refuges.get(pos + step)
        if lane == step:
            return "thicket"
        if lane and lane.x*step.x + lane.y*step.y == 0:
            return "reeds" if pos in world.river_cells else "kelp"
    pattern = (pos.x * 73856093 ^ pos.y * 19349663 ^ world.seed) & 0xffffffff
    mouth = world.river_mouth
    if mouth and abs(pos.x-mouth.x) + abs(pos.y-mouth.y) <= 5:
        choices = ("fan", "reeds", "shell")
        density = 22
    elif pos in world.river_cells:
        choices = ("ribbon", "stones", "reeds")
        density = 40
    elif pos in world.sea_cells or not (0 <= pos.x < size and 0 <= pos.y < size):
        patch = math.sin(pos.x*.37 + world.seed % 31) + math.cos(pos.y*.34)
        choices = ("kelp", "kelp", "shell") if patch > .45 else ("shell", "star", "kelp")
        density = 23 if patch > .45 else 6
    else:
        depth = shore_depth(world, pos)
        if depth == 1:
            choices, density = ("reeds", "reeds", "lily"), 30
        elif depth == 2:
            choices, density = ("lily",), 14
        else:
            return None
    if pattern % 100 >= density:
        return None
    return choices[(pattern >> 8) % len(choices)]


@lru_cache(maxsize=64)
def aquatic_glyph(name, width, height):
    art = pygame.Surface((33, 17), pygame.SRCALPHA)
    draw = pygame.draw
    dark, green, light = (40, 102, 93), (62, 139, 107), (125, 172, 121)
    if name == "thicket":
        draw.ellipse(art, dark, (4, 4, 25, 9))
        draw.ellipse(art, green, (7, 4, 19, 8))
        for x, tip, y in ((6, 4, 6), (9, 8, 4), (13, 10, 4), (16, 17, 1),
                          (19, 21, 3), (23, 25, 5), (26, 29, 7)):
            draw.polygon(art, dark, [(x-2, 10), (tip, y), (x+2, 9)])
            draw.line(art, light, (x, 8), (tip, y))
        draw.lines(art, (77, 151, 108), False, [(8,9),(12,11),(18,9),(22,10),(26,8)], 2)
    elif name == "kelp":
        for x,y in ((11,6),(15,2),(21,4)):
            draw.lines(art, (49,105,99), False, [(x+2,12),(x-1,10),(x+1,7),(x,y)],2)
            draw.polygon(art,(75,145,123),[(x+1,9),(x+4,6),(x+4,8),(x+2,10)])
            draw.line(art,(111,159,132),(x,7),(x-1,y))
    elif name in ("ribbon", "reeds", "fan"):
        blades = {"ribbon": ((8,7),(11,5),(14,3)),
                  "reeds": ((12,4),(16,2),(19,3)), "fan": ((7,7),(10,5),(16,3),(21,4),(25,7))}
        shade = (113, 135, 107) if name == "fan" else dark
        for tip, y in blades[name]:
            base = 15 + (tip-15)//3
            bend = tip + (2 if name == "kelp" else 0)
            draw.polygon(art, shade, [(base-1,12),(bend-1,7),(tip,y),(bend+1,7),(base+1,12)])
            draw.line(art, light if name == "reeds" else green, (bend,7), (tip,y))
            if name == "reeds":
                draw.line(art,(151,138,94),(tip,y),(tip,y+2),2)
    elif name == "lily":
        for x, y, w in ((7, 6, 10), (17, 8, 9)):
            draw.ellipse(art, (52, 118, 72), (x, y, w, 5))
            draw.ellipse(art, (86, 152, 86), (x + 1, y, w - 3, 3))
            draw.line(art, (40, 96, 64), (x + w // 2, y + 2), (x + w - 1, y + 1))
        draw.circle(art, (238, 214, 226), (12, 7), 2)
        draw.circle(art, (248, 230, 150), (12, 7), 1)
    elif name == "star":
        draw.polygon(art,(151,133,115),[(16,3),(17,7),(22,7),(18,9),(20,13),
                                       (16,10),(12,13),(14,9),(10,7),(15,7)])
        draw.line(art,(176,153,129),(16,6),(16,9))
    elif name == "shell":
        draw.polygon(art,(109,145,144),[(10,8),(13,5),(18,5),(21,8),(17,11),(14,11)])
        for x in (12,16,19):
            draw.line(art,(178,181,155),(16,10),(x,7))
    elif name == "stones":
        for x,y,w in ((9,8,7),(16,6,6),(18,10,4)):
            draw.ellipse(art,(76,113,114),(x,y,w,4))
            draw.line(art,(140,160,148),(x+1,y+1),(x+w-2,y+1))
    clip = pygame.Surface(art.get_size(), pygame.SRCALPHA)
    draw.polygon(clip, (255,255,255,255), [(16,0),(32,8),(16,16),(0,8)])
    art.blit(clip, (0,0), special_flags=pygame.BLEND_RGBA_MULT)
    return pygame.transform.scale(art, (width+1, height+1))


def bed_level(world, pos):
    size = world.tile_map.ocean_island_size
    offshore = max(-pos.x, -pos.y, pos.x-size+1, pos.y-size+1)
    phase = math.radians(world.seed % 360)
    ridges = math.sin(pos.x*.29 + phase) + math.cos(pos.y*.24 - phase)
    if offshore > 0:
        depth = offshore / 3.7 + .55*ridges
    else:
        depth = shore_depth(world, pos) - .65 + .85*ridges
    return max(0, min(3, 3 - math.floor(depth)))


def sandbank_at(world: World, pos: GridPos, neighbors: tuple[Tile | None, ...], levels=None) -> Sandbank | None:
    if not world.tile_map.ocean_island_size:
        return None

    def level(p):
        if levels is None:
            return bed_level(world, p)
        if p not in levels:
            levels[p] = bed_level(world, p)
        return levels[p]

    height = level(pos)
    if not height:
        return None
    drops = [0, 0]
    for i, (neighbor, step) in enumerate(zip(neighbors[:2], (GridPos(0,1), GridPos(1,0)))):
        if neighbor and neighbor.kind is TileKind.WATER:
            drops[i] = max(0, height - (0 if neighbor.deep_water else level(pos + step)))
    dx, dy = pos.x, pos.y
    phase = math.radians(world.seed % 360)
    pattern = (pos.x * 73856093 ^ pos.y * 19349663 ^ world.seed) & 0xffffffff
    reeds = math.sin(dx * .57 + phase) + math.cos(dy * .63 - phase) > .65
    detail = 0
    if reeds and pattern % 4:
        detail = 1 + (pattern % 2)
    elif pattern % 23 == 0:
        detail = 3
    return Sandbank(height, *drops, detail)


def paint_sandbank(surface: pygame.Surface, bank: Sandbank, first, last, width: int, height: int):
    body = SAND[bank.level - 1]
    half = width // 2
    for drop, columns, shade in ((bank.left_drop, range(half + 1), .81),
                                 (bank.right_drop, range(half, width + 1), .70)):
        if drop:
            face = (*[round(channel * shade) for channel in body[:3]], body[3])
            for x in columns:
                top = max(first[x], last[x] - max(2, height // 4) * drop + 1)
                pygame.draw.line(surface, face, (x, top), (x, last[x]))
    x, y = half, height // 2
    if bank.detail in (1, 2):
        x += 3 if bank.detail == 1 else -3
        pygame.draw.ellipse(surface, (76, 132, 123, 158), (x - 4, y + 1, 9, 3))
        blades = ((-2, -4, 4), (0, -2, 7), (2, 1, 5)) if bank.detail == 1 else (
            (-2, -5, 3), (-1, -3, 6), (1, 2, 7), (2, 5, 4))
        for base, tip, length in blades:
            foot = (x + base, y + 2)
            end = (x + tip, y + 2 - length)
            pygame.draw.polygon(surface, (49, 132, 110, 225),
                                [foot, (x + tip - 1, y - 1), end, (x + base + 1, y)])
        pygame.draw.line(surface, (117, 174, 136, 222), (x, y), (x - 2, y - 4))
    elif bank.detail == 3:
        pygame.draw.ellipse(surface, (88, 134, 133, 213), (x - 4, y, 6, 3))
        pygame.draw.line(surface, (168, 183, 160, 218), (x - 2, y), (x, y))
