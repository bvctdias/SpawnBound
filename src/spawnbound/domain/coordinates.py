from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Final


@dataclass(frozen=True, order=True, slots=True)
class GridPos:
    x: int
    y: int

    def __add__(self, other: "GridPos") -> "GridPos":
        return GridPos(self.x + other.x, self.y + other.y)

    def __sub__(self, other: "GridPos") -> "GridPos":
        return GridPos(self.x - other.x, self.y - other.y)


@dataclass(frozen=True, slots=True)
class WorldPos:
    x: float
    y: float
    z: float

    @property
    def grid(self) -> GridPos:
        # O clique e o movimento precisam atribuir as bordas à mesma célula, inclusive em coordenadas negativas.
        return GridPos(math.floor(self.x + 0.5), math.floor(self.y + 0.5))


NORTH: Final = GridPos(-1, -1)
NORTH_EAST: Final = GridPos(0, -1)
EAST: Final = GridPos(1, -1)
SOUTH_EAST: Final = GridPos(1, 0)
SOUTH: Final = GridPos(1, 1)
SOUTH_WEST: Final = GridPos(0, 1)
WEST: Final = GridPos(-1, 1)
NORTH_WEST: Final = GridPos(-1, 0)

NEIGHBOR_DIRECTIONS: Final = (
    NORTH,
    NORTH_EAST,
    EAST,
    SOUTH_EAST,
    SOUTH,
    SOUTH_WEST,
    WEST,
    NORTH_WEST,
)


def grid_to_screen(
    position: GridPos,
    tile_width: int,
    tile_height: int,
    elevation: int = 0,
) -> tuple[float, float]:
    screen_x = (position.x - position.y) * (tile_width / 2)
    screen_y = (position.x + position.y) * (tile_height / 2) - elevation
    return screen_x, screen_y


def screen_to_grid(
    screen_x: float,
    screen_y: float,
    tile_width: int,
    tile_height: int,
) -> tuple[float, float]:
    grid_x = (screen_x / tile_width) + (screen_y / tile_height)
    grid_y = (screen_y / tile_height) - (screen_x / tile_width)
    return grid_x, grid_y


def screen_to_grid_cell(
    screen_x: float,
    screen_y: float,
    tile_width: int,
    tile_height: int,
) -> GridPos:
    grid_x, grid_y = screen_to_grid(screen_x, screen_y, tile_width, tile_height)
    return GridPos(math.floor(grid_x + 0.5), math.floor(grid_y + 0.5))
