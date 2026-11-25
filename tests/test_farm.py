import os
import sys
import unittest
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "dependencias")]

import pygame

from spawnbound.config import DEFAULT_CONFIG
from spawnbound.crop_art import crop_sprite
from spawnbound.domain.coordinates import GridPos
from spawnbound.domain.crafting import RECIPES
from spawnbound.domain.farming import CROPS, SEEDS, STAGES, Crop
from spawnbound.domain.inventory import Stack
from spawnbound.domain.model import Biome, TileKind, World
from spawnbound.domain.session import FOOD, ActionCode, GameSession
from spawnbound.input import InputFrame
from spawnbound.renderer import PlaceholderRenderer
from spawnbound.states import GameplayState
from spawnbound.view import camera_origin, screen_center


class WildGardenTests(unittest.TestCase):
    def test_a_ripe_garden_near_the_camp_on_every_seed(self):
        for seed in (1234, 77, 2024, 5):
            with self.subTest(seed=seed):
                session = GameSession.create(seed, DEFAULT_CONFIG, chunk_preview_size=128)
                world = session.world
                self.assertEqual(["carrot", "carrot", "turnip", "pumpkin"],
                                 sorted((c.kind for c in world.crops.values()), key=["carrot", "turnip", "pumpkin"].index))
                for cell in world.crops:
                    self.assertTrue(session.crop_ripe(cell))
                    self.assertLessEqual(max(abs(cell.x - world.camp.x), abs(cell.y - world.camp.y)), 5)
                    self.assertNotIn(cell, world.objects)
                    self.assertTrue(world.is_walkable(cell))

    def test_the_composter_turns_each_crop_into_its_seed(self):
        products = {recipe.product: recipe.costs for recipe in RECIPES["composter"]}
        for kind, spec in CROPS.items():
            self.assertEqual({kind: 1}, products[spec.seed])
            self.assertIn(kind, FOOD)

    def test_old_worlds_have_no_crops(self):
        self.assertEqual({}, World.__dataclass_fields__["crops"].default_factory())


