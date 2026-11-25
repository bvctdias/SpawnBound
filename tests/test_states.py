from __future__ import annotations

import sys
import unittest
from pathlib import Path


SOURCE_ROOT = Path(__file__).resolve().parents[1] / "src"
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

from spawnbound.config import GameConfig
from spawnbound.domain.coordinates import GridPos, WorldPos
from spawnbound.domain.model import ObjectKind, TreeVariant, WorldObject
from spawnbound.domain.session import GameSession
from spawnbound.input import InputFrame
from spawnbound.states import ClickIntent, GameplayState
from spawnbound.view import camera_origin, screen_center, slot_rect


class GameplayStatePointAndClickTests(unittest.TestCase):
    def _slot_center(self, index, backpack=True):
        x, y, w, h = slot_rect(self.config, index, backpack)
        return x+w//2, y+h//2

    def test_wheel_wrap_numbers_and_hud_click_do_not_move_player(self):
        bag = self.session.player.inventory
        self.state.step(InputFrame(wheel_steps=1), 0)
        self.assertEqual(4, bag.selected)
        self.state.step(InputFrame(wheel_steps=-2), 0)
        self.assertEqual(1, bag.selected)
        self.state.step(InputFrame(hotbar_index=3), 0)
        self.assertEqual(3, bag.selected)
        self.state.step(InputFrame(destination_click=self._slot_center(0, False)), 0)
        self.assertEqual("pickaxe", bag.equipped)
        self.assertFalse(self.state._path)

    def test_backpack_drag_click_single_and_number_pause_the_world(self):
        bag = self.session.player.inventory
        bag.add("stone", 4)
        self.state.step(InputFrame(inventory_pressed=True), 0)
        self.state.step(InputFrame(destination_click=self._slot_center(4), left_release=self._slot_center(8)), 31)
        self.state.step(InputFrame(destination_click=self._slot_center(8)), 1)
        self.state.step(InputFrame(right_click=self._slot_center(9)), 1)
        self.state.step(InputFrame(destination_click=self._slot_center(10)), 1)
        self.state.step(InputFrame(pointer=self._slot_center(10), hotbar_index=0), 1)
        self.assertEqual(("stone", 3), (bag.equipped, bag.slots[0].count))
        self.assertEqual("pickaxe", bag.slots[10].item)
        self.assertEqual(1, bag.slots[9].count)
        self.assertEqual(0, self.session.cycle_seconds)
        self.state.step(InputFrame(pause_pressed=True), 0)
        self.assertFalse(self.state.inventory_open)
        self.assertFalse(self.state._path)

    def test_selected_tool_controls_harvest_and_selected_meat_is_eaten_first(self):
        from spawnbound.domain.session import ActionCode

        bag = self.session.player.inventory
        pos = self.session.player.position + GridPos(1, 0)
        self.session.world.objects[pos] = WorldObject.create(pos, ObjectKind.ROCK)
        bag.selected = 1
        energy = self.session.player.energy
        self.assertEqual(ActionCode.TOOL_REQUIRED, self.session.primary_action(pos).code)
        self.assertEqual(energy, self.session.player.energy)
        bag.selected = 0
        self.assertTrue(self.session.primary_action(pos).success)
        bag.add("meat", 65)
        bag.selected = 4
        self.state.step(InputFrame(right_click=(30, 100)), 0)
        self.assertEqual((63, 1), (bag.slots[4].count, bag.slots[5].count))

    def setUp(self) -> None:
        self.config = GameConfig(movement_seconds_per_cell=.40, camera_zoom=1)
        self.session = GameSession.create(
            seed=1234,
            config=self.config,
            chunk_preview_size=8,
        )
        self.session.world.objects.clear()
        self.state = GameplayState(session=self.session, config=self.config)

    def _click_for(self, position: GridPos) -> tuple[int, int]:
        origin = camera_origin(self.session, self.config)
        return screen_center(position, origin, self.config)

    def test_click_builds_a_route_and_moves_until_the_destination(self) -> None:
        start = self.session.player.position
        destination = start + GridPos(2, 0)
        click = self._click_for(destination)

        self.state.step(InputFrame(destination_click=click), 0.0)
        self.assertEqual(start, self.session.player.position)
        self.assertTrue(self.state._path)

        self.state.step(InputFrame(), 0.05)
        self.assertEqual(start, self.session.player.position)
        self.assertAlmostEqual(start.x + .125, self.session.player.position3d.x)

        self.state.step(InputFrame(), 0.75)
        self.assertEqual(destination, self.session.player.position)
        self.assertEqual((), self.state._path)

    def test_actual_position_matches_visual_xy_during_movement(self) -> None:
        start = self.session.player.position
        destination = start + GridPos(2, 0)

        self.state.step(InputFrame(destination_click=self._click_for(destination)), 0.0)
        logical_first_step = self.session.player.position
        self.assertEqual((float(start.x), float(start.y)), self.state.visual_position)

        self.state.step(InputFrame(), 0.09)

        self.assertNotEqual((float(start.x), float(start.y)), self.state.visual_position)
        self.assertNotEqual(
            (float(logical_first_step.x), float(logical_first_step.y)),
            self.state.visual_position,
        )
        actual = self.session.player.position3d
        self.assertEqual((actual.x, actual.y), self.state.visual_position)
        self.assertEqual(actual.grid, self.session.player.position)

    def _click_point(self, point: WorldPos) -> tuple[int, int]:
        origin = camera_origin(self.session, self.config, self.state.visual_position3d)
        return screen_center(point, origin, self.config)

    def test_can_move_and_stop_inside_the_current_tile(self) -> None:
        start = self.session.player.position
        point = WorldPos(start.x + .25, start.y + .125, 0)
        self.state.step(InputFrame(destination_click=self._click_point(point)), 0)
        self.state.step(InputFrame(), 1)
        self.assertEqual(start, self.session.player.position)
        self.assertEqual(point, self.session.player.position3d)
        self.assertEqual((point.x, point.y, point.z), self.state.visual_position3d)
        self.assertIsNone(self.state._animation_to)

    def test_zero_duration_movement_finishes_at_exact_point(self) -> None:
        config = GameConfig(movement_seconds_per_cell=0, camera_zoom=1)
        self.state = GameplayState(self.session, config)
        p = self.session.player.position
        point = WorldPos(p.x + 1.25, p.y + .125, 0)
        self.state.step(InputFrame(destination_click=self._click_point(point)), 0)
        self.assertEqual(point, self.session.player.position3d)
        self.assertEqual((), self.state._path)
        self.assertIsNone(self.state._animation_to)

    def test_resource_hit_does_not_recenter_player_already_in_range(self) -> None:
        p = self.session.player.position
        point = WorldPos(p.x + .25, p.y + .125, 0)
        self.state.step(InputFrame(destination_click=self._click_point(point)), 1)
        target = p + GridPos(1, 0)
        self.session.world.objects[target] = WorldObject.create(target, ObjectKind.ROCK)
        self.state._plan_target(target, ClickIntent.PRIMARY_ACTION)
        self.assertEqual(point, self.session.player.position3d)
        self.assertEqual(22, self.session.world.objects[target].durability)
        self.assertEqual(99, self.session.player.energy)

    def test_stops_at_the_junction_of_four_tiles(self) -> None:
        start = self.session.player.position
        point = WorldPos(start.x + .5, start.y + .5, 0)
        self.state.step(InputFrame(destination_click=self._click_point(point)), 0)
        self.state.step(InputFrame(), 1)
        self.assertAlmostEqual(point.x, self.session.player.position3d.x)
        self.assertAlmostEqual(point.y, self.session.player.position3d.y)

    def test_cancel_stops_immediately_without_finishing_the_cell(self) -> None:
        start = self.session.player.position
        point = WorldPos(start.x + 2.25, start.y + .125, 0)
        self.state.step(InputFrame(destination_click=self._click_point(point)), .04)
        before = self.session.player.position3d
        self.assertNotEqual(start.x, before.x)
        self.state.step(InputFrame(cancel_path_pressed=True), 1)
        self.assertEqual(before, self.session.player.position3d)
        self.assertEqual((before.x, before.y, before.z), self.state.visual_position3d)
        self.assertIsNone(self.state._animation_to)

    def test_retarget_mid_walk_starts_from_actual_position(self) -> None:
        start = self.session.player.position
        self.state.step(InputFrame(destination_click=self._click_point(
            WorldPos(start.x + 2, start.y, 0))), .06)
        before = self.session.player.position3d
        point = WorldPos(start.x + .125, start.y + 1.25, 0)
        self.state.step(InputFrame(destination_click=self._click_point(point)), 0)
        self.assertEqual(before, self.session.player.position3d)
        self.assertEqual((before.x, before.y), self.state.visual_position)
        self.state.step(InputFrame(), 1)
        self.assertAlmostEqual(point.x, self.session.player.position3d.x, delta=.025)
        self.assertAlmostEqual(point.y, self.session.player.position3d.y, delta=.025)

    def test_open_route_goes_directly_to_off_center_click(self) -> None:
        start = self.session.player.position
        point = WorldPos(start.x + 2, start.y + .25, 0)
        self.state.step(InputFrame(destination_click=self._click_point(point)), .08)
        x, y = self.state.visual_position
        self.assertAlmostEqual(.25 / 2, (y - start.y) / (x - start.x))

    def test_new_blocker_during_movement_cannot_be_crossed(self) -> None:
        start = self.session.player.position
        target = start + GridPos(3, 0)
        self.state.step(InputFrame(destination_click=self._click_for(target)), .03)
        block = start + GridPos(1, 0)
        self.session.world.objects[block] = WorldObject.create(block, ObjectKind.ROCK)
        for _ in range(60):
            self.state.step(InputFrame(), .04)
            self.assertNotEqual(block, self.session.player.position)
        self.assertEqual(target, self.session.player.position)

    def test_visual_velocity_is_constant_inside_each_cell(self) -> None:
        start = self.session.player.position
        destination = start + GridPos(3, 0)

        self.state.step(InputFrame(destination_click=self._click_for(destination)), 0.0)
        samples: list[tuple[float, float]] = []
        for _frame in range(5):
            self.state.step(InputFrame(), 0.04)
            samples.append(self.state.visual_position)

        points = [(float(start.x), float(start.y)), *samples]
        deltas = [
            (current[0] - previous[0], current[1] - previous[1])
            for previous, current in zip(points, points[1:])
        ]
        for delta in deltas[1:]:
            self.assertAlmostEqual(deltas[0][0], delta[0])
            self.assertAlmostEqual(deltas[0][1], delta[1])

    def test_clicking_a_resource_approaches_and_hits_it(self) -> None:
        self.session.player.inventory.selected = 1
        target = self.session.player.position + GridPos(3, 0)
        self.session.world.objects[target] = WorldObject.create(target, ObjectKind.TREE)

        self.state.step(InputFrame(destination_click=self._click_for(target)), 0.0)
        for _frame in range(12):
            self.state.step(InputFrame(), 0.10)

        self.assertIn(target, self.session.world.objects)
        self.assertEqual(28, self.session.world.objects[target].durability)
        self.assertEqual(0, self.session.player.inventory.quantity("wood"))
        self.assertEqual(99, self.session.player.energy)

        self.state.step(InputFrame(destination_click=self._click_for(target), primary_held=True), 0.0)
        for _ in range(95):
            self.state.step(InputFrame(primary_held=True), .05)
        self.assertNotIn(target, self.session.world.objects)
        self.assertEqual(2, self.session.player.inventory.quantity("wood"))
        self.assertEqual(92, self.session.player.energy)

    def test_holding_harvests_only_the_clicked_resource_and_credits_once(self):
        self.session.player.inventory.selected = 1
        target = self.session.player.position + GridPos(3, 0)
        tree = WorldObject.create(target, ObjectKind.TREE)
        self.session.world.objects[target] = tree
        self.state.step(InputFrame(destination_click=self._click_for(target), primary_held=True), 0)
        for _ in range(145):
            self.state.step(InputFrame(primary_held=True), .05)
        self.assertNotIn(target, self.session.world.objects)
        self.assertEqual(2, self.session.player.inventory.quantity("wood"))
        self.assertEqual(92, self.session.player.energy)
        self.assertEqual([], self.session.afterimages)

    def test_releasing_after_a_strike_keeps_the_damaged_resource(self):
        target = self.session.player.position + GridPos(1, 0)
        rock = WorldObject.create(target, ObjectKind.ROCK, variant="coal_ore")
        self.session.world.objects[target] = rock
        self.state.step(InputFrame(destination_click=self._click_for(target), primary_held=True), 0)
        self.state.step(InputFrame(), .60)
        self.assertEqual(22, rock.durability)
        self.assertEqual([], self.session.afterimages)
        self.state.step(InputFrame(destination_click=self._click_for(target), primary_held=True), 0)
        for _ in range(61):
            self.state.step(InputFrame(primary_held=True), .05)
        self.assertEqual("coal", self.session.afterimages[0].loot)
        self.assertEqual(1, self.session.player.inventory.quantity("coal"))

    def test_upgrade_in_selected_slot_and_harvest_duration_at_multiple_frame_rates(self):
        from spawnbound.domain.inventory import Inventory, Stack
        from spawnbound.domain.tools import UPGRADES
        p = self.session.player.position + GridPos(1, 0)
        bag = self.session.player.inventory
        bag.transfer(0, 2)
        bag.selected = 2
        for item, rock_time in (("pickaxe", 3.45), ("stone_pickaxe", 2.5875),
                                ("copper_pickaxe", 1.725), ("quartz_pickaxe", 1.29375)):
            self.assertEqual(item, bag.equipped)
            chest = Inventory()
            bag.transfer(2, 0, destination=chest)
            self.assertFalse(self.session.player.tool_tier)
            chest.transfer(0, 2, destination=bag)
            for fps in (30, 60, 144):
                for kind, expected in ((ObjectKind.TREE, 4.50), (ObjectKind.ROCK, rock_time)):
                    bag.selected = 1 if kind is ObjectKind.TREE else 2
                    state = GameplayState(self.session, self.config)
                    self.session.world.objects[p] = WorldObject.create(p, kind)
                    self.session.player.energy = 100
                    state._plan_target(p, ClickIntent.PRIMARY_ACTION)
                    for n in range(1, 6*fps):
                        state.step(InputFrame(primary_held=True), 1/fps)
                        if p not in self.session.world.objects:
                            break
                    self.assertAlmostEqual(expected, n/fps, delta=1/fps + 1e-8)
                    self.assertEqual(92 if kind is ObjectKind.TREE else 90, self.session.player.energy)
            if item in UPGRADES:
                _, costs, _, _ = UPGRADES[item]
                for ingredient, count in costs.items():
                    bag.add(ingredient, count)
                state.step(InputFrame(upgrade_pressed=True), 0)
        before = bag.snapshot()
        state.step(InputFrame(upgrade_pressed=True), 0)
        self.assertEqual(before, bag.snapshot())
        self.assertEqual(Stack("quartz_pickaxe", 1), bag.slots[2])

    def test_click_spam_cannot_bypass_swing_and_failed_upgrade_preserves_inventory(self):
        p = self.session.player.position + GridPos(1, 0)
        tree = WorldObject.create(p, ObjectKind.TREE)
        self.session.world.objects[p] = tree
        bag = self.session.player.inventory
        before = bag.snapshot()
        self.state.step(InputFrame(upgrade_pressed=True), 0)
        self.assertEqual(before, bag.snapshot())
        bag.selected = 1
        for _ in range(30):
            self.state.step(InputFrame(destination_click=self._click_for(p)), .01)
        self.assertEqual(tree.spec.durability - 3, tree.durability)

    def test_context_target_waits_for_e_after_the_player_approaches(self) -> None:
        session = GameSession.create(seed=42, config=self.config)
        state = GameplayState(session=session, config=self.config)

        state._plan_target(session.world.bridge.cells[0], ClickIntent.CONTEXT_INTERACTION)
        for _frame in range(100):
            state.step(InputFrame(), 0.10)

        self.assertEqual("Pressione E para interagir.", session.last_message)
        self.assertEqual(
            session.world.bridge.cells[0],
            session.player.position + session.player.facing,
        )

        state.step(InputFrame(interact_pressed=True), 0.0)
        self.assertEqual("Fabrique um kit de ponte com C.", session.last_message)

    def test_clicking_the_hud_does_not_change_the_route(self) -> None:
        start = self.session.player.position

        self.state.step(InputFrame(destination_click=(480, 504)), 0.0)

        self.assertEqual(start, self.session.player.position)
        self.assertEqual((), self.state._path)

    def test_tree_trunk_click_targets_tree_instead_of_floor_beneath_it(self) -> None:
        target = self.session.player.position + GridPos(3, 0)
        self.session.world.objects[target] = WorldObject.create(
            target, ObjectKind.TREE, variant=TreeVariant.PINE_DARK.value)
        x, y = self._click_for(target)
        self.state.step(InputFrame(destination_click=(x, y - 15)), 0)
        self.assertEqual(target, self.state._pending_target)

    def test_route_speed_does_not_depend_on_frame_rate(self) -> None:
        for fps in (30, 50, 60, 120, 144):
            with self.subTest(fps=fps):
                self.setUp()
                start = self.session.player.position
                destination = start + GridPos(3, 0)
                self.state.step(InputFrame(destination_click=self._click_for(destination)), 0)
                total = .37
                steps = int(total * fps)
                for _ in range(steps):
                    self.state.step(InputFrame(), 1 / fps)
                self.state.step(InputFrame(), total - steps / fps)
                self.assertAlmostEqual(start.x + .925, self.state.visual_position[0])
                self.assertAlmostEqual(start.y, self.state.visual_position[1])

    def test_right_click_cancels_the_current_route(self) -> None:
        destination = self.session.player.position + GridPos(3, 0)
        self.state.step(InputFrame(destination_click=self._click_for(destination)), 0.0)
        self.assertTrue(self.state._path)

        position_before_cancel = self.session.player.position
        self.state.step(InputFrame(cancel_path_pressed=True), 1.0)

        self.assertEqual(position_before_cancel, self.session.player.position)
        self.assertEqual((), self.state._path)


if __name__ == "__main__":
    unittest.main()
