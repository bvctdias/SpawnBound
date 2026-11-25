from dataclasses import dataclass

from spawnbound.config import GameConfig
from spawnbound.domain.crafting import Production, RECIPES, shown_recipes
from spawnbound.view import inventory_panel


Box = tuple[int, int, int, int]
Point = tuple[float, float]
TITLES = {"bench": "Bancada", "kiln": "Fornalha", "composter": "Composteira", "campfire": "Fogueira"}


def contains(box: Box, point: Point | None) -> bool:
    from spawnbound.pplay_ui import pointed
    return pointed(box, point)


def bench_button(config: GameConfig) -> Box:
    x, y, _, height = inventory_panel(config)
    return max(0, x - 68), y + height // 2 - 24, 48, 48


@dataclass(slots=True)
class CraftPanel:
    equipment: str | None = None
    production: Production | None = None
    pointer: Point | None = None
    message: str = ""


@dataclass(frozen=True, slots=True)
class RecipeLayout:
    title: Box
    output: Box
    collect: Box
    cancel: Box
    rows: tuple[Box, ...]
    beside_bag: bool


def recipe_layout(config: GameConfig, equipment: str, inventory=None) -> RecipeLayout:
    width = min(242, config.virtual_width - 12)
    button = bench_button(config)
    beside = equipment == "bench" and button[0] >= width + 18
    left = button[0] - width - 12 if beside else (config.virtual_width - width) // 2
    center = left + width // 2
    count = len(shown_recipes(equipment, inventory))
    columns = 2 if equipment != "bench" and count > 8 else 1
    per_column = -(-count // columns)
    pitch = min(44, max(20, (config.virtual_height - 162) // count))
    if columns == 2:
        pitch = min(44, max(20, (config.virtual_height - 190) // per_column))
    if equipment == "bench":
        top = (config.virtual_height - (count * pitch + 48)) // 2
        rows_y = top + 48
    else:
        top = max(8, (config.virtual_height - 464) // 2)
        rows_y = min(top + (258 if equipment == "composter" else 150),
                     config.virtual_height - count * pitch - 24)
        if columns == 2:
            rows_y = max(top + 150, config.virtual_height - per_column * pitch - 24)
    gap = 8
    lefts = (left,) if columns == 1 else (center - width - gap // 2, center + gap // 2)
    rows = tuple((lefts[i // per_column], rows_y + (i % per_column) * pitch, width, pitch - 3) for i in range(count))
    return RecipeLayout((center - 80, top, 160, 34), (center - 23, top + 46, 46, 46),
                        (center - 49, top + 103, 98, 25), (center + 12, top + 41, 17, 17),
                        rows, beside)
