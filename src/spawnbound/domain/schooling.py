import math
from dataclasses import dataclass

from spawnbound.domain.coordinates import GridPos


def narrow_water(world, home):
    size = world.tile_map.ocean_island_size
    inland = 0 <= home.x < size and 0 <= home.y < size and home not in world.sea_cells
    return home in world.river_cells or inland


@dataclass(slots=True)
class SchoolVisit:
    home: GridPos | None = None
    elapsed: float = 0.0
    return_time: float = 0.0

    def advance(self, world, player, seconds):
        homes = world.fish_refuges
        if self.home not in homes:
            self.home = None
        if self.home is None:
            if not homes:
                return
            near = (((p.x-player.x)**2 + (p.y-player.y)**2, p) for p in homes)
            distance, home = min(near, default=(math.inf, None))
            if distance > 6**2:
                return
            self.home = home
            self.elapsed = self.return_time = 0.0
        away = (self.home.x-player.x)**2 + (self.home.y-player.y)**2 > 8**2
        if away or self.return_time > 0:
            self.return_time += seconds
            if self.return_time >= 1.2:
                self.home = None
        else:
            self.elapsed = (self.elapsed + seconds) % 12

    def offset(self, index, narrow, previous=False):
        dt = .02 if previous else 0
        elapsed = self.elapsed - (0 if self.return_time else dt)
        t = max(0.0, elapsed - index * .20)
        reach = min(1.0, t / 1.8, max(0.0, (9.5-t)/1.8))
        reach *= max(0.0, 1 - max(0.0, self.return_time-dt) / 1.2)
        angle = t * math.tau / 3.7 - index * .35
        length = 1.75 + .85 * math.sin(angle) + .09 * index
        spread = (.19 if narrow else .80) * math.cos(angle) + (.04 if narrow else .14) * (index-2)
        return reach * length, reach * spread
