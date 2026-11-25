import random
import unittest

from test_wild_fauna import flat_session, run
from spawnbound import savegame
from spawnbound.config import DEFAULT_CONFIG
from spawnbound.domain.coordinates import GridPos, WorldPos
from spawnbound.domain.mobs import (HEALTH, SAFE_START, WORM_DESERT, WORM_SECOND, WORM_SPACING,
                                    WORM_TERRITORY, MobKind, Wildlife, chebyshev)
from spawnbound.domain.session import ActionCode, GameSession

LAIR_NAMES = ("_lairs", "_lair_hp", "_lair_dead", "_worm_lair")


class LairTests(unittest.TestCase):
    def setUp(self):
        self.s = flat_session()
        self.life = self.s.wildlife
        self.life._lairs = [(GridPos(4, 4), 0)]

    def step(self, cell):
        here = self.s.world.surface_position(cell)
        self.life.tick(.05, here)
        moved = WorldPos(here.x + .03, here.y, here.z)
        self.s.player.place(moved)
        self.life.tick(.05, moved)
        return self.life.mobs.get(self.life._worm_id) if self.life._worm_id is not None else None

    def test_steps_far_from_the_lair_bring_nothing_up(self):
        self.assertIsNone(self.step(GridPos(4 + WORM_TERRITORY + 1, 4)))
        self.assertIsNone(self.step(GridPos(20, 20)))

    def test_steps_near_the_lair_bring_its_worm_up(self):
        worm = self.step(GridPos(4 + WORM_TERRITORY, 6))
        self.assertIs(MobKind.SANDWORM, worm.kind)
        self.assertEqual(0, self.life._worm_lair)

    def test_it_dives_when_the_player_leaves_its_territory_and_keeps_its_wounds(self):
        worm = self.step(GridPos(12, 4))
        worm.hp = 7
        run(self.life, 1.2, self.s.world.surface_position(GridPos(12, 4)))
        away = self.s.world.surface_position(GridPos(4 + WORM_TERRITORY + 1, 4))
        run(self.life, 1.5, away)
        self.assertNotIn(worm.id, self.life.mobs)
        self.assertEqual({0: 7}, self.life._lair_hp)
        self.assertIsNone(self.step(GridPos(4 + WORM_TERRITORY + 2, 4)))
        self.assertEqual(7, self.step(GridPos(6, 6)).hp)

    def kill(self, worm):
        worm.hp = 1
        self.s.player.facing = worm.end.grid - self.s.player.position
        self.assertIs(ActionCode.MOB_DEFEATED, self.s.attack_mob(worm.id).code)

    def test_a_killed_worm_never_comes_back(self):
        self.kill(self.step(GridPos(6, 6)))
        for x in range(1, 12):
            self.assertIsNone(self.step(GridPos(x, 5)))
        self.assertEqual({0}, self.life._lair_dead)
        self.assertEqual([], self.life.worm_lairs)

    def test_the_second_lair_of_a_desert_keeps_its_own_worm(self):
        self.life._lairs.append((GridPos(20, 20), 0))
        self.kill(self.step(GridPos(6, 6)))
        self.assertIsNone(self.step(GridPos(8, 8)))
        worm = self.step(GridPos(18, 18))
        self.assertEqual(1, self.life._worm_lair)
        self.assertEqual(HEALTH[MobKind.SANDWORM], worm.hp)

    def test_a_game_saved_before_the_lairs_gets_them(self):
        session = GameSession.create(7, DEFAULT_CONFIG, chunk_preview_size=128)
        life = session.wildlife
        lairs = list(life._lairs)
        saved = savegame.schema(session)
        for name in LAIR_NAMES:
            delattr(life, name)
        saved[savegame._key(Wildlife)] = sorted(vars(life))
        savegame.upgrade(session, saved)
        self.assertEqual(lairs, life._lairs)
        self.assertEqual((set(), {}, None), (life._lair_dead, life._lair_hp, life._worm_lair))


class IslandLairTests(unittest.TestCase):
    def test_at_most_two_lairs_per_desert_away_from_the_camp(self):
        seeds = [7] + [random.Random(2311 + i).randrange(2_147_483_647) for i in range(2)]
        for seed in seeds:
            with self.subTest(seed=seed):
                session = GameSession.create(seed, DEFAULT_CONFIG, chunk_preview_size=128)
                world, life = session.world, session.wildlife
                self.assertTrue(life._lairs)
                sizes = {}
                for desert in life._desert_of.values():
                    sizes[desert] = sizes.get(desert, 0) + 1
                for desert, size in sizes.items():
                    lairs = [cell for cell, home in life._lairs if home == desert]
                    self.assertLessEqual(len(lairs), 2 if size >= WORM_SECOND else 1 if size >= WORM_DESERT else 0)
                    if len(lairs) == 2:
                        self.assertGreaterEqual(chebyshev(*lairs), WORM_SPACING)
                for cell, desert in life._lairs:
                    self.assertEqual(desert, life._desert_of[cell])
                    self.assertGreaterEqual(chebyshev(cell, world.spawn), SAFE_START + WORM_TERRITORY)


if __name__ == "__main__":
    unittest.main()
