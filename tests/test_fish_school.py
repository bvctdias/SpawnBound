import sys
import unittest
from dataclasses import replace
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import pygame

from spawnbound.config import GameConfig
from spawnbound.domain.coordinates import GridPos, WorldPos, screen_to_grid
from spawnbound.domain.model import TileKind
from spawnbound.domain.schooling import SchoolVisit, narrow_water
from spawnbound.domain.session import GameSession
from spawnbound.fish_school import school_frame
from spawnbound.seabed import aquatic_glyph, water_decoration
from spawnbound.renderer import PlaceholderRenderer
from spawnbound.view import screen_center

SEEDS = (1234, 7, 99, 1256104511)
SIZE = 128


class FishSchoolTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pygame.font.init()
        cls.config = GameConfig()
        cls.islands = {seed: GameSession.create(seed, cls.config, chunk_preview_size=SIZE) for seed in SEEDS}

    def session(self, seed):
        session = self.islands[seed]
        session.school = SchoolVisit()
        return session

    def centred_on(self, home):
        x, y = screen_center(home, (0, 0), self.config)
        return 480 - x, 270 - y

    def frame(self, session, origin):
        renderer = PlaceholderRenderer(pygame.Surface((960, 540)), self.config)
        return school_frame(session, self.config, origin, renderer.screen.get_rect(), renderer._top_alpha)

    def test_approach_starts_at_cover_and_departure_brings_fish_home(self):
        for seed in SEEDS:
            with self.subTest(seed=seed):
                session = self.session(seed)
                world, visit = session.world, session.school
                home = next(iter(world.fish_refuges))
                far_cell = max((p for p in world.tile_map.tiles if world.is_walkable(p)),
                               key=lambda p: (min(max(abs(p.x - h.x), abs(p.y - h.y)) for h in world.fish_refuges), p))
                far = world.surface_position(far_cell)
                visit.advance(world, far, 4)
                self.assertIsNone(visit.home)
                visit.advance(world, world.surface_position(home), 0)
                self.assertEqual(home, visit.home)
                self.assertIsNone(self.frame(session, self.centred_on(home)))
                visit.advance(world, world.surface_position(home), 2)
                before = visit.offset(0, False)
                self.assertGreater(before[0], 0)
                visit.advance(world, far, .6)
                self.assertAlmostEqual(visit.offset(0, False)[0], before[0] / 2)
                visit.advance(world, far, .6)
                self.assertIsNone(visit.home)
                visit.advance(world, world.surface_position(home), 10.5)
                self.assertTrue(all(visit.offset(i, False) == (0, 0) for i in range(5)))
                self.assertIsNone(self.frame(session, self.centred_on(home)))

    def test_generated_water_has_distinct_region_palettes(self):
        for seed in SEEDS:
            with self.subTest(seed=seed):
                world = self.session(seed).world
                mouth = world.river_mouth
                near_mouth = [GridPos(mouth.x + dx, mouth.y + dy) for dx in range(-5, 6) for dy in range(-5, 6)
                              if abs(dx) + abs(dy) <= 5]
                sea = [GridPos(x, y) for x in range(-12, SIZE + 12) for y in range(-12, SIZE + 12)
                       if not (0 <= x < SIZE and 0 <= y < SIZE) and abs(x - mouth.x) + abs(y - mouth.y) > 10]
                for region, signature in ((world.river_cells - set(near_mouth), {"stones", "ribbon"}),
                                          (near_mouth, {"fan", "reeds"}),
                                          (sea, {"star", "shell", "kelp"})):
                    decorations = {water_decoration(world, p, world.tile_map.tile_at(p)) for p in region
                                   if world.tile_map.kind_at(p) is TileKind.WATER}
                    self.assertTrue(decorations & signature, (seed, signature))
                    self.assertIn(None, decorations)

    def test_all_refuges_have_water_routes_and_the_foliage_hides_the_fish(self):
        glyph = aquatic_glyph("thicket", self.config.tile_width, self.config.tile_height)
        cover = pygame.mask.from_surface(glyph)
        for seed in SEEDS:
            with self.subTest(seed=seed):
                session = self.session(seed)
                world, visit = session.world, session.school
                self.assertTrue(set(world.fish_refuges) & world.river_cells)
                for home, d in world.fish_refuges.items():
                    self.assertEqual("thicket", water_decoration(world, home, world.tile_map.tile_at(home)))
                    visit.home = home
                    for tick in range(1, 110):
                        visit.elapsed = tick / 10
                        for index in range(5):
                            a, b = visit.offset(index, narrow_water(world, home))
                            cell = WorldPos(home.x + a * d.x - b * d.y, home.y + a * d.y + b * d.x, 0).grid
                            tile = world.tile_map.tile_at(cell)
                            self.assertIs(tile.kind, TileKind.WATER)
                            self.assertFalse(tile.deep_water)
                    origin = self.centred_on(home)
                    rect = glyph.get_rect(center=(480, 270 - self.config.water_lift))
                    for visit.elapsed in (.02, .6, 1.5, 8.8, 9.4):
                        frame = self.frame(session, origin)
                        ink = pygame.mask.from_surface(frame.image)
                        self.assertEqual(0, cover.overlap_area(ink, (frame.rect.x - rect.x, frame.rect.y - rect.y)))
                    visit.elapsed = .02
                    self.assertEqual(0, pygame.mask.from_surface(self.frame(session, origin).image).count(),
                                     (seed, home))

    def test_cached_fish_match_direct_drawing_and_pass_under_the_swimmer(self):
        for seed in SEEDS[:2]:
            with self.subTest(seed=seed):
                session = self.session(seed)
                home = next(iter(session.world.fish_refuges))
                session.school.advance(session.world, session.world.surface_position(home), 2.5)
                origin = self.centred_on(home)
                frame = self.frame(session, origin)
                ink = pygame.mask.from_surface(frame.image)
                x, y = next((x, y) for x in range(ink.get_size()[0]) for y in range(ink.get_size()[1])
                            if ink.get_at((x, y)))
                gx, gy = screen_to_grid(frame.rect.x + x - origin[0],
                                        frame.rect.y + y - origin[1] + self.config.water_lift + 4,
                                        self.config.tile_width, self.config.tile_height)
                session.player.place(WorldPos(gx, gy, 0))
                direct = PlaceholderRenderer(pygame.Surface((960, 540)), replace(self.config, scene_cache=False))
                cached = PlaceholderRenderer(pygame.Surface((960, 540)), self.config)
                cached.draw_gameplay(session, debug=False)
                box = cached._school.rect.inflate(8, 8).clip(cached._world_screen.get_rect())
                actual = cached._world_screen.subsurface(box).copy()
                direct.draw_gameplay(session, debug=False)
                self.assertEqual(pygame.image.tobytes(actual, "RGB"),
                                 pygame.image.tobytes(direct._world_screen.subsurface(box), "RGB"))
                with patch("spawnbound.renderer.school_frame", return_value=None):
                    cached.draw_gameplay(session, debug=False)
                clear = cached._world_screen.subsurface(box)
                self.assertNotEqual(pygame.image.tobytes(actual, "RGB"), pygame.image.tobytes(clear, "RGB"))
                head = pygame.mask.from_threshold(clear, (106, 71, 52), (1, 1, 1, 255))
                covered = pygame.mask.from_threshold(actual, (106, 71, 52), (1, 1, 1, 255))
                self.assertGreater(head.count(), 0)
                self.assertEqual(head.count(), head.overlap_area(covered, (0, 0)))
