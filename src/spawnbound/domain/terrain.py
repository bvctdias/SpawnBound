from __future__ import annotations

from collections import deque
from dataclasses import replace
import math
import random

from spawnbound.domain.coordinates import GridPos, NEIGHBOR_DIRECTIONS
from spawnbound.domain.model import ObjectKind, Portal, SpaceKind, TileKind, World
from spawnbound.domain.noise import PerlinNoise

CARDINAL = (GridPos(1, 0), GridPos(-1, 0), GridPos(0, 1), GridPos(0, -1))


def reachable_surface(world: World, start: GridPos | None = None) -> set[GridPos]:
    start = start or world.spawn
    if not world.is_walkable(start):
        return set()
    visited = {start}
    pending = deque([start])
    while pending:
        current = pending.popleft()
        for direction in NEIGHBOR_DIRECTIONS:
            neighbor = current + direction
            if neighbor not in visited and world.can_step(current, neighbor):
                visited.add(neighbor)
                pending.append(neighbor)
    return visited


def add_exploration_relief(world: World) -> None:
    size = world.chunk_preview_size
    if size is None or size < 16:
        return
    coast = size >= 32
    rivers = _river_courses(world, size) if coast else set()
    heights, cliffs, coastal = _height_field(world, size, coast, rivers)
    water, sea, rivers = _settle_water(world, heights, coastal, rivers, size, coast)
    levels = {p: 0 if p in water else min(MAX_LEVEL, max(LAND_FLOOR, int(h))) for p, h in heights.items()}
    spawn_height = levels[world.spawn]
    for dx in range(-2, 3):
        for dy in range(-2, 3):
            levels[world.spawn + GridPos(dx, dy)] = spawn_height
    _smooth_slopes(levels, cliffs, size if coast else 0)
    _cut_ramps(levels, world.spawn)
    tiles = world.tile_map
    for p, tile in tuple(tiles.tiles.items()):
        if p in water:
            tiles.add(p, TileKind.WATER, tile.variant, tile.biome, 0)
            world.objects.pop(p, None)
        else:
            tiles.add(p, tile.kind, tile.variant, tile.biome, levels[p])
    world.sea_cells = frozenset(sea)
    world.strict_diagonals = True
    _add_portals(world, size, rivers)
    if coast:
        world.river_cells = frozenset(rivers)
        world.river_mouth = _river_mouth(rivers, size)
        if world.river_mouth is None:
            world.river_cells = frozenset()
            _add_estuary(world, size)
        world.tile_map.ocean_island_size = size
        _place_fish_refuges(world, size)
    # Remover uma pedra pode abrir um bolsão isolado. Criar uma rampa pode expor outra pedra.
    _clear_low_objects_against_higher_ground(world)
    repair_surface_connectivity(world)
    if _clear_low_objects_against_higher_ground(world):
        repair_surface_connectivity(world)
    for p, obj in world.objects.items():
        obj.elevation = world.elevation_at(p)


# Nesses três lados, o terreno alto encobre a parte do sprite que ultrapassa a célula.
OVERHANG_SIDES = (GridPos(1, -1), GridPos(1, 0), GridPos(0, 1))
LOW_WIDE_OBJECTS = (ObjectKind.ROCK, ObjectKind.BERRY_BUSH, ObjectKind.FALLEN_LOG)


def _clear_low_objects_against_higher_ground(world: World) -> int:
    removed = [p for p, obj in world.objects.items()
               if obj.kind in LOW_WIDE_OBJECTS and overhangs_higher_ground(world.tile_map, p)]
    for p in removed:
        world.objects.pop(p)
    return len(removed)


def overhangs_higher_ground(tile_map, position: GridPos) -> bool:
    tile = tile_map.tile_at(position)
    height = tile.elevation if tile is not None else 0
    return any((neighbor := tile_map.tile_at(position + d)) is not None
               and neighbor.elevation > height for d in OVERHANG_SIDES)


LAND_FLOOR = 1
SEA_LEVEL = 1.0
MAX_LEVEL = 7
HEIGHT_PROFILE = ((.40, .55),
                  (.53, 1.8),
                  (.60, 4.2))
