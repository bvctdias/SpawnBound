from __future__ import annotations

import math
import random
from collections import deque
from dataclasses import dataclass, field

from spawnbound.domain.coordinates import NEIGHBOR_DIRECTIONS, GridPos, WorldPos

NAME = "Guardião de Pedra"
HEALTH = 40
ARENA_RADIUS = 6
RING_RADIUS = 7
SLOPE = 3
CLEAR_OF_WATER = RING_RADIUS + SLOPE + 1
MENHIRS = 8
WAKE_RADIUS = 5.5
LEAVE_RADIUS = 11
WAKE_PAUSE = 1.2
# Os pares guardam os valores da primeira e da segunda fase, nessa ordem.
PUNCH_WINDUP = (1.0, .7)
STUCK = (1.7, 1.25)
SLAM_WINDUP = (.85, .6)
AIR = .75
LANDED = (1.1, .8)
THROW_WINDUP = (.8, .6)
RELEASE = .45
ROCK_FLIGHT = (1.25, 1.)
STEP = (.8, .6)
REST = (1.1, .7)
RING_SPEED = (4.5, 6.)
RING_REACH = 9.
SECOND_RING = 1.6
ROCK_RADIUS = .9
LIFT = 2.2
OPENINGS = ("stuck", "landed")


@dataclass(slots=True)
class Ring:
    center: WorldPos
    radius: float = 0.
    done: bool = False


@dataclass(slots=True)
class Rock:
    start: WorldPos
    target: WorldPos
    left: float
    total: float

    @property
    def progress(self) -> float:
        return 1 - max(0., self.left) / self.total


@dataclass(slots=True)
class Guardian:
    arena: GridPos
    rng: random.Random
    move: str = ""
    stage: str = ""
    timer: float = 0.
    rest: float = 0.
    marked: tuple[GridPos, ...] = ()
    leap_from: WorldPos | None = None
    leap_to: WorldPos | None = None
    rings: list[Ring] = field(default_factory=list)
    rocks: list[Rock] = field(default_factory=list)
    moves: int = 0
    lift: float = 0.
    impact: float = 0.


def wrath(mob) -> bool:
    return mob.hp <= HEALTH // 2


def opening(mob) -> bool:
    return mob.boss is not None and mob.boss.stage in OPENINGS


def _water_distance(world) -> dict[GridPos, int]:
    tiles = world.tile_map.tiles
    from spawnbound.domain.model import TileKind
    dist: dict[GridPos, int] = {}
    pending = deque()
    for cell, tile in tiles.items():
        if tile.kind is TileKind.WATER:
            dist[cell] = 0
            pending.append(cell)
        elif any(cell + d not in tiles for d in NEIGHBOR_DIRECTIONS):
            dist[cell] = 0
            pending.append(cell)
    while pending:
        cell = pending.popleft()
        for d in NEIGHBOR_DIRECTIONS:
            nxt = cell + d
            if nxt in tiles and nxt not in dist:
                dist[nxt] = dist[cell] + 1
                pending.append(nxt)
    return dist


def _disk(center: GridPos, radius: float):
    r = int(math.ceil(radius))
    for dx in range(-r, r + 1):
        for dy in range(-r, r + 1):
            d = math.hypot(dx, dy)
            if d <= radius:
                yield center + GridPos(dx, dy), d


def menhir_cells(center: GridPos) -> tuple[GridPos, ...]:
    cells = []
    for k in range(MENHIRS):
        angle = 2 * math.pi * (k + .5) / MENHIRS
        cells.append(center + GridPos(round(RING_RADIUS * math.cos(angle)), round(RING_RADIUS * math.sin(angle))))
    return tuple(cells)


