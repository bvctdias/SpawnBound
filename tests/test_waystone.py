import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from spawnbound.config import DEFAULT_CONFIG
from spawnbound.domain.coordinates import NEIGHBOR_DIRECTIONS
from spawnbound.domain.session import ActionCode, GameSession
from spawnbound.input import InputFrame
from spawnbound.states import GameplayState
from spawnbound.view import object_contains
from spawnbound.waystone_art import waystone_sprite


class WaystoneTests(unittest.TestCase):
    def test_only_the_home_stone_starts_active_and_colours_belong_to_the_seed(self):
        def colours(seed):
            game = GameSession.create(seed, DEFAULT_CONFIG)
            return [game.world.objects[p].variant for p in game.world.waystones]

        palette = colours(1234)
        self.assertEqual(2, len(set(palette)))
        self.assertEqual(palette, colours(1234))
        self.assertNotEqual(palette, colours(7))
        game = GameSession.create(1234, DEFAULT_CONFIG, chunk_preview_size=32)
        home, = game.world.waystones
        self.assertEqual(palette[0], game.world.objects[home].variant)
        self.assertEqual([home], [stone.position for stone in game.world.active_waystones()])

    def test_visit_then_activate_allows_a_round_trip(self):
        game = GameSession.create(1234, DEFAULT_CONFIG)
        world = game.world
        home, other = world.waystones
        self.assertEqual([home], [s.position for s in world.active_waystones()])

        def walk_to(stone):
            for d in NEIGHBOR_DIRECTIONS:
                neighbour = stone - d
                route = game.navigation.route(game.player.position, (neighbour,))
                if route is not None:
                    for cell in route:
                        if cell != game.player.position:
                            self.assertTrue(game.move(cell - game.player.position).success)
                    game.player.facing = d
                    return
            self.fail("Stone has no reachable approach")

        walk_to(home)
        before = game.player.position
        self.assertEqual(ActionCode.NOTHING_HERE, game.interact().code)
        self.assertEqual(before, game.player.position)
        world.build_bridge()
        walk_to(other)
        self.assertEqual(ActionCode.WAYSTONE_ACTIVATED, game.interact().code)
        self.assertEqual(other, game.player.position + game.player.facing)
        state = GameplayState(game, DEFAULT_CONFIG)
        for destination in (home, other):
            state.step(InputFrame(interact_pressed=True), 0)
            self.assertEqual(destination, game.player.position + game.player.facing)
            self.assertTrue(world.is_walkable(game.player.position))
            self.assertEqual((game.player.position.x, game.player.position.y), state._visual_position[:2])

    def test_only_the_crystal_changes_colour_and_the_empty_corners_are_not_pickable(self):
        game = GameSession.create(1234, DEFAULT_CONFIG)
        first, second = (game.world.objects[p] for p in game.world.waystones)
        sprite, (px, py) = waystone_sprite(first.variant, True)
        other = waystone_sprite(second.variant, True)[0]
        dormant = waystone_sprite(first.variant, False)[0]
        self.assertNotEqual(sprite.get_at((13, 7)), other.get_at((13, 7)))
        self.assertNotEqual(sprite.get_at((13, 7)), dormant.get_at((13, 7)))
        self.assertEqual(sprite.get_at((13, 30)), other.get_at((13, 30)))
        self.assertTrue(object_contains(first, 13 - px, 7 - py))
        self.assertFalse(object_contains(first, -px, -py))