class FarmTests(unittest.TestCase):
    def setUp(self):
        self.game = GameSession.create(7, DEFAULT_CONFIG, chunk_preview_size=24)
        self.game.wildlife.mobs.clear()
        self.world = self.game.world
        self.world.crops.clear()
        self.world.objects.clear()
        self.world.portals.clear()
        self.home = self.game.player.position
        for p in tuple(self.world.tile_map.tiles):
            self.world.tile_map.add(p, TileKind.GRASS, biome=Biome.MEADOW, elevation=self.game.player.elevation)
        self.state = GameplayState(self.game, DEFAULT_CONFIG)
        self.cell = self.home + GridPos(1, 0)
        self.bag = self.game.player.inventory

    def click(self, cell):
        origin = camera_origin(self.game, DEFAULT_CONFIG, self.state.visual_position3d)
        return screen_center(self.world.surface_position(cell), origin, DEFAULT_CONFIG)

    def hold_seed(self, seed="carrot_seed", count=3):
        self.bag.slots[4] = Stack(seed, count)
        self.bag.selected = 4

    def test_a_seed_needs_soil_the_sickle_prepared(self):
        self.hold_seed()
        self.assertIs(ActionCode.BLOCKED, self.game.plant(self.cell).code)
        self.world.tilled_soil[self.cell] = 1
        self.assertIs(ActionCode.BLOCKED, self.game.plant(self.cell).code)
        self.world.tilled_soil[self.cell] = 2
        result = self.game.plant(self.cell)
        self.assertIs(ActionCode.PLANTED, result.code)
        self.assertEqual("Semente de cenoura plantada.", result.message)
        self.assertEqual(2, self.bag.quantity("carrot_seed"))
        self.assertEqual("carrot", self.world.crops[self.cell].kind)
        self.assertIs(ActionCode.BLOCKED, self.game.plant(self.cell).code, "one plant per cell")
        self.bag.selected = 0
        self.assertIs(ActionCode.TOOL_REQUIRED, self.game.plant(self.cell + GridPos(0, 1)).code)

    def test_it_grows_through_four_stages_over_its_days(self):
        day = self.game.day_seconds
        for kind, spec in CROPS.items():
            with self.subTest(kind=kind):
                self.world.crops[self.cell] = Crop(kind, self.game.production_seconds)
                total = spec.days * day
                seen = []
                for fraction in (0, .2, .4, .7, .99, 1.):
                    self.world.crops[self.cell].planted = self.game.production_seconds - fraction * total
                    seen.append(self.game.crop_stage(self.cell))
                self.assertEqual([0, 0, 1, 2, 2, 3], seen)
                self.assertTrue(self.game.crop_ripe(self.cell))

    def test_the_ripe_crop_comes_out_and_the_soil_stays_ready(self):
        self.world.tilled_soil[self.cell] = 2
        self.world.crops[self.cell] = Crop("pumpkin", self.game.production_seconds)
        self.assertIs(ActionCode.BLOCKED, self.game.harvest(self.cell).code)
        self.game.production_seconds += CROPS["pumpkin"].days * self.game.day_seconds
        result = self.game.harvest(self.cell)
        self.assertIs(ActionCode.RESOURCE_GATHERED, result.code)
        self.assertEqual(1, self.bag.quantity("pumpkin"))
        self.assertNotIn(self.cell, self.world.crops)
        self.assertEqual(2, self.world.tilled_soil[self.cell])
        self.assertEqual("pumpkin", self.game.afterimages[-1].loot)

    def test_growing_plants_keep_the_sickle_and_furniture_away(self):
        self.world.tilled_soil[self.cell] = 2
        self.world.crops[self.cell] = Crop("turnip", self.game.production_seconds)
        self.assertEqual("Já há uma planta aqui.", self.game.soil_obstacle(self.cell))
        self.assertFalse(self.game.can_place(self.cell))

    def test_sleeping_makes_it_grow(self):
        self.world.crops[self.cell] = Crop("carrot", self.game.production_seconds)
        before = self.game.crop_stage(self.cell)
        self.game.production_seconds += self.game.day_seconds
        self.assertGreater(self.game.crop_stage(self.cell), before)

    def test_right_clicks_sow_and_harvest(self):
        self.world.tilled_soil[self.cell] = 2
        self.hold_seed("turnip_seed")
        self.state.step(InputFrame(right_click=self.click(self.cell)), 0)
        for _ in range(20):
            self.state.step(InputFrame(), .1)
        self.assertEqual("turnip", self.world.crops[self.cell].kind)
        self.game.production_seconds += CROPS["turnip"].days * self.game.day_seconds
        self.bag.selected = 1
        self.state.step(InputFrame(right_click=self.click(self.cell)), 0)
        for _ in range(20):
            self.state.step(InputFrame(), .1)
        self.assertNotIn(self.cell, self.world.crops)
        self.assertEqual(2, self.bag.quantity("turnip"))

    def test_a_seed_on_unprepared_soil_explains_why(self):
        self.hold_seed()
        self.state.step(InputFrame(right_click=self.click(self.cell)), 0)
        self.assertEqual("Prepare a terra com a foice antes de plantar.", self.game.notice)
        self.assertFalse(self.world.crops)


class CropArtTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pygame.init()

    def test_every_stage_of_every_crop_has_its_own_picture(self):
        for kind in CROPS:
            images = {pygame.image.tobytes(crop_sprite(kind, s, 0, 1)[0], "RGBA") for s in range(STAGES)}
            self.assertEqual(STAGES, len(images), kind)
        ripe = {pygame.image.tobytes(crop_sprite(kind, 3, 1, 1)[0], "RGBA") for kind in CROPS}
        self.assertEqual(3, len(ripe))

    def test_the_leaves_sway_but_a_seed_stays_still(self):
        frames = {pygame.image.tobytes(crop_sprite("carrot", 3, f, 1)[0], "RGBA") for f in range(4)}
        self.assertGreater(len(frames), 1)
        seed = {pygame.image.tobytes(crop_sprite("carrot", 0, f, 1)[0], "RGBA") for f in range(4)}
        self.assertEqual(1, len(seed))

    def test_the_garden_is_drawn(self):
        session = GameSession.create(1234, DEFAULT_CONFIG, chunk_preview_size=128)
        session.player.place(session.world.surface_position(session.world.camp))
        renderer = PlaceholderRenderer(pygame.Surface((960, 540)), DEFAULT_CONFIG)
        renderer.draw_gameplay(session, debug=False)
        actors = renderer._actors(session, session.player.position3d)
        self.assertEqual(4, sum(1 for actor in actors if actor.kind == "crop"))


if __name__ == "__main__":
    unittest.main()
