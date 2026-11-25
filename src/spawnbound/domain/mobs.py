from __future__ import annotations

import math
import random
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum

from spawnbound.domain import boss
from spawnbound.domain.coordinates import GridPos, NEIGHBOR_DIRECTIONS, WorldPos
from spawnbound.domain.model import (DEEP_BAND, OCEAN_WIDTH, ORE_YIELDS, Biome, ObjectKind, SpaceKind, TileKind,
                                     World)
from spawnbound.domain.movement import segment_allowed
from spawnbound.domain.navigation import find_path

HERD_AREA = 600
BIOME_WEIGHT = {Biome.MEADOW: 1.0, Biome.FOREST: .5, Biome.DRY: .25}
HERD_SIZE = (2, 4)
HERD_SPACING = 9
HERD_CANDIDATES = 16
HOME_RADIUS = 5
ACTIVE_RADIUS = 40
REPLENISH_SECONDS = 40.0
NIGHT_ARCHERS = 2
MAX_ARCHERS = 3
ARCHER_SECONDS = 20.0
CHASE_RADIUS = 14
HUNT_RADIUS = 40
DESPAWN_RADIUS = 48
DEER_AREA = 500
DEER_SPACING = 10
DEER_RADIUS = 6
ANGER_SECONDS = 12.0
CALM_DISTANCE = 10
KICK_WINDUP = .45
CHARGE_WINDUP = .7
CHARGE_REACH = 5
CHARGE_STEP = .09
DAZED_SECONDS = .9
SNAKE_AREA = 400
SNAKE_DESERT = 120
SNAKE_SPACING = 8
SNAKE_RADIUS = 4
SNAKE_SIGHT = 4
STRIKE_WINDUP = .6
RECOVER_SECONDS = 1.0
SAFE_START = 16
WORM_DESERT = 150
WORM_SECOND = 600
WORM_SPACING = 16
WORM_TERRITORY = 9
WORM_DRAWS = 12
ARMADILLO_AREA = 300
ARMADILLO_SPACING = 6
ARMADILLO_RADIUS = 5
ARMADILLO_WARY = 3
WARY_PAUSE = .15
CURL_SECONDS = 3.0
BOLT_SECONDS = 2.5
SHARK_AREA = 1500
SHARK_SPACING = 14
SHARK_RADIUS = 10
SHARK_SIGHT = 7
SHARK_WINDUP = .6
SHARK_LUNGE = .45
SHARK_CIRCLE = 4.0
SHARK_RING = 2
SHARK_BITES = 3
PATROL_STEP, RUSH_STEP, CIRCLE_STEP = .7, .26, .3
ORE_VEINS = ("coal_ore", "copper_ore", "quartz_ore")
MONSTER_VEINS = 3
MONSTER_MIN = 2
MONSTER_SPACING = 8
MONSTER_SAFE = 12
MAX_MONSTERS = 6
WAKE_RADIUS = 3
GIVE_UP = 8
WAKE_PAUSE = .6
MAW_WINDUP = .5
MONSTER_REACH = 4
MONSTER_STEP = .12
MONSTER_ORE = 2
NIGHT_SPIDERS = 2
MAX_SPIDERS = 3
SPIDER_SECONDS = 20.0
SPIDER_NEAR = 10
SPIDER_FAR = 26
SPIDER_RADIUS = 6
SPIDER_SIGHT = 8
SPIDER_LOSE = 16
SPIDER_PACE = .6
LEAP_WINDUP = .55
LEAP_REACH = 3
LEAP_STEP = .07
LEAP_RECOVER = 1.0
FANG_WINDUP = .45
GLAND_CHANCE = 1 / 3

InView = Callable[[WorldPos, WorldPos], bool]


def chebyshev(a, b) -> float:
    return max(abs(a.x - b.x), abs(a.y - b.y))


class MobKind(str, Enum):
    CHICKEN = "chicken"
    PIG = "pig"
    SKELETON = "skeleton"
    DEER = "deer"
    SNAKE = "snake"
    SPIDER = "spider"
    ARMADILLO = "armadillo"
    SHARK = "shark"
    SANDWORM = "sandworm"
    MINE_MONSTER = "mine_monster"
    GUARDIAN = "guardian"


SWORD_DAMAGE = 2
HEALTH = {MobKind.CHICKEN: 2, MobKind.PIG: 4, MobKind.SKELETON: 8, MobKind.DEER: 14, MobKind.SNAKE: 6,
          MobKind.SPIDER: 10, MobKind.ARMADILLO: 6, MobKind.SANDWORM: 12, MobKind.SHARK: 1,
          MobKind.MINE_MONSTER: 16, MobKind.GUARDIAN: boss.HEALTH}
BLOW_HEARTS = {"antlers": 2, "ram": 2, "pounce": 2,
               "fist": 2, "stomp": 2, "boulder": 2}
HERD_KINDS = (MobKind.CHICKEN, MobKind.PIG)
DROPS: dict[MobKind, tuple[tuple[str, int], ...]] = {
    MobKind.CHICKEN: (("meat", 1),), MobKind.PIG: (("meat", 2),), MobKind.SKELETON: (),
    MobKind.DEER: (("venison", 2), ("hide", 1)), MobKind.SNAKE: (("snake_meat", 1),),
    MobKind.SPIDER: (("silk", 1),),
    MobKind.ARMADILLO: (("meat", 1), ("hide", 1)), MobKind.SHARK: (),
    MobKind.SANDWORM: (("sandworm_shell", 1),),
    MobKind.MINE_MONSTER: (),
    MobKind.GUARDIAN: (("quartz", 3), ("copper", 4))}
WANDER_RADIUS = {MobKind.DEER: DEER_RADIUS, MobKind.SNAKE: SNAKE_RADIUS, MobKind.SPIDER: SPIDER_RADIUS,
                 MobKind.ARMADILLO: ARMADILLO_RADIUS}
DESERT_KINDS = (MobKind.SNAKE, MobKind.ARMADILLO)


def faces_left(cell: GridPos, target) -> bool:
    return target.x - cell.x < target.y - cell.y


def toward(cell: GridPos, target: GridPos) -> GridPos:
    dx, dy = target.x - cell.x, target.y - cell.y
    return max(NEIGHBOR_DIRECTIONS, key=lambda d: (d.x*dx + d.y*dy) / math.hypot(d.x, d.y))


