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
from spawnbound.domain.mobs import (FANG_WINDUP, LEAP_RECOVER, LEAP_REACH, LEAP_WINDUP, MAX_SPIDERS, SAFE_START,
                                    SPIDER_FAR, SPIDER_NEAR, SPIDER_SIGHT, HEALTH, SWORD_DAMAGE, MobKind, Wildlife, chebyshev)
from spawnbound.domain.model import Biome
from spawnbound.mob_art import posed_pixels
from spawnbound.renderer import PlaceholderRenderer
from spawnbound.wild_art import SPIDER_EYE

from test_wild_fauna import flat_session, put, run


class SpiderSpawnTests(unittest.TestCase):
    def test_spiders_are_born_in_the_forest_out_of_sight(self):
        for seed in (1234, 7, 39658298):
            with self.subTest(seed=seed):
                world = WorldGenerator().generate_chunk_preview(seed, 128)
                born = []
                for cell in sorted(Wildlife(world)._forest)[::97][:12]:
                    life = Wildlife(world)
                    player = world.surface_position(cell)
                    life.start_night(player)
                    for _ in range(3):
                        life._spider_in = 0.
                        life.tick(.01, player)
                    spiders = [m for m in life.mobs.values() if m.kind is MobKind.SPIDER]
                    self.assertLessEqual(len(spiders), MAX_SPIDERS)
                    for spider in spiders:
                        home = spider.home
                        self.assertIs(Biome.FOREST, world.tile_map.tile_at(home).biome)
                        self.assertGreater(chebyshev(home, cell), 20)
                        self.assertLessEqual(chebyshev(home, cell), SPIDER_FAR)
                        self.assertGreaterEqual(chebyshev(home, cell), SPIDER_NEAR)
                        self.assertGreaterEqual(chebyshev(home, world.spawn), SAFE_START)
                    born += spiders
                self.assertGreaterEqual(len(born), 6)
                glands = sum(any(item == "venom_gland" for item, _ in s.loot) for s in born)
                self.assertTrue(all(dict(s.loot)["silk"] in (1, 2) for s in born))
                self.assertLess(glands, len(born))

    def test_no_forest_no_spiders(self):
        session = flat_session()
        life = session.wildlife
        life.start_night(session.player.position3d)
        self.assertEqual(0, life.spider_count)
        self.assertGreater(life.archer_count, 0)


class SpiderHuntTests(unittest.TestCase):
    def setUp(self):
        self.session = flat_session()
        self.life = self.session.wildlife
        self.life.night_spawned = True
        self.spider = put(self.session, MobKind.SPIDER, GridPos(10, 10))

    def at(self, cell):
        return self.session.world.surface_position(cell)

    def test_it_crouches_and_leaps_at_the_player(self):
        player = self.at(GridPos(13, 10))
        self.life.tick(.01, player)
        self.assertEqual("charge", self.spider.attack)
        self.assertEqual(GridPos(1, 0), self.spider.charge)
        self.assertTrue(self.spider.hostile)
        self.assertTrue(run(self.life, LEAP_WINDUP + .4, player))
        self.assertEqual("pounce", self.life.last_blow)
        self.assertGreater(self.spider.dazed, 0)

    def test_stepping_out_of_the_line_dodges_the_leap(self):
        self.life.tick(.01, self.at(GridPos(13, 10)))
        aside = self.at(GridPos(13, 13))
        self.assertFalse(run(self.life, LEAP_WINDUP + .2, aside))
        for _ in range(120):
            self.assertFalse(self.life.tick(1 / 60, aside))
            if self.spider.dazed:
                break
        self.assertGreater(self.spider.dazed, LEAP_RECOVER - .1)
        self.assertLessEqual(self.spider.end.x - 10, LEAP_REACH)
        self.assertEqual(10, self.spider.end.y)

    def test_it_bites_whoever_stays_close(self):
        player = self.at(GridPos(11, 10))
        self.life.tick(.01, player)
        self.assertEqual("strike", self.spider.attack)
        self.assertTrue(run(self.life, FANG_WINDUP + .05, player))
        self.assertEqual("fangs", self.life.last_blow)

    def test_it_closes_in_from_afar_and_ignores_a_player_out_of_sight(self):
        far = self.at(GridPos(10 + SPIDER_SIGHT + 4, 10))
        run(self.life, 3., far, step=.05)
        self.assertEqual(0., self.spider.anger)
        here = self.spider.end.grid
        side = 1 if here.x + SPIDER_SIGHT <= 23 else -1
        near = self.at(GridPos(here.x + side * SPIDER_SIGHT, here.y))
        self.spider.wait = 0.
        run(self.life, 1.5, near, step=1 / 60)
        self.assertGreater(self.spider.anger, 0)
        self.assertLess(chebyshev(self.spider.end, near), SPIDER_SIGHT)

    def test_dawn_sends_it_away(self):
        player = self.at(GridPos(13, 10))
        self.life.dawn()
        self.assertEqual(0., self.spider.anger)
        self.life.in_view = lambda player, pos: True
        start = chebyshev(self.spider.end, player)
        self.assertFalse(run(self.life, 2., player))
        self.assertGreater(chebyshev(self.spider.end, player), start)
        self.life.in_view = lambda player, pos: False
        self.life.tick(.01, player)
        self.assertEqual(0, self.life.spider_count)

    def test_struck_in_the_dark_it_hunts_the_striker(self):
        session = self.session
        session.player.position = GridPos(11, 10)
        self.spider.anger = 0.
        result = session.attack_mob(self.spider.id)
        self.assertTrue(result.success)
        self.assertGreater(self.spider.anger, 0)


