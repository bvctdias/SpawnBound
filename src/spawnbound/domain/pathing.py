from __future__ import annotations

import heapq
from collections import deque

from spawnbound.domain.coordinates import GridPos
from spawnbound.domain.model import OCEAN_WIDTH, World

SECTOR = 16
DIRECT_BUDGET = 600  # Limite de células exploradas antes de recorrer à busca por regiões.
STRIP = 2
_OVER_BUDGET = object()


def _octile(ax: float, ay: float, bx: float, by: float) -> float:
    dx, dy = abs(ax - bx), abs(ay - by)
    return 10 * max(dx, dy) + 4 * min(dx, dy)


class PlayerNavigation:
    def __init__(self, world: World, max_step: int, *, swim: bool = True) -> None:
        self.world = world
        self.max_step = max_step
        self.swim = swim
        self.strict = world.strict_diagonals
        cells = list(world.tile_map.tiles) + list(world.bridge.cells)
        margin = OCEAN_WIDTH if world.tile_map.ocean_island_size else 0
        # A borda bloqueada permite consultar os vizinhos sem sair do vetor.
        self.x0 = min(p.x for p in cells) - margin - 1
        self.y0 = min(p.y for p in cells) - margin - 1
        self.width = max(p.x for p in cells) + margin + 2 - self.x0
        self.rows = max(p.y for p in cells) + margin + 2 - self.y0
        w = self.width
        self.height = [-1] * (w * self.rows)
        for gy in range(1, self.rows - 1):
            for gx in range(1, w - 1):
                z = world.passable_height(GridPos(self.x0 + gx, self.y0 + gy), swim=swim)
                if z is not None:
                    self.height[gy * w + gx] = z
        self._moves = ((1, 1, 0, 10), (-1, -1, 0, 10), (w, 0, 1, 10), (-w, 0, -1, 10),
                       (w + 1, 1, 1, 14), (w - 1, -1, 1, 14), (-w + 1, 1, -1, 14), (-w - 1, -1, -1, 14))
        # A diagonal exige as duas laterais livres, então quatro direções bastam para identificar as áreas conectadas.
        self._flood_moves = self._moves[:4] if self.strict else self._moves
        self.sectors_x = -(-w // SECTOR)
        self.area = [-1] * len(self.height)
        self._sector_areas: dict[int, list[int]] = {}
        self._links: dict[int, dict[int, set[tuple[int, int]]]] = {}
        self._portals: dict[tuple[int, int], tuple[int, int]] = {}
        self._region: dict[int, int] = {}
        self._next_area = 0
        sectors = range(self.sectors_x * -(-self.rows // SECTOR))
        for sector in sectors:
            self._flood_sector(sector)
        for sector in sectors:
            self._link_sector(sector)
        self._label_regions()
        self._seen = len(world.tile_map.changes)
        self._objects_seen = len(world.objects)
        self._recheck: list[GridPos] = []

    def refresh(self, positions) -> None:
        self._recheck.extend(positions)

    def route(self, start: GridPos, goals) -> tuple[GridPos, ...] | None:
        # A rota exclui a origem. A tupla vazia indica que já chegamos e None indica destino inalcançável.
        self._sync()
        si = self._index(start)
        if si is None or self.area[si] < 0:
            return None
        region = self._region[self.area[si]]
        targets = []
        for goal in dict.fromkeys(goals):
            gi = self._index(goal)
            if gi is not None and self.area[gi] >= 0 and self._region[self.area[gi]] == region:
                targets.append(gi)
        if si in targets:
            return ()
        if not targets:
            return None
        found = self._search(si, targets, None, DIRECT_BUDGET)
        if found is _OVER_BUDGET:
            found = self._refine(si, targets, self._area_plan(si, targets))
        return self._positions(found)

    def reachable(self, start: GridPos, target: GridPos) -> bool:
        self._sync()
        si, ti = self._index(start), self._index(target)
        return (si is not None and ti is not None and self.area[si] >= 0 and self.area[ti] >= 0
                and self._region[self.area[si]] == self._region[self.area[ti]])

    def nearest_reachable(self, start: GridPos, target: GridPos,
                          radius: int | None = None) -> GridPos | None:
        self._sync()
        si = self._index(start)
        if si is None or self.area[si] < 0:
            return None
        region = self._region[self.area[si]]
        # Depois que a distância mínima de um setor supera a melhor já encontrada, a busca pode parar.
        sectors = []
        for sector in self._region_sectors[region]:
            x0, y0, x1, y1 = self._sector_bounds(sector)
            x = min(max(target.x, x0 + self.x0), x1 - 1 + self.x0)
            y = min(max(target.y, y0 + self.y0), y1 - 1 + self.y0)
            sectors.append((_octile(x, y, target.x, target.y), sector))
        best = None
        for distance, sector in sorted(sectors):
            if best is not None and distance > best[0]:
                break
            x0, y0, x1, y1 = self._sector_bounds(sector)
            for gy in range(y0, y1):
                for gx in range(x0, x1):
                    if self._region.get(self.area[gy * self.width + gx]) != region:
                        continue
                    x, y = gx + self.x0, gy + self.y0
                    if radius is not None and max(abs(target.x-x), abs(target.y-y)) > radius:
                        continue
                    to_target = _octile(x, y, target.x, target.y)
                    if best is not None and to_target > best[0]:
                        continue
                    key = (to_target, _octile(x, y, start.x, start.y), x, y)
                    if best is None or key < best:
                        best = key
        return None if best is None else GridPos(best[2], best[3])

    def _search(self, si: int, targets: list[int], allowed: set[int] | None, budget: int | None,
                cells: set[int] | None = None):
        w = self.width
        height, area, ms, strict = self.height, self.area, self.max_step, self.strict
        order = {t: k for k, t in enumerate(targets)}
        goals = [(t % w, t // w) for t in targets]
        single = len(goals) == 1
        gx, gy = goals[0]

        def estimate(i: int) -> float:
            x, y = i % w, i // w
            if single:
                dx, dy = abs(x - gx), abs(y - gy)
                return 10 * max(dx, dy) + 4 * min(dx, dy)
            return min(_octile(x, y, ax, ay) for ax, ay in goals)

        frontier = [(estimate(si), 0, si)]
        cost = {si: 0}
        previous = {si: -1}
        best = None
        expanded = 0
        while frontier:
            f, negative, i = heapq.heappop(frontier)
            here = -negative
            if best is not None and f > best[0]:
                break
            if here != cost[i]:
                continue
            if i in order:
                if single:
                    return self._trace(previous, i)
                candidate = (here, order[i], i)
                if best is None or candidate < best:
                    best = candidate
                continue
            expanded += 1
            if budget is not None and expanded > budget:
                return _OVER_BUDGET
            hi = height[i]
            for di, dx, dy, step in self._moves:
                j = i + di
                new = here + step
                if new >= cost.get(j, new + 1):
                    continue
                hj = height[j]
                if hj < 0 or hj - hi > ms or hi - hj > ms:
                    continue
                if allowed is not None and area[j] not in allowed:
                    continue
                if cells is not None and j not in cells:
                    continue
                if strict and dx and dy:
                    ha, hb = height[i + dx], height[i + dy * w]
                    if (ha < 0 or hb < 0 or abs(hi - ha) > ms or abs(hj - ha) > ms
                            or abs(hi - hb) > ms or abs(hj - hb) > ms):
                        continue
                cost[j] = new
                previous[j] = i
                if single:
                    y, x = divmod(j, w)
                    dx = x - gx if x > gx else gx - x
                    dy = y - gy if y > gy else gy - y
                    heapq.heappush(frontier, (new + (10 * dx + 4 * dy if dx > dy else 10 * dy + 4 * dx), -new, j))
                else:
                    heapq.heappush(frontier, (new + estimate(j), -new, j))
        return self._trace(previous, best[2]) if best is not None else None

    @staticmethod
    def _trace(previous: dict[int, int], end: int) -> list[int]:
        cells = []
        while previous[end] != -1:
            cells.append(end)
            end = previous[end]
        cells.reverse()
        return cells

    def _positions(self, cells) -> tuple[GridPos, ...] | None:
        if cells is None:
            return None
        w = self.width
        return tuple(GridPos(self.x0 + i % w, self.y0 + i // w) for i in cells)

    def _portal(self, a: int, b: int) -> tuple[int, int]:
        key = (a, b)
        portal = self._portals.get(key)
        if portal is None:
            w = self.width
            crossings = self._links[a][b]
            mx = sum(j % w for _i, j in crossings) / len(crossings)
            my = sum(j // w for _i, j in crossings) / len(crossings)
            j = min((j for _i, j in crossings), key=lambda j: (_octile(j % w, j // w, mx, my), j))
            portal = self._portals[key] = (j % w, j // w)
        return portal

    def _area_plan(self, si: int, targets: list[int]) -> list[int]:
        w = self.width
        first = self.area[si]
        goal_areas = {self.area[t] for t in targets}
        goals = [(t % w, t // w) for t in targets]
        start = (si % w, si // w)

        def estimate(point) -> float:
            return min(_octile(*point, x, y) for x, y in goals)

        frontier = [(estimate(start), 0.0, first)]
        cost = {first: 0.0}
        previous = {first: None}
        points = {first: start}
        while frontier:
            _f, here, a = heapq.heappop(frontier)
            if here != cost[a]:
                continue
            if a in goal_areas:
                plan = []
                while a is not None:
                    plan.append(a)
                    a = previous[a]
                plan.reverse()
                return plan
            point = points[a]
            for b in self._links[a]:
                portal = self._portal(a, b)
                new = here + _octile(*point, *portal)
                if new < cost.get(b, new + 1):
                    cost[b] = new
                    previous[b] = a
                    points[b] = portal
                    heapq.heappush(frontier, (new + estimate(portal), new, b))
        return [first]

    def _refine(self, si: int, targets: list[int], plan: list[int]) -> list[int] | None:
        cells: list[int] = []
        here = si
        for a, b in zip(plan, plan[1:]):
            entries = sorted({j for _i, j in self._links[a][b]})
            part = self._search(here, entries, {a, b}, None)
            if part is None:
                return self._search(si, targets, None, None)  # Sem passagem no plano atual, refaz a busca diretamente nas células.
            cells += part
            if part:
                here = part[-1]
        last = self._search(here, targets, {plan[-1]}, None)
        if last is None:
            return self._search(si, targets, None, None)
        cells += last
        w = self.width
        strip = set()
        for i in [si, *cells]:
            for dy in range(-STRIP, STRIP + 1):
                row = i + dy * w
                strip.update(range(row - STRIP, row + STRIP + 1))
        polished = self._search(si, targets, None, None, strip)
        return polished if polished is not None else cells

    def _sector_bounds(self, sector: int) -> tuple[int, int, int, int]:
        gx0 = (sector % self.sectors_x) * SECTOR
        gy0 = (sector // self.sectors_x) * SECTOR
        return gx0, gy0, min(gx0 + SECTOR, self.width), min(gy0 + SECTOR, self.rows)

    def _step_ok(self, i: int, j: int, dx: int, dy: int) -> bool:
        height, ms = self.height, self.max_step
        hi, hj = height[i], height[j]
        if hi < 0 or hj < 0 or abs(hi - hj) > ms:
            return False
        if self.strict and dx and dy:
            ha, hb = height[i + dx], height[i + dy * self.width]
            return not (ha < 0 or hb < 0 or abs(hi - ha) > ms or abs(hj - ha) > ms
                        or abs(hi - hb) > ms or abs(hj - hb) > ms)
        return True

    def _flood_sector(self, sector: int) -> None:
        for a in self._sector_areas.pop(sector, ()):
            for b in self._links.pop(a):
                del self._links[b][a]
                self._portals.pop((b, a), None)
                self._portals.pop((a, b), None)
        w = self.width
        gx0, gy0, gx1, gy1 = self._sector_bounds(sector)
        area = self.area
        for gy in range(gy0, gy1):
            for gx in range(gx0, gx1):
                area[gy * w + gx] = -1
        areas = []
        for gy in range(gy0, gy1):
            for gx in range(gx0, gx1):
                seed = gy * w + gx
                if area[seed] >= 0 or self.height[seed] < 0:
                    continue
                a = self._next_area
                self._next_area += 1
                area[seed] = a
                queue = deque([seed])
                while queue:
                    i = queue.popleft()
                    x, y = i % w, i // w
                    for di, dx, dy, _step in self._flood_moves:
                        j = i + di
                        if (area[j] < 0 and gx0 <= x + dx < gx1 and gy0 <= y + dy < gy1
                                and self._step_ok(i, j, dx, dy)):
                            area[j] = a
                            queue.append(j)
                areas.append(a)
                self._links[a] = {}
        self._sector_areas[sector] = areas

    def _link_sector(self, sector: int) -> None:
        w = self.width
        gx0, gy0, gx1, gy1 = self._sector_bounds(sector)
        area, links = self.area, self._links
        for gy in range(gy0, gy1):
            for gx in range(gx0, gx1):
                if not (gx in (gx0, gx1 - 1) or gy in (gy0, gy1 - 1)):
                    continue
                i = gy * w + gx
                a = area[i]
                if a < 0:
                    continue
                for di, dx, dy, _step in self._flood_moves:
                    if gx0 <= gx + dx < gx1 and gy0 <= gy + dy < gy1:
                        continue
                    j = i + di
                    b = area[j]
                    if b >= 0 and self._step_ok(i, j, dx, dy):
                        links[a].setdefault(b, set()).add((i, j))
                        links[b].setdefault(a, set()).add((j, i))
                        self._portals.pop((a, b), None)
                        self._portals.pop((b, a), None)

    def _label_regions(self) -> None:
        region: dict[int, int] = {}
        for start in self._links:
            if start in region:
                continue
            region[start] = start
            queue = deque([start])
            while queue:
                for b in self._links[queue.popleft()]:
                    if b not in region:
                        region[b] = start
                        queue.append(b)
        self._region = region
        self._region_sectors: dict[int, set[int]] = {}
        for sector, areas in self._sector_areas.items():
            for area in areas:
                self._region_sectors.setdefault(region[area], set()).add(sector)

    def _index(self, p: GridPos) -> int | None:
        gx, gy = p.x - self.x0, p.y - self.y0
        if 0 < gx < self.width - 1 and 0 < gy < self.rows - 1:
            return gy * self.width + gx
        return None

    def _sync(self) -> None:
        changes = self.world.tile_map.changes
        objects = len(self.world.objects)
        if self._seen == len(changes):
            if objects != self._objects_seen:
                self.__init__(self.world, self.max_step, swim=self.swim)
                return
            if not self._recheck:
                return
        dirty = set()
        pending = changes[self._seen:] + self._recheck
        self._recheck = []
        self._objects_seen = objects
        for p in pending:
            i = self._index(p)
            if i is None:
                continue
            z = self.world.passable_height(p, swim=self.swim)
            z = -1 if z is None else z
            if z != self.height[i]:
                self.height[i] = z
                gx, gy = p.x - self.x0, p.y - self.y0
                dirty.add((gy // SECTOR) * self.sectors_x + gx // SECTOR)
        self._seen = len(changes)
        if not dirty:
            return
        for sector in dirty:
            self._flood_sector(sector)
        for sector in dirty:
            self._link_sector(sector)
        self._label_regions()
