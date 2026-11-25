from __future__ import annotations

import random
from dataclasses import dataclass
from enum import Enum

from spawnbound.domain.coordinates import GridPos


class Swim(str, Enum):
    MIXED = "misto"
    SMOOTH = "suave"
    SINKER = "afunda"
    FLOATER = "flutua"
    DART = "dardo"


FRESH, SEA = "fresh", "sea"
ANY, DAY, NIGHT = "any", "day", "night"


@dataclass(frozen=True, slots=True)
class Fish:
    item: str
    name: str
    water: str
    difficulty: int
    swim: Swim
    period: str = ANY
    weight: int = 10
    feminine: bool = False


FISH = {fish.item: fish for fish in (
    Fish("lambari", "Lambari", FRESH, 15, Swim.MIXED, ANY, 30),
    Fish("tilapia", "Tilápia", FRESH, 25, Swim.SMOOTH, DAY, 25, feminine=True),
    Fish("bagre", "Bagre", FRESH, 45, Swim.SINKER, NIGHT, 15),
    Fish("traira", "Traíra", FRESH, 55, Swim.DART, ANY, 15, feminine=True),
    Fish("tucunare", "Tucunaré", FRESH, 70, Swim.DART, DAY, 10),
    Fish("pirarucu", "Pirarucu", FRESH, 90, Swim.MIXED, ANY, 3),
    Fish("sardinha", "Sardinha", SEA, 15, Swim.MIXED, ANY, 30, feminine=True),
    Fish("tainha", "Tainha", SEA, 30, Swim.SMOOTH, DAY, 22, feminine=True),
    Fish("baiacu", "Baiacu", SEA, 40, Swim.FLOATER, ANY, 15),
    Fish("robalo", "Robalo", SEA, 55, Swim.MIXED, NIGHT, 15),
    Fish("garoupa", "Garoupa", SEA, 65, Swim.SINKER, ANY, 10, feminine=True),
    Fish("atum", "Atum", SEA, 85, Swim.DART, DAY, 4),
)}
COOKED = {item: f"cooked_{item}" for item in FISH}
RAW_ENERGY = 6


def cooked_energy(fish: Fish) -> int:
    return 20 + fish.difficulty // 4


def water_of(world, cell: GridPos) -> str | None:
    from spawnbound.domain.model import TileKind
    tile = world.tile_map.tiles.get(cell)
    if tile is None or tile.kind is not TileKind.WATER:
        return None
    size = world.tile_map.ocean_island_size
    inside = size is not None and 0 <= cell.x < size and 0 <= cell.y < size
    if cell in world.river_cells or (inside and cell not in world.sea_cells):
        return FRESH
    return SEA


def biting(water: str, night: bool) -> tuple[Fish, ...]:
    now = NIGHT if night else DAY
    return tuple(fish for fish in FISH.values() if fish.water == water and fish.period in (ANY, now))


def pick_fish(rng: random.Random, water: str, night: bool) -> Fish:
    choices = biting(water, night)
    return rng.choices(choices, weights=[fish.weight for fish in choices])[0]