def distance(a, b):
    return math.hypot(a.x - b.x, a.y - b.y)


def interpolate(a: WorldPos, b: WorldPos, t: float) -> WorldPos:
    return WorldPos(a.x + (b.x-a.x)*t, a.y + (b.y-a.y)*t, a.z + (b.z-a.z)*t)


@dataclass(slots=True)
class Mob:
    id: int
    kind: MobKind
    hp: int
    start: WorldPos
    end: WorldPos
    wait: float
    progress: float = 1.0
    duration: float = .55
    shoot_in: float = 2.0
    left: bool = False
    flash: float = 0.0
    home: GridPos | None = None
    flee_time: float = 0.0
    shot_time: float = 0.0
    aiming: bool = False
    anger: float = 0.0
    attack: str = ""
    windup: float = 0.0
    lunge: float = 0.0
    dazed: float = 0.0
    charge: GridPos | None = None
    charge_left: int = 0
    loot: tuple[tuple[str, int], ...] = ()
    curled: float = 0.0
    circle: float = 0.0
    spin: int = 1
    asleep: bool = False
    vein: GridPos | None = None
    boss: object | None = None

    worm_frame: int = 0
    worm_phase: str = "rise"

    @property
    def location(self) -> WorldPos:
        return interpolate(self.start, self.end, self.progress)

    @property
    def hostile(self) -> bool:
        return (self.kind in (MobKind.SKELETON, MobKind.SNAKE, MobKind.SPIDER, MobKind.SHARK, MobKind.SANDWORM,
                              MobKind.MINE_MONSTER, MobKind.GUARDIAN)
                or self.anger > 0)

    def walk(self, destination: WorldPos) -> None:
        self.start = self.end
        self.end = destination
        self.progress = 0.0
        self.duration = .46 * distance(self.start, destination)
        self.left = destination.x - self.start.x < destination.y - self.start.y


@dataclass(slots=True)
class Arrow:
    start: WorldPos
    end: WorldPos
    duration: float
    progress: float = 0.0

    @property
    def location(self) -> WorldPos:
        return interpolate(self.start, self.end, self.progress)

    def hits(self, previous: WorldPos, player: WorldPos) -> bool:
        current = self.location
        dx, dy = current.x-previous.x, current.y-previous.y
        length2 = dx*dx + dy*dy
        t = min(1., max(0., ((player.x-previous.x)*dx + (player.y-previous.y)*dy)/length2)) if length2 else 0.
        nearest = interpolate(previous, current, t)
        return distance(nearest, player) <= .48 and abs(nearest.z-player.z) <= 1


