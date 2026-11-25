from __future__ import annotations

import heapq
import itertools
from collections.abc import Callable

from spawnbound.domain.coordinates import GridPos, NEIGHBOR_DIRECTIONS


Walkability = Callable[[GridPos], bool]
StepValidity = Callable[[GridPos, GridPos], bool]


def find_path(
    start: GridPos,
    destination: GridPos,
    is_walkable: Walkability,
    can_step: StepValidity | None = None,
) -> tuple[GridPos, ...]:
    return find_path_to_any(start, (destination,), is_walkable, can_step) or ()


def find_path_to_any(
    start: GridPos,
    destinations: tuple[GridPos, ...],
    is_walkable: Walkability,
    can_step: StepValidity | None = None,
) -> tuple[GridPos, ...] | None:
    goals = tuple(dict.fromkeys(p for p in destinations if is_walkable(p)))
    if start in goals:
        return ()
    if not goals:
        return None
    goal_order = {p: i for i, p in enumerate(goals)}

    def heuristic(p: GridPos) -> int:
        if len(goals) == 1:
            return _distance(p, goals[0])
        return min(_distance(p, goal) for goal in goals)

    order = itertools.count()
    frontier: list[tuple[int, int, int, GridPos]] = []
    heapq.heappush(frontier, (heuristic(start), 0, next(order), start))
    previous: dict[GridPos, GridPos | None] = {start: None}
    costs: dict[GridPos, int] = {start: 0}
    best: tuple[int, int, GridPos] | None = None
    walkable: dict[GridPos, bool] = {}

    while frontier:
        _priority, cost, _order, current = heapq.heappop(frontier)
        if best is not None and _priority > best[0]:
            break
        if cost != costs[current]:
            continue
        if current in goal_order:
            if len(goals) == 1:
                return _reconstruct_path(previous, current)
            candidate = (cost, goal_order[current], current)
            if best is None or candidate < best:
                best = candidate
            continue

        for direction in NEIGHBOR_DIRECTIONS:
            neighbor = current + direction
            new_cost = cost + _movement_cost(direction)
            if new_cost >= costs.get(neighbor, new_cost + 1):
                continue
            open_cell = walkable.get(neighbor)
            if open_cell is None:
                open_cell = walkable[neighbor] = is_walkable(neighbor)
            if not open_cell:
                continue
            if can_step is not None and not can_step(current, neighbor):
                continue

            costs[neighbor] = new_cost
            previous[neighbor] = current
            priority = new_cost + heuristic(neighbor)
            heapq.heappush(frontier, (priority, new_cost, next(order), neighbor))

    return _reconstruct_path(previous, best[2]) if best is not None else None


def _distance(first: GridPos, second: GridPos) -> int:
    delta_x = abs(first.x - second.x)
    delta_y = abs(first.y - second.y)
    diagonal = min(delta_x, delta_y)
    straight = max(delta_x, delta_y) - diagonal
    return diagonal * 14 + straight * 10


def _movement_cost(direction: GridPos) -> int:
    return 14 if direction.x and direction.y else 10


def _reconstruct_path(
    previous: dict[GridPos, GridPos | None],
    destination: GridPos,
) -> tuple[GridPos, ...]:
    reversed_path: list[GridPos] = []
    current: GridPos | None = destination
    while current is not None and previous[current] is not None:
        reversed_path.append(current)
        current = previous[current]
    reversed_path.reverse()
    return tuple(reversed_path)
