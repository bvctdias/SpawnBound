import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from spawnbound.animation import MotionKind
from spawnbound.config import DEFAULT_CONFIG
from spawnbound.domain.coordinates import GridPos
from spawnbound.domain.model import TileKind
from spawnbound.domain.session import GameSession
from spawnbound.domain.terrain import CARDINAL
from spawnbound.input import InputFrame
from spawnbound.states import GameplayState
from spawnbound.view import camera_origin, pick_world_point, screen_center


SEEDS = (1234, 952265258, 1256104511)


class SwimmingTests(unittest.TestCase):
    def setUp(self):
        self.session = GameSession.create(1234, DEFAULT_CONFIG, chunk_preview_size=128)
        self.world = self.session.world

    def visible_click(self, state, destination):
        origin = camera_origin(self.session, DEFAULT_CONFIG, state.visual_position3d)
        x, y = screen_center(self.world.surface_position(destination), origin, DEFAULT_CONFIG)
        if self.world.tile_map.kind_at(destination) is TileKind.WATER:
            y -= DEFAULT_CONFIG.water_lift
        hit = pick_world_point(self.session, (x, y), origin, DEFAULT_CONFIG)
        return (x, y) if hit is not None and hit.position == destination else None

    def click_first_visible(self, state, candidates):
        destination, point = next((p, c) for p in candidates if (c := self.visible_click(state, p)))
        state.step(InputFrame(destination_click=point), 0)
        for _ in range(240):
            state.step(InputFrame(), 1/60)
        self.assertEqual(destination, self.session.player.position)
        return destination

    def test_swim_by_click_from_the_estuary_into_the_ocean_and_back(self):
        for seed in SEEDS:
            with self.subTest(seed=seed):
                self.session = GameSession.create(seed, DEFAULT_CONFIG, chunk_preview_size=128)
                self.world = self.session.world
                mouth = self.world.river_mouth
                self.assertIsNotNone(mouth)
                outward = next(d for d in CARDINAL if mouth + d not in self.world.tile_map.tiles)
                side = GridPos(-outward.y, outward.x)
                at_depth = lambda n, across=0: GridPos(mouth.x + n * outward.x + across * side.x,
                                                       mouth.y + n * outward.y + across * side.y)
                self.session.player.place(self.world.surface_position(mouth))
                state = GameplayState(self.session, DEFAULT_CONFIG)
                self.click_first_visible(state, [at_depth(n, a) for n in range(1, 9)
                                                 for a in sorted(range(-3, 4), key=abs)])
                self.assertIs(state.player_pose.motion, MotionKind.SWIM)
                near = lambda p: (abs(p.x - mouth.x) + abs(p.y - mouth.y), p)
                navigation = self.session.navigation
                banks = [GridPos(mouth.x + dx, mouth.y + dy) for dx in range(-4, 5) for dy in range(-4, 5)]
                banks = [p for p in banks if p not in self.world.river_cells
                         and navigation.reachable(self.session.player.position, p)]
                arrived = self.click_first_visible(state, sorted(self.world.river_cells, key=near) + sorted(banks, key=near))
                self.assertLessEqual(max(abs(arrived.x - mouth.x), abs(arrived.y - mouth.y)), 14)
                self.assertTrue(self.world.player_can_enter(at_depth(12)))
                self.assertFalse(self.world.player_can_enter(at_depth(13)))
                self.assertTrue(self.world.tile_map.tile_at(at_depth(16)).deep_water)
                self.assertIsNone(self.world.tile_map.tile_at(at_depth(17)))
                self.assertEqual(128**2, len(self.world.tile_map.tiles))

    def test_shallow_bank_allows_return_and_steep_banks_block_swimmers(self):
        water = sorted(p for p,t in self.world.tile_map.tiles.items() if t.kind is TileKind.WATER)
        lake, shore = next((p,p+d) for p in water for d in CARDINAL
                           if self.world.is_walkable(p+d) and self.world.elevation_at(p+d)==1)
        self.session.player.place(self.world.surface_position(shore))
        self.assertFalse(self.world.can_step(shore, lake))
        self.assertTrue(self.session.move(lake-shore).success)
        self.assertIs(GameplayState(self.session, DEFAULT_CONFIG).player_pose.motion, MotionKind.SWIM)
        self.assertTrue(self.session.move(shore-lake).success)
        self.assertIs(GameplayState(self.session, DEFAULT_CONFIG).player_pose.motion, MotionKind.IDLE)
        self.world.tile_map.add(shore, TileKind.GRASS, elevation=3)
        self.assertFalse(self.session.can_step(lake, shore))
