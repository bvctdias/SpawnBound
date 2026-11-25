from __future__ import annotations

from dataclasses import dataclass

from spawnbound.domain.coordinates import GridPos


@dataclass(frozen=True, slots=True)
class CropSpec:
    seed: str
    days: float
    harvest: int


CROPS = {
    "carrot": CropSpec("carrot_seed", 2, 2),
    "turnip": CropSpec("turnip_seed", 3, 2),
    "pumpkin": CropSpec("pumpkin_seed", 5, 1),
}
SEEDS = {spec.seed: kind for kind, spec in CROPS.items()}
STAGES = 4
WILD = -1e9


@dataclass(slots=True)
class Crop:
    kind: str
    planted: float


def stage(crop: Crop, now: float, day_seconds: float) -> int:
    grown = min(1., (now - crop.planted) / (CROPS[crop.kind].days * day_seconds))
    return min(STAGES - 1, max(0, int(grown * (STAGES - 1))))


def ripe(crop: Crop, now: float, day_seconds: float) -> bool:
    return stage(crop, now, day_seconds) == STAGES - 1


def garden_cells(camp: GridPos) -> tuple[GridPos, ...]:
    offsets = [GridPos(dx, dy) for dx in range(-5, 6) for dy in range(-5, 6) if 3 <= max(abs(dx), abs(dy)) <= 5]
    return tuple(camp + offset for offset in sorted(offsets, key=lambda o: (abs(o.x) + abs(o.y), o.x, o.y)))
