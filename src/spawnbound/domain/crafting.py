from __future__ import annotations

from dataclasses import dataclass, field
from math import floor

from spawnbound.domain.inventory import Inventory, STACK_LIMIT
from spawnbound.domain.fish import COOKED, FISH
from spawnbound.domain.tools import CRAFTED_TOOLS, UPGRADES


BRIDGE_RECIPE = {"wood": 3, "stone": 2}
WINDMILL_REPAIR = {"wood": 10, "stone": 5}
DOCK_REPAIR = {"wood": 15, "stone": 5}
FURNITURE = {"torch": {"wood": 2}, "bed": {"wood": 6, "hide": 1}, "chest": {"wood": 5},
             "kiln": {"stone": 8, "wood": 2}, "composter": {"wood": 4, "berry": 2}, "bench": {"wood": 6, "stone": 2},
             "campfire": {"coal": 3, "stone": 5}}
TURNABLE = {"kiln": ("left", "right"), "bench": ("left", "right"),
            "bed": ("left", "right"), "chest": ("left", "right"), "composter": ("left", "right")}
MIRRORED = frozenset({"bed", "chest", "composter"})


def shown_recipes(equipment: str, inventory=None) -> tuple:
    recipes = RECIPES[equipment]
    if inventory is None:
        return recipes
    if equipment == "campfire":
        return tuple(recipe for recipe in recipes
                     if not any(item in FISH for item in recipe.costs)
                     or any(inventory.quantity(item) for item in recipe.costs))
    if equipment != "bench":
        return recipes
    return tuple(recipe for recipe in recipes
                 if not (tools := [item for item in recipe.costs if item in UPGRADES])
                 or any(inventory.quantity(tool) for tool in tools))


@dataclass(frozen=True, slots=True)
class Recipe:
    product: str
    costs: dict[str, int]
    seconds: float = 0.


RECIPES = {
    "bench": (
        Recipe("bridge_kit", BRIDGE_RECIPE),
        *(Recipe(product, {tool: 1, **materials}) for tool, (product, materials, _, _) in UPGRADES.items()),
        *(Recipe(tool, materials) for tool, materials in CRAFTED_TOOLS.items()),
        *(Recipe(item, materials) for item, materials in FURNITURE.items()),
    ),
    "kiln": (
        Recipe("copper_bar", {"coal": 3, "copper": 6}, 3.),
        Recipe("iron_bar", {"coal": 3, "iron_ore": 6}, 3.),
        Recipe("gold_bar", {"coal": 3, "gold_ore": 6}, 3.),
        Recipe("brick", {"coal": 2, "clay": 3}, 2.),
        Recipe("glass", {"coal": 3, "sand": 10}, 2.),
        Recipe("flask", {"coal": 3, "glass": 12}, 2.),
        Recipe("jar", {"coal": 3, "glass": 14}, 2.),
    ),
    "campfire": (
        Recipe("cooked_meat", {"meat": 1}, 2.5),
        Recipe("cooked_venison", {"venison": 1}, 3.),
        Recipe("cooked_snake_meat", {"snake_meat": 1}, 2.),
        *(Recipe(COOKED[item], {item: 1}, 2.) for item in FISH),
    ),
    "composter": (
        Recipe("carrot_seed", {"carrot": 1}, 1.5),
        Recipe("turnip_seed", {"turnip": 1}, 1.5),
        Recipe("pumpkin_seed", {"pumpkin": 1}, 1.5),
    ),
}


QUEUE_KINDS = {"campfire": 4}


@dataclass(slots=True)
class Production:
    equipment: str
    recipe: Recipe | None = None
    pending: int = 0
    ready: int = 0
    next_finish: float = 0.
    queue: list = field(default_factory=list)
    stock: dict = field(default_factory=dict)

    @property
    def kinds(self) -> set[str]:
        kinds = set(self.stock) | {recipe.product for recipe, _ in self.queue}
        if self.recipe:
            kinds.add(self.recipe.product)
        return kinds

    @property
    def outputs(self) -> list[tuple[str, int]]:
        items = dict(self.stock)
        if self.recipe and self.ready:
            items[self.recipe.product] = items.get(self.recipe.product, 0) + self.ready
        return list(items.items())

    def amount(self, product: str) -> int:
        count = self.stock.get(product, 0) + sum(n for recipe, n in self.queue if recipe.product == product)
        if self.recipe and self.recipe.product == product:
            count += self.ready + self.pending
        return count

    def refresh(self, now: float) -> None:
        while True:
            if self.pending and now >= self.next_finish:
                count = min(self.pending, 1 + floor((now - self.next_finish) / self.recipe.seconds))
                self.ready += count
                self.pending -= count
                self.next_finish += count * self.recipe.seconds
            if self.pending or not self.queue:
                return
            ended = self.next_finish - self.recipe.seconds
            self._stock_ready()
            self.recipe, self.pending = self.queue.pop(0)
            self.next_finish = ended + self.recipe.seconds

    def _stock_ready(self) -> None:
        if self.recipe and self.ready:
            self.stock[self.recipe.product] = self.stock.get(self.recipe.product, 0) + self.ready
            self.ready = 0

    def start(self, recipe: Recipe, bag: Inventory, now: float) -> str:
        self.refresh(now)
        if recipe not in RECIPES[self.equipment]:
            return "Receita de outro equipamento."
        limit = QUEUE_KINDS.get(self.equipment, 1)
        if limit == 1 and self.recipe and self.recipe != recipe:
            return "Libere a saída primeiro."
        kinds = self.kinds
        if recipe.product not in kinds and len(kinds) >= limit:
            return f"Até {limit} tipos por vez."
        if self.amount(recipe.product) >= STACK_LIMIT:
            return "Lote cheio."
        if not bag.remove(recipe.costs):
            return "Faltam ingredientes."
        waiting = next((batch for batch in self.queue if batch[0] == recipe), None)
        if waiting is not None:
            waiting[1] += 1
        elif self.pending and self.recipe != recipe:
            self.queue.append([recipe, 1])
        else:
            if self.recipe != recipe:
                self._stock_ready()
            if not self.pending:
                self.next_finish = now + recipe.seconds
            self.recipe = recipe
            self.pending += 1
        return ""

    def collect(self, bag: Inventory, now: float) -> str:
        self.refresh(now)
        outputs = self.outputs
        if not outputs:
            return "Nenhum produto pronto."
        if not bag.exchange({}, tuple(outputs)):
            return "Mochila cheia."
        self.ready = 0
        self.stock.clear()
        if not self.pending:
            self.recipe = None
        return ""

    def refund(self) -> tuple[tuple[str, int], ...]:
        batches = ([(self.recipe, self.pending)] if self.pending else []) + [tuple(batch) for batch in self.queue]
        return tuple((item, n * count) for recipe, count in batches for item, n in recipe.costs.items())

    def cancel(self, bag: Inventory, now: float) -> str:
        self.refresh(now)
        if not self.pending:
            return "Nenhuma produção em andamento."
        if not bag.exchange({}, self.refund()):
            return "Abra espaço para os ingredientes."
        self.pending = 0
        self.queue.clear()
        if not self.ready:
            self.recipe = None
        return ""
