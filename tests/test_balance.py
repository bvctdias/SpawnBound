import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "dependencias")]
import pygame  # noqa: F401

from spawnbound.config import DEFAULT_CONFIG
from spawnbound.domain.coordinates import GridPos
from spawnbound.domain.mobs import BLOW_HEARTS, CHARGE_WINDUP, HEALTH, LEAP_WINDUP, SWORD_DAMAGE, MobKind
from spawnbound.domain.session import BLOW_MESSAGES

sys.path.insert(0, str(ROOT / "tests"))
from test_wild_fauna import flat_session, put  # noqa: E402

STEP = 1 / 60


def struck(session, blow):
    life = session.wildlife
    life.last_blow, life.last_hit = blow, (1., 0.)
    life.tick = lambda dt, player: True
    return session.update_mobs(STEP)


class BlowTests(unittest.TestCase):
    def test_the_heavy_blows_take_two_hearts_and_every_other_one(self):
        self.assertEqual({"antlers", "ram", "pounce", "fist", "stomp", "boulder"}, set(BLOW_HEARTS))
        self.assertTrue(set(BLOW_HEARTS) <= set(BLOW_MESSAGES))
        for blow in BLOW_MESSAGES:
            with self.subTest(blow=blow):
                session = flat_session()
                self.assertFalse(struck(session, blow))
                self.assertEqual(DEFAULT_CONFIG.starting_hearts - BLOW_HEARTS.get(blow, 1), session.player.hearts)
                self.assertEqual(BLOW_MESSAGES[blow], session.last_message)

    def test_a_heavy_blow_on_the_last_heart_sends_the_player_to_camp(self):
        session = flat_session()
        session.player.hearts = 1
        self.assertTrue(struck(session, "ram"))
        self.assertEqual(DEFAULT_CONFIG.starting_hearts, session.player.hearts)

    def test_a_deer_charge_and_a_spider_leap_take_two_hearts(self):
        for kind, attack, windup in ((MobKind.DEER, "charge", CHARGE_WINDUP), (MobKind.SPIDER, "charge", LEAP_WINDUP)):
            with self.subTest(kind=kind):
                session = flat_session()
                here = session.player.position
                mob = put(session, kind, here + GridPos(3, 0))
                if kind is MobKind.DEER:
                    mob.anger = 12.
                else:
                    session.wildlife.night_spawned = True
                hearts = session.player.hearts
                for _ in range(round(3 / STEP)):
                    session.update_mobs(STEP)
                    if session.player.hearts < hearts:
                        break
                self.assertEqual(hearts - 2, session.player.hearts)
                self.assertIn(session.wildlife.last_blow, ("antlers", "pounce"))


class HealthTests(unittest.TestCase):
    def test_the_fighters_take_several_blows(self):
        self.assertEqual({MobKind.DEER: 7, MobKind.MINE_MONSTER: 8, MobKind.SPIDER: 5, MobKind.SKELETON: 4,
                          MobKind.SNAKE: 3},
                         {kind: -(-HEALTH[kind] // SWORD_DAMAGE)
                          for kind in (MobKind.DEER, MobKind.MINE_MONSTER, MobKind.SPIDER,
                                       MobKind.SKELETON, MobKind.SNAKE)})

    def test_a_struck_deer_still_stands_after_three_blows(self):
        session = flat_session()
        deer = put(session, MobKind.DEER, GridPos(10, 10))
        session.player.position = GridPos(11, 10)
        for _ in range(3):
            session.player.energy = session.player.max_energy
            self.assertTrue(session.attack_mob(deer.id).success)
        self.assertEqual(HEALTH[MobKind.DEER] - 3 * SWORD_DAMAGE, deer.hp)
        self.assertIn(deer.id, session.wildlife.mobs)


if __name__ == "__main__":
    unittest.main()
