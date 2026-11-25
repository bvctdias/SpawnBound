from __future__ import annotations

import sys
import unittest
from pathlib import Path


SOURCE_ROOT = Path(__file__).resolve().parents[1] / "src"
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

from spawnbound.config import DEFAULT_CONFIG
from spawnbound.domain.coordinates import GridPos, NEIGHBOR_DIRECTIONS
from spawnbound.domain.model import BerryColor, ObjectKind, ToolTier, WorldObject
from spawnbound.domain.session import ActionCode, GameSession


class WorldObjectTests(unittest.TestCase):
    def setUp(self) -> None:
        self.session = GameSession.create(
            seed=1234,
            config=DEFAULT_CONFIG,
            chunk_preview_size=8,
        )
        self.session.world.objects.clear()

    def _place_player_next_to(self, position: GridPos) -> None:
        direction = NEIGHBOR_DIRECTIONS[0]
        self.session.player.position = position - direction

    def test_fallen_log_blocks_path_and_falls_faster_to_the_axe(self) -> None:
        position = GridPos(2, 2)
        fallen_log = WorldObject.create(position, ObjectKind.FALLEN_LOG)
        self.session.world.objects[position] = fallen_log
        self._place_player_next_to(position)

        self.assertFalse(self.session.world.is_walkable(position))
        result = self.session.primary_action(position)

        self.assertEqual(ActionCode.RESOURCE_HIT, result.code)
        self.assertEqual(ToolTier.BASIC, self.session.player.tool_tier)
        self.assertEqual(fallen_log.spec.durability - 1, fallen_log.durability)
        self.session.player.inventory.selected = 1
        self.assertTrue(self.session.primary_action(position).success)
        self.assertEqual(fallen_log.spec.durability - 4, fallen_log.durability)

    def test_bush_is_walkable_and_keeps_its_color_after_harvest(self) -> None:
        position = GridPos(2, 2)
        bush = WorldObject.create(
            position,
            ObjectKind.BERRY_BUSH,
            variant=BerryColor.PURPLE.value,
        )
        self.session.world.objects[position] = bush
        self._place_player_next_to(position)

        self.assertTrue(self.session.world.is_walkable(position))
        result = self.session.primary_action(position)

        self.assertEqual(ActionCode.RESOURCE_GATHERED, result.code)
        self.assertIs(bush, self.session.world.object_at(position))
        self.assertFalse(bush.available)
        self.assertEqual(BerryColor.PURPLE.value, bush.variant)
        self.assertEqual(1, self.session.player.inventory.quantity("berry"))
        self.assertFalse(self.session.afterimages[0].destroyed)

    def test_last_quartz_strike_keeps_resource_when_bag_is_full(self):
        from spawnbound.domain.inventory import Stack
        bag = self.session.player.inventory
        bag.slots[:] = [Stack("wood", 64)] * len(bag.slots)
        bag.slots[bag.selected] = Stack("quartz_pickaxe", 1)
        position = GridPos(2, 2)
        self._place_player_next_to(position)
        ore = WorldObject.create(position, ObjectKind.ROCK, variant="copper_ore")
        ore.durability = 3
        self.session.world.objects[position] = ore
        energy = self.session.player.energy
        self.assertEqual(ActionCode.INVENTORY_FULL, self.session.primary_action(position).code)
        self.assertFalse(self.session.afterimages)
        self.assertEqual((3, energy), (ore.durability, self.session.player.energy))
        bag.slots[-1] = None
        self.assertEqual(ActionCode.RESOURCE_GATHERED, self.session.primary_action(position).code)
        self.assertEqual(1, bag.quantity("copper"))
        self.assertEqual([True], [e.destroyed for e in self.session.afterimages])
        self.session.advance_time(.86)
        self.assertFalse(self.session.afterimages)


if __name__ == "__main__":
    unittest.main()
