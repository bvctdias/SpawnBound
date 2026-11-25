from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from spawnbound.domain.tools import ToolTier

from spawnbound.domain.coordinates import GridPos, NEIGHBOR_DIRECTIONS, WorldPos
from spawnbound.domain.mine_guides import MineGuides
from spawnbound.domain.inventory import CHEST_SIZE, Inventory
from spawnbound.domain.crafting import Production


class TileKind(str, Enum):
    GRASS = "grass"
    BRIDGE = "bridge"
    CAVE_FLOOR = "cave_floor"
    CAVE_WALL = "cave_wall"
    WOOD_FLOOR = "wood_floor"
    INTERIOR_WALL = "interior_wall"
    # Nos lagos, a elevação da célula corresponde ao leito.
    WATER = "water"


class SpaceKind(str, Enum):
    OUTDOOR = "outdoor"
    CAVE = "cave"
    INTERIOR = "interior"


class GrassVariant(str, Enum):
    NORMAL = "normal"
    TALL_GRASS = "tall_grass"
    PEBBLES = "pebbles"


class Biome(str, Enum):
    FOREST = "forest"
    MEADOW = "meadow"
    DRY = "dry"


class ObjectKind(str, Enum):
    WAYSTONE = "waystone"
    WINDMILL = "windmill"
    DOCK = "dock"
    CACTUS = "cactus"
    CHEST = "chest"
    KILN = "kiln"
    COMPOSTER = "composter"
    BENCH = "bench"
    BED = "bed"
    TORCH = "torch"
    TREE = "tree"
    FALLEN_LOG = "fallen_log"
    ROCK = "rock"
    BERRY_BUSH = "berry_bush"
    MUSHROOM = "mushroom"
    CAMPFIRE = "campfire"
    MENHIR = "menhir"


class TreeVariant(str, Enum):
    PINE_DARK = "pine_dark"
    PINE_LIGHT = "pine_light"
    BROADLEAF = "broadleaf"
    AUTUMN_GOLD = "autumn_gold"
    AUTUMN_RED = "autumn_red"
    PALM_SMALL = "palm_small"
    PALM_MEDIUM = "palm_medium"
    PALM_TALL = "palm_tall"


PALMS = frozenset((TreeVariant.PALM_SMALL.value, TreeVariant.PALM_MEDIUM.value, TreeVariant.PALM_TALL.value))


class BerryColor(str, Enum):
    RED = "red"
    PURPLE = "purple"
    PINK = "pink"


@dataclass(frozen=True, slots=True)
class Tile:
    kind: TileKind
    variant: GrassVariant = GrassVariant.NORMAL
    biome: Biome = Biome.FOREST
    elevation: int = 0
    deep_water: bool = False

    def __post_init__(self) -> None:
        if self.elevation < 0:
            raise ValueError("terrain elevation must be nonnegative")


@dataclass(frozen=True, slots=True)
class ObjectSpec:
    durability: int
    total_energy: int
    xp_reward: int
    drops: tuple[tuple[str, int], ...]
    blocks_movement: bool
    required_tool_tier: ToolTier
    removed_when_depleted: bool = True
    swing_seconds: float = .36


