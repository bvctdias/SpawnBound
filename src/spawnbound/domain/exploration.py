from __future__ import annotations

from dataclasses import dataclass, field

from spawnbound.domain.coordinates import GridPos

REVEAL_RADIUS = 12
BASE_REVEAL = 15
PORTAL_REVEAL = 3
MAP_MARGIN = 6


def _disc(radius):
    return tuple((dx, dy) for dx in range(-radius, radius + 1) for dy in range(-radius, radius + 1)
                 if dx * dx + dy * dy <= radius * radius + radius)


@dataclass(slots=True)
class IslandSurvey:
    space_id: str
    size: int
    margin: int = MAP_MARGIN
    cells: bytearray = field(init=False)
    version: int = 0
    _last: GridPos | None = None

    def __post_init__(self) -> None:
        self.cells = bytearray(self.side * self.side)

    @classmethod
    def of(cls, world) -> "IslandSurvey | None":
        size = world.tile_map.ocean_island_size
        if not size:
            return None
        survey = cls(world.space_id, size)
        survey.reveal(world.spawn, BASE_REVEAL)
        for portal in world.portals.values():
            survey.reveal(portal.position, PORTAL_REVEAL)
        return survey

    @property
    def side(self) -> int:
        return self.size + 2 * self.margin

    def index(self, position: GridPos) -> int | None:
        x, y = position.x + self.margin, position.y + self.margin
        if 0 <= x < self.side and 0 <= y < self.side:
            return y * self.side + x
        return None

    def seen(self, position: GridPos) -> bool:
        i = self.index(position)
        return i is not None and bool(self.cells[i])

    def reveal(self, centre: GridPos, radius: int) -> int:
        side, cells = self.side, self.cells
        cx, cy = centre.x + self.margin, centre.y + self.margin
        new = 0
        for dx, dy in _disc(radius):
            x, y = cx + dx, cy + dy
            if 0 <= x < side and 0 <= y < side and not cells[y * side + x]:
                cells[y * side + x] = 1
                new += 1
        if new:
            self.version += 1
        return new

    def follow(self, position: GridPos) -> None:
        if position != self._last:
            self._last = position
            self.reveal(position, REVEAL_RADIUS)

    @property
    def explored_share(self) -> float:
        m, side, size = self.margin, self.side, self.size
        seen = sum(sum(self.cells[(y + m) * side + m:(y + m) * side + m + size]) for y in range(size))
        return seen / (size * size)