class SpiderLootTests(unittest.TestCase):
    def test_silk_and_venom_gland(self):
        session = flat_session()
        spider = put(session, MobKind.SPIDER, GridPos(10, 10))
        spider.loot = (("silk", 2), ("venom_gland", 1))
        session.player.position = GridPos(11, 10)
        for _ in range(-(-HEALTH[MobKind.SPIDER] // SWORD_DAMAGE)):
            session.player.energy = 100
            result = session.attack_mob(spider.id)
        self.assertNotIn(spider.id, session.wildlife.mobs)
        self.assertEqual(2, session.player.inventory.quantity("silk"))
        self.assertEqual(1, session.player.inventory.quantity("venom_gland"))
        self.assertIn("fio de teia", result.message)
        self.assertNotIn("comer", result.message)

    def test_each_spider_blow_has_its_message(self):
        session = flat_session()
        session.wildlife.night_spawned = True
        put(session, MobKind.SPIDER, GridPos(11, 10))
        session.player.position = GridPos(12, 10)
        for _ in range(120):
            if session.update_mobs(1 / 60) or session.hurt_time:
                break
        self.assertEqual("A aranha te mordeu!", session.last_message)


class SpiderArtTests(unittest.TestCase):
    def test_poses_read_differently_and_fit_the_sprite(self):
        idle = posed_pixels(MobKind.SPIDER, False, 0, "idle")
        leap = posed_pixels(MobKind.SPIDER, False, 0, "charge")
        crouch = posed_pixels(MobKind.SPIDER, False, 0, "charge_ready")
        self.assertLess(max(y for _, y in leap), max(y for _, y in idle) - 1)
        body = lambda px: min(y for (x, y), c in px.items() if c == (146, 92, 58))
        self.assertGreater(body(crouch), body(idle))
        for stance in ("idle", "walk", "hurt", "charge_ready", "charge", "dazed", "strike_ready", "strike",
                       "run", "rest"):
            for left in (False, True):
                for stride in (0, 1):
                    pixels = posed_pixels(MobKind.SPIDER, left, stride, stance)
                    self.assertTrue(all(-20 <= x <= 19 and -32 <= y <= 3 for x, y in pixels), stance)
        self.assertIn(SPIDER_EYE, idle.values())

    def test_eyes_glow_at_night(self):
        pygame.font.init()
        session = flat_session()
        put(session, MobKind.SPIDER, GridPos(11, 11))
        session.player.position = GridPos(9, 13)
        session.cycle_seconds = sum(DEFAULT_CONFIG.phase_durations[:2]) + DEFAULT_CONFIG.phase_durations[2] / 2
        renderer = PlaceholderRenderer(pygame.Surface((960, 540)), DEFAULT_CONFIG)
        glowing = renderer._draw_spider_eyes
        counts = []
        renderer._draw_spider_eyes = lambda *args: counts.append(glowing(*args))
        renderer.draw_gameplay(session, debug=False)
        lit = pygame.image.tobytes(renderer._world_screen, "RGB")
        self.assertGreater(counts[0], 0)
        renderer._draw_spider_eyes = lambda *args: 0
        renderer.draw_gameplay(session, debug=False)
        self.assertNotEqual(lit, pygame.image.tobytes(renderer._world_screen, "RGB"))


if __name__ == "__main__":
    unittest.main()