OBJECT_SPECS: dict[ObjectKind, ObjectSpec] = {
    ObjectKind.WAYSTONE: ObjectSpec(1, 0, 0, (), True, ToolTier.NONE, removed_when_depleted=False),
    ObjectKind.WINDMILL: ObjectSpec(1, 0, 0, (), True, ToolTier.NONE, removed_when_depleted=False),
    ObjectKind.DOCK: ObjectSpec(1, 0, 0, (), True, ToolTier.NONE, removed_when_depleted=False),
    ObjectKind.CACTUS: ObjectSpec(6, 6, 6, (("cactus", 1),), True, ToolTier.NONE),
    ObjectKind.CHEST: ObjectSpec(1, 0, 0, (), True, ToolTier.NONE, removed_when_depleted=False),
    ObjectKind.KILN: ObjectSpec(1, 0, 0, (), True, ToolTier.NONE, removed_when_depleted=False),
    ObjectKind.COMPOSTER: ObjectSpec(1, 0, 0, (), True, ToolTier.NONE, removed_when_depleted=False),
    ObjectKind.BENCH: ObjectSpec(1, 0, 0, (), True, ToolTier.NONE, removed_when_depleted=False),
    ObjectKind.CAMPFIRE: ObjectSpec(1, 0, 0, (), True, ToolTier.NONE, removed_when_depleted=False),
    ObjectKind.MENHIR: ObjectSpec(1, 0, 0, (), True, ToolTier.NONE, removed_when_depleted=False),
    ObjectKind.BED: ObjectSpec(1, 0, 0, (), False, ToolTier.NONE),
    ObjectKind.TORCH: ObjectSpec(1, 0, 0, (), False, ToolTier.NONE),
    ObjectKind.TREE: ObjectSpec(
        durability=31,
        total_energy=8,
        swing_seconds=.45,
        xp_reward=8,
        drops=(("wood", 2),),
        blocks_movement=True,
        required_tool_tier=ToolTier.NONE,
    ),
    ObjectKind.FALLEN_LOG: ObjectSpec(
        durability=40,
        total_energy=24,
        swing_seconds=.45,
        xp_reward=18,
        drops=(("wood", 3),),
        blocks_movement=True,
        required_tool_tier=ToolTier.NONE,
    ),
    ObjectKind.ROCK: ObjectSpec(
        durability=25,
        total_energy=10,
        swing_seconds=3.45 / 8,
        xp_reward=12,
        drops=(("stone", 1),),
        blocks_movement=True,
        required_tool_tier=ToolTier.BASIC,
    ),
    ObjectKind.BERRY_BUSH: ObjectSpec(
        durability=1,
        total_energy=0,
        xp_reward=4,
        drops=(("berry", 1),),
        blocks_movement=False,
        required_tool_tier=ToolTier.NONE,
        removed_when_depleted=False,
    ),
    ObjectKind.MUSHROOM: ObjectSpec(
        durability=1,
        total_energy=0,
        xp_reward=3,
        drops=(("white_mushroom", 1),),
        blocks_movement=False,
        required_tool_tier=ToolTier.NONE,
    ),
}

MUSHROOMS = ("white_mushroom", "brown_mushroom", "morel")


def mushroom_caps(variant: str, position: GridPos) -> int:
    if variant == "morel":
        return 1
    return 2 + ((position.x * 40503) ^ (position.y * 9973)) % 2


ORE_YIELDS: dict[str, tuple[tuple[tuple[str, int], ...], int]] = {
    "copper_ore": ((("copper", 1),), 20),
    "quartz_ore": ((("quartz", 1),), 30),
    "coal_ore": ((("coal", 1),), 15),
    "sandstone_coal": ((("coal", 1),), 15),
}


@dataclass(slots=True)
class WorldObject:
    object_id: str
    position: GridPos
    kind: ObjectKind
    durability: int
    variant: str = "default"
    available: bool = True
    elevation: int = 0
    storage: Inventory | None = None
    production: Production | None = None

    @property
    def position3d(self) -> WorldPos:
        return WorldPos(self.position.x, self.position.y, self.elevation)

    @classmethod
    def create(
        cls,
        position: GridPos,
        kind: ObjectKind,
        *,
        variant: str = "default",
        object_id: str | None = None,
        elevation: int = 0,
    ) -> "WorldObject":
        return cls(
            object_id=object_id or f"{kind.value}@{position.x},{position.y}",
            position=position,
            kind=kind,
            durability=OBJECT_SPECS[kind].durability,
            storage=Inventory([None] * CHEST_SIZE) if kind is ObjectKind.CHEST else None,
            production=(Production(kind.value)
                        if kind in (ObjectKind.KILN, ObjectKind.COMPOSTER, ObjectKind.CAMPFIRE) else None),
            variant=variant,
            elevation=elevation,
        )

    @property
    def spec(self) -> ObjectSpec:
        return OBJECT_SPECS[self.kind]

    @property
    def damage_stage(self) -> int:
        total = self.spec.durability
        return (4 * (total - self.durability) + total - 1) // total

    @property
    def blocks_movement(self) -> bool:
        return self.spec.blocks_movement

    @property
    def drops(self) -> tuple[tuple[str, int], ...]:
        if self.kind is ObjectKind.MUSHROOM:
            return ((self.variant, mushroom_caps(self.variant, self.position)),)
        ore = ORE_YIELDS.get(self.variant)
        return ore[0] if ore else self.spec.drops

    @property
    def xp_reward(self) -> int:
        ore = ORE_YIELDS.get(self.variant)
        return ore[1] if ore else self.spec.xp_reward


