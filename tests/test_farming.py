import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from spawnbound.config import DEFAULT_CONFIG
from spawnbound.domain.coordinates import GridPos
from spawnbound.domain.mobs import Mob, MobKind
from spawnbound.domain.model import Biome, ObjectKind, SpaceKind, TileKind, WorldObject
from spawnbound.domain.session import ActionCode, GameSession
from spawnbound.input import InputFrame
from spawnbound.states import GameplayState
from spawnbound.view import camera_origin, screen_center


class FarmingTests(unittest.TestCase):
    def setUp(self):
        self.game = GameSession.create(7, DEFAULT_CONFIG, chunk_preview_size=24)
        self.game.wildlife.mobs.clear()
        self.world = self.game.world
        self.home = self.game.player.position
        self.world.objects.clear()
        self.world.portals.clear()
        for p in tuple(self.world.tile_map.tiles):
            self.world.tile_map.add(p, TileKind.GRASS, biome=Biome.MEADOW, elevation=self.game.player.elevation)
        self.state = GameplayState(self.game, DEFAULT_CONFIG)
        self.cell = self.home + GridPos(1, 0)

    def click(self, cell):
        origin = camera_origin(self.game, DEFAULT_CONFIG, self.state.visual_position3d)
        return screen_center(self.world.surface_position(cell), origin, DEFAULT_CONFIG)

    def test_two_separate_right_clicks_prepare_only_the_selected_cell(self):
        self.state.step(InputFrame(right_click=self.click(self.cell)), 0)
        self.assertFalse(self.world.tilled_soil)
        for expected in (1, 2, 2):
            self.state.step(InputFrame(hotbar_index=2, right_click=self.click(self.cell)), .5)
            self.assertEqual({self.cell: expected}, self.world.tilled_soil)
            self.state.step(InputFrame(), .5)
            self.assertEqual(expected, self.world.tilled_soil[self.cell])
        self.assertTrue(self.world.is_walkable(self.cell))

    def test_changing_tool_while_approaching_cancels_the_farm_action(self):
        far = self.home + GridPos(4, 0)
        self.state.step(InputFrame(hotbar_index=2, right_click=self.click(far)), 0)
        self.assertEqual(far, self.state._pending_target)
        self.state.step(InputFrame(hotbar_index=0), 0)
        self.assertIsNone(self.state._pending_target)
        self.assertFalse(self.world.tilled_soil)

    def test_remote_plot_is_tilled_once_on_arrival(self):
        far = self.home + GridPos(4, 0)
        self.state.step(InputFrame(hotbar_index=2, right_click=self.click(far)), 0)
        for _ in range(40):
            self.state.step(InputFrame(), .05)
        self.assertEqual({far: 1}, self.world.tilled_soil)

    def test_invalid_tiles_are_protected(self):
        self.game.player.inventory.selected = 2
        self.world.objects[self.cell] = WorldObject.create(self.cell, ObjectKind.ROCK)
        self.assertEqual(ActionCode.BLOCKED, self.game.till_soil(self.cell).code)
        self.world.objects.pop(self.cell)
        for kind, biome in ((TileKind.GRASS, Biome.DRY), (TileKind.WATER, Biome.MEADOW)):
            self.world.tile_map.add(self.cell, kind, biome=biome, elevation=self.game.player.elevation)
            self.assertEqual(ActionCode.BLOCKED, self.game.till_soil(self.cell).code)
        self.world.tile_map.add(self.cell, TileKind.GRASS, elevation=self.game.player.elevation)
        self.world.space_kind = SpaceKind.CAVE
        self.assertEqual(ActionCode.BLOCKED, self.game.till_soil(self.cell).code)
        self.assertFalse(self.world.tilled_soil)

    def test_each_tool_and_what_it_can_do(self):
        bag = self.game.player.inventory
        self.assertEqual(["pickaxe", "axe", "sickle", "sword"], [s.item for s in bag.slots[:4]])
        location = self.world.surface_position(self.cell)
        self.game.wildlife.mobs[17] = Mob(17, MobKind.PIG, 20, location, location, 0.)
        for slot in range(4):
            bag.selected = slot
            self.game.player.energy = self.game.player.max_energy
            self.assertEqual(ActionCode.MOB_HIT, self.game.attack_mob(17).code)
        self.world.objects[self.cell] = WorldObject.create(self.cell, ObjectKind.TREE)
        for slot in range(4):
            bag.selected = slot
            self.assertEqual(ActionCode.RESOURCE_HIT, self.game.primary_action(self.cell).code)
        self.world.objects[self.cell] = WorldObject.create(self.cell, ObjectKind.ROCK)
        for wrong in (1, 2, 3):
            bag.selected = wrong
            self.assertEqual(ActionCode.TOOL_REQUIRED, self.game.primary_action(self.cell).code)
        bag.selected = 0
        self.assertEqual(ActionCode.RESOURCE_HIT, self.game.primary_action(self.cell).code)
