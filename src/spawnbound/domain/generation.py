from __future__ import annotations

import random
from collections import Counter, deque
from dataclasses import dataclass

from spawnbound.domain.coordinates import EAST, GridPos, NEIGHBOR_DIRECTIONS
from spawnbound.domain.archipelago import DOCK_MIN_SIZE, place_dock
from spawnbound.domain.crafting import BRIDGE_RECIPE
from spawnbound.domain.noise import PerlinNoise
from spawnbound.domain.terrain import (
    MILL_FOOT,
    MILL_SKIRT,
    add_exploration_relief,
    base_clearing,
    mill_distance,
    mill_site,
    overhangs_higher_ground,
)
from spawnbound.domain.model import (
    BerryColor,
    Biome,
    BridgeSite,
    GrassVariant,
    ObjectKind,
    TileKind,
    TileMap,
    TreeVariant,
    World,
    WorldObject,
)


FOREST_PEAK = .9
FOREST_NEIGHBOURS = 1
BASE_MOISTURE = .485

@dataclass(frozen=True, slots=True)
class ValidationResult:
    valid: bool
    errors: tuple[str, ...] = ()


class WorldGenerator:
    def generate(self, seed: int) -> World:
        rng = random.Random(seed)

        for _attempt in range(50):
            world = self._build_candidate(seed, rng)
            validation = validate_world(world)
            if validation.valid:
                return world

        raise RuntimeError(f"could not generate a valid prototype world for seed {seed}")

    def generate_chunk_preview(self, seed: int, size: int = 128, *, home: bool = True,
                               space_id: str = "overworld") -> World:
        if size < 8:
            raise ValueError("chunk preview size must be at least 8")
        rng = random.Random(seed)
        climate = PerlinNoise(seed ^ 0x434C494D)
        vegetation = PerlinNoise(seed ^ 0x564547)
        tile_map = TileMap()
        center = size // 2
        spawn, camp = GridPos(center, center), (GridPos(center - 1, center) if home else None)
        goal = GridPos(size - 2, size - 2)
        objects: dict[GridPos, WorldObject] = {}
        trees: set[GridPos] = set()
        candidates = []
        mill = mill_site(spawn, size) if home else None
        for x in range(size):
            for y in range(size):
                position = GridPos(x, y)
                clearing = base_clearing(position, spawn, seed) if size >= 32 else 0.0
                to_mill = mill_distance(position, mill)
                clearing = max(clearing, min(1.0, (MILL_SKIRT - to_mill) / (MILL_SKIRT - MILL_FOOT)))
                moisture = climate.fractal(x + 137.3, y + 241.7, scale=48, octaves=2)
                moisture += (BASE_MOISTURE - moisture) * clearing
                biome = (Biome.DRY if moisture < .44 else
                         Biome.FOREST if moisture > .53 else Biome.MEADOW)
                tile_map.add(position, TileKind.GRASS, _grass_variant(seed, position), biome)
                if max(abs(x - center), abs(y - center)) <= 2 or position == goal or to_mill <= MILL_FOOT + 1:
                    continue
                density = vegetation.fractal(x + 71.2, y + 19.8, scale=18)
                base = {Biome.FOREST: .30, Biome.MEADOW: .03, Biome.DRY: .035}[biome]
                probability = base * max(.15, min(FOREST_PEAK, (density - .34) * 7)) * (1 - clearing)
                candidates.append((position, biome, probability))
        rng.shuffle(candidates)
        for position, biome, probability in candidates:
            neighbours = FOREST_NEIGHBOURS if biome is Biome.FOREST else 2
            if rng.random() < probability and _keeps_forest_permeable(position, trees, neighbours):
                trees.add(position)
                if biome is Biome.DRY:
                    variant = rng.choice(("column", "paddle"))
                    palm = desert_palm(position)
                    if palm is not None:
                        objects[position] = WorldObject.create(position, ObjectKind.TREE, variant=palm)
                    else:
                        objects[position] = WorldObject.create(position, ObjectKind.CACTUS, variant=variant)
                    continue
                variant = _tree_variant(rng)
                if biome is not Biome.FOREST and variant in (TreeVariant.PINE_DARK, TreeVariant.PINE_LIGHT):
                    variant = TreeVariant.BROADLEAF
                objects[position] = WorldObject.create(position, ObjectKind.TREE, variant=variant.value)
        blocked = set(trees)
        for position, biome, _probability in candidates:
            if position in objects:
                continue
            roll = rng.random()
            near_tree = any(position + direction in trees for direction in NEIGHBOR_DIRECTIONS)
            kind = None
            if roll < (.018 if biome is Biome.DRY else .009):
                kind = ObjectKind.ROCK
            elif roll < .023 and biome is Biome.FOREST and near_tree:
                kind = ObjectKind.FALLEN_LOG
            elif roll < (.045 if biome is Biome.FOREST else .02) and biome is not Biome.DRY:
                kind = ObjectKind.BERRY_BUSH
            if kind is None:
                continue
            if kind is not ObjectKind.BERRY_BUSH:
                if not _keeps_forest_permeable(position, blocked):
                    continue
                blocked.add(position)
            variant = "default"
            if kind is ObjectKind.ROCK and biome is Biome.DRY:
                variant = desert_rock(position)
            elif kind is ObjectKind.BERRY_BUSH:
                variant = rng.choice(tuple(BerryColor)).value
            elif kind is ObjectKind.FALLEN_LOG:
                variant = "northwest" if (position.x + position.y) % 2 else "northeast"
            objects[position] = WorldObject.create(position, kind, variant=variant)
        world = World(seed=seed, tile_map=tile_map, objects=objects, spawn=spawn, camp=camp,
                      bridge=BridgeSite(entry=goal, cells=(), exit=goal, direction=EAST, built=True),
                      goal=goal, chunk_preview_size=size, space_id=space_id, home_island=home)
        walkable = set(tile_map.tiles) - blocked
        reachable = flood_fill(spawn, walkable)
        while unreachable := walkable - reachable:
            frontier = {p + d for p in unreachable for d in NEIGHBOR_DIRECTIONS} & blocked
            if not frontier:
                raise RuntimeError("island connectivity repair failed")
            for position in sorted(frontier):
                objects.pop(position)
            blocked -= frontier
            walkable |= frontier
            reachable = flood_fill(spawn, walkable)
        add_exploration_relief(world)
        world.add_waystone(spawn + GridPos(0, -2), active=home)
        if mill is not None:
            objects[mill] = WorldObject.create(mill, ObjectKind.WINDMILL, elevation=world.elevation_at(mill))
        scatter_mushrooms(world)
        if size >= DOCK_MIN_SIZE:
            place_dock(world, restored=not home)
        return world

    def _build_candidate(self, seed: int, rng: random.Random) -> World:
        tile_map = TileMap()

        initial_tiles = {GridPos(x, y) for x in range(0, 6) for y in range(0, 6)}
        target_tiles = {GridPos(x, y) for x in range(8, 14) for y in range(-8, -2)}

        spawn = GridPos(2, 2)
        camp = GridPos(1, 2)
        bridge_entry = GridPos(5, 0)
        bridge_cells = (GridPos(6, -1), GridPos(7, -2))
        bridge_exit = GridPos(8, -3)
        goal = GridPos(11, -6)
        home_stone = spawn + GridPos(0, -2)
        far_stone = goal + GridPos(1, 0)

        protected_initial = {
            home_stone,
            spawn,
            camp,
            bridge_entry,
            GridPos(3, 1),
            GridPos(4, 0),
        }
        protected_target = {
            far_stone,
            bridge_exit,
            GridPos(9, -4),
            GridPos(10, -5),
            goal,
        }

        initial_tiles -= self._choose_edge_cuts(initial_tiles, protected_initial, rng)
        target_tiles -= self._choose_edge_cuts(target_tiles, protected_target, rng)

        for position in sorted(initial_tiles | target_tiles):
            tile_map.add(position, TileKind.GRASS, _grass_variant(seed, position))

        blocked_for_objects = protected_initial | {GridPos(5, 1), GridPos(4, 1)}
        candidates = sorted(initial_tiles - blocked_for_objects)
        object_positions = rng.sample(candidates, 7)

        objects: dict[GridPos, WorldObject] = {}
        for position in object_positions[:4]:
            objects[position] = WorldObject.create(
                position,
                ObjectKind.TREE,
                variant=_tree_variant(rng).value,
            )
        for position in object_positions[4:]:
            objects[position] = WorldObject.create(position, ObjectKind.ROCK)

        world = World(
            seed=seed,
            tile_map=tile_map,
            objects=objects,
            spawn=spawn,
            camp=camp,
            bridge=BridgeSite(
                entry=bridge_entry,
                cells=bridge_cells,
                exit=bridge_exit,
                direction=EAST,
            ),
            goal=goal,
        )
        world.add_waystone(home_stone)
        world.add_waystone(far_stone)
        return world

    @staticmethod
    def _choose_edge_cuts(
        tiles: set[GridPos],
        protected: set[GridPos],
        rng: random.Random,
    ) -> set[GridPos]:
        xs = [position.x for position in tiles]
        ys = [position.y for position in tiles]
        min_x, max_x = min(xs), max(xs)
        min_y, max_y = min(ys), max(ys)
        corners = {
            GridPos(min_x, min_y),
            GridPos(min_x, max_y),
            GridPos(max_x, min_y),
            GridPos(max_x, max_y),
        } - protected
        amount = rng.randint(1, min(3, len(corners)))
        return set(rng.sample(sorted(corners), amount))


