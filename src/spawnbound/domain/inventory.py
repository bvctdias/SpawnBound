from __future__ import annotations

from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Mapping
from spawnbound.domain.tools import STARTER_TOOLS, TOOLS


HOTBAR_SIZE = 5
SLOT_COUNT = HOTBAR_SIZE * 4
CHEST_COLUMNS = 8
CHEST_SIZE = CHEST_COLUMNS * 4
STACK_LIMIT = 64


def stack_limit(item: str) -> int:
    return 1 if item in TOOLS else STACK_LIMIT


@dataclass(frozen=True, slots=True)
class Stack:
    item: str
    count: int


@dataclass(slots=True)
class Inventory:
    slots: list[Stack | None] = field(default_factory=lambda: [None] * SLOT_COUNT)
    selected: int = 0

    @classmethod
    def starter(cls) -> Inventory:
        inventory = cls()
        for tool in STARTER_TOOLS:
            inventory.add(tool)
        return inventory

    @property
    def equipped(self) -> str | None:
        stack = self.slots[self.selected]
        return stack.item if stack else None

    def quantity(self, item_id: str) -> int:
        return sum(stack.count for stack in self.slots if stack and stack.item == item_id)

    def can_add(self, item_id: str, amount: int = 1) -> bool:
        limit = stack_limit(item_id)
        capacity = sum(limit if stack is None else limit - stack.count
                       for stack in self.slots if stack is None or stack.item == item_id)
        return 0 < amount <= capacity

    def add(self, item_id: str, amount: int = 1) -> bool:
        if amount <= 0:
            raise ValueError("amount must be positive")
        if not self.can_add(item_id, amount):
            return False
        limit = stack_limit(item_id)
        for empty in (False, True):
            for i, stack in enumerate(self.slots):
                if (stack is None) != empty or (stack and stack.item != item_id):
                    continue
                count = stack.count if stack else 0
                added = min(limit - count, amount)
                self.slots[i] = Stack(item_id, count + added)
                amount -= added
                if not amount:
                    return True
        return False

    def has(self, costs: Mapping[str, int]) -> bool:
        return all(amount >= 0 and self.quantity(item) >= amount for item, amount in costs.items())

    def remove(self, costs: Mapping[str, int], *, selected_first: bool = False) -> bool:
        if not self.has(costs):
            return False
        order = list(reversed(range(len(self.slots))))
        if selected_first:
            order.remove(self.selected)
            order.insert(0, self.selected)
        for item, amount in costs.items():
            # Gasta primeiro o estoque para preservar as pilhas da barra de atalhos.
            for i in order:
                if not amount:
                    break
                stack = self.slots[i]
                if stack and stack.item == item:
                    taken = min(amount, stack.count)
                    self.slots[i] = Stack(item, stack.count - taken) if stack.count > taken else None
                    amount -= taken
        return True

    def transfer(self, source: int, target: int, *, single: bool = False, destination: Inventory | None = None) -> None:
        slots = self.slots if destination is None else destination.slots
        stack, other = self.slots[source], slots[target]
        if stack is None or (slots is self.slots and source == target):
            return
        if other and other.item != stack.item:
            if not single:
                slots[target], self.slots[source] = stack, other
            return
        count = other.count if other else 0
        limit = stack_limit(stack.item)
        moved = min(1 if single else stack.count, limit - count)
        slots[target] = Stack(stack.item, count + moved)
        self.slots[source] = Stack(stack.item, stack.count - moved) if moved < stack.count else None

    def exchange(self, costs: Mapping[str, int], rewards: tuple[tuple[str, int], ...]) -> bool:
        trial = Inventory(self.slots.copy(), self.selected)
        if not trial.remove(costs) or not all(trial.add(item, n) for item, n in rewards):
            return False
        self.slots[:] = trial.slots
        return True

    def snapshot(self) -> Mapping[str, int]:
        items = {stack.item for stack in self.slots if stack}
        return MappingProxyType({item: self.quantity(item) for item in sorted(items)})
