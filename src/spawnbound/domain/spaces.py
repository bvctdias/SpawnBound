from __future__ import annotations

import hashlib
import json
import random
from collections import deque
from dataclasses import dataclass, field

from spawnbound.domain.coordinates import EAST, GridPos
from spawnbound.domain.mine_guides import MineGuides
from spawnbound.domain.model import (
    Biome, BridgeSite, ObjectKind, Portal, SpaceKind, TileKind, TileMap, World, WorldObject,
)
from spawnbound.domain.noise import PerlinNoise
from spawnbound.domain.terrain import CARDINAL, OVERHANG_SIDES, overhangs_higher_ground, reachable_surface, repair_surface_connectivity

CAVE_MIN, CAVE_MAX = .45, .55
CAVE_GENERATOR_VERSION = 3
COAL_PEAK, COAL_TO = .30, .575
COPPER_FROM, COPPER_PEAK = .2, .40
QUARTZ_FROM, QUARTZ_PEAK = .55, .30


def ore_variant(depth: float, roll: float) -> str:
    quartz = QUARTZ_PEAK * max(0.0, min(1.0, (depth - QUARTZ_FROM) / (1 - QUARTZ_FROM)))
    copper = COPPER_PEAK * max(0.0, min(1.0, (depth - COPPER_FROM) / (.7 - COPPER_FROM)))
    coal = COAL_PEAK * max(0.0, min(1.0, (COAL_TO - depth) / (COAL_TO - COPPER_FROM)))
    if roll < quartz:
        return "quartz_ore"
    if roll < quartz + copper:
        return "copper_ore"
    if roll < quartz + copper + coal:
        return "coal_ore"
    return "cave_stone"


def walking_depth(floors: set[GridPos], start: GridPos) -> dict[GridPos, float]:
    steps = {start: 0}
    pending = deque([start])
    while pending:
        p = pending.popleft()
        for d in CARDINAL:
            q = p + d
            if q in floors and q not in steps:
                steps[q] = steps[p] + 1
                pending.append(q)
    far = max(steps.values()) or 1
    return {p: n / far for p, n in steps.items()}


def derive_space_seed(master_seed: int, parent_id: str, portal: Portal, elevation: int) -> int:
    payload = json.dumps([CAVE_GENERATOR_VERSION, master_seed, parent_id,
                          portal.portal_id, portal.target_kind.value,
                          portal.position.x, portal.position.y, elevation],
                         ensure_ascii=True, separators=(",", ":")).encode("utf-8")
    return int.from_bytes(hashlib.blake2b(payload, digest_size=8).digest(), "big")


