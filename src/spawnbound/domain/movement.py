from __future__ import annotations

import math

from spawnbound.domain.coordinates import GridPos, WorldPos
from spawnbound.domain.model import World


def segment_cells(start: WorldPos, end: WorldPos) -> tuple[GridPos, ...]:
    # Um quadro pode atravessar várias células. Cruzar duas bordas ao mesmo tempo conta como uma diagonal.
    cuts = [0.0, 1.0]
    for a, b in ((start.x, end.x), (start.y, end.y)):
        if abs(b - a) < 1e-12:
            continue
        for cell in range(math.floor(min(a, b) + .5), math.floor(max(a, b) + .5)):
            t = (cell + .5 - a) / (b - a)
            if 0 < t < 1:
                cuts.append(t)
    ordered = []
    for t in sorted(cuts):
        if not ordered or t - ordered[-1] > 1e-10:
            ordered.append(t)
    cells = [start.grid]
    for a, b in zip(ordered, ordered[1:]):
        t = (a + b) / 2
        cell = WorldPos(start.x + (end.x - start.x) * t,
                        start.y + (end.y - start.y) * t, 0).grid
        if cell != cells[-1]:
            cells.append(cell)
    if end.grid != cells[-1]:
        cells.append(end.grid)
    return tuple(cells)


def segment_allowed(world: World, start: WorldPos, end: WorldPos,
                    max_height: int = 1, *, flat: bool = False, swim: bool = False) -> bool:
    if not all(math.isfinite(v) for v in (start.x, start.y, end.x, end.y)):
        return False
    cells = segment_cells(start, end)
    passable = world.player_can_enter if swim else world.is_walkable
    if any(not passable(cell) for cell in cells):
        return False
    if flat and any(world.elevation_at(cell) != world.elevation_at(cells[0]) for cell in cells):
        return False
    return all(world.can_step(a, b, max_height, swim=swim) for a, b in zip(cells, cells[1:]))


def walking_waypoints(world: World, start: WorldPos, path: tuple[GridPos, ...],
                      destination: WorldPos, max_height: int = 1, *, swim: bool = False) -> tuple[WorldPos, ...]:
    points = [world.surface_position(start.grid)]
    points.extend(world.surface_position(cell) for cell in path)
    points.append(destination)
    result = []
    anchor = start
    index = 0
    while index < len(points):
        if math.hypot(points[index].x - anchor.x, points[index].y - anchor.y) < 1e-9:
            index += 1
            continue
        chosen = index
        if not segment_allowed(world, anchor, points[index], max_height, swim=swim):
            raise ValueError("route crosses a blocked surface")
        if segment_allowed(world, anchor, points[index], max_height, flat=True, swim=swim):
            for candidate in range(index + 1, len(points)):
                if not segment_allowed(world, anchor, points[candidate], max_height, flat=True, swim=swim):
                    break
                chosen = candidate
        anchor = points[chosen]
        result.append(anchor)
        index = chosen + 1
    return tuple(result)