MOUNTAIN_RISE = 32
DETAIL_AMPLITUDE = 6
SHORE_MEAN, SHORE_SPREAD = 2.0, 12
COAST_SLOPE, CLIFF_COAST_SLOPE = .6, 2.5
CLIFF_THRESHOLD = .52
MIN_LAKE_CELLS = 6
LAKE_SHARE = .08
MIN_ISLET_CELLS = 16


BASE_CLEAR, BASE_EDGE = 9.5, 15.5
BASE_HEIGHT = 2.5


def base_clearing(position: GridPos, centre: GridPos, seed: int) -> float:
    dx, dy = position.x - centre.x, position.y - centre.y
    angle = math.atan2(dy, dx)
    phase = (seed % 6283) / 1000
    wobble = 1 + .10 * math.sin(3 * angle + phase) + .05 * math.sin(5 * angle - 2 * phase)
    distance = math.hypot(dx, dy) / wobble
    return max(0.0, min(1.0, (BASE_EDGE - distance) / (BASE_EDGE - BASE_CLEAR)))


MILL_OFFSET = GridPos(-12, -12)
MILL_TOP, MILL_TERRACE, MILL_RISE = 3.5, 2.0, 3
MILL_FOOT = MILL_TOP + MILL_TERRACE * (MILL_RISE - 1)
MILL_SKIRT = MILL_FOOT + 3
MILL_MIN_SIZE = 96


def mill_site(spawn: GridPos, size: int | None) -> GridPos | None:
    return spawn + MILL_OFFSET if size is not None and size >= MILL_MIN_SIZE else None


def mill_distance(position: GridPos, site: GridPos | None) -> float:
    if site is None:
        return math.inf
    return math.hypot(position.x - site.x, position.y - site.y)


def mill_rise(distance: float) -> int:
    if distance <= MILL_TOP:
        return MILL_RISE
    return max(0, MILL_RISE - math.ceil((distance - MILL_TOP) / MILL_TERRACE))


def profile_height(value: float) -> float:
    for limit, height in HEIGHT_PROFILE:
        if value < limit:
            return height
    limit, height = HEIGHT_PROFILE[-1]
    return height + (value - limit) * MOUNTAIN_RISE


RIVER_WIDTH = 1.1
BRANCH_WIDTH = .6
RIVER_SHARE = .04
INTERIOR_SHARE = .12
RIVER_SLOPE, CLIFF_RIVER_SLOPE = .8, 2.2


def _river_courses(world: World, size: int) -> set[GridPos]:
    tiles = world.tile_map.tiles
    main_field = PerlinNoise(world.seed ^ 0x52495645)
    branch_field = PerlinNoise(world.seed ^ 0x4252414E)
    main = {p: main_field.fractal(p.x + 19.7, p.y + 263.1, scale=56, octaves=2) for p in tiles}
    branch = {p: branch_field.fractal(p.x + 141.9, p.y + 7.3, scale=30, octaves=1) for p in tiles}

    def near_half(field, p, width):
        # Dividir pela inclinação local mantém a largura do rio onde o ruído varia devagar.
        east, west = field.get(p + CARDINAL[0], field[p]), field.get(p + CARDINAL[1], field[p])
        south, north = field.get(p + CARDINAL[2], field[p]), field.get(p + CARDINAL[3], field[p])
        slope = math.hypot((east - west) / 2, (south - north) / 2)
        return abs(field[p] - .5) < width * max(slope, 1e-4)

    blocked = _protected_cells(world, size)
    mill = mill_site(world.spawn, size) if world.home_island else None
    bands, branches = set(), set()
    for p in tiles:
        if (p in blocked or base_clearing(p, world.spawn, world.seed) > 0
                or mill_distance(p, mill) <= MILL_SKIRT + 2):
            continue
        if near_half(main, p, RIVER_WIDTH):
            bands.add(p)
        elif near_half(branch, p, BRANCH_WIDTH):
            branches.add(p)
    budget = RIVER_SHARE * len(world.tile_map.tiles)
    rivers: set[GridPos] = set()
    by_length = lambda piece: (-len(piece), min(piece))
    for piece in sorted(_components(bands, CARDINAL), key=by_length):
        reaches_sea = any(min(p.x, p.y, size - 1 - p.x, size - 1 - p.y) == 0 for p in piece)
        if reaches_sea and len(piece) >= 24 and len(rivers) + len(piece) <= budget:
            rivers |= piece
    for piece in sorted(_components(branches, CARDINAL), key=by_length):
        joins = any(p + d in rivers for p in piece for d in CARDINAL)
        if joins and len(piece) >= 8 and len(rivers) + len(piece) <= budget:
            rivers |= piece
    return rivers


