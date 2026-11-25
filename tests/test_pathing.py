import random
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from spawnbound.config import DEFAULT_CONFIG
from spawnbound.domain.coordinates import GridPos
from spawnbound.domain.model import BridgeSite, ObjectKind, TileKind, TileMap, World, WorldObject
from spawnbound.domain.navigation import find_path_to_any
from spawnbound.domain.pathing import PlayerNavigation
from spawnbound.domain.session import GameSession
from spawnbound.input import InputFrame
from spawnbound.states import GameplayState
from spawnbound.view import camera_origin, pick_world_point, screen_center

SEEDS = (1234, 7, 99, 1995926428)


def route_cost(start, route):
    total, previous = 0, start
    for cell in route:
        step = cell - previous
        total += 14 if step.x and step.y else 10
        previous = cell
    return total


def on_screen(world, a, b):
    dx, dy = b.x - a.x, b.y - a.y
    dz = world.elevation_at(b) - world.elevation_at(a)
    cfg = DEFAULT_CONFIG
    return (abs((dx - dy) * cfg.tile_width / 2) <= 460
            and abs((dx + dy) * cfg.tile_height / 2 - dz * cfg.height_unit_pixels) <= 250)


class IslandRouteTests(unittest.TestCase):
    def test_routes_follow_the_step_rules_and_stay_close_to_the_shortest(self):
        for seed in SEEDS[:2]:
            with self.subTest(seed=seed):
                session = GameSession.create(seed, DEFAULT_CONFIG, chunk_preview_size=128)
                world, navigation = session.world, session.navigation
                rng = random.Random(seed)
                ground = [p for p in world.tile_map.tiles if navigation.reachable(world.spawn, p)]
                for _ in range(30):
                    start = rng.choice(ground)
                    nearby = [GridPos(start.x + dx, start.y + dy) for dx in range(-20, 21) for dy in range(-20, 21)]
                    target = rng.choice([p for p in nearby if world.player_can_enter(p) and on_screen(world, start, p)])
                    exact = find_path_to_any(start, (target,), world.player_can_enter, session.can_step)
                    route = navigation.route(start, (target,))
                    self.assertEqual(exact is None, route is None, (start, target))
                    if route is None:
                        continue
                    previous = start
                    for cell in route:
                        self.assertTrue(session.can_step(previous, cell), (start, target, previous, cell))
                        previous = cell
                    self.assertEqual(target, route[-1] if route else start)
                    self.assertLessEqual(route_cost(start, route), 1.10 * route_cost(start, exact))

    def test_an_unreachable_click_walks_to_the_nearest_ground(self):
        for seed in SEEDS[:2]:
            with self.subTest(seed=seed):
                session = GameSession.create(seed, DEFAULT_CONFIG, chunk_preview_size=128)
                world, navigation = session.world, session.navigation
                spawn = world.spawn

                def flat(p):
                    patch = [GridPos(p.x + dx, p.y + dy) for dx in range(-2, 3) for dy in range(-2, 3)]
                    return (all(world.is_walkable(q) and navigation.reachable(spawn, q) for q in patch)
                            and len({world.elevation_at(q) for q in patch}) == 1)

                around = sorted(world.tile_map.tiles, key=lambda q: (abs(q.x - spawn.x) + abs(q.y - spawn.y), q))
                pillar = next(p for p in around if max(abs(p.x - spawn.x), abs(p.y - spawn.y)) >= 6 and flat(p))
                tile = world.tile_map.tiles[pillar]
                world.tile_map.add(pillar, tile.kind, tile.variant, tile.biome, tile.elevation + 3)
                stand = next(p for p in around if 4 <= max(abs(p.x - pillar.x), abs(p.y - pillar.y)) <= 6
                             and p.x + p.y < pillar.x + pillar.y
                             and world.is_walkable(p) and navigation.reachable(spawn, p))
                session.player.place(world.surface_position(stand))
                state = GameplayState(session, DEFAULT_CONFIG)
                origin = camera_origin(session, DEFAULT_CONFIG, state.visual_position3d)
                x, y = screen_center(world.surface_position(pillar), origin, DEFAULT_CONFIG)
                hit = pick_world_point(session, (x, y), origin, DEFAULT_CONFIG)
                self.assertEqual(pillar, hit.position)
                self.assertFalse(navigation.reachable(stand, pillar))
                expected = navigation.nearest_reachable(stand, pillar)
                self.assertEqual(1, max(abs(expected.x - pillar.x), abs(expected.y - pillar.y)))
                state.step(InputFrame(destination_click=(x, y)), 0)
                self.assertIn("ponto mais proximo", session.last_message)
                for _ in range(600):
                    state.step(InputFrame(), 1 / 60)
                self.assertEqual(expected, session.player.position, (seed, pillar, stand))


