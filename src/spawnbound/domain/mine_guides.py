from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

from spawnbound.domain.coordinates import GridPos, NEIGHBOR_DIRECTIONS, WorldPos

if TYPE_CHECKING:
    from spawnbound.domain.model import World


@dataclass(slots=True)
class MineGuides:
    toward_exit: dict[GridPos, GridPos] = field(default_factory=dict)
    influence: dict[GridPos, dict[GridPos, float]] = field(default_factory=dict)

    @classmethod
    def place(cls, world: World) -> MineGuides:
        guides = cls()
        root = world.spawn
        # A distância segue os túneis. Duas tochas próximas na tela podem estar separadas por um abismo.
        neighbors = {p: [p + d for d in NEIGHBOR_DIRECTIONS if world.can_step(p, p + d)]
                     for p in world.tile_map.tiles if world.is_walkable(p)}
        parent = {root: next(iter(world.portals))}
        frontier = deque([root])
        covered = set()
        while frontier:
            p = frontier.popleft()
            for q in neighbors[p]:
                if q not in parent:
                    parent[q] = p
                    frontier.append(q)
            if p in covered or p in world.portals:
                continue
            guides.toward_exit[p] = parent[p] - p
            distances = {p: 0}
            nearby = deque([p])
            while nearby:
                q = nearby.popleft()
                steps = distances[q]
                if steps <= 5:
                    covered.add(q)
                t = min(1.0, (9 - steps) / 6)
                guides.influence.setdefault(q, {})[p] = t * t * (3 - 2 * t)
                if steps < 8:
                    for adjacent in neighbors[q]:
                        if adjacent not in distances:
                            distances[adjacent] = steps + 1
                            nearby.append(adjacent)
        for rock in world.objects:
            levels = guides.influence.setdefault(rock, {})
            for d in NEIGHBOR_DIRECTIONS:
                approach = rock + d
                if not world.can_step(rock, approach):
                    continue
                for lamp, value in guides.influence.get(approach, {}).items():
                    levels[lamp] = max(levels.get(lamp, 0.0), value)
        return guides

    def nearby(self, player: WorldPos) -> dict[GridPos, float]:
        x, y = math.floor(player.x), math.floor(player.y)
        dx, dy = player.x - x, player.y - y
        result: dict[GridPos, float] = {}
        for i, wx in ((0, 1 - dx), (1, dx)):
            for j, wy in ((0, 1 - dy), (1, dy)):
                weight = wx * wy
                if weight:
                    for lamp, strength in self.influence.get(GridPos(x + i, y + j), {}).items():
                        result[lamp] = result.get(lamp, 0.0) + weight * strength
        return result