@dataclass(slots=True)
class WorldSpaces:
    master_seed: int
    worlds: dict[str, World] = field(default_factory=dict)

    def resolve(self, source: World, portal: Portal) -> tuple[World, GridPos]:
        destination = self.worlds.get(portal.target_space_id)
        if destination is None:
            if portal.target_kind is SpaceKind.OUTDOOR:
                raise ValueError("return space is missing")
            destination = self._generate(source, portal)
            self.worlds[destination.space_id] = destination
        arrival = portal.arrival or destination.spawn
        if not destination.is_walkable(arrival):
            candidates = (GridPos(arrival.x + dx, arrival.y + dy)
                          for radius in range(1, 5)
                          for dx in range(-radius, radius + 1)
                          for dy in range(-radius, radius + 1)
                          if max(abs(dx), abs(dy)) == radius)
            arrival = next((p for p in candidates if destination.is_walkable(p)), None)
            if arrival is None:
                raise ValueError("no safe arrival in destination space")
        return destination, arrival

    def build_behind(self, source: World) -> list[World]:
        return [self._generate(source, portal) for portal in source.portals.values()
                if portal.target_kind is not SpaceKind.OUTDOOR and portal.target_space_id not in self.worlds]

    def prepare(self, source: World) -> None:
        for world in self.build_behind(source):
            self.worlds.setdefault(world.space_id, world)

    def _generate(self, source: World, portal: Portal) -> World:
        seed = derive_space_seed(self.master_seed, source.space_id, portal,
                                 source.elevation_at(portal.position))
        cave_size = max(16, (source.chunk_preview_size or 96) // 2)
        return generate_space(seed, portal, source.space_id, cave_size=cave_size)


def exit_landing(world: World) -> frozenset[GridPos]:
    if world.space_kind is not SpaceKind.INTERIOR:
        return frozenset()
    door = next((portal for portal in world.portals.values() if portal.target_kind is SpaceKind.OUTDOOR), None)
    if door is None:
        return frozenset()
    return frozenset(cell for cell in world.tile_map.tiles if cell.y >= door.position.y)


def exit_from(world: World, position: GridPos, facing: GridPos | None = None) -> Portal | None:
    if position not in exit_landing(world):
        return None
    if facing is not None and world.object_at(position + facing) is not None:
        return None
    return next(portal for portal in world.portals.values() if portal.target_kind is SpaceKind.OUTDOOR)


def generate_space(seed: int, entrance: Portal, parent_id: str, *, cave_size: int = 64) -> World:
    if entrance.target_kind is SpaceKind.CAVE:
        size = max(16, cave_size)
        spawn = GridPos(size // 2, size - 5)
        noise = PerlinNoise(seed)
        floors = {GridPos(x, y) for x in range(2, size - 2) for y in range(2, size - 2)
                  if CAVE_MIN < noise.fractal(x + 17.3, y + 63.1, scale=13, octaves=3) < CAVE_MAX}
        floors |= {spawn + GridPos(dx, dy) for dx in range(-2, 3) for dy in range(-2, 3)}
        ore_ledge = spawn + GridPos(3, 0)
        floors |= {ore_ledge + GridPos(dx, dy) for dx in range(-1, 2) for dy in range(-1, 2)}
        _connect_cave(floors, spawn, size=size)
        _add_short_cave_links(floors, size)
        floor_kind = TileKind.CAVE_FLOOR
    elif entrance.target_kind is SpaceKind.INTERIOR:
        size = 13
        spawn = GridPos(5, 10)
        floors = {GridPos(x, y) for x in range(1, 11) for y in range(1, 11)}
        floors.update(GridPos(x, y) for x in (5, 6) for y in (11, 12))
        floor_kind = TileKind.WOOD_FLOOR
    else:
        raise ValueError("unsupported generated space kind")
    tile_map = TileMap()
    height_noise = PerlinNoise(seed ^ 0x43415645485A)
    heights = {p: max(1, min(5, int(height_noise.fractal(p.x + 51.7, p.y + 23.3,
                                                        scale=11, octaves=2) * 12) - 3))
               for p in floors} if entrance.target_kind is SpaceKind.CAVE else {}
    if heights:
        for p in floors:
            if max(abs(p.x - spawn.x), abs(p.y - spawn.y)) <= 2:
                heights[p] = 1
        pending = deque(sorted(floors))
        while pending:
            p = pending.popleft()
            neighbors = [p + d for d in CARDINAL if p + d in floors]
            cap = min((heights[q] + 1 for q in neighbors), default=heights[p])
            if heights[p] > cap:
                heights[p] = cap
                pending.extend(neighbors)
    for x in range(size):
        for y in range(size):
            p = GridPos(x, y)
            floor = p in floors
            if floor:
                tile_map.add(p, floor_kind, biome=Biome.DRY, elevation=heights.get(p, 0))
    exit_position = spawn + GridPos(0, 1)
    back = Portal("return", exit_position, spawn, parent_id, SpaceKind.OUTDOOR,
                  "SAIDA", arrival=entrance.approach)
    objects = {}
    if entrance.target_kind is SpaceKind.CAVE:
        rng = random.Random(seed ^ 0x4F5245)
        # Sortear o minério em separado preserva a posição das pedras para a mesma seed.
        material = random.Random(seed ^ 0x4D494E45)
        depth = walking_depth(floors, spawn)
        ore_height = tile_map.tile_at(ore_ledge).elevation
        for d in OVERHANG_SIDES:
            neighbor = tile_map.tile_at(ore_ledge + d)
            if neighbor is not None and neighbor.elevation > ore_height:
                tile_map.add(ore_ledge + d, neighbor.kind, neighbor.variant, neighbor.biome, ore_height)
        objects[ore_ledge] = WorldObject.create(ore_ledge, ObjectKind.ROCK, variant="cave_stone",
                                                elevation=ore_height)
        for p in sorted(floors):
            if max(abs(p.x - spawn.x), abs(p.y - spawn.y)) <= 3:
                continue
            if overhangs_higher_ground(tile_map, p):
                continue
            if rng.random() < .025 and all(p + GridPos(dx, dy) in floors for dx in range(-1, 2) for dy in range(-1, 2)):
                if all(p + GridPos(dx, dy) not in objects
                       for dx in range(-2, 3) for dy in range(-2, 3)):
                    variant = ore_variant(depth.get(p, 0.0), material.random())
                    objects[p] = WorldObject.create(p, ObjectKind.ROCK, variant=variant,
                                                    elevation=tile_map.tile_at(p).elevation)
        # Se o sorteio não produzir quartzo, a pedra mais funda ainda pode virar um veio.
        if not any(obj.variant == "quartz_ore" for obj in objects.values()):
            deepest = max((p for p in objects if p != ore_ledge), key=lambda p: (depth.get(p, 0.0), p), default=None)
            if deepest is not None and depth.get(deepest, 0.0) > QUARTZ_FROM:
                objects[deepest].variant = "quartz_ore"
    world = World(seed, tile_map, objects, spawn, None if entrance.target_kind is SpaceKind.INTERIOR else spawn,
                  BridgeSite(spawn, (), spawn, EAST, built=True), spawn,
                  chunk_preview_size=size, space_id=entrance.target_space_id,
                  space_kind=entrance.target_kind, portals={exit_position: back}, strict_diagonals=True)
    if entrance.target_kind is SpaceKind.CAVE:
        repair_surface_connectivity(world)
        for p, obj in world.objects.items():
            obj.elevation = world.elevation_at(p)
        _ensure_upgrade_ores(world, depth, ore_ledge)
        world.guides = MineGuides.place(world)
    return world


def _ensure_upgrade_ores(world, depth, ore_ledge):
    targets = {"quartz_ore": .85, "copper_ore": .50, "coal_ore": .15}
    for variant, threshold in (("quartz_ore", QUARTZ_FROM), ("copper_ore", COPPER_FROM), ("coal_ore", 0.0)):
        def accessible(p):
            return any(world.is_walkable(p+d) and world.can_reach(p+d, p) for d in CARDINAL)
        if any(o.variant == variant and accessible(p) for p,o in world.objects.items()):
            continue
        sites = [p for p in depth if depth[p] > threshold and p != ore_ledge and p not in world.portals
                 and not overhangs_higher_ground(world.tile_map, p) and accessible(p)]
        sites.sort(key=lambda p: (abs(depth[p] - targets[variant]), p))
        rock = next((world.objects[p] for p in sites if p in world.objects and
                     world.objects[p].variant == "cave_stone"), None)
        if rock is not None:
            rock.variant = variant
            continue
        before = len(reachable_surface(world))
        for p in sites:
            if not world.is_walkable(p) or p == world.spawn:
                continue
            world.objects[p] = WorldObject.create(p, ObjectKind.ROCK, variant=variant, elevation=world.elevation_at(p))
            if len(reachable_surface(world)) == before - 1:
                break
            del world.objects[p]


def _component(start: GridPos, floors: set[GridPos]) -> set[GridPos]:
    visited = {start}
    pending = deque([start])
    while pending:
        current = pending.popleft()
        for direction in CARDINAL:
            neighbor = current + direction
            if neighbor in floors and neighbor not in visited:
                visited.add(neighbor)
                pending.append(neighbor)
    return visited


def _stamp_cave_link(floors: set[GridPos], path: list[GridPos], size: int | None) -> None:
    for p in path:
        for dx in range(-1, 2):
            for dy in range(-1, 2):
                q = p + GridPos(dx, dy)
                if size is None or (2 <= q.x < size - 2 and 2 <= q.y < size - 2):
                    floors.add(q)


def _connect_cave(floors: set[GridPos], spawn: GridPos, *, size: int | None = None) -> None:
    connected = _component(spawn, floors)
    while remaining := floors - connected:
        origin = min(remaining)
        target = min(connected, key=lambda p: (abs(p.x - origin.x) + abs(p.y - origin.y), p))
        current = origin
        path = [current]
        while current != target:
            if current.x != target.x:
                current += GridPos(1 if target.x > current.x else -1, 0)
            else:
                current += GridPos(0, 1 if target.y > current.y else -1)
            floors.add(current)
            path.append(current)
        _stamp_cave_link(floors, path, size)
        connected = _component(spawn, floors)


def _has_short_floor_route(floors: set[GridPos], start: GridPos, target: GridPos, budget: int) -> bool:
    pending = deque([(start, 0)])
    seen = {start}
    while pending:
        p, distance = pending.popleft()
        if p == target:
            return True
        if distance >= budget:
            continue
        for d in CARDINAL:
            q = p + d
            if q in floors and q not in seen:
                seen.add(q)
                pending.append((q, distance + 1))
    return False


def _add_short_cave_links(floors: set[GridPos], size: int) -> None:
    for start in sorted(floors):
        for direction in (GridPos(1, 0), GridPos(0, 1)):
            for gap in (2, 3, 4):
                target = start + GridPos(direction.x * gap, direction.y * gap)
                if target not in floors:
                    continue
                middle = [start + GridPos(direction.x * n, direction.y * n) for n in range(1, gap)]
                if any(p in floors for p in middle):
                    continue
                if not _has_short_floor_route(floors, start, target, gap * 2):
                    _stamp_cave_link(floors, [start, *middle, target], size)