class Wildlife:
    def __init__(self, world: World):
        self.world = world
        self.mobs: dict[int, Mob] = {}
        self.arrows: list[Arrow] = []
        self.last_hit: tuple[float, float] = (0.0, 0.0)
        self.last_blow = "arrow"
        self.rng = random.Random(world.seed ^ 0x4D4F4253)
        self.next_id = 1
        self.night_spawned = False
        self.grace = 0.
        self.in_view: InView | None = None
        self._replenish_in = REPLENISH_SECONDS
        self._archer_in = ARCHER_SECONDS
        self._spider_in = SPIDER_SECONDS
        self._night = random.Random(world.seed ^ 0x53504944)
        self._sites: list[GridPos] = []
        self._cumulative: list[float] = []
        total = 0.
        for p, tile in world.tile_map.tiles.items():
            weight = BIOME_WEIGHT.get(tile.biome, 0.) if tile.kind is TileKind.GRASS else 0.
            if weight and world.is_walkable(p) and p not in world.objects and p not in world.portals:
                total += weight
                self._sites.append(p)
                self._cumulative.append(total)
        if world.space_kind is not SpaceKind.CAVE:
            self._starter_herds(world.spawn)
        self._island_herds(round(total / HERD_AREA))
        self.target_animals = self.animal_count
        self._fauna = random.Random(world.seed ^ 0x46415541)
        spawn = world.spawn
        forest = [p for p, t in world.tile_map.tiles.items()
                  if t.kind is TileKind.GRASS and t.biome is Biome.FOREST]
        self._forest = [p for p in forest if chebyshev(p, spawn) >= SAFE_START]
        self.target_deer = round(len(forest) / DEER_AREA) if self._forest else 0
        self._deserts: list[tuple[list[GridPos], int]] = []
        self._armadillo_target: list[int] = []
        self._desert_of: dict[GridPos, int] = {}
        self._worm_id: int | None = None
        self._worm_previous: WorldPos | None = None
        self._worm_quiet = 0.
        self._lairs: list[tuple[GridPos, int]] = []
        self._lair_hp: dict[int, int] = {}
        self._lair_dead: set[int] = set()
        self._worm_lair: int | None = None
        worms: list[int] = []
        for region in self._dry_regions():
            if len(region) < SNAKE_DESERT:
                continue
            cells = [p for p in region if chebyshev(p, spawn) >= SAFE_START]
            index = len(self._deserts)
            self._deserts.append((cells, -(-len(region) // SNAKE_AREA) if cells else 0))
            self._armadillo_target.append(-(-len(region) // ARMADILLO_AREA) if cells else 0)
            self._desert_of.update(dict.fromkeys(region, index))
            worms.append(2 if len(region) >= WORM_SECOND else 1 if len(region) >= WORM_DESERT else 0)
        self._place_lairs(worms, spawn)
        for _ in range(self.target_deer):
            self._place_deer(lambda p: True)
        for index, (_, target) in enumerate(self._deserts):
            for _ in range(target):
                self._place_snake(index, lambda p: True)
        self._burrow = random.Random(world.seed ^ 0x54415455)
        for index, target in enumerate(self._armadillo_target):
            for _ in range(target):
                self._place_armadillo(index, lambda p: True)
        self._sea = random.Random(world.seed ^ 0x5348524B)
        self.shark_bites = 0
        self.dragging: Mob | None = None
        sea = self._swimmable_sea()
        for _ in range(round(len(sea) / SHARK_AREA)):
            self._place_shark(sea)
        self._lair = random.Random(world.seed ^ 0x4D4F4E53)
        self.woke: Mob | None = None
        if world.space_kind is SpaceKind.CAVE:
            self._place_monsters()
        self.airborne = False
        boss.spawn(self)
        Wildlife.attribute_names = frozenset(vars(self))

    def __getstate__(self) -> dict:
        # A câmera depende da janela atual e precisa ser associada de novo ao carregar a partida.
        state = self.__dict__.copy()
        state["in_view"] = None
        return state

    @property
    def animal_count(self) -> int:
        return sum(m.kind in HERD_KINDS for m in self.mobs.values())

    @property
    def deer_count(self) -> int:
        return sum(m.kind is MobKind.DEER for m in self.mobs.values())

    def snakes_in(self, desert: int) -> int:
        return sum(m.kind is MobKind.SNAKE and self._desert_of.get(m.home) == desert for m in self.mobs.values())

    def armadillos_in(self, desert: int) -> int:
        return sum(m.kind is MobKind.ARMADILLO and self._desert_of.get(m.home) == desert
                   for m in self.mobs.values())

    @property
    def archer_count(self) -> int:
        return sum(m.kind is MobKind.SKELETON for m in self.mobs.values())

    @property
    def spider_count(self) -> int:
        return sum(m.kind is MobKind.SPIDER for m in self.mobs.values())

    def _occupied(self) -> set[GridPos]:
        world = self.world
        occupied = {m.end.grid for m in self.mobs.values()} | set(world.objects) | set(world.portals)
        occupied.update((world.camp, world.goal))
        return occupied

    def _add(self, kind: MobKind, cell: GridPos, home: GridPos | None, rng: random.Random | None = None) -> None:
        pos = self.world.surface_position(cell)
        self.mobs[self.next_id] = Mob(self.next_id, kind, HEALTH[kind], pos, pos,
                                      (rng or self.rng).uniform(.5, 2), home=home)
        self.next_id += 1

    def _spawn_herd(self, home: GridPos, kind: MobKind, count: int, occupied: set[GridPos]) -> int:
        world = self.world
        cells = [home + GridPos(dx, dy) for dx in range(-2, 3) for dy in range(-2, 3)]
        self.rng.shuffle(cells)
        cells.sort(key=lambda q: chebyshev(q, home))
        placed = 0
        for q in cells:
            if placed == count:
                break
            if (q in occupied or not world.is_walkable(q)
                    or abs(world.elevation_at(q) - world.elevation_at(home)) > 1):
                continue
            self._add(kind, q, home)
            occupied.add(q)
            placed += 1
        return placed

    def _starter_herds(self, center: GridPos) -> None:
        world = self.world
        occupied = self._occupied() | {center}
        queue = deque([(center, 0)])
        seen = {center}
        sites = []
        while queue:
            p, steps = queue.popleft()
            if steps >= 3 and p not in occupied:
                sites.append(p)
            if steps >= 9:
                continue
            for d in NEIGHBOR_DIRECTIONS:
                q = p + d
                if q not in seen and world.can_step(p, q):
                    seen.add(q)
                    queue.append((q, steps + 1))
        self.rng.shuffle(sites)
        homes: list[GridPos] = []
        for kind in (MobKind.CHICKEN, MobKind.PIG):
            free = [s for s in sites if s not in occupied]
            if not free:
                return
            home = next((s for s in free if all(chebyshev(s, h) >= 4 for h in homes)), free[0])
            homes.append(home)
            for site in sorted(free, key=lambda s: chebyshev(s, home))[:2]:
                self._add(kind, site, home)
                occupied.add(site)

    def _herd_home(self, homes: list[GridPos], accept) -> GridPos | None:
        best, best_gap = None, -1.
        for home in self.rng.choices(self._sites, cum_weights=self._cumulative, k=HERD_CANDIDATES):
            if not accept(home):
                continue
            gap = min((chebyshev(home, h) for h in homes), default=math.inf)
            if gap >= HERD_SPACING and gap > best_gap:
                best, best_gap = home, gap
        return best

    def _island_herds(self, count: int) -> None:
        if not self._sites or count <= 0:
            return
        occupied = self._occupied()
        homes = [m.home for m in self.mobs.values() if m.home is not None]
        spawn = self.world.spawn
        for _ in range(count * 3):
            if count <= 0:
                break
            home = self._herd_home(homes, lambda h: h not in occupied and chebyshev(h, spawn) >= 12)
            if home is None:
                continue
            kind = self.rng.choice((MobKind.CHICKEN, MobKind.PIG))
            if self._spawn_herd(home, kind, self.rng.randint(*HERD_SIZE), occupied):
                homes.append(home)
                count -= 1

    def _dry_regions(self) -> list[list[GridPos]]:
        dry = {p for p, t in self.world.tile_map.tiles.items() if t.kind is TileKind.GRASS and t.biome is Biome.DRY}
        regions = []
        for start in sorted(dry):  # Ordenar os pontos de partida mantém os desertos na mesma ordem para cada seed.
            if start not in dry:
                continue
            dry.discard(start)
            region, stack = [], [start]
            while stack:
                p = stack.pop()
                region.append(p)
                for d in (GridPos(1, 0), GridPos(-1, 0), GridPos(0, 1), GridPos(0, -1)):
                    if p + d in dry:
                        dry.discard(p + d)
                        stack.append(p + d)
            regions.append(sorted(region))
        return regions

    def _solitary_spot(self, cells: list[GridPos], kind: MobKind, spacing: int, accept,
                       rng: random.Random | None = None) -> GridPos | None:
        world = self.world
        occupied = self._occupied()
        others = [m.end.grid for m in self.mobs.values() if m.kind is kind]
        herds = {m.home for m in self.mobs.values() if m.kind in HERD_KINDS}
        best, best_gap = None, -1.
        for cell in (rng or self._fauna).sample(cells, min(len(cells), 3 * HERD_CANDIDATES)):
            if (cell in occupied or not world.is_walkable(cell) or not accept(cell)
                    or any(chebyshev(cell, h) < 4 for h in herds)):
                continue
            gap = min((chebyshev(cell, o) for o in others), default=math.inf)
            if gap >= spacing and gap > best_gap:
                best, best_gap = cell, gap
        return best

    def _place_deer(self, accept) -> bool:
        cell = self._solitary_spot(self._forest, MobKind.DEER, DEER_SPACING, accept)
        if cell is not None:
            self._add(MobKind.DEER, cell, cell)
        return cell is not None

    def _place_snake(self, desert: int, accept) -> bool:
        cell = self._solitary_spot(self._deserts[desert][0], MobKind.SNAKE, SNAKE_SPACING, accept)
        if cell is not None:
            self._add(MobKind.SNAKE, cell, cell)
        return cell is not None

    def _place_armadillo(self, desert: int, accept) -> bool:
        cell = self._solitary_spot(self._deserts[desert][0], MobKind.ARMADILLO, ARMADILLO_SPACING, accept,
                                   self._burrow)
        if cell is not None:
            self._add(MobKind.ARMADILLO, cell, cell, self._burrow)
        return cell is not None

    def _replenish_wild(self, player: WorldPos) -> None:
        hidden = lambda p: not self._visible(player, p)
        if self.deer_count < self.target_deer:
            self._place_deer(hidden)
        for index, (_, target) in enumerate(self._deserts):
            if self.snakes_in(index) < target:
                self._place_snake(index, hidden)
        for index, target in enumerate(self._armadillo_target):
            if self.armadillos_in(index) < target:
                self._place_armadillo(index, hidden)

    def _visible(self, player: WorldPos, cell: GridPos) -> bool:
        if self.in_view is not None:
            return self.in_view(player, self.world.surface_position(cell))
        return chebyshev(cell, player) <= 20

    def _replenish(self, player: WorldPos) -> None:
        if not self._sites:
            return
        occupied = self._occupied()
        homes = [m.home for m in self.mobs.values() if m.home is not None]
        for _ in range(3):
            home = self._herd_home(homes, lambda h: h not in occupied and not self._visible(player, h))
            if home is None:
                continue
            kind = self.rng.choice((MobKind.CHICKEN, MobKind.PIG))
            size = max(HERD_SIZE[0], min(self.rng.randint(*HERD_SIZE), self.target_animals - self.animal_count))
            if self._spawn_herd(home, kind, size, occupied):
                return

    def _spawn_archer(self, player: WorldPos) -> None:
        world = self.world
        occupied = self._occupied()
        here = player.grid
        occupied.add(here)
        def fits(cell):
            return (chebyshev(cell, here) >= 8 and cell not in occupied and world.is_walkable(cell)
                    and not self._visible(player, cell))

        for _ in range(80):
            cell = here + GridPos(self.rng.randint(-30, 30), self.rng.randint(-30, 30))
            if fits(cell):
                self._add(MobKind.SKELETON, cell, None)
                return
        nearby = [cell for dx in range(-30, 31) for dy in range(-30, 31)
                  if fits(cell := here + GridPos(dx, dy))]
        if nearby:
            self._add(MobKind.SKELETON, self.rng.choice(nearby), None)
            return
        far = sorted((p for p in world.tile_map.tiles
                      if p not in occupied and world.is_walkable(p) and chebyshev(p, here) >= 3),
                     key=lambda p: -chebyshev(p, here))[:8]
        if far:
            self._add(MobKind.SKELETON, self.rng.choice(far), None)

    def _spawn_spider(self, player: WorldPos) -> bool:
        world = self.world
        here = player.grid
        occupied = self._occupied()
        near = [p for p in self._forest if SPIDER_NEAR <= chebyshev(p, here) <= SPIDER_FAR]
        for cell in self._night.sample(near, min(len(near), 40)):
            if cell in occupied or not world.is_walkable(cell) or self._visible(player, cell):
                continue
            self._add(MobKind.SPIDER, cell, cell)
            loot = [("silk", self._night.randint(1, 2))]
            if self._night.random() < GLAND_CHANCE:
                loot.append(("venom_gland", 1))
            self.mobs[self.next_id - 1].loot = tuple(loot)
            return True
        return False

    def start_night(self, player: WorldPos) -> None:
        self.night_spawned = True
        self._archer_in = ARCHER_SECONDS
        self._spider_in = SPIDER_SECONDS
        for _ in range(NIGHT_ARCHERS):
            self._spawn_archer(player)
        for _ in range(NIGHT_SPIDERS):
            self._spawn_spider(player)

    def dawn(self) -> None:
        self.mobs = {uid: m for uid, m in self.mobs.items() if m.kind is not MobKind.SKELETON}
        for mob in self.mobs.values():
            if mob.kind is MobKind.SPIDER:
                mob.anger = 0.
        self.arrows.clear()
        self.night_spawned = False

    def tick(self, seconds: float, player: WorldPos) -> bool:
        dt = max(0., seconds)
        self.grace = max(0., self.grace-dt)
        if self.world.tile_map.kind_at(player.grid) is not TileKind.WATER:
            self.shark_bites = 0
        self._replenish_in -= dt
        if self._replenish_in <= 0:
            self._replenish_in = REPLENISH_SECONDS
            if self.animal_count < self.target_animals:
                self._replenish(player)
            self._replenish_wild(player)
        if self.night_spawned:
            self._archer_in -= dt
            if self._archer_in <= 0:
                self._archer_in = ARCHER_SECONDS
                self.mobs = {uid: m for uid, m in self.mobs.items()
                             if m.kind is not MobKind.SKELETON or chebyshev(m.end, player) <= DESPAWN_RADIUS}
                if self.archer_count < MAX_ARCHERS:
                    self._spawn_archer(player)
            self._spider_in -= dt
            if self._spider_in <= 0:
                self._spider_in = SPIDER_SECONDS
                self.mobs = {uid: m for uid, m in self.mobs.items()
                             if m.kind is not MobKind.SPIDER or chebyshev(m.end, player) <= DESPAWN_RADIUS}
                if self.spider_count < MAX_SPIDERS:
                    self._spawn_spider(player)
        elif any(m.kind is MobKind.SPIDER for m in self.mobs.values()):
            self.mobs = {uid: m for uid, m in self.mobs.items()
                         if m.kind is not MobKind.SPIDER or self._visible(player, m.end.grid)}
        damaged = self._sandworm_turn(dt, player)
        reserved = {m.end.grid for m in self.mobs.values()}
        for mob in self.mobs.values():
            mob.flash = max(0., mob.flash-dt)
            if mob.kind is MobKind.SANDWORM:
                continue
            if mob.kind is MobKind.GUARDIAN:
                damaged |= boss.turn(self, mob, player, dt, reserved)
                continue
            mob.flee_time = max(0., mob.flee_time-dt)
            mob.shot_time = max(0., mob.shot_time-dt)
            mob.shoot_in = max(0., mob.shoot_in-dt)
            mob.lunge = max(0., mob.lunge-dt)
            mob.dazed = max(0., mob.dazed-dt)
            mob.anger = max(0., mob.anger-dt)
            mob.circle = max(0., mob.circle-dt)
            if mob.curled > 0:
                mob.curled -= dt
                if mob.curled > 0:
                    if mob.progress < 1:
                        mob.progress = min(1., mob.progress + dt/mob.duration)
                    continue
                mob.curled, mob.flee_time, mob.wait = 0., BOLT_SECONDS, 0.
            if mob.windup > 0:
                mob.windup -= dt
                if mob.windup <= 0:
                    damaged |= self._release(mob, player)
                continue
            if mob.progress < 1:
                mob.progress = min(1., mob.progress + dt/mob.duration)
                continue
            if mob.charge is not None:
                damaged |= self._charge_step(mob, player, reserved)
                continue
            if mob.kind is MobKind.SHARK:
                self._shark_turn(mob, player, reserved, dt)
                continue
            if mob.dazed > 0 or chebyshev(mob.end, player) > ACTIVE_RADIUS:
                continue
            if mob.kind is MobKind.MINE_MONSTER:
                self._monster_turn(mob, player, reserved, dt)
                continue
            if mob.kind is MobKind.DEER and mob.anger and chebyshev(mob.end, player) > CALM_DISTANCE:
                mob.anger = 0.
            if mob.kind is MobKind.SPIDER and not self.night_spawned:
                mob.flee_time = max(mob.flee_time, .5)
            if mob.kind is MobKind.ARMADILLO and self._wary(mob, player):
                mob.wait = min(mob.wait, WARY_PAUSE)
            mob.wait -= dt
            if mob.wait > 0:
                continue
            p = mob.end.grid
            mob.aiming = False
            rng = self._burrow if mob.kind is MobKind.ARMADILLO else self.rng
            mob.wait = rng.uniform(1.3, 3.5)
            if mob.kind is MobKind.DEER and mob.anger:
                choices = self._deer_turn(mob, player)
            elif mob.kind is MobKind.SNAKE and not mob.flee_time and self._stalks(mob, player):
                choices = self._snake_turn(mob, player)
            elif mob.kind is MobKind.SPIDER and self.night_spawned and self._hunts(mob, player):
                choices = self._spider_turn(mob, player)
            elif mob.kind is MobKind.SKELETON and distance(mob.end, player) <= CHASE_RADIUS:
                mob.wait = .45
                if distance(mob.end, player) <= 7 and abs(mob.end.z-player.z) <= 2 and segment_allowed(self.world, mob.end, player):
                    mob.left = player.x-p.x < player.y-p.y
                    mob.aiming = True
                    if mob.shoot_in <= 0:
                        self.arrows.append(Arrow(mob.end, player, max(.38, distance(mob.end, player)/7)))
                        mob.shoot_in = 2.7
                        mob.shot_time = .42
                    continue
                route = find_path(p, player.grid, self.world.is_walkable, self.world.can_step)
                choices = route[:1]
            elif mob.kind is MobKind.SKELETON and chebyshev(mob.end, player) <= HUNT_RADIUS:
                mob.wait = .45
                here = distance(p, player)
                choices = sorted((p + d for d in NEIGHBOR_DIRECTIONS if distance(p + d, player) < here),
                                 key=lambda q: distance(q, player))
            elif mob.kind is MobKind.ARMADILLO and not mob.flee_time and self._wary(mob, player):
                choices = self._armadillo_turn(mob, player)
            elif mob.flee_time:
                mob.wait = .03
                choices = sorted((p+d for d in NEIGHBOR_DIRECTIONS if distance(p+d, player) > distance(p, player)),
                                 key=lambda q: -distance(q, player))
            else:
                directions = list(NEIGHBOR_DIRECTIONS)
                rng.shuffle(directions)
                choices = [p + d for d in directions]
                home = mob.home
                if home is not None:
                    away = chebyshev(p, home)
                    radius = WANDER_RADIUS.get(mob.kind, HOME_RADIUS)
                    choices = [q for q in choices if chebyshev(q, home) <= radius or chebyshev(q, home) < away]
                if mob.kind is MobKind.ARMADILLO:
                    choices = [q for q in choices if chebyshev(q, player) > ARMADILLO_WARY + 1]
            desert = self._desert_of.get(mob.home) if mob.kind in DESERT_KINDS else None
            for q in choices:
                if (q != player.grid and q not in reserved and q not in self.world.portals
                        and q != self.world.camp and self.world.can_step(p, q)
                        and (desert is None or self._desert_of.get(q) == desert)):
                    reserved.discard(p)
                    reserved.add(q)
                    mob.walk(self.world.surface_position(q))
                    if mob.flee_time:
                        mob.duration *= .55
                    elif mob.kind is MobKind.SPIDER and mob.anger:
                        mob.duration *= SPIDER_PACE
                    break

        remaining = []
        for arrow in self.arrows:
            previous = arrow.location
            arrow.progress = min(1., arrow.progress + dt/arrow.duration)
            if arrow.hits(previous, player):
                damaged |= self._hurt((arrow.end.x - arrow.start.x, arrow.end.y - arrow.start.y), "arrow")
            elif arrow.progress < 1:
                remaining.append(arrow)
        self.arrows = remaining
        return damaged

    def _sand_at(self, cell: GridPos) -> int | None:
        region = self._desert_of.get(cell)
        if region is not None:
            tile = self.world.tile_map.tile_at(cell)
            if tile and tile.kind is TileKind.GRASS and tile.biome is Biome.DRY:
                return region
        return None

    def _place_lairs(self, worms: list[int], spawn: GridPos) -> None:
        rng = random.Random(self.world.seed ^ 0x574F524D)
        for desert, count in enumerate(worms):
            cells = [p for p in self._deserts[desert][0] if chebyshev(p, spawn) >= SAFE_START + WORM_TERRITORY]
            mine: list[GridPos] = []
            for _ in range(count if cells else 0):
                draws = [p for p in (rng.choice(cells) for _ in range(WORM_DRAWS))
                         if all(chebyshev(p, q) >= WORM_SPACING for q in mine)]
                if not draws:
                    break
                best = max(draws, key=lambda p: self._sand_around(p, desert))
                mine.append(best)
                self._lairs.append((best, desert))

    def _sand_around(self, cell: GridPos, desert: int) -> int:
        return sum(self._desert_of.get(GridPos(cell.x + dx, cell.y + dy)) == desert
                   for dx in range(-4, 5) for dy in range(-4, 5))

    def _lair_near(self, cell: GridPos, desert: int, reach: int = WORM_TERRITORY) -> int | None:
        near = [(chebyshev(cell, lair), index) for index, (lair, home) in enumerate(self._lairs)
                if home == desert and index not in self._lair_dead and chebyshev(cell, lair) <= reach]
        return min(near)[1] if near else None

    @property
    def worm_lairs(self) -> list[GridPos]:
        return [lair for index, (lair, _) in enumerate(self._lairs) if index not in self._lair_dead]

    def _sandworm_turn(self, dt: float, player: WorldPos) -> bool:
        previous, self._worm_previous = self._worm_previous, player
        moving = previous is not None and 0.00001 < distance(previous, player) <= 3
        self._worm_quiet = 0. if moving else self._worm_quiet + dt
        desert = self._sand_at(player.grid)
        worm = self.mobs.get(self._worm_id) if self._worm_id is not None else None
        if worm is None:
            if self._worm_id is not None and self._worm_lair is not None:
                self._lair_dead.add(self._worm_lair)
            self._worm_id = self._worm_lair = None
            if not moving or desert is None:
                return False
            lair = self._lair_near(player.grid, desert)
            if lair is None:
                return False
            occupied = self._occupied()
            dx, dy = player.x - previous.x, player.y - previous.y
            directions = sorted(NEIGHBOR_DIRECTIONS,
                                key=lambda d: (dx*d.x + dy*d.y) / math.hypot(d.x, d.y), reverse=True)
            for direction in directions:
                cell = player.grid + direction
                if (self._sand_at(cell) == desert and cell not in occupied
                        and self.world.can_step(player.grid, cell)):
                    pos = self.world.surface_position(cell)
                    uid = self.next_id
                    self.next_id += 1
                    self._worm_id, self._worm_lair = uid, lair
                    hp = self._lair_hp.pop(lair, HEALTH[MobKind.SANDWORM])
                    self.mobs[uid] = Mob(uid, MobKind.SANDWORM, hp, pos, pos, 0.,
                                         left=faces_left(cell, player))
                    break
            return False

        home = self._desert_of[worm.end.grid]
        if self._worm_lair is None:
            self._worm_lair = self._lair_near(worm.end.grid, home, reach=10**6)
        lair = self._lairs[self._worm_lair][0] if self._worm_lair is not None else None
        if worm.worm_phase != "dive" and (desert != home or self._worm_quiet >= 3. or distance(worm.end, player) > 4.
                                          or lair is None or chebyshev(player.grid, lair) > WORM_TERRITORY):
            worm.worm_phase = "dive"
            worm.wait = min(worm.worm_frame, 12) / 15.
        if worm.worm_phase == "dive":
            worm.wait -= dt
            worm.worm_frame = max(0, round(15 * worm.wait))
            if worm.wait <= 0:
                if self._worm_lair is not None:
                    self._lair_hp[self._worm_lair] = worm.hp
                del self.mobs[worm.id]
                self._worm_id = self._worm_lair = None
            return False

        previous_time = worm.wait
        worm.wait += dt
        near = self._reaches(worm.end.grid, worm.end.z, player)
        if worm.worm_phase == "rise":
            worm.worm_frame = min(12, int(worm.wait * 12))
            if worm.wait >= 1.05:
                worm.worm_phase, worm.wait = "idle", 0.
        elif worm.worm_phase == "idle":
            worm.left = faces_left(worm.end.grid, player)
            worm.worm_frame = 12 + int(worm.wait * 8) % 8
            if near and worm.wait >= .75:
                worm.worm_phase, worm.wait = "bite", 0.
        elif worm.worm_phase == "bite":
            worm.worm_frame = min(30, 20 + int(worm.wait * 12))
            if worm.wait >= 11/12:
                worm.worm_phase, worm.wait = "idle", 0.
            if near and previous_time < .5 <= previous_time + dt:
                return self._hurt((player.x - worm.end.x, player.y - worm.end.y), "sandworm")
        return False

    def _hurt(self, direction: tuple[float, float], blow: str) -> bool:
        if self.grace:
            return False
        self.grace = 1.5
        self.last_hit = direction
        self.last_blow = blow
        return True

    def _reaches(self, cell: GridPos, z: float, player: WorldPos) -> bool:
        return chebyshev(cell, player.grid) <= 1 and abs(player.z - z) <= 1

    def _deer_turn(self, mob: Mob, player: WorldPos) -> list[GridPos]:
        p = mob.end.grid
        gap = chebyshev(p, player.grid)
        level = abs(player.z - mob.end.z) <= 1
        mob.wait = .35
        if gap <= 1 and level:
            mob.attack, mob.windup = "kick", KICK_WINDUP
            mob.left = not faces_left(p, player)
            return []
        if 2 <= gap <= CHARGE_REACH and level and segment_allowed(self.world, mob.end, player):
            mob.attack, mob.windup = "charge", CHARGE_WINDUP
            mob.charge, mob.charge_left = toward(p, player.grid), CHARGE_REACH
            mob.left = faces_left(p, player)
            return []
        here = distance(p, player)
        return sorted((p + d for d in NEIGHBOR_DIRECTIONS if distance(p + d, player) < here),
                      key=lambda q: distance(q, player))

    def _stalks(self, mob: Mob, player: WorldPos) -> bool:
        return chebyshev(mob.end, player) <= SNAKE_SIGHT and abs(player.z - mob.end.z) <= 1

    def _snake_turn(self, mob: Mob, player: WorldPos) -> list[GridPos]:
        p = mob.end.grid
        mob.anger = 1.5
        mob.left = faces_left(p, player)
        mob.wait = .3
        if self._reaches(p, mob.end.z, player):
            mob.attack, mob.windup = "strike", STRIKE_WINDUP
            return []
        here = distance(p, player)
        return sorted((p + d for d in NEIGHBOR_DIRECTIONS if distance(p + d, player) < here),
                      key=lambda q: distance(q, player))

    def is_sea(self, cell: GridPos) -> bool:
        world = self.world
        tile = world.tile_map.tile_at(cell)
        if tile is None or tile.kind is not TileKind.WATER or cell in world.river_cells:
            return False
        size = world.tile_map.ocean_island_size
        return cell in world.sea_cells or (size > 0 and not (0 <= cell.x < size and 0 <= cell.y < size))

    def is_open_sea(self, cell: GridPos) -> bool:
        tile_at = self.world.tile_map.tile_at
        if not self.is_sea(cell):
            return False
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                tile = tile_at(GridPos(cell.x + dx, cell.y + dy))
                if tile is None or tile.kind is not TileKind.WATER:
                    return False
        return True

    def _swimmable_sea(self) -> list[GridPos]:
        world = self.world
        size = world.tile_map.ocean_island_size
        cells = set(world.sea_cells)
        for d in range(1, OCEAN_WIDTH - DEEP_BAND + 1 if size else 1):
            for i in range(-d, size + d):
                cells.update((GridPos(i, -d), GridPos(i, size - 1 + d), GridPos(-d, i), GridPos(size - 1 + d, i)))
        return sorted(p for p in cells if self.is_open_sea(p) and not world.tile_map.tile_at(p).deep_water
                      and chebyshev(p, world.spawn) >= SAFE_START)

    def _place_shark(self, cells: list[GridPos]) -> None:
        others = [m.end.grid for m in self.mobs.values() if m.kind is MobKind.SHARK]
        best, best_gap = None, -1.
        for cell in self._sea.sample(cells, min(len(cells), 3 * HERD_CANDIDATES)):
            gap = min((chebyshev(cell, o) for o in others), default=math.inf)
            if gap >= SHARK_SPACING and gap > best_gap:
                best, best_gap = cell, gap
        if best is not None:
            self._add(MobKind.SHARK, best, best, self._sea)

    def swimming_in_sea(self, player: WorldPos) -> bool:
        return self.is_sea(player.grid)

    def _shark_turn(self, mob: Mob, player: WorldPos, reserved: set[GridPos], dt: float) -> None:
        p = mob.end.grid
        if chebyshev(p, player) > ACTIVE_RADIUS:
            return
        prey = self.swimming_in_sea(player) and chebyshev(p, player) <= SHARK_SIGHT
        if prey and not mob.circle and chebyshev(p, player.grid) <= 1:
            mob.attack, mob.windup = "strike", SHARK_WINDUP
            mob.left = faces_left(p, player)
            return
        if prey and mob.circle:
            choices, pace = self._ring_steps(mob, player), CIRCLE_STEP
        elif prey:
            here = distance(p, player)
            choices = sorted((p + d for d in NEIGHBOR_DIRECTIONS if distance(p + d, player) < here),
                             key=lambda q: distance(q, player))
            pace = RUSH_STEP
        else:
            mob.wait -= dt
            if mob.wait > 0:
                return
            mob.wait = self._sea.uniform(.3, 1.4)
            directions = list(NEIGHBOR_DIRECTIONS)
            self._sea.shuffle(directions)
            away = chebyshev(p, mob.home)
            choices = [p + d for d in directions
                       if chebyshev(p + d, mob.home) <= SHARK_RADIUS or chebyshev(p + d, mob.home) < away]
            pace = PATROL_STEP
        for q in choices:
            if q != player.grid and q not in reserved and self.is_open_sea(q):
                reserved.discard(p)
                reserved.add(q)
                mob.walk(self.world.surface_position(q))
                mob.duration = pace * distance(mob.start, mob.end)
                return

    def _ring_steps(self, mob: Mob, player: WorldPos) -> list[GridPos]:
        p = mob.end.grid
        here = math.atan2(p.y - player.y, p.x - player.x)

        def score(q):
            turn = (math.atan2(q.y - player.y, q.x - player.x) - here) * mob.spin
            turn = (turn + math.pi) % (2 * math.pi) - math.pi
            return turn - abs(distance(q, player) - SHARK_RING)
        return sorted((p + d for d in NEIGHBOR_DIRECTIONS), key=score, reverse=True)

    def _place_monsters(self) -> None:
        world = self.world
        veins = sorted(p for p, o in world.objects.items()
                       if o.kind is ObjectKind.ROCK and o.variant in ORE_VEINS
                       and chebyshev(p, world.spawn) >= MONSTER_SAFE)
        target = min(MAX_MONSTERS, len(veins), max(MONSTER_MIN, round(len(veins) / MONSTER_VEINS)))
        self._lair.shuffle(veins)
        guarded: list[GridPos] = []
        for vein in veins:
            if len(guarded) >= target:
                break
            if any(chebyshev(vein, other) < MONSTER_SPACING for other in guarded):
                continue
            bed = self._bed_by(vein)
            if bed is None:
                continue
            guarded.append(vein)
            self._add(MobKind.MINE_MONSTER, bed, bed, self._lair)
            mob = self.mobs[self.next_id - 1]
            mob.asleep, mob.vein = True, vein
            mob.left = faces_left(bed, world.surface_position(vein))
            (ore, _), = ORE_YIELDS[world.objects[vein].variant][0]
            mob.loot = ((ore, MONSTER_ORE),)

    def _bed_by(self, vein: GridPos) -> GridPos | None:
        world = self.world
        level = world.elevation_at(vein)
        taken = {m.end.grid for m in self.mobs.values()}
        for d in (GridPos(1, 0), GridPos(0, 1), GridPos(-1, 0), GridPos(0, -1),
                  GridPos(1, 1), GridPos(-1, 1), GridPos(1, -1), GridPos(-1, -1)):
            cell = vein + d
            if (world.is_walkable(cell) and cell not in world.objects and cell not in world.portals
                    and cell not in taken and abs(world.elevation_at(cell) - level) <= 1):
                return cell
        return None

    def wake(self, mob: Mob) -> None:
        if mob.asleep:
            mob.asleep = False
            mob.wait = WAKE_PAUSE
            self.woke = mob

    def wake_guards(self, vein: GridPos) -> int:
        sleepers = [m for m in self.mobs.values()
                    if m.kind is MobKind.MINE_MONSTER and m.asleep and m.vein == vein]
        for mob in sleepers:
            self.wake(mob)
        return len(sleepers)

    def settle(self) -> None:
        for mob in self.mobs.values():
            if mob.kind is MobKind.MINE_MONSTER and mob.home is not None:
                where = self.world.surface_position(mob.home)
                mob.start = mob.end = where
                mob.progress, mob.asleep = 1., True
                mob.windup, mob.lunge, mob.dazed, mob.charge, mob.charge_left, mob.attack = 0., 0., 0., None, 0, ""
        self.woke = None

    def _monster_turn(self, mob: Mob, player: WorldPos, reserved: set[GridPos], dt: float) -> None:
        p = mob.end.grid
        gap = chebyshev(p, player.grid)
        if mob.asleep:
            if gap <= WAKE_RADIUS and abs(player.z - mob.end.z) <= 2:
                self.wake(mob)
            return
        mob.wait -= dt
        if mob.wait > 0:
            return
        if gap > GIVE_UP:
            if p == mob.home:
                mob.asleep = True
                if mob.vein is not None:
                    mob.left = faces_left(p, self.world.surface_position(mob.vein))
                return
            mob.wait = .2
            choices = find_path(p, mob.home, self.world.is_walkable, self.world.can_step)[:1]
        else:
            level = abs(player.z - mob.end.z) <= 1
            mob.wait = .3
            if gap <= 1 and level:
                mob.attack, mob.windup = "strike", MAW_WINDUP
                mob.left = faces_left(p, player)
                return
            if 2 <= gap <= MONSTER_REACH and level and segment_allowed(self.world, mob.end, player):
                mob.attack, mob.windup = "charge", CHARGE_WINDUP
                mob.charge, mob.charge_left = toward(p, player.grid), MONSTER_REACH
                mob.left = faces_left(p, player)
                return
            here = distance(p, player)
            choices = sorted((p + d for d in NEIGHBOR_DIRECTIONS if distance(p + d, player) < here),
                             key=lambda q: distance(q, player))
            choices += find_path(p, player.grid, self.world.is_walkable, self.world.can_step)[:1]
        for q in choices:
            if (q != player.grid and q not in reserved and q not in self.world.portals
                    and q != self.world.camp and self.world.can_step(p, q)):
                reserved.discard(p)
                reserved.add(q)
                mob.walk(self.world.surface_position(q))
                return

    def _shark_bite(self, mob: Mob, player: WorldPos) -> bool:
        mob.lunge, mob.wait = SHARK_LUNGE, 0.
        mob.circle, mob.spin = SHARK_CIRCLE, self._sea.choice((-1, 1))
        if not (self.swimming_in_sea(player) and chebyshev(mob.end.grid, player.grid) <= 1):
            return False
        if self.shark_bites >= SHARK_BITES:
            mob.circle = 0.
            self.dragging = mob
            return False
        if not self._hurt((player.x - mob.end.x, player.y - mob.end.y), "shark"):
            return False
        self.shark_bites += 1
        return True

    def _wary(self, mob: Mob, player: WorldPos) -> bool:
        return chebyshev(mob.end, player) <= ARMADILLO_WARY and abs(player.z - mob.end.z) <= 1

    def _armadillo_turn(self, mob: Mob, player: WorldPos) -> list[GridPos]:
        p = mob.end.grid
        mob.wait = WARY_PAUSE
        here = distance(p, player)
        return sorted((p + d for d in NEIGHBOR_DIRECTIONS if distance(p + d, player) > here),
                      key=lambda q: -distance(q, player))

    def _hunts(self, mob: Mob, player: WorldPos) -> bool:
        gap = chebyshev(mob.end, player)
        return abs(player.z - mob.end.z) <= 2 and (gap <= SPIDER_SIGHT or (mob.anger > 0 and gap <= SPIDER_LOSE))

    def _spider_turn(self, mob: Mob, player: WorldPos) -> list[GridPos]:
        p = mob.end.grid
        gap = chebyshev(p, player.grid)
        level = abs(player.z - mob.end.z) <= 1
        mob.anger = 2.0
        mob.left = faces_left(p, player)
        mob.wait = .25
        if gap <= 1 and level:
            mob.attack, mob.windup = "strike", FANG_WINDUP
            return []
        if 2 <= gap <= LEAP_REACH and level and segment_allowed(self.world, mob.end, player):
            mob.attack, mob.windup = "charge", LEAP_WINDUP
            mob.charge, mob.charge_left = toward(p, player.grid), LEAP_REACH
            return []
        here = distance(p, player)
        return sorted((p + d for d in NEIGHBOR_DIRECTIONS if distance(p + d, player) < here),
                      key=lambda q: distance(q, player))

    def _release(self, mob: Mob, player: WorldPos) -> bool:
        attack, mob.attack, mob.windup = mob.attack, "", 0.
        if attack == "charge":
            return False
        if mob.kind is MobKind.SHARK:
            return self._shark_bite(mob, player)
        mob.lunge = .25
        reach = self._reaches(mob.end.grid, mob.end.z, player)
        direction = (player.x - mob.end.x, player.y - mob.end.y)
        if mob.kind is MobKind.MINE_MONSTER:
            mob.wait = .6
            return reach and self._hurt(direction, "maw")
        if attack == "kick":
            mob.wait = .6
            return reach and self._hurt(direction, "kick")
        mob.dazed = RECOVER_SECONDS
        mob.wait = 0.
        return reach and self._hurt(direction, "fangs" if mob.kind is MobKind.SPIDER else "bite")

    def _charge_step(self, mob: Mob, player: WorldPos, reserved: set[GridPos]) -> bool:
        spider = mob.kind is MobKind.SPIDER
        p = mob.end.grid
        q = p + mob.charge
        hit = False
        if player.grid in (p, q) and abs(player.z - mob.end.z) <= 1:
            blow = "pounce" if spider else "ram" if mob.kind is MobKind.MINE_MONSTER else "antlers"
            hit = self._hurt((float(mob.charge.x), float(mob.charge.y)), blow)
        elif (mob.charge_left > 0 and q not in reserved and q not in self.world.portals
              and q != self.world.camp and self.world.can_step(p, q)):
            reserved.discard(p)
            reserved.add(q)
            mob.walk(self.world.surface_position(q))
            step = LEAP_STEP if spider else MONSTER_STEP if mob.kind is MobKind.MINE_MONSTER else CHARGE_STEP
            mob.duration = step * distance(mob.start, mob.end)
            mob.charge_left -= 1
            return False
        mob.charge, mob.charge_left = None, 0
        mob.dazed = LEAP_RECOVER if spider else DAZED_SECONDS
        mob.wait = 0.
        return hit
