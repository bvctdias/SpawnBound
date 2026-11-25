import math
import os
import sys
import unittest
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "dependencias")]

import pygame

from spawnbound import guardian_art
from spawnbound.config import DEFAULT_CONFIG
from spawnbound.domain import boss
from spawnbound.domain.archipelago import archipelago, build_island, dock_landing, place_dock
from spawnbound.domain.coordinates import GridPos
from spawnbound.domain.mobs import BLOW_HEARTS, MobKind, Wildlife
from spawnbound.domain.model import ObjectKind
from spawnbound.domain.session import ActionCode, GameSession
from spawnbound.domain.terrain import reachable_surface
from spawnbound.mob_art import pick_pixels, posed_pixels
from spawnbound.renderer import PlaceholderRenderer

ISLANDS = {}


def island(seed=1234):
    if seed not in ISLANDS:
        world = build_island(archipelago(seed, 128)[1])
        place_dock(world, restored=True)
        ISLANDS[seed] = world
    return ISLANDS[seed]


class ArenaTests(unittest.TestCase):
    def test_a_flat_ring_of_stones_reachable_from_the_dock_on_every_seed(self):
        for seed in (1234, 77, 2024):
            with self.subTest(seed=seed):
                world = island(seed)
                self.assertIsNotNone(world.arena)
                heights = {world.tile_map.tiles[p].elevation for p, _ in boss._disk(world.arena, boss.ARENA_RADIUS)}
                self.assertEqual(1, len(heights), "level ground")
                for p, _ in boss._disk(world.arena, boss.ARENA_RADIUS):
                    self.assertNotIn(p, world.objects)
                stones = [world.objects.get(p) for p in boss.menhir_cells(world.arena)]
                self.assertTrue(all(s is not None and s.kind is ObjectKind.MENHIR for s in stones))
                self.assertIn(world.arena, reachable_surface(world, dock_landing(world)))

    def test_the_home_island_has_no_guardian(self):
        session = GameSession.create(1234, DEFAULT_CONFIG, chunk_preview_size=128)
        self.assertIsNone(session.world.arena)
        self.assertFalse(any(m.kind is MobKind.GUARDIAN for m in session.wildlife.mobs.values()))


class FightTests(unittest.TestCase):
    def setUp(self):
        self.world = island()
        self.world.guardian_defeated = False
        self.life = Wildlife(self.world)
        self.mob = next(m for m in self.life.mobs.values() if m.kind is MobKind.GUARDIAN)
        self.life.mobs = {self.mob.id: self.mob}
        self.g = self.mob.boss
        self.arena = self.world.arena

    def at(self, offset):
        return self.world.surface_position(self.arena + offset)

    def run_until(self, player, done, seconds=8., airborne=False):
        hits = []
        for _ in range(round(seconds * 30)):
            self.life.airborne = airborne
            if self.life.tick(1 / 30, player):
                hits.append(self.life.last_blow)
                self.life.grace = 0.
            if done():
                break
        return hits

    def wake(self, offset=GridPos(1, 1)):
        player = self.at(offset)
        self.assertTrue(self.mob.asleep)
        self.life.tick(1 / 30, player)
        self.assertFalse(self.mob.asleep)
        self.assertIs(self.mob, self.life.woke)
        return player

    def test_it_sleeps_until_the_player_steps_into_the_ring(self):
        self.run_until(self.at(GridPos(0, 9)), lambda: False, 2.)
        self.assertTrue(self.mob.asleep)
        self.wake()

    def test_the_punch_marks_the_cells_then_the_fist_sticks(self):
        player = self.wake(GridPos(1, 1))
        self.run_until(player, lambda: self.g.move == "punch")
        self.assertEqual("windup", self.g.stage)
        self.assertIn(player.grid, self.g.marked)
        self.assertGreater(self.mob.windup, 0, "the warning over its head")
        self.assertFalse(boss.opening(self.mob))
        hits = self.run_until(player, lambda: self.g.stage == "stuck")
        self.assertEqual(["fist"], hits)
        self.assertTrue(boss.opening(self.mob))
        self.assertEqual(2, BLOW_HEARTS["fist"])

    def test_stepping_off_the_marked_cells_dodges_the_punch(self):
        player = self.wake(GridPos(1, 1))
        self.run_until(player, lambda: self.g.move == "punch")
        away = self.at(GridPos(5, 0))
        self.assertNotIn(away.grid, self.g.marked)
        self.assertEqual([], self.run_until(away, lambda: self.g.stage == "stuck"))

    def test_the_leap_sends_a_ring_that_a_jump_clears(self):
        self.wake(GridPos(1, 1))
        far = self.at(GridPos(-4, 0))
        self.g.rest, self.g.moves = 0., 1
        self.run_until(far, lambda: self.g.stage == "air")
        landing = self.g.leap_to
        self.run_until(far, lambda: self.g.lift > 0)
        self.assertGreater(self.g.lift, 0, "up in the air")
        self.run_until(far, lambda: self.g.stage == "landed")
        self.assertEqual(landing, self.mob.end)
        self.assertTrue(boss.opening(self.mob), "getting up after the leap")
        self.assertTrue(self.g.rings)
        aside = self.world.surface_position(landing.grid + GridPos(0, 4))
        jumped = self.run_until(aside, lambda: not self.g.rings, airborne=True)
        self.assertEqual([], jumped)

    def test_standing_still_the_ring_knocks_the_player_down(self):
        self.wake(GridPos(1, 1))
        far = self.at(GridPos(-4, 0))
        self.g.rest, self.g.moves = 0., 1
        self.run_until(far, lambda: self.g.stage == "landed")
        aside = self.world.surface_position(self.mob.end.grid + GridPos(0, 4))
        self.assertEqual(["shockwave"], self.run_until(aside, lambda: not self.g.rings))

    def test_a_rock_falls_where_its_shadow_grew(self):
        self.wake(GridPos(1, 1))
        far = self.at(GridPos(4, 0))
        self.g.rest, self.g.moves = 0., 0
        self.run_until(far, lambda: self.g.rocks)
        self.assertEqual(1, len(self.g.rocks))
        self.assertEqual(far.grid, self.g.rocks[0].target.grid)
        self.assertEqual(["boulder"], self.run_until(far, lambda: not self.g.rocks))

    def test_below_half_it_hurries_and_throws_three_rocks(self):
        self.wake(GridPos(1, 1))
        self.mob.hp = boss.HEALTH // 2
        self.assertTrue(boss.wrath(self.mob))
        far = self.at(GridPos(4, 0))
        self.g.rest, self.g.moves = 0., 0
        self.run_until(far, lambda: self.g.move == "throw")
        self.assertAlmostEqual(boss.THROW_WINDUP[1], self.g.timer, delta=.05)
        self.run_until(far, lambda: self.g.rocks)
        self.assertEqual(3, len(self.g.rocks))
        self.assertTrue(boss.stance(self.mob)[1].endswith("+"), "the cracks glow")

    def test_left_behind_it_walks_back_and_sleeps(self):
        self.wake(GridPos(1, 1))
        self.mob.start = self.mob.end = self.at(GridPos(3, 0))
        gone = self.at(GridPos(0, 14))
        self.run_until(gone, lambda: self.mob.asleep, 20.)
        self.assertTrue(self.mob.asleep)
        self.assertEqual(self.arena, self.mob.end.grid)


