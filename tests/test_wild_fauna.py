import os
import sys
import unittest
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import pygame

from spawnbound.config import DEFAULT_CONFIG
from spawnbound.domain.coordinates import GridPos
from spawnbound.domain.generation import WorldGenerator
from spawnbound.domain.mobs import (SWORD_DAMAGE, ANGER_SECONDS, CHARGE_REACH, CHARGE_WINDUP, DEER_AREA, DEER_SPACING, KICK_WINDUP,
                                    RECOVER_SECONDS, SAFE_START, SNAKE_AREA, SNAKE_DESERT, SNAKE_SPACING,
                                    STRIKE_WINDUP, HEALTH, Mob, MobKind, Wildlife, chebyshev)
from spawnbound.domain.model import Biome, TileKind
from spawnbound.domain.session import FOOD, GameSession
from spawnbound.mob_art import mob_pixels, pick_pixels, posed_pixels
from spawnbound.renderer import PlaceholderRenderer


def flat_session():
    session = GameSession.create(1234, DEFAULT_CONFIG, chunk_preview_size=24)
    world = session.world
    for p in list(world.tile_map.tiles):
        world.tile_map.add(p, TileKind.GRASS, elevation=2, biome=Biome.DRY)
    world.objects.clear()
    world.portals.clear()
    world.camp, world.goal = GridPos(-50, -50), GridPos(-60, -60)
    life = session.wildlife
    life.mobs = {}
    life._replenish_in = 1e9
    life._desert_of = dict.fromkeys(world.tile_map.tiles, 0)
    session.player.inventory.selected = 3
    return session


def put(session, kind, cell, uid=1):
    location = session.world.surface_position(cell)
    mob = Mob(uid, kind, HEALTH[kind], location, location, 0., home=cell)
    session.wildlife.mobs[uid] = mob
    return mob


def run(life, seconds, player, step=1 / 60):
    hurt = False
    for _ in range(round(seconds / step)):
        hurt |= life.tick(step, player)
    return hurt