@dataclass(slots=True)
class BridgeSite:
    entry: GridPos
    cells: tuple[GridPos, ...]
    exit: GridPos
    direction: GridPos
    built: bool = False

    def contains(self, position: GridPos) -> bool:
        return position in self.cells


@dataclass(frozen=True, slots=True)
class Portal:
    portal_id: str
    position: GridPos
    approach: GridPos
    target_space_id: str
    target_kind: SpaceKind
    label: str
    arrival: GridPos | None = None


OCEAN_WIDTH = 16
WALKABLE_TILES = frozenset((TileKind.GRASS, TileKind.BRIDGE, TileKind.CAVE_FLOOR, TileKind.WOOD_FLOOR))
DEEP_BAND = 4
COAST_WATER = Tile(TileKind.WATER)
DEEP_WATER = Tile(TileKind.WATER, deep_water=True)


@dataclass(slots=True)
class TileMap:
    tiles: dict[GridPos, Tile] = field(default_factory=dict)
    max_elevation: int = 0
    revision: int = 0
    ocean_island_size: int = 0
    # A ordem das alterações permite que cada cache retome de onde parou.
    changes: list[GridPos] = field(default_factory=list)

    def __post_init__(self) -> None:
        self.max_elevation = max((tile.elevation for tile in self.tiles.values()), default=0)

    def tile_at(self, position: GridPos) -> Tile | None:
        tile = self.tiles.get(position)
        if tile is not None or not self.ocean_island_size:
            return tile
        size = self.ocean_island_size
        distance = max(-position.x, -position.y, position.x-size+1, position.y-size+1)
        if 0 < distance <= OCEAN_WIDTH:
            return DEEP_WATER if distance > OCEAN_WIDTH - DEEP_BAND else COAST_WATER
        return None

    def kind_at(self, position: GridPos) -> TileKind | None:
        tile = self.tile_at(position)
        return tile.kind if tile is not None else None

    def is_walkable(self, position: GridPos) -> bool:
        return self.kind_at(position) in WALKABLE_TILES

    def add(
        self,
        position: GridPos,
        kind: TileKind,
        variant: GrassVariant = GrassVariant.NORMAL,
        biome: Biome = Biome.FOREST,
        elevation: int = 0,
    ) -> None:
        self.tiles[position] = Tile(kind=kind, variant=variant, biome=biome, elevation=elevation)
        self.max_elevation = max(self.max_elevation, elevation)
        self.revision += 1
        self.changes.append(position)


