from __future__ import annotations

import sys
import unittest
from pathlib import Path


SOURCE_ROOT = Path(__file__).resolve().parents[1] / "src"
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

from spawnbound.config import DEFAULT_CONFIG
from spawnbound.domain.coordinates import NEIGHBOR_DIRECTIONS
from spawnbound.domain.coordinates import GridPos
from spawnbound.domain.model import ObjectKind, WorldObject
from spawnbound.domain.session import ActionCode, BRIDGE_KIT_ID, GameSession


class SessionTests(unittest.TestCase):
    def test_preview_corner_does_not_complete_a_sector(self) -> None:
        session = GameSession.create(seed=42, config=DEFAULT_CONFIG, chunk_preview_size=8)
        session.world.objects.clear()
        session.player.position = session.world.goal - GridPos(1, 0)
        self.assertTrue(session.move(GridPos(1, 0)).success)
        self.assertFalse(session.completed)

    def test_core_loop_gather_craft_build_cross(self) -> None:
        session = GameSession.create(seed=42, config=DEFAULT_CONFIG)

        for node in tuple(session.world.objects.values()):
            if not node.spec.drops:
                continue
            neighbor_and_facing = next(
                (
                    (node.position - direction, direction)
                    for direction in NEIGHBOR_DIRECTIONS
                    if session.world.is_walkable(node.position - direction)
                ),
                None,
            )
            self.assertIsNotNone(neighbor_and_facing)
            neighbor, facing = neighbor_and_facing  # type: ignore[misc]
            session.player.position = neighbor
            session.player.facing = facing
            session.player.inventory.selected = 1 if node.drops[0][0] == "wood" else 0
            while node.position in session.world.objects:
                result = session.primary_action(node.position)
                self.assertTrue(result.success)

        self.assertEqual(set(session.world.waystones), set(session.world.objects))
        crafted = session.craft_bridge_kit()
        self.assertEqual(ActionCode.CRAFTED, crafted.code)
        self.assertEqual(1, session.player.inventory.quantity(BRIDGE_KIT_ID))

        session.player.position = session.world.bridge.entry
        session.player.facing = session.world.bridge.direction
        built = session.interact()
        self.assertEqual(ActionCode.BRIDGE_BUILT, built.code)
        self.assertTrue(session.world.bridge.built)
        self.assertTrue(all(session.world.tile_map.is_walkable(cell) for cell in session.world.bridge.cells))

        for _ in session.world.bridge.cells:
            session.move(session.world.bridge.direction)
        session.move(session.world.bridge.direction)
        self.assertEqual(session.world.bridge.exit, session.player.position)

        while session.player.position != session.world.goal:
            result = session.move(session.world.bridge.direction)
            self.assertTrue(result.success)
        self.assertTrue(session.completed)

    def test_e_does_not_break_a_resource(self) -> None:
        session = GameSession.create(seed=42, config=DEFAULT_CONFIG)
        node = next(iter(session.world.objects.values()))
        neighbor, facing = next(
            (node.position - direction, direction)
            for direction in NEIGHBOR_DIRECTIONS
            if session.world.is_walkable(node.position - direction)
        )
        session.player.position = neighbor
        session.player.facing = facing
        durability_before = node.durability

        result = session.interact()

        self.assertEqual(ActionCode.PRIMARY_ACTION_REQUIRED, result.code)
        self.assertEqual(durability_before, node.durability)

    def test_rest_recovers_only_fifteen_percent_in_a_bed(self) -> None:
        session = GameSession.create(seed=7, config=DEFAULT_CONFIG)
        session.player.energy = 20

        session.player.position = session.world.camp
        denied = session.rest()
        self.assertEqual(ActionCode.CAMP_REQUIRED, denied.code, "the camp tent left the game")

        bed = session.player.position + session.player.facing
        session.world.objects[bed] = WorldObject.create(bed, ObjectKind.BED, elevation=session.world.elevation_at(bed))
        rested = session.rest()
        self.assertEqual(ActionCode.RESTED, rested.code)
        self.assertEqual(35, session.player.energy)


if __name__ == "__main__":
    unittest.main()