def walled_world(width: int = 20, height: int = 20) -> World:
    tiles = TileMap({GridPos(x, y): _grass() for x in range(width) for y in range(height)})
    wall = width // 2
    objects = {GridPos(wall, y): WorldObject.create(GridPos(wall, y), ObjectKind.TREE) for y in range(height)}
    origin = GridPos(0, 0)
    return World(seed=0, tile_map=tiles, objects=objects, spawn=GridPos(2, 2), camp=GridPos(2, 3),
                 bridge=BridgeSite(origin, (), origin, GridPos(1, 0)), goal=origin, strict_diagonals=True)


def _grass():
    from spawnbound.domain.model import Tile
    return Tile(TileKind.GRASS, elevation=1)


class WorldEditTests(unittest.TestCase):
    def test_a_distant_upper_terrace_is_reached_with_one_click(self):
        world = walled_world(38, 12)
        world.objects.clear()
        for p in list(world.tile_map.tiles):
            if p.x >= 8:
                world.tile_map.add(p, TileKind.GRASS, elevation=2 if p.x < 11 else 3)
        session = GameSession.create(1234, DEFAULT_CONFIG, chunk_preview_size=8)
        session.world = world
        session.player.place(world.surface_position(GridPos(3, 5)))
        session.wildlife.mobs.clear()
        state = GameplayState(session, DEFAULT_CONFIG)
        target = GridPos(26, 5)
        def click():
            origin = camera_origin(session, DEFAULT_CONFIG, state.visual_position3d)
            state.step(InputFrame(destination_click=screen_center(world.surface_position(target),
                                                                   origin, DEFAULT_CONFIG)), 0)
        click()
        state.step(InputFrame(), 10)
        self.assertEqual(target, session.player.position)
        self.assertEqual(3, session.player.elevation)

    def test_removing_a_blocker_joins_the_regions(self):
        world = walled_world()
        navigation = PlayerNavigation(world, 1)
        left, right = GridPos(2, 9), GridPos(17, 9)
        self.assertFalse(navigation.reachable(left, right))
        self.assertIsNone(navigation.route(left, (right,)))
        world.remove_object(GridPos(10, 15))
        route = navigation.route(left, (right,))
        self.assertIsNotNone(route)
        self.assertIn(GridPos(10, 15), route)

    def test_raising_a_cell_closes_the_gap_again(self):
        world = walled_world()
        world.remove_object(GridPos(10, 4))
        navigation = PlayerNavigation(world, 1)
        self.assertTrue(navigation.reachable(GridPos(2, 4), GridPos(17, 4)))
        world.tile_map.add(GridPos(10, 4), TileKind.GRASS, elevation=4)
        self.assertFalse(navigation.reachable(GridPos(2, 4), GridPos(17, 4)))
        self.assertEqual(GridPos(9, 4), navigation.nearest_reachable(GridPos(2, 4), GridPos(12, 4)))

    def test_long_detours_use_the_area_plan_and_stay_valid(self):
        # A única abertura fica longe o bastante para esgotar o limite da busca direta.
        world = walled_world(40, 64)
        world.remove_object(GridPos(20, 63))
        navigation = PlayerNavigation(world, 1)
        start, target = GridPos(19, 0), GridPos(21, 0)
        route = navigation.route(start, (target,))
        exact = find_path_to_any(start, (target,), world.player_can_enter,
                                 lambda a, b: world.can_step(a, b, 1, swim=True))
        self.assertEqual(target, route[-1])
        self.assertIn(GridPos(20, 63), route)
        self.assertLessEqual(route_cost(start, route), 1.10 * route_cost(start, exact))


if __name__ == "__main__":
    unittest.main()