@dataclass(slots=True)
class World:
    seed: int
    tile_map: TileMap
    objects: dict[GridPos, WorldObject]
    spawn: GridPos
    camp: GridPos | None
    bridge: BridgeSite
    goal: GridPos
    chunk_preview_size: int | None = None
    space_id: str = "overworld"
    space_kind: SpaceKind = SpaceKind.OUTDOOR
    portals: dict[GridPos, Portal] = field(default_factory=dict)
    strict_diagonals: bool = False
    wall_damage: dict[GridPos, int] = field(default_factory=dict)
    guides: MineGuides = field(default_factory=MineGuides)
    river_mouth: GridPos | None = None
    river_cells: frozenset[GridPos] = frozenset()
    sea_cells: frozenset[GridPos] = frozenset()
    fish_refuges: dict[GridPos, GridPos] = field(default_factory=dict)
    chipped: list[GridPos] = field(default_factory=list)
    placed_torches: set[GridPos] = field(default_factory=set)
    placed_stations: set[GridPos] = field(default_factory=set)
    placed_fires: set[GridPos] = field(default_factory=set)
    waystones: list[GridPos] = field(default_factory=list)
    tilled_soil: dict[GridPos, int] = field(default_factory=dict)
    crops: dict = field(default_factory=dict)
    home_island: bool = True
    dock: GridPos | None = None
    arena: GridPos | None = None
    guardian_defeated: bool = False

    def add_waystone(self, position: GridPos, active: bool | None = None) -> None:
        index = len(self.waystones)
        hue = (self.seed * 71 + 172 + 137 * index) % 360
        stone = WorldObject.create(position, ObjectKind.WAYSTONE, variant=str(hue),
                                   elevation=self.elevation_at(position))
        stone.available = index == 0 if active is None else active
        self.objects[position] = stone
        self.waystones.append(position)

    def active_waystones(self):
        for position in self.waystones:
            stone = self.objects.get(position)
            if stone is not None and stone.kind is ObjectKind.WAYSTONE and stone.available:
                yield stone

    def elevation_at(self, position: GridPos) -> int:
        tile = self.tile_map.tile_at(position)
        return tile.elevation if tile is not None else 0

    def surface_position(self, position: GridPos) -> WorldPos:
        return WorldPos(position.x, position.y, self.elevation_at(position))

    def can_step(self, source: GridPos, destination: GridPos, max_height: int = 1, *, swim: bool = False) -> bool:
        dx, dy = destination.x - source.x, destination.y - source.y
        if not (dx or dy) or dx < -1 or dx > 1 or dy < -1 or dy > 1:
            return False
        target_z = self._passable_height(destination, swim)
        source_z = self.elevation_at(source)
        if target_z is None or abs(source_z - target_z) > max_height:
            return False
        if self.strict_diagonals and dx and dy:
            for side in (GridPos(source.x + dx, source.y), GridPos(source.x, source.y + dy)):
                side_z = self._passable_height(side, swim)
                if side_z is None or abs(source_z-side_z) > max_height or abs(target_z-side_z) > max_height:
                    return False
        return True

    def can_reach(self, source: GridPos, target: GridPos, max_height: int = 1) -> bool:
        if target - source not in NEIGHBOR_DIRECTIONS:
            return False
        tile = self.tile_map.tile_at(target)
        height = 0 if tile is not None and tile.kind is TileKind.CAVE_WALL else self.elevation_at(target)
        return abs(self.elevation_at(source) - height) <= max_height

    def is_walkable(self, position: GridPos) -> bool:
        return self._passable_height(position, False) is not None

    def player_can_enter(self, position: GridPos) -> bool:
        return self._passable_height(position, True) is not None

    def passable_height(self, position: GridPos, *, swim: bool = False) -> int | None:
        return self._passable_height(position, swim)

    def _passable_height(self, position: GridPos, swim: bool) -> int | None:
        tile = self.tile_map.tile_at(position)
        if tile is None:
            return None
        if tile.kind is TileKind.WATER:
            return tile.elevation if swim and not tile.deep_water else None
        if tile.kind not in WALKABLE_TILES:
            return None
        obj = self.object_at(position)
        return tile.elevation if obj is None or not obj.blocks_movement else None

    def object_at(self, position: GridPos) -> WorldObject | None:
        return self.objects.get(position)

    def remove_object(self, position: GridPos) -> WorldObject:
        self.tile_map.changes.append(position)
        if position in self.waystones:
            self.waystones.remove(position)
        self.placed_torches.discard(position)
        self.placed_stations.discard(position)
        self.placed_fires.discard(position)
        return self.objects.pop(position)

    def build_bridge(self) -> None:
        for position in self.bridge.cells:
            self.tile_map.add(position, TileKind.BRIDGE)
        self.bridge.built = True

    def signature(self) -> tuple[object, ...]:
        tiles = tuple(
            sorted(
                (pos.x, pos.y, tile.kind.value, tile.variant.value, tile.biome.value, tile.elevation)
                for pos, tile in self.tile_map.tiles.items()
            )
        )
        objects = tuple(
            sorted(
                (
                    pos.x,
                    pos.y,
                    world_object.object_id,
                    world_object.kind.value,
                    world_object.variant,
                    world_object.durability,
                    world_object.available,
                    world_object.elevation,
                )
                for pos, world_object in self.objects.items()
            )
        )
        return (
            self.seed,
            tiles,
            objects,
            (self.spawn.x, self.spawn.y),
            (self.camp.x, self.camp.y) if self.camp is not None else None,
            tuple((cell.x, cell.y) for cell in self.bridge.cells),
            (self.goal.x, self.goal.y),
            self.chunk_preview_size,
            self.space_id,
            self.space_kind.value,
            tuple(sorted((p.x, p.y, portal.portal_id, portal.target_space_id,
                          portal.target_kind.value, portal.approach.x, portal.approach.y,
                          None if portal.arrival is None else (portal.arrival.x, portal.arrival.y))
                         for p, portal in self.portals.items())),
            tuple(sorted((p.x, p.y, hits) for p, hits in self.wall_damage.items())),
        )