class WildPlacementTests(unittest.TestCase):
    SEEDS = (1234, 7, 39658298)

    @classmethod
    def setUpClass(cls):
        cls.islands = []
        for seed in cls.SEEDS:
            world = WorldGenerator().generate_chunk_preview(seed, 128)
            cls.islands.append((world, Wildlife(world)))

    def test_deer_live_one_by_one_in_the_forest(self):
        for world, life in self.islands:
            with self.subTest(seed=world.seed):
                deer = [m for m in life.mobs.values() if m.kind is MobKind.DEER]
                forest = sum(t.kind is TileKind.GRASS and t.biome is Biome.FOREST
                             for t in world.tile_map.tiles.values())
                self.assertEqual(round(forest / DEER_AREA), len(deer))
                self.assertGreaterEqual(len(deer), 5)
                for a in deer:
                    self.assertIs(Biome.FOREST, world.tile_map.tile_at(a.end.grid).biome)
                    self.assertGreaterEqual(chebyshev(a.end, world.spawn), SAFE_START)
                    self.assertTrue(all(chebyshev(a.end, b.end) >= DEER_SPACING for b in deer if b is not a))

    def test_each_desert_gets_snakes_by_its_size(self):
        for world, life in self.islands:
            with self.subTest(seed=world.seed):
                snakes = [m for m in life.mobs.values() if m.kind is MobKind.SNAKE]
                total = 0
                for region in life._dry_regions():
                    cells = set(region)
                    inside = [s for s in snakes if s.end.grid in cells]
                    expected = -(-len(region) // SNAKE_AREA) if len(region) >= SNAKE_DESERT else 0
                    self.assertEqual(expected, len(inside), len(region))
                    total += expected
                self.assertEqual(total, len(snakes))
                self.assertGreaterEqual(len(snakes), 6)
                for a in snakes:
                    self.assertGreaterEqual(chebyshev(a.end, world.spawn), SAFE_START)
                    self.assertTrue(all(chebyshev(a.end, b.end) >= SNAKE_SPACING for b in snakes if b is not a))

    def test_snakes_never_leave_their_desert(self):
        world, life = self.islands[0]
        snake = next(m for m in life.mobs.values() if m.kind is MobKind.SNAKE)
        desert = life._desert_of[snake.home]
        near = next(p for p in life._deserts[desert][0] if chebyshev(p, snake.home) == 3)
        player = world.surface_position(near)
        life._replenish_in = 1e9
        for _ in range(900):
            life.tick(.05, player)
            for mob in life.mobs.values():
                if mob.kind is MobKind.SNAKE:
                    self.assertEqual(life._desert_of[mob.home], life._desert_of.get(mob.end.grid))


class DeerTests(unittest.TestCase):
    def setUp(self):
        self.session = flat_session()
        self.life = self.session.wildlife
        self.deer = put(self.session, MobKind.DEER, GridPos(10, 10))

    def at(self, cell):
        return self.session.world.surface_position(cell)

    def test_a_calm_deer_lets_the_player_stand_close(self):
        self.assertFalse(run(self.life, 8., self.at(GridPos(11, 10))))
        self.assertEqual("", self.deer.attack)
        self.assertFalse(self.deer.hostile)

    def test_struck_deer_kicks_whoever_stays_close(self):
        self.deer.anger = ANGER_SECONDS
        player = self.at(GridPos(11, 10))
        self.life.tick(.01, player)
        self.assertEqual("kick", self.deer.attack)
        self.assertTrue(self.deer.hostile)
        self.assertTrue(run(self.life, KICK_WINDUP + .05, player))
        self.assertEqual("kick", self.life.last_blow)

    def test_stepping_back_from_the_warning_dodges_the_kick(self):
        self.deer.anger = ANGER_SECONDS
        self.life.tick(.01, self.at(GridPos(11, 10)))
        self.assertGreater(self.deer.windup, 0)
        self.assertFalse(run(self.life, KICK_WINDUP + .05, self.at(GridPos(13, 10))))

    def test_charge_hits_in_a_straight_line_and_leaves_the_deer_dazed(self):
        self.deer.anger = ANGER_SECONDS
        player = self.at(GridPos(14, 10))
        self.life.tick(.01, player)
        self.assertEqual("charge", self.deer.attack)
        self.assertEqual(GridPos(1, 0), self.deer.charge)
        self.assertTrue(run(self.life, CHARGE_WINDUP + .6, player))
        self.assertEqual("antlers", self.life.last_blow)
        self.assertIsNone(self.deer.charge)
        self.assertEqual(GridPos(13, 10), self.deer.end.grid)

    def test_a_dodged_charge_runs_on_and_stops_dazed(self):
        self.deer.anger = ANGER_SECONDS
        self.life.tick(.01, self.at(GridPos(14, 10)))
        aside = self.at(GridPos(14, 13))
        self.assertFalse(run(self.life, CHARGE_WINDUP + .2, aside))
        for _ in range(200):
            self.life.tick(1 / 60, aside)
            if self.deer.dazed:
                break
        self.assertGreater(self.deer.dazed, 0)
        self.assertLessEqual(self.deer.end.x - 10, CHARGE_REACH)
        self.assertEqual(10, self.deer.end.y)

    def test_anger_fades(self):
        self.deer.anger = ANGER_SECONDS
        run(self.life, ANGER_SECONDS + .5, self.at(GridPos(20, 20)), step=.1)
        self.assertFalse(self.deer.hostile)


class SnakeTests(unittest.TestCase):
    def setUp(self):
        self.session = flat_session()
        self.life = self.session.wildlife
        self.snake = put(self.session, MobKind.SNAKE, GridPos(10, 10))

    def at(self, cell):
        return self.session.world.surface_position(cell)

    def test_snake_slides_closer_and_warns_before_the_bite(self):
        player = self.at(GridPos(13, 10))
        for _ in range(240):
            self.life.tick(1 / 60, player)
            if self.snake.windup:
                break
        self.assertEqual("strike", self.snake.attack)
        self.assertLessEqual(chebyshev(self.snake.end, player), 1)
        self.assertTrue(run(self.life, STRIKE_WINDUP + .05, player))
        self.assertEqual("bite", self.life.last_blow)
        self.assertGreater(self.snake.dazed, RECOVER_SECONDS - .1)

    def test_stepping_back_dodges_the_bite_and_opens_the_snake(self):
        self.snake.anger = 1.
        self.life.tick(.01, self.at(GridPos(11, 10)))
        self.assertEqual("strike", self.snake.attack)
        self.assertFalse(run(self.life, STRIKE_WINDUP + .05, self.at(GridPos(13, 10))))
        self.assertGreater(self.snake.dazed, 0)

    def test_struck_snake_slips_away(self):
        session = self.session
        session.player.position = GridPos(11, 10)
        result = session.attack_mob(self.snake.id)
        self.assertTrue(result.success)
        self.assertEqual(HEALTH[MobKind.SNAKE] - SWORD_DAMAGE, self.snake.hp)
        self.assertGreater(self.snake.flee_time, 0)
        run(self.life, .5, session.player.position3d)
        self.assertGreater(chebyshev(self.snake.end, session.player.position3d), 1)


class HuntingTests(unittest.TestCase):
    def test_deer_and_snake_drops_and_food(self):
        session = flat_session()
        deer = put(session, MobKind.DEER, GridPos(10, 10), 1)
        snake = put(session, MobKind.SNAKE, GridPos(14, 14), 2)
        session.player.position = GridPos(11, 10)
        for _ in range(-(-HEALTH[MobKind.DEER] // SWORD_DAMAGE)):
            session.player.energy = 100
            result = session.attack_mob(deer.id)
        self.assertNotIn(deer.id, session.wildlife.mobs)
        self.assertIn("carne de cervo", result.message)
        self.assertEqual(2, session.player.inventory.quantity("venison"))
        self.assertEqual(1, session.player.inventory.quantity("hide"))
        session.player.position = GridPos(13, 14)
        for _ in range(-(-HEALTH[MobKind.SNAKE] // SWORD_DAMAGE)):
            session.attack_mob(snake.id)
        self.assertEqual(1, session.player.inventory.quantity("snake_meat"))
        session.player.energy = 10
        inventory = session.player.inventory
        inventory.selected = next(i for i, s in enumerate(inventory.slots) if s and s.item == "venison")
        session.eat()
        self.assertEqual(10 + FOOD["venison"], session.player.energy)
        self.assertEqual(1, inventory.quantity("venison"))

    def test_each_blow_has_its_message(self):
        session = flat_session()
        put(session, MobKind.SNAKE, GridPos(11, 10))
        session.player.position = GridPos(12, 10)
        session.wildlife.mobs[1].anger = 1.
        for _ in range(120):
            if session.update_mobs(1 / 60) or session.hurt_time:
                break
        self.assertEqual("A cobra te picou!", session.last_message)
        self.assertEqual(session.config.starting_hearts - 1, session.player.hearts)


class WildArtTests(unittest.TestCase):
    def test_poses_read_differently_and_fit_the_sprite(self):
        idle = posed_pixels(MobKind.DEER, False, 0, "idle")
        kick = posed_pixels(MobKind.DEER, False, 0, "kick")
        charge = posed_pixels(MobKind.DEER, False, 0, "charge_ready")
        self.assertLess(min(x for x, y in kick), min(x for x, y in idle) - 2)
        self.assertGreater(min(y for _, y in charge), min(y for _, y in idle) + 4)
        resting = posed_pixels(MobKind.SNAKE, False, 0, "idle")
        raised = posed_pixels(MobKind.SNAKE, False, 0, "strike_ready")
        self.assertLess(min(y for _, y in raised), min(y for _, y in resting) - 4)
        for kind in (MobKind.DEER, MobKind.SNAKE):
            for stance in ("idle", "walk", "hurt", "kick_ready", "kick", "charge_ready", "charge", "dazed",
                           "alert", "strike_ready", "strike", "run", "rest"):
                for left in (False, True):
                    pixels = posed_pixels(kind, left, 1, stance)
                    self.assertTrue(all(-20 <= x <= 19 and -32 <= y <= 3 for x, y in pixels), (kind, stance))
        mirrored = posed_pixels(MobKind.DEER, True, 0, "idle")
        self.assertEqual({(-x, y) for x, y in idle}, set(mirrored))

    def test_the_slim_snake_is_easier_to_click(self):
        session = flat_session()
        snake = put(session, MobKind.SNAKE, GridPos(10, 10))
        self.assertGreater(len(pick_pixels(snake)), 1.4 * len(mob_pixels(snake)))
        self.assertTrue(set(mob_pixels(snake)) <= pick_pixels(snake))

    def test_warning_and_dazed_stars_are_drawn(self):
        pygame.font.init()
        session = flat_session()
        deer = put(session, MobKind.DEER, GridPos(11, 11))
        session.player.position = GridPos(8, 14)
        renderer = PlaceholderRenderer(pygame.Surface((960, 540)), DEFAULT_CONFIG)

        def frame(fill):
            renderer.CUE_FILL = fill
            renderer.draw_gameplay(session, debug=False)
            return pygame.image.tobytes(renderer._world_screen, "RGB")

        self.assertEqual(frame((255, 0, 0)), frame((0, 0, 255)))
        deer.attack, deer.windup = "kick", .3
        self.assertNotEqual(frame((255, 0, 0)), frame((0, 0, 255)))
        deer.attack, deer.windup, deer.dazed = "", 0., .5
        self.assertNotEqual(frame((255, 0, 0)), frame((0, 0, 255)))


if __name__ == "__main__":
    unittest.main()
