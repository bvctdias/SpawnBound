import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "dependencias")]
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame

from spawnbound.config import GameConfig
from spawnbound.domain.coordinates import GridPos
from spawnbound.domain.exploration import BASE_REVEAL, REVEAL_RADIUS, IslandSurvey
from spawnbound.domain.model import TileKind
from spawnbound.domain.session import GameSession
from spawnbound.input import InputFrame
from spawnbound.island_map import CELL, WATER, IslandMap, island_pixels
from spawnbound.pixel_font import PixelFont
from spawnbound.renderer import PlaceholderRenderer
from spawnbound.seabed import shore_depth
from spawnbound.states import GameplayState

SEEDS = (1234, 99)


class IslandMapTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pygame.font.init()
        cls.config = GameConfig()
        cls.sessions = {seed: GameSession.create(seed, cls.config, chunk_preview_size=128) for seed in SEEDS}

    def fresh(self, seed):
        session = self.sessions[seed]
        session.survey = IslandSurvey.of(session.world)
        return session

    def test_the_base_and_every_travel_point_start_revealed(self):
        for seed in SEEDS:
            with self.subTest(seed=seed):
                world = self.fresh(seed).world
                survey = IslandSurvey.of(world)
                self.assertTrue(survey.seen(world.spawn))
                self.assertTrue(survey.seen(world.spawn + GridPos(BASE_REVEAL, 0)))
                self.assertTrue(all(survey.seen(p.position) for p in world.portals.values()))
                far = GridPos(world.spawn.x + BASE_REVEAL + 3, world.spawn.y + BASE_REVEAL + 3)
                if not any(abs(far.x - p.x) <= 4 and abs(far.y - p.y) <= 4 for p in world.portals):
                    self.assertFalse(survey.seen(far))
                self.assertFalse(survey.seen(GridPos(-100, 5)))
                self.assertLess(survey.explored_share, .15)

    def test_walking_reveals_around_the_player_but_not_underground(self):
        session = self.fresh(1234)
        survey, world = session.survey, session.world
        corner = GridPos(20, 20)
        self.assertFalse(survey.seen(corner))
        session.player.position = corner
        before = survey.version
        session.advance_time(.01)
        self.assertGreater(survey.version, before)
        self.assertTrue(survey.seen(corner + GridPos(REVEAL_RADIUS, 0)))
        self.assertFalse(survey.seen(corner + GridPos(REVEAL_RADIUS + 2, 0)))
        session.advance_time(.01)
        self.assertEqual(before + 1, survey.version)
        cave = next(p for p in world.portals.values() if p.target_space_id != world.space_id)
        session.world, session.player.position = session.spaces.resolve(world, cave)
        session.advance_time(.01)
        self.assertEqual(before + 1, survey.version)
        session.world, session.player.position = world, world.spawn

    def test_water_darkens_by_rings_like_the_shore_depth(self):
        for seed in SEEDS:
            with self.subTest(seed=seed):
                session = self.fresh(seed)
                world, survey = session.world, session.survey
                pixels = island_pixels(world, survey)
                side, m = survey.side, survey.margin
                checked = 0
                for p, tile in world.tile_map.tiles.items():
                    if tile.kind is not TileKind.WATER or tile.deep_water or p in world.river_cells:
                        continue
                    i = ((p.y + m) * side + p.x + m) * 3
                    self.assertEqual(WATER[shore_depth(world, p, len(WATER)) - 1], tuple(pixels[i:i + 3]), p)
                    checked += 1
                self.assertGreater(checked, 300)

    def test_markers_land_on_their_cells_in_the_isometric_image(self):
        session = self.fresh(1234)
        world, survey = session.world, session.survey
        island = IslandMap(PixelFont())
        image = island.image(world, survey)
        side, m = survey.side, survey.margin
        pixels = island_pixels(world, survey)
        centre = (image.get_width() // 2, image.get_height() // 2)
        for offset in ((0, 0), (3, -2), (-4, 1), (2, 4)):
            cell = world.spawn + GridPos(*offset)
            i = ((cell.y + m) * side + cell.x + m) * 3
            point = IslandMap.project(survey, cell, centre)
            self.assertEqual(tuple(pixels[i:i + 3]), tuple(image.get_at(point))[:3], cell)
        self.assertAlmostEqual(image.get_width(), side * CELL * 2 ** .5, delta=3)
        self.assertEqual(image.get_width() // 2, image.get_height())

    def test_another_island_gets_its_own_picture(self):
        island = IslandMap(PixelFont())
        first, second = (self.fresh(seed) for seed in SEEDS)
        before = pygame.image.tobytes(island.image(first.world, first.survey), "RGBA")
        after = pygame.image.tobytes(island.image(second.world, second.survey), "RGBA")
        self.assertNotEqual(before, after)
        self.assertEqual(before, pygame.image.tobytes(island.image(first.world, first.survey), "RGBA"))

    def test_m_opens_a_paused_map_and_m_esc_or_i_close_it(self):
        session = self.fresh(1234)
        state = GameplayState(session, self.config)
        renderer = PlaceholderRenderer(pygame.Surface((960, 540)), self.config)
        for close in (InputFrame(map_pressed=True), InputFrame(pause_pressed=True),
                      InputFrame(inventory_pressed=True)):
            state.step(InputFrame(map_pressed=True), 1 / 60)
            self.assertTrue(state.map_open)
            clock = session.cycle_seconds
            state.step(InputFrame(), 5.0)
            self.assertEqual(clock, session.cycle_seconds)
            state.draw(renderer)
            self.assertGreater(renderer._ui_bounds.width, 600)
            state.step(close, 1 / 60)
            self.assertFalse(state.map_open)
            self.assertFalse(state.inventory_open)
        state.step(InputFrame(inventory_pressed=True), 1 / 60)
        state.step(InputFrame(map_pressed=True), 1 / 60)
        self.assertFalse(state.map_open)
        state.step(InputFrame(inventory_pressed=True), 1 / 60)

    def test_underground_the_map_marks_the_entrance_taken(self):
        session = self.fresh(1234)
        world = session.world
        cave = next(p for p in world.portals.values() if p.target_space_id != world.space_id)
        session.world, session.player.position = session.spaces.resolve(world, cave)
        try:
            screen = pygame.Surface((960, 540), pygame.SRCALPHA)
            drawn = []
            island = IslandMap(PixelFont())
            island._player_icon = lambda surface, point, pulse=True: drawn.append((point, pulse))
            island.draw(screen, self.config, session)
            image = island.image(world, session.survey)
            panel = screen.get_bounding_rect()
            centre = (panel.centerx, panel.top + 34 + image.get_height() // 2)
            self.assertIn((IslandMap.project(session.survey, cave.position, centre), True), drawn)
        finally:
            session.world, session.player.position = world, world.spawn


if __name__ == "__main__":
    unittest.main()
