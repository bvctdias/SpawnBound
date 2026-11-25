from __future__ import annotations

import hashlib
import json
import random
from dataclasses import dataclass

from spawnbound.domain.coordinates import GridPos
from spawnbound.domain.model import ObjectKind, World, WorldObject
from spawnbound.domain.terrain import reachable_surface

ARCHIPELAGO_VERSION = 1
HOME_ID = "overworld"
ISLANDS = 2
OTHER_SIZE = 96
DOCK_MIN_SIZE = 64
NAMES = ("Ilha das Garças", "Ilha do Farol", "Ilha da Bruma", "Ilha dos Ventos", "Ilha do Coral",
         "Ilha Verde")
# O píer avança em +x ou +y para ficar visível à frente da praia.
DOCK_AXES = {"x": GridPos(1, 0), "y": GridPos(0, 1)}


@dataclass(frozen=True, slots=True)
class IslandSpec:
    space_id: str
    name: str
    seed: int
    size: int
    bearing: float

    @property
    def home(self) -> bool:
        return self.space_id == HOME_ID


def island_seed(master_seed: int, index: int) -> int:
    payload = json.dumps([ARCHIPELAGO_VERSION, master_seed, index], separators=(",", ":")).encode("ascii")
    return int.from_bytes(hashlib.blake2b(payload, digest_size=8).digest(), "big")


def archipelago(master_seed: int, home_size: int) -> tuple[IslandSpec, ...]:
    rng = random.Random(island_seed(master_seed, 0))
    names = list(NAMES)
    rng.shuffle(names)
    home = IslandSpec(HOME_ID, "Ilha principal", master_seed, home_size, 0.)
    others = tuple(IslandSpec(f"ilha-{index + 1}", names[index - 1], island_seed(master_seed, index),
                              OTHER_SIZE, rng.uniform(0., 360.))
                   for index in range(1, ISLANDS))
    return (home, *others)


def build_island(spec: IslandSpec) -> World:
    from spawnbound.domain.boss import place_arena
    from spawnbound.domain.generation import WorldGenerator
    world = WorldGenerator().generate_chunk_preview(spec.seed, spec.size, home=False, space_id=spec.space_id)
    place_arena(world)
    return world


def _is_sea(world: World, cell: GridPos) -> bool:
    if cell in world.sea_cells:
        return True
    return cell not in world.tile_map.tiles and world.tile_map.tile_at(cell) is not None


def place_dock(world: World, *, restored: bool) -> GridPos | None:
    reachable = reachable_surface(world)
    taken = set(world.objects) | set(world.portals) | {world.spawn, world.camp, world.goal}
    candidates = []
    for cell in reachable:
        if cell in taken:
            continue
        for axis, step in DOCK_AXES.items():
            behind = cell - step
            if (_is_sea(world, cell + step) and _is_sea(world, cell + step + step)
                    and behind in reachable and behind not in taken):
                across = GridPos(step.y, step.x)
                ashore = not (_is_sea(world, cell + step + across) and _is_sea(world, cell + step + step + across))
                distance = (cell.x - world.spawn.x) ** 2 + (cell.y - world.spawn.y) ** 2
                candidates.append((ashore, distance, cell.x, cell.y, axis))
    for _, _, x, y, axis in sorted(candidates)[:12]:
        cell = GridPos(x, y)
        variant = f"{'restored' if restored else 'ruined'}-{axis}"
        world.objects[cell] = WorldObject.create(cell, ObjectKind.DOCK, variant=variant,
                                                 elevation=world.elevation_at(cell))
        if reachable - {cell} <= reachable_surface(world):
            world.dock = cell
            return cell
        del world.objects[cell]
    return None


def dock_axis(dock: WorldObject) -> GridPos:
    return DOCK_AXES[dock.variant.rsplit("-", 1)[1]]


def dock_front(dock: WorldObject) -> GridPos:
    step = dock_axis(dock)
    return dock.position + step + step + GridPos(step.y, step.x)


def pier_cells(dock: WorldObject) -> frozenset[GridPos]:
    step = dock_axis(dock)
    across = GridPos(step.y, step.x)
    cells, cell = set(), dock.position
    for _ in range(4):
        cells.update((cell, cell + across))
        cell = cell + step
    return frozenset(cells)


def dock_restored(dock: WorldObject) -> bool:
    return dock.variant.startswith("restored")


def dock_landing(world: World) -> GridPos | None:
    if world.dock is None or world.dock not in world.objects:
        return None
    dock = world.objects[world.dock]
    step = dock_axis(dock)
    for cell in (world.dock - step, world.dock - step + GridPos(step.y, step.x),
                 world.dock - step - GridPos(step.y, step.x)):
        if world.is_walkable(cell) and cell not in world.objects and cell not in world.portals:
            return cell
    return None