def place_arena(world) -> GridPos | None:
    from spawnbound.domain.model import Biome, ObjectKind, TileKind, WorldObject
    from spawnbound.domain.terrain import reachable_surface
    tiles = world.tile_map.tiles
    reach = reachable_surface(world)
    if not reach:
        return None
    water = _water_distance(world)
    keep_out = set(world.portals) | {world.spawn} | {p for p, o in world.objects.items()
                                                       if o.kind in (ObjectKind.WAYSTONE, ObjectKind.DOCK)}
    candidates = []
    for cell in reach:
        if water.get(cell, 0) < CLEAR_OF_WATER or cell.x % 2 or cell.y % 2:
            continue
        if any(max(abs(cell.x - p.x), abs(cell.y - p.y)) <= CLEAR_OF_WATER for p in keep_out):
            continue
        heights = [tiles[p].elevation for p, _ in _disk(cell, ARENA_RADIUS)]
        trees = sum(1 for p, _ in _disk(cell, RING_RADIUS) if p in world.objects)
        candidates.append((max(heights) - min(heights), trees, cell.x, cell.y))
    for _, _, x, y in sorted(candidates)[:12]:
        center = GridPos(x, y)
        before_tiles = {p: tiles[p] for p, _ in _disk(center, CLEAR_OF_WATER)}
        before_objects = {p: world.objects[p] for p in before_tiles if p in world.objects}
        heights = sorted(tiles[p].elevation for p, _ in _disk(center, ARENA_RADIUS))
        level = heights[len(heights) // 2]
        for p, d in _disk(center, RING_RADIUS + SLOPE + .5):
            tile = tiles[p]
            if d <= RING_RADIUS + .5:
                world.tile_map.add(p, TileKind.GRASS, biome=Biome.MEADOW, elevation=level)
                world.objects.pop(p, None)
                continue
            allowed = math.ceil(d - RING_RADIUS - .5)
            height = max(level - allowed, min(level + allowed, tile.elevation))
            if height != tile.elevation:
                world.tile_map.add(p, tile.kind, tile.variant, tile.biome, height)
                world.objects.pop(p, None)
        for p in menhir_cells(center):
            world.objects[p] = WorldObject.create(p, ObjectKind.MENHIR, variant=str((p.x * 7 + p.y * 3) % 3),
                                                  elevation=level)
        after = reachable_surface(world)
        if center in after and reach - set(before_tiles) <= after:
            world.arena = center
            return center
        for p, tile in before_tiles.items():  # Desfaz o nivelamento se a arena separar a ilha.
            world.tile_map.tiles[p] = tile
        for p in menhir_cells(center):
            world.objects.pop(p, None)
        world.objects.update(before_objects)
        world.tile_map.revision += 1
    return None


def spawn(wildlife) -> None:
    from spawnbound.domain.mobs import MobKind
    world = wildlife.world
    if world.arena is None or world.guardian_defeated:
        return
    wildlife._add(MobKind.GUARDIAN, world.arena, world.arena)
    mob = wildlife.mobs[wildlife.next_id - 1]
    mob.asleep, mob.left = True, True
    mob.boss = Guardian(world.arena, random.Random(world.seed ^ 0x47554152))


def _phase(mob) -> int:
    return 1 if wrath(mob) else 0


def _flat(a, b) -> float:
    return math.hypot(a.x - b.x, a.y - b.y)


def turn(wildlife, mob, player: WorldPos, dt: float, reserved: set[GridPos]) -> bool:
    from spawnbound.domain.mobs import faces_left
    g, world = mob.boss, wildlife.world
    damaged = _fly(wildlife, g, player, dt)
    g.impact += dt
    mob.lunge = max(0., mob.lunge - dt)
    centre = world.surface_position(g.arena)
    near = _flat(player, centre)
    if mob.asleep:
        if near <= WAKE_RADIUS and abs(player.z - centre.z) <= 1.5:
            mob.asleep = False
            g.rest = WAKE_PAUSE
            mob.left = faces_left(mob.end.grid, player)
            wildlife.woke = mob
        return damaged
    if mob.progress < 1:
        mob.progress = min(1., mob.progress + dt / mob.duration)
        if g.stage == "air":
            g.lift = LIFT * math.sin(math.pi * mob.progress)
    if g.move:
        return damaged | _go_on(wildlife, mob, g, player, dt)
    if mob.progress < 1:
        return damaged
    if near > LEAVE_RADIUS:
        g.rings.clear()
        g.rocks.clear()
        here = mob.end.grid
        if here == g.arena:
            mob.asleep, mob.windup, mob.dazed = True, 0., 0.
            return damaged
        _step(wildlife, mob, g.arena, reserved, player, home=True)
        return damaged
    mob.left = faces_left(mob.end.grid, player)
    g.rest -= dt
    if g.rest > 0:
        return damaged
    phase = _phase(mob)
    here = mob.end.grid
    gap = max(abs(here.x - player.grid.x), abs(here.y - player.grid.y))
    level = abs(player.z - mob.end.z) <= 1.5
    pick = g.moves % 4
    if gap <= 2 and level and pick != 3:
        _start(mob, g, "punch", PUNCH_WINDUP[phase])
        g.marked = tuple(player.grid + GridPos(dx, dy) for dx in (-1, 0, 1) for dy in (-1, 0, 1))
    elif gap <= 8 and level:
        if pick % 2 == 0 and gap >= 3:
            _start(mob, g, "throw", THROW_WINDUP[phase])
        else:
            _start(mob, g, "slam", SLAM_WINDUP[phase])
    else:
        if not _step(wildlife, mob, player.grid, reserved, player):
            _start(mob, g, "slam", SLAM_WINDUP[phase])
        else:
            g.rest = 0.
    return damaged


def _start(mob, g: Guardian, move: str, windup: float) -> None:
    g.move, g.stage, g.timer = move, "windup", windup
    mob.windup, mob.dazed = windup, 0.


def _finish(mob, g: Guardian) -> None:
    g.move = g.stage = ""
    g.marked = ()
    g.moves += 1
    g.rest = REST[_phase(mob)]
    mob.windup = mob.dazed = 0.


def _step(wildlife, mob, goal: GridPos, reserved, player, *, home: bool = False) -> bool:
    world, g = wildlife.world, mob.boss
    here = mob.end.grid
    options = sorted((here + d for d in NEIGHBOR_DIRECTIONS),
                     key=lambda q: math.hypot(q.x - goal.x, q.y - goal.y))
    for q in options:
        if math.hypot(q.x - goal.x, q.y - goal.y) >= math.hypot(here.x - goal.x, here.y - goal.y):
            break
        if (q != player.grid and q not in reserved and math.hypot(q.x - g.arena.x, q.y - g.arena.y) <= ARENA_RADIUS
                and world.can_step(here, q)):
            reserved.discard(here)
            reserved.add(q)
            mob.walk(world.surface_position(q))
            mob.duration = STEP[_phase(mob)] * math.hypot(q.x - here.x, q.y - here.y)
            return True
    return False


def _go_on(wildlife, mob, g: Guardian, player: WorldPos, dt: float) -> bool:
    world = wildlife.world
    phase = _phase(mob)
    g.timer -= dt
    if g.stage == "windup":
        mob.windup = max(0., g.timer)
    elif g.stage in OPENINGS:
        mob.dazed = max(0., g.timer)
    if g.timer > 0:
        return False
    direction = (player.x - mob.end.x, player.y - mob.end.y)
    if g.move == "punch" and g.stage == "windup":
        g.stage, g.timer, g.impact = "stuck", STUCK[phase], 0.
        mob.windup, mob.dazed, mob.lunge = 0., STUCK[phase], .3
        if player.grid in g.marked and abs(player.z - mob.end.z) <= 1.5:
            return wildlife._hurt(direction, "fist")
        return False
    if g.move == "slam" and g.stage == "windup":
        target = player.grid
        if math.hypot(target.x - g.arena.x, target.y - g.arena.y) > ARENA_RADIUS:
            angle = math.atan2(target.y - g.arena.y, target.x - g.arena.x)
            target = g.arena + GridPos(round(ARENA_RADIUS * math.cos(angle)), round(ARENA_RADIUS * math.sin(angle)))
        g.leap_from, g.leap_to = mob.end, world.surface_position(target)
        mob.start, mob.end, mob.progress = g.leap_from, g.leap_to, 0.
        mob.duration = AIR
        g.stage, g.timer = "air", AIR
        mob.windup = 0.
        return False
    if g.stage == "air":
        mob.start = mob.end = g.leap_to
        mob.progress, g.lift, g.impact = 1., 0., 0.
        g.rings.append(Ring(g.leap_to))
        if phase:
            g.rings.append(Ring(g.leap_to, -SECOND_RING))
        g.stage, g.timer = "landed", LANDED[phase]
        mob.dazed = LANDED[phase]
        if _flat(player, g.leap_to) <= 1.2 and abs(player.z - g.leap_to.z) <= 1.5:
            return wildlife._hurt(direction, "stomp")
        return False
    if g.move == "throw" and g.stage == "windup":
        targets = [player.grid]
        if phase:
            for _ in range(2):
                targets.append(player.grid + GridPos(g.rng.randint(-2, 2), g.rng.randint(-2, 2)))
        hand = WorldPos(mob.end.x, mob.end.y, mob.end.z + 3)
        for cell in targets:
            if cell in world.tile_map.tiles:
                g.rocks.append(Rock(hand, world.surface_position(cell), ROCK_FLIGHT[phase], ROCK_FLIGHT[phase]))
        g.stage, g.timer = "release", RELEASE
        mob.windup, mob.lunge = 0., RELEASE
        return False
    _finish(mob, g)
    return False


def _fly(wildlife, g: Guardian, player: WorldPos, dt: float) -> bool:
    damaged = False
    speed = RING_SPEED[1 if any(r.radius < 0 for r in g.rings) or len(g.rings) > 1 else 0]
    for ring in g.rings:
        before = ring.radius
        ring.radius += speed * dt
        distance = _flat(player, ring.center)
        if not ring.done and before < distance <= ring.radius:
            ring.done = True
            if abs(player.z - ring.center.z) <= 1.5 and not wildlife.airborne:
                damaged |= wildlife._hurt((player.x - ring.center.x, player.y - ring.center.y), "shockwave")
    g.rings = [ring for ring in g.rings if ring.radius < RING_REACH]
    falling = []
    for rock in g.rocks:
        rock.left -= dt
        if rock.left > 0:
            falling.append(rock)
        elif _flat(player, rock.target) <= ROCK_RADIUS and abs(player.z - rock.target.z) <= 1.5:
            damaged |= wildlife._hurt((player.x - rock.start.x, player.y - rock.start.y), "boulder")
    g.rocks = falling
    return damaged


def stance(mob) -> tuple[int, str]:
    g = mob.boss
    suffix = "+" if wrath(mob) else ""
    if mob.asleep:
        return 0, "sleep"
    if mob.flash > 0:
        return 0, "hurt"
    poses = {("punch", "windup"): "punch_ready", ("punch", "stuck"): "stuck",
             ("slam", "windup"): "crouch", ("slam", "air"): "air", ("slam", "landed"): "landed",
             ("throw", "windup"): "lift", ("throw", "release"): "throw"}
    if g is not None and (g.move, g.stage) in poses:
        pose = poses[g.move, g.stage]
        frame = int(g.timer * 12) % 2 if pose in ("stuck", "punch_ready", "crouch") else 0
        return frame, pose + suffix
    if mob.progress < 1:
        return int(mob.progress * 4) % 2, "walk" + suffix
    return 0, "idle" + suffix