class BladeTests(unittest.TestCase):
    def setUp(self):
        self.session = GameSession.create(1234, DEFAULT_CONFIG, chunk_preview_size=24)
        world = self.world = island()
        world.guardian_defeated = False
        life = Wildlife(world)
        self.mob = next(m for m in life.mobs.values() if m.kind is MobKind.GUARDIAN)
        life.mobs = {self.mob.id: self.mob}
        self.session.world, self.session.wildlife = world, life
        self.session.player.place(world.surface_position(world.arena + GridPos(1, 0)))
        self.session.player.inventory.selected = 3

    def test_stone_turns_the_blade_except_in_its_openings(self):
        result = self.session.attack_mob(self.mob.id)
        self.assertIn("A pedra desvia", result.message)
        self.assertEqual(boss.HEALTH, self.mob.hp)
        self.assertFalse(self.mob.asleep, "a blow wakes it")
        self.mob.boss.stage = "stuck"
        self.session.attack_mob(self.mob.id)
        self.assertEqual(boss.HEALTH - 2, self.mob.hp)

    def test_beaten_it_stays_beaten_and_the_heart_grows(self):
        self.mob.boss.stage = "landed"
        self.mob.hp = 1
        before = self.session.max_hearts
        result = self.session.attack_mob(self.mob.id)
        self.assertIs(ActionCode.MOB_DEFEATED, result.code)
        self.assertEqual(before + 1, self.session.max_hearts)
        self.assertEqual(self.session.max_hearts, self.session.player.hearts)
        self.assertEqual(3, self.session.player.inventory.quantity("quartz"))
        self.assertTrue(self.world.guardian_defeated)
        self.assertFalse(any(m.kind is MobKind.GUARDIAN for m in Wildlife(self.world).mobs.values()))
        self.world.guardian_defeated = False


class GuardianArtTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pygame.init()

    def test_every_pose_has_its_own_picture_and_can_be_clicked(self):
        pictures = set()
        for pose in guardian_art.POSES:
            for suffix in ("", "+"):
                pixels = posed_pixels(MobKind.GUARDIAN, False, 0, pose + suffix)
                self.assertGreater(len(pixels), 600, pose)
                pictures.add(frozenset(pixels.items()))
        self.assertEqual(2 * len(guardian_art.POSES), len(pictures))
        world = island()
        mob = next(m for m in Wildlife(world).mobs.values() if m.kind is MobKind.GUARDIAN)
        self.assertTrue(pick_pixels(mob))

    def test_it_is_about_twice_the_explorers_height(self):
        pixels = posed_pixels(MobKind.GUARDIAN, False, 0, "idle")
        height = -min(y for _, y in pixels)
        self.assertTrue(55 <= height <= 75, height)

    def test_the_fight_is_drawn_with_its_health_bar(self):
        session = GameSession.create(1234, DEFAULT_CONFIG, chunk_preview_size=24)
        world = island()
        world.guardian_defeated = False
        life = Wildlife(world)
        mob = next(m for m in life.mobs.values() if m.kind is MobKind.GUARDIAN)
        session.world, session.wildlife = world, life
        session.player.place(world.surface_position(world.arena + GridPos(2, 1)))
        renderer = PlaceholderRenderer(pygame.Surface((960, 540)), DEFAULT_CONFIG)
        renderer.draw_gameplay(session, debug=False)
        self.assertIsNone(renderer._draw_guardian_health(session), "asleep: no bar")
        mob.asleep = False
        mob.boss.move, mob.boss.stage, mob.boss.timer = "punch", "windup", .5
        mob.boss.marked = (world.arena + GridPos(2, 1),)
        mob.boss.rings.append(boss.Ring(world.surface_position(world.arena), 3.))
        mob.boss.rocks.append(boss.Rock(mob.end, world.surface_position(world.arena + GridPos(2, 1)), .5, 1.))
        renderer.draw_gameplay(session, debug=False)
        self.assertIsNotNone(renderer._draw_guardian_health(session))


if __name__ == "__main__":
    unittest.main()