def _grass_variant(seed: int, position: GridPos) -> GrassVariant:
    value = (
        seed * 1_103_515_245
        + position.x * 73_856_093
        + position.y * 19_349_663
    ) & 0xFFFF
    roll = value % 100
    if roll < 12:
        return GrassVariant.TALL_GRASS
    if roll < 19:
        return GrassVariant.PEBBLES
    return GrassVariant.NORMAL


def desert_palm(position: GridPos) -> str | None:
    mix = (position.x * 2246822519) ^ (position.y * 3266489917)
    if mix % 2:
        return None
    return (TreeVariant.PALM_SMALL, TreeVariant.PALM_MEDIUM, TreeVariant.PALM_TALL)[(mix // 2) % 3].value


MUSHROOM_BIOMES = {Biome.DRY: "white_mushroom", Biome.FOREST: "brown_mushroom"}
AROUND = tuple(GridPos(dx, dy) for dx in (-1, 0, 1) for dy in (-1, 0, 1) if dx or dy)


def mushroom_patch(rock: GridPos) -> tuple[str, int] | None:
    mix = ((rock.x * 1103515245) ^ (rock.y * 2654435761)) & 0xFFFFFF
    if mix % 3 == 0:
        return "group", 1 + (mix // 3) % 3
    if mix % 13 == 1:
        return "morel", 1
    return None


def scatter_mushrooms(world: World) -> None:
    tiles = world.tile_map
    reserved = {world.spawn, world.camp, world.goal}
    near_portal = {p + d for p in world.portals for d in AROUND + (GridPos(0, 0),)}
    for rock, obj in sorted(tuple(world.objects.items())):
        tile = tiles.tile_at(rock)
        if obj.kind is not ObjectKind.ROCK or tile is None or tile.biome not in MUSHROOM_BIOMES:
            continue
        patch = mushroom_patch(rock)
        if patch is None:
            continue
        kind, count = patch
        variant = MUSHROOM_BIOMES[tile.biome] if kind == "group" else "morel"
        sides = sorted(AROUND, key=lambda d: ((rock.x + d.x) * 7919 ^ (rock.y + d.y) * 104729) % 1009)
        for d in sides:
            cell = rock + d
            ground = tiles.tile_at(cell)
            if (ground is None or ground.kind is not TileKind.GRASS or ground.biome is not tile.biome
                    or ground.elevation != tile.elevation or cell in world.objects or cell in reserved
                    or cell in near_portal or overhangs_higher_ground(tiles, cell)):
                continue
            world.objects[cell] = WorldObject.create(cell, ObjectKind.MUSHROOM, variant=variant,
                                                     elevation=ground.elevation)
            count -= 1
            if count == 0:
                break


def desert_rock(position: GridPos) -> str:
    return "sandstone_coal" if ((position.x * 83492791) ^ (position.y * 2654435761)) % 4 == 0 else "sandstone"


def _keeps_forest_permeable(
    position: GridPos,
    selected: set[GridPos],
    max_neighbours: int = 2,
) -> bool:
    adjacent = sum(
        position + direction in selected
        for direction in NEIGHBOR_DIRECTIONS
    )
    if adjacent > max_neighbours:
        return False

    for offset_x in (-1, 0):
        for offset_y in (-1, 0):
            square = {
                GridPos(position.x + offset_x + dx, position.y + offset_y + dy)
                for dx in (0, 1)
                for dy in (0, 1)
            }
            if square - {position} <= selected:
                return False
    return True


def _tree_variant(rng: random.Random) -> TreeVariant:
    roll = rng.random()
    if roll < 0.31:
        return TreeVariant.PINE_DARK
    if roll < 0.60:
        return TreeVariant.PINE_LIGHT
    if roll < 0.90:
        return TreeVariant.BROADLEAF
    if roll < 0.97:
        return TreeVariant.AUTUMN_GOLD
    return TreeVariant.AUTUMN_RED


def flood_fill(
    start: GridPos,
    walkable: set[GridPos],
) -> set[GridPos]:
    if start not in walkable:
        return set()

    visited = {start}
    pending: deque[GridPos] = deque([start])
    while pending:
        current = pending.popleft()
        for direction in NEIGHBOR_DIRECTIONS:
            neighbor = current + direction
            if neighbor in walkable and neighbor not in visited:
                visited.add(neighbor)
                pending.append(neighbor)
    return visited


def validate_world(world: World) -> ValidationResult:
    errors: list[str] = []
    walkable_before_bridge = {
        position for position in world.tile_map.tiles if world.is_walkable(position)
    }
    reachable = flood_fill(world.spawn, walkable_before_bridge)

    if world.bridge.entry not in reachable:
        errors.append("bridge entry is not reachable from spawn")

    for position, world_object in world.objects.items():
        if world_object.kind is ObjectKind.WAYSTONE and not world_object.available:
            continue
        has_reachable_neighbor = any(
            position + direction in reachable for direction in NEIGHBOR_DIRECTIONS
        )
        if not has_reachable_neighbor:
            errors.append(f"object at {position} cannot be reached")
        if world_object.durability <= 0:
            errors.append(f"object at {position} has invalid durability")

    available: Counter[str] = Counter()
    for world_object in world.objects.values():
        for item_id, amount in world_object.spec.drops:
            available[item_id] += amount
    for item_id, amount in BRIDGE_RECIPE.items():
        if available[item_id] < amount:
            errors.append(f"not enough {item_id} for bridge recipe")

    if any(cell in world.tile_map.tiles for cell in world.bridge.cells):
        errors.append("bridge gap must start as void")

    walkable_after_bridge = walkable_before_bridge | set(world.bridge.cells)
    reachable_after_bridge = flood_fill(world.spawn, walkable_after_bridge)
    if world.goal not in reachable_after_bridge:
        errors.append("goal is not reachable after bridge construction")
    if any(not any(p + d in reachable_after_bridge for d in NEIGHBOR_DIRECTIONS) for p in world.waystones):
        errors.append("waystone is not reachable after bridge construction")

    return ValidationResult(valid=not errors, errors=tuple(errors))
