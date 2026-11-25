from __future__ import annotations

import sys
import unittest
from pathlib import Path


SOURCE_ROOT = Path(__file__).resolve().parents[1] / "src"
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

from spawnbound.domain.inventory import Inventory, SLOT_COUNT, STACK_LIMIT, Stack


class InventoryTests(unittest.TestCase):
    def test_partial_merge_swap_and_single_transfer_preserve_items(self):
        bag = Inventory()
        bag.add("pickaxe")
        bag.add("wood", 70)
        bag.transfer(1, 12)
        bag.transfer(12, 2)
        self.assertEqual((Stack("wood", 64), Stack("wood", 6)), (bag.slots[2], bag.slots[12]))
        bag.transfer(12, 9, single=True)
        bag.transfer(0, 9)
        self.assertEqual({"wood": 70, "pickaxe": 1}, dict(bag.snapshot()))
        self.assertEqual((Stack("wood", 1), Stack("pickaxe", 1)), (bag.slots[0], bag.slots[9]))

    def test_full_bag_rolls_back_exchange_and_reuses_emptied_recipe_slot(self):
        bag = Inventory()
        bag.add("wood", STACK_LIMIT * SLOT_COUNT)
        before = bag.slots.copy()
        self.assertFalse(bag.add("stone"))
        self.assertFalse(bag.exchange({"wood": 3}, (("bridge_kit", 1),)))
        self.assertEqual(before, bag.slots)
        self.assertTrue(bag.exchange({"wood": STACK_LIMIT}, (("bridge_kit", 1),)))
        self.assertEqual(1, bag.quantity("bridge_kit"))

    def test_recipe_removal_is_atomic(self) -> None:
        inventory = Inventory()
        inventory.add("wood", 3)

        self.assertFalse(inventory.remove({"wood": 3, "stone": 2}))
        self.assertEqual(3, inventory.quantity("wood"))

        inventory.add("stone", 2)
        self.assertTrue(inventory.remove({"wood": 3, "stone": 2}))
        self.assertEqual(0, inventory.quantity("wood"))
        self.assertEqual(0, inventory.quantity("stone"))

    def test_snapshot_cannot_mutate_inventory(self) -> None:
        inventory = Inventory()
        inventory.add("wood", 1)
        snapshot = inventory.snapshot()
        with self.assertRaises(TypeError):
            snapshot["wood"] = 99  # type: ignore[index]


if __name__ == "__main__":
    unittest.main()