def _distance_field(cells: set[GridPos], limit: int) -> dict[GridPos, int]:
    distance = dict.fromkeys(cells, 0)
    pending = deque(cells)
    while pending:
        p = pending.popleft()
        step = distance[p] + 1
        if step > limit:
            continue
        for d in NEIGHBOR_DIRECTIONS:
            q = p + d
            if q not in distance:
                distance[q] = step
                pending.append(q)
    return distance


def _river_mouth(rivers: set[GridPos], size: int) -> GridPos | None:
    best = None
    for piece in _components(rivers, CARDINAL):
        border = sorted(p for p in piece if min(p.x, p.y, size - 1 - p.x, size - 1 - p.y) == 0)
        if border and (best is None or len(piece) > best[0]):
            best = (len(piece), border[len(border) // 2])
    return best[1] if best else None


def _height_field(world: World, size: int, coast: bool,
                  rivers: set[GridPos] = frozenset()) -> tuple[dict[GridPos, float], set[GridPos], set[GridPos]]:
    base = PerlinNoise(world.seed ^ 0x50524F46)
    detail = PerlinNoise(world.seed ^ 0x484549474854)
    shore = PerlinNoise(world.seed ^ 0x434F415354)
    cliff = PerlinNoise(world.seed ^ 0x434C494646)
    protected = _protected_cells(world, size)
    valley = _distance_field(rivers, 9)
    mill = mill_site(world.spawn, size) if coast and world.home_island else None
    heights, cliffs, coastal = {}, set(), set()
    for p in world.tile_map.tiles:
        x, y = p.x, p.y
        h = (profile_height(base.fractal(x + 211.4, y + 97.1, scale=44, octaves=2))
             + (detail.fractal(x + 57.3, y + 83.7, scale=14, octaves=2) - .5) * DETAIL_AMPLITUDE)
        clearing = base_clearing(p, world.spawn, world.seed) if coast else 0.0
        h += (BASE_HEIGHT - h) * clearing
        to_mill = mill_distance(p, mill)
        sheer = (not clearing and to_mill > MILL_SKIRT
                 and cliff.fractal(x + 5.9, y + 301.3, scale=12, octaves=1) > CLIFF_THRESHOLD)
        if sheer:
            cliffs.add(p)
        edge = min(x, y, size - 1 - x, size - 1 - y)
        if coast and edge < 24:
            line = SHORE_MEAN + (shore.fractal(x + 33.3, y + 12.9, scale=10, octaves=2) - .5) * SHORE_SPREAD
            cap = SEA_LEVEL + (edge - line) * (CLIFF_COAST_SLOPE if sheer else COAST_SLOPE)
            if cap < SEA_LEVEL:
                coastal.add(p)
            h = min(h, cap)
        steps = valley.get(p)
        if steps is not None:
            h = min(h, SEA_LEVEL + (steps - .6) * (CLIFF_RIVER_SLOPE if sheer else RIVER_SLOPE))
        if to_mill <= MILL_FOOT:
            h = BASE_HEIGHT + mill_rise(to_mill)
            coastal.discard(p)
        elif to_mill < MILL_SKIRT:
            h += (BASE_HEIGHT - h) * (MILL_SKIRT - to_mill) / (MILL_SKIRT - MILL_FOOT)
            h = max(h, BASE_HEIGHT - max(0.0, to_mill - MILL_FOOT - 1))
        if p in protected:
            h = max(h, SEA_LEVEL + .5)
            coastal.discard(p)
        heights[p] = h
    return heights, cliffs, coastal


def _protected_cells(world: World, size: int) -> set[GridPos]:
    protected = {world.spawn + GridPos(dx, dy) for dx in range(-4, 5) for dy in range(-4, 5)}
    protected.add(world.camp)
    for site, _kind, _label in _portal_sites(world, size):
        protected |= {site + GridPos(dx, dy) for dx in range(-2, 3) for dy in range(-2, 3)}
    return protected


def _settle_water(world: World, heights: dict[GridPos, float], coastal: set[GridPos], rivers: set[GridPos],
                  size: int, coast: bool) -> tuple[set[GridPos], set[GridPos], set[GridPos]]:
    water = {p for p, h in heights.items() if h < SEA_LEVEL}
    rivers = rivers & water
    rim = set()
    if coast:
        rim = {p for p in water - coastal - rivers
               if min(p.x, p.y, size - 1 - p.x, size - 1 - p.y) == 0
               or any(p + d in coastal for d in NEIGHBOR_DIRECTIONS)}
        water -= rim

    def sea_of(water):
        open_water = water - rivers
        border = {p for p in open_water if min(p.x, p.y, size - 1 - p.x, size - 1 - p.y) == 0}
        return _flood_many(border, open_water, CARDINAL) if coast else set()

    lakes = sorted(_components(water - sea_of(water) - rivers, CARDINAL),
                   key=lambda lake: (-len(lake), min(lake)))
    room = min(LAKE_SHARE, INTERIOR_SHARE - .005 - len(rivers) / len(heights)) * len(heights)
    kept = 0
    for lake in lakes:
        if len(lake) < MIN_LAKE_CELLS or kept + len(lake) > room:
            water -= lake
        else:
            kept += len(lake)
    while True:
        pieces = _components(set(heights) - water, CARDINAL)
        main = next(piece for piece in pieces if world.spawn in piece)
        stranded = sorted((piece for piece in pieces if piece is not main), key=min)
        if not stranded:
            break
        for piece in stranded:
            keep = len(piece) >= MIN_ISLET_CELLS or piece & rim
            bar = _water_path(piece, main, water) if keep else []
            if bar:
                water -= set(bar)
                main |= piece | set(bar)
            else:
                water |= piece
    for p in set(heights) - water:
        heights[p] = max(heights[p], SEA_LEVEL)
    return water, sea_of(water), rivers & water


def _water_path(starts: set[GridPos], goal: set[GridPos], water: set[GridPos]) -> list[GridPos]:
    previous: dict[GridPos, GridPos | None] = {}
    pending = deque()
    for p in sorted(starts):
        for d in CARDINAL:
            if (q := p + d) in water and q not in previous:
                previous[q] = None
                pending.append(q)
    while pending:
        p = pending.popleft()
        if any(p + d in goal for d in CARDINAL):
            path = []
            while p is not None:
                path.append(p)
                p = previous[p]
            return path
        for d in CARDINAL:
            if (q := p + d) in water and q not in previous:
                previous[q] = p
                pending.append(q)
    return []


def _smooth_slopes(levels: dict[GridPos, int], cliffs: set[GridPos], size: int) -> None:
    pending = deque(p for p, level in levels.items() if level > LAND_FLOOR)
    while pending:
        p = pending.popleft()
        level = levels[p]
        if level <= LAND_FLOOR:
            continue
        sheer = p in cliffs
        cap = level
        for d in CARDINAL:
            q = p + d
            other = levels.get(q)
            if other is None:
                if not size:
                    continue
                other, shared = 0, sheer
            else:
                shared = sheer and q in cliffs
            if not shared and other + 1 < cap:
                cap = other + 1
        cap = max(cap, LAND_FLOOR)
        if cap < level:
            levels[p] = cap
            pending.extend(q for d in CARDINAL if (q := p + d) in levels)


def _terrace_flood(levels: dict[GridPos, int], start: GridPos,
                   reached: set[GridPos] | None = None) -> set[GridPos]:
    reached = reached if reached is not None else set()
    reached.add(start)
    pending = deque([start])
    while pending:
        p = pending.popleft()
        level = levels[p]
        for d in CARDINAL:
            q = p + d
            other = levels.get(q)
            if other and q not in reached and abs(other - level) <= 1:
                reached.add(q)
                pending.append(q)
    return reached


def _cut_ramps(levels: dict[GridPos, int], start: GridPos, attempts: int = 48) -> None:
    land = {p for p, level in levels.items() if level}
    reached = _terrace_flood(levels, start)
    for _ in range(attempts):
        best = None
        for p in land - reached:
            level = levels[p]
            for d in CARDINAL:
                q = p + d
                if q in reached:
                    key = (abs(level - levels[q]), p, q)
                    if best is None or key < best:
                        best = key
        if best is None:
            return
        _, p, q = best
        step = p - q
        side = GridPos(-step.y, step.x)
        rise = 1 if levels[p] > levels[q] else -1
        cell, target = p, levels[q] + rise
        needs = lambda c: c not in reached and levels.get(c, 0) and (levels[c] - target) * rise > 0
        while needs(cell):
            for c in (cell, cell + side):
                if needs(c):
                    levels[c] = target
            cell += step
            target += rise
        _terrace_flood(levels, q, reached)


def _add_estuary(world: World, size: int) -> None:
    tiles = world.tile_map.tiles
    land = {p for p, tile in tiles.items() if tile.kind is TileKind.GRASS}
    protected = {world.spawn, world.camp, world.goal, *world.portals}
    rng = random.Random(world.seed ^ 0x45535455)
    length = min(14, size // 5)
    # O limite dos lagos considera só a água doce dentro da ilha.
    budget = int(len(tiles) * .12) - (len(tiles) - len(land) - len(world.sea_cells))
    candidates = []
    for _ in range(64):
        direction = rng.choice(CARDINAL)
        side = GridPos(-direction.y, direction.x)
        coast = rng.randrange(length, size - length)
        mouth = GridPos(0 if direction.x == 1 else size-1 if direction.x == -1 else coast,
                        0 if direction.y == 1 else size-1 if direction.y == -1 else coast)
        channel = set()
        p = mouth
        for i in range(length):
            channel.update((p, p + side))
            p += direction
            if i % 3 == 2:
                p += rng.choice((GridPos(0, 0), side, GridPos(-side.x, -side.y)))
        cut = channel & land
        if len(cut) < length or len(cut) > budget or any(
            max(abs(p.x-q.x), abs(p.y-q.y)) <= 4 for p in cut for q in protected
        ):
            continue
        banks = {q for p in channel for d in CARDINAL if (q := p + d) in land and q not in channel
                 and tiles[q].elevation == 1 and world.is_walkable(q)}
        if not banks:
            continue
        bank_distance = min(abs(q.x-mouth.x) + abs(q.y-mouth.y) for q in banks)
        cost = sum(tiles[p].elevation for p in cut) / len(cut) + bank_distance
        if tiles[p].kind is TileKind.WATER:
            cost -= .5
        candidates.append((cost, mouth, channel))
    for _, mouth, channel in sorted(candidates, key=lambda candidate: candidate[0]):
        cut = channel & land
        remaining = land - cut
        if len(_flood(world.spawn, remaining, CARDINAL)) != len(remaining):
            continue
        for p in cut:
            tile = tiles[p]
            world.tile_map.add(p, TileKind.WATER, tile.variant, tile.biome, 0)
            world.objects.pop(p, None)
        world.river_mouth = mouth
        world.river_cells = frozenset(channel)
        return
    existing = sorted(p for p, tile in tiles.items() if tile.kind is TileKind.WATER
                      and (p.x in (0, size-1) or p.y in (0, size-1)))
    if existing:
        world.river_mouth = rng.choice(existing)


def _place_fish_refuges(world: World, size: int) -> None:
    rng = random.Random(world.seed ^ 0xF157)

    def add(home, direction):
        for step in range(4):
            p = GridPos(home.x + direction.x * step, home.y + direction.y * step)
            tile = world.tile_map.tile_at(p)
            if tile is None or tile.kind is not TileKind.WATER or tile.deep_water:
                return False
        if any((p.x-home.x)**2 + (p.y-home.y)**2 < 36 for p in world.fish_refuges):
            return False
        world.fish_refuges[home] = direction
        return True

    mouth = world.river_mouth
    if mouth is not None:
        if mouth.x in (0, size - 1):
            sea = GridPos(-1 if mouth.x == 0 else 1, 0)
        else:
            sea = GridPos(0, -1 if mouth.y == 0 else 1)
        add(mouth + sea + sea + sea, sea)
        def river_view(p):
            cover = 0
            for dx in range(-1, 6):
                for dy in range(max(-1, dx-1), min(6, dx+2)):
                    if dx+dy <= 0:
                        continue
                    q = GridPos(p.x+dx, p.y+dy)
                    obj = world.objects.get(q)
                    height = world.elevation_at(q)*10 + (48 if obj and obj.kind is ObjectKind.TREE else 0)
                    if height >= (dx+dy)*8:
                        cover += 1
            return cover, -abs(p.x-mouth.x)-abs(p.y-mouth.y), p

        for home in sorted(world.river_cells, key=river_view):
            if any(add(home, d) for d in CARDINAL):
                break
    for offset in range(8, size - 3, 28):
        for side in CARDINAL:
            along = min(size - 4, offset + rng.randrange(7))
            depth = rng.randrange(5, 9)
            cross = -depth if side.x + side.y < 0 else size-1 + depth
            home = GridPos(cross, along) if side.x else GridPos(along, cross)
            add(home, GridPos(-side.y, side.x))
    tiles = world.tile_map.tiles
    lake_water = {p for p, tile in tiles.items() if tile.kind is TileKind.WATER
                  and p not in world.sea_cells and p not in world.river_cells}
    for lake in sorted(_components(lake_water, CARDINAL), key=lambda lake: (-len(lake), min(lake))):
        if len(lake) < LAKE_REFUGE_CELLS:
            break
        cx = sum(p.x for p in lake) / len(lake)
        cy = sum(p.y for p in lake) / len(lake)
        shore = {p for p in lake if any(p + d not in lake_water and p + d in tiles for d in CARDINAL)}
        inner = sorted(p for p in lake - shore if any(p + d in shore for d in CARDINAL))
        for home in inner:
            toward = sorted(CARDINAL, key=lambda d: -((cx - home.x) * d.x + (cy - home.y) * d.y))
            if add(home, toward[0]):
                break


LAKE_REFUGE_CELLS = 40


def _flood(start: GridPos, cells: set[GridPos], directions) -> set[GridPos]:
    return _flood_many({start} & cells, cells, directions)


def _flood_many(starts: set[GridPos], cells: set[GridPos], directions) -> set[GridPos]:
    visited = set(starts)
    pending = deque(starts)
    while pending:
        current = pending.popleft()
        for direction in directions:
            neighbor = current + direction
            if neighbor in cells and neighbor not in visited:
                visited.add(neighbor)
                pending.append(neighbor)
    return visited


def _components(cells: set[GridPos], directions) -> list[set[GridPos]]:
    remaining = set(cells)
    components = []
    while remaining:
        component = _flood(next(iter(remaining)), remaining, directions)
        remaining -= component
        components.append(component)
    return components


def _portal_sites(world: World, size: int) -> tuple[tuple[GridPos, SpaceKind, str], ...]:
    distance = min(7, size // 2 - 3)
    sites = [(world.spawn + GridPos(0, distance), SpaceKind.INTERIOR, "ABRIGO")] if world.home_island else []
    if size < MINE_MIN_SIZE:
        sites.insert(0, (world.spawn + GridPos(distance, 0), SpaceKind.CAVE, "MINA"))
    return tuple(sites)


def _add_portals(world: World, size: int, rivers: set[GridPos] = frozenset()) -> None:
    for p, kind, label in _portal_sites(world, size):
        if kind is SpaceKind.CAVE:
            _carve_mine_entrance(world, p)
            continue
        height = world.elevation_at(p)
        approach = p + GridPos(0, 1)
        portal_id = f"{kind.value}@{p.x},{p.y},{height}"
        world.portals[p] = Portal(portal_id, p, approach,
                                 f"{world.space_id}/{portal_id}", kind, label)
        for dx in range(-1, 2):
            for dy in range(-1, 2):
                q = p + GridPos(dx, dy)
                tile = world.tile_map.tiles[q]
                world.tile_map.add(q, tile.kind, tile.variant, tile.biome, height)
                world.objects.pop(q, None)
        for d in SHELTER_VIEW:
            if (obj := world.objects.get(p + d)) is not None and obj.kind in TALL_OBJECTS:
                world.objects.pop(p + d)
    if size >= MINE_MIN_SIZE:
        site = _mine_site(world, size, rivers)
        _carve_mine_entrance(world, site or world.spawn + GridPos(min(7, size // 2 - 3), 0))


MINE_NEAR, MINE_FAR = 22, 46
MINE_MIN_SIZE = 96
MINE_PAD = tuple(GridPos(dx, dy) for dx in range(-3, 3) for dy in range(-2, 3))
# Uma copa nessas células pode esconder a entrada da mina na projeção isométrica.
MINE_VIEW = tuple(GridPos(dx, dy) for dx in range(0, 8) for dy in range(-4, 8)
                  if 0 <= dx + dy <= 9 and abs(16 * (dx - dy) + 8) <= 40 and (dx, dy) != (0, 0))
TALL_OBJECTS = (ObjectKind.TREE, ObjectKind.CACTUS)
SHELTER_VIEW = tuple(GridPos(dx, dy) for dx in range(-2, 9) for dy in range(-2, 9)
                     if 1 <= dx + dy <= 10 and abs(16 * (dx - dy)) <= 64)


def _mine_site(world: World, size: int, rivers: set[GridPos]) -> GridPos | None:
    tiles = world.tile_map.tiles
    mill = mill_site(world.spawn, size)
    tall = {p for p, obj in world.objects.items() if obj.kind in TALL_OBJECTS}
    candidates = []
    for p in sorted(tiles):
        if p.x % 2 or p.y % 2:
            continue
        if not MINE_NEAR <= math.hypot(p.x - world.spawn.x, p.y - world.spawn.y) <= MINE_FAR:
            continue
        if mill_distance(p, mill) < MILL_SKIRT + 5:
            continue
        level = tiles[p].elevation
        if tiles[p].kind is TileKind.WATER or level < LAND_FLOOR or level + 2 > MAX_LEVEL:
            continue
        pad = [p + d for d in MINE_PAD]
        if any(q not in tiles or q in rivers or q in world.portals or tiles[q].kind is TileKind.WATER
               or abs(tiles[q].elevation - level) > 1 for q in pad):
            continue
        view = [p + d for d in MINE_VIEW]
        if any(q in tiles and tiles[q].kind is not TileKind.WATER and tiles[q].elevation > level for q in view):
            continue
        candidates.append((sum(q in tall for q in view), p))
    if not candidates:
        return None
    fewest = min(cover for cover, _p in candidates)
    pool = [p for cover, p in candidates if cover <= fewest + 1]
    return random.Random(world.seed ^ 0x4D494E41).choice(pool)


def _carve_mine_entrance(world: World, p: GridPos) -> None:
    tiles = world.tile_map
    level = world.elevation_at(p)

    def put(q: GridPos, height: int) -> None:
        tile = tiles.tiles[q]
        kind = TileKind.GRASS if tile.kind is TileKind.WATER else tile.kind
        tiles.add(q, kind, tile.variant, tile.biome, height)

    for d in MINE_PAD:
        put(p + d, level)
        world.objects.pop(p + d, None)
    for dy in (-1, 0, 1):
        put(p + GridPos(-1, dy), level + 2)
        put(p + GridPos(-2, dy), level + 1)
    for d in MINE_VIEW:
        world.objects.pop(p + d, None)
    portal_id = f"{SpaceKind.CAVE.value}@{p.x},{p.y},{level}"
    world.portals[p] = Portal(portal_id, p, p + GridPos(1, 0),
                             f"{world.space_id}/{portal_id}", SpaceKind.CAVE, "MINA")


def repair_surface_connectivity(world: World) -> None:
    while True:
        walkable = {p for p in world.tile_map.tiles if world.is_walkable(p)}
        reachable = reachable_surface(world)
        disconnected = walkable - reachable
        if not disconnected:
            return
        blockers = {p + d for p in disconnected for d in NEIGHBOR_DIRECTIONS
                    if (obj := world.object_at(p + d)) is not None and obj.blocks_movement}
        if blockers:
            for p in sorted(blockers):
                world.objects.pop(p)
            continue
        edge = next(((p, p + d) for p in sorted(disconnected) for d in CARDINAL
                     if p + d in reachable), None)
        if edge is None:
            raise RuntimeError("could not connect terrain surface")
        p, q = edge
        tile = world.tile_map.tiles[p]
        height = world.elevation_at(q)
        new_height = height + 1 if tile.elevation > height else max(0, height - 1)
        world.tile_map.tiles[p] = replace(tile, elevation=new_height)
