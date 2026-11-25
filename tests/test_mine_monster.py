import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "dependencias")]
import pygame

from spawnbound.config import DEFAULT_CONFIG
from spawnbound.domain.coordinates import GridPos
from spawnbound.domain.inventory import Stack
from spawnbound.domain.mobs import (SWORD_DAMAGE, BLOW_HEARTS, GIVE_UP, HEALTH, MAW_WINDUP, MAX_MONSTERS, MONSTER_MIN, MONSTER_ORE,
                                    MONSTER_SAFE, MONSTER_SPACING, MONSTER_VEINS, ORE_VEINS, WAKE_RADIUS, MobKind,
                                    chebyshev)
from spawnbound.domain.model import ORE_YIELDS, ObjectKind, SpaceKind, WorldObject
from spawnbound.domain.session import GameSession
from spawnbound.mine_monster_art import INK, MAW, PURPLE, TOOTH, mine_monster
from spawnbound.mob_art import ANCHOR, CANVAS, mob_pose, pick_pixels
from spawnbound.renderer import PlaceholderRenderer

sys.path.insert(0, str(ROOT / "tests"))
from test_wild_fauna import flat_session, put, run  # noqa: E402

STEP = 1 / 30


def sleeper(session, cell, vein, uid=1):
    world = session.world
    world.objects[vein] = WorldObject.create(vein, ObjectKind.ROCK, variant="copper_ore",
                                             elevation=world.elevation_at(vein))
    mob = put(session, MobKind.MINE_MONSTER, cell, uid)
    mob.asleep, mob.vein, mob.loot = True, vein, (("copper", MONSTER_ORE),)
    return mob


def enter_mine(session):
    island = session.world
    entrance = next(p for p in island.portals.values() if p.target_kind is SpaceKind.CAVE)
    session.player.place(island.surface_position(entrance.approach))
    session.player.facing = entrance.position - entrance.approach
    session.interact()
    return session.world


def leave_mine(session):
    exit_portal = next(iter(session.world.portals.values()))
    session.player.place(session.world.surface_position(exit_portal.approach))
    session.player.facing = exit_portal.position - exit_portal.approach
    session.interact()


class MinePlacementTests(unittest.TestCase):
    SEEDS = (1234, 7, 39658298)

    @classmethod
    def setUpClass(cls):
        cls.mines = []
        for seed in cls.SEEDS:
            session = GameSession.create(seed, DEFAULT_CONFIG, chunk_preview_size=128)
            island_mobs = set(session.wildlife.mobs)
            cave = enter_mine(session)
            cls.mines.append((session, cave, island_mobs))

    def test_monsters_sleep_beside_veins_away_from_the_entrance(self):
        for session, cave, _ in self.mines:
            life = session.wildlife
            monsters = list(life.mobs.values())
            veins = [p for p, o in cave.objects.items() if o.kind is ObjectKind.ROCK and o.variant in ORE_VEINS
                     and chebyshev(p, cave.spawn) >= MONSTER_SAFE]
            with self.subTest(seed=cave.seed):
                self.assertIs(SpaceKind.CAVE, cave.space_kind)
                self.assertGreaterEqual(len(monsters), min(MONSTER_MIN, len(veins)))
                self.assertLessEqual(len(monsters),
                                     min(MAX_MONSTERS, max(MONSTER_MIN, round(len(veins) / MONSTER_VEINS))))
                for m in monsters:
                    self.assertIs(MobKind.MINE_MONSTER, m.kind)
                    self.assertTrue(m.asleep)
                    self.assertIn(m.vein, veins)
                    self.assertEqual(1, chebyshev(m.end.grid, m.vein))
                    self.assertTrue(cave.is_walkable(m.end.grid))
                    (ore, _), = ORE_YIELDS[cave.objects[m.vein].variant][0]
                    self.assertEqual(((ore, MONSTER_ORE),), m.loot)
                    self.assertTrue(all(chebyshev(m.vein, o.vein) >= MONSTER_SPACING for o in monsters if o is not m))

    def test_the_island_keeps_its_creatures_while_in_the_mine(self):
        for session, cave, island_mobs in self.mines:
            with self.subTest(seed=cave.seed):
                self.assertIsNot(session.island_life, session.wildlife)
                self.assertIs(cave, session.wildlife.world)
                self.assertEqual(island_mobs, set(session.island_life.mobs))
                self.assertTrue(all(m.kind is MobKind.MINE_MONSTER for m in session.wildlife.mobs.values()))
                self.assertFalse(any(m.kind is MobKind.MINE_MONSTER for m in session.island_life.mobs.values()))


class MineMonsterBehaviourTests(unittest.TestCase):
    def setUp(self):
        self.session = flat_session()
        self.life = self.session.wildlife
        self.here = self.session.player.position

    def test_asleep_until_the_player_comes_close(self):
        session, life = self.session, self.life
        mob = sleeper(session, self.here + GridPos(5, 0), self.here + GridPos(6, 0))
        self.assertFalse(run(life, 3., session.player.position3d))
        self.assertTrue(mob.asleep)
        self.assertEqual(self.here + GridPos(5, 0), mob.end.grid)
        self.assertEqual("sleep", mob_pose(mob)[3])
        session.player.place(session.world.surface_position(self.here + GridPos(5 - WAKE_RADIUS, 0)))
        session.update_mobs(STEP)
        self.assertFalse(mob.asleep)
        self.assertEqual("O monstro da mina acordou!", session.last_message)

    def test_a_blow_on_its_vein_wakes_it(self):
        session = self.session
        vein = self.here + GridPos(1, 0)
        mob = sleeper(session, vein + GridPos(1, 1), vein)
        other = sleeper(session, self.here + GridPos(-6, 6), self.here + GridPos(-7, 6), uid=2)
        session.player.inventory.slots[0] = Stack("stone_pickaxe", 1)
        session.player.inventory.selected = 0
        result = session.primary_action(vein)
        self.assertIn("acordou", result.message)
        self.assertFalse(mob.asleep)
        self.assertTrue(other.asleep)

    def test_it_bites_with_a_warning_and_charges_from_afar(self):
        session, life = self.session, self.life
        mob = sleeper(session, self.here + GridPos(1, 0), self.here + GridPos(2, 0))
        mob.asleep = False
        run(life, STEP, session.player.position3d)
        self.assertEqual("strike", mob.attack)
        self.assertAlmostEqual(MAW_WINDUP, mob.windup, delta=STEP)
        self.assertFalse(session.update_mobs(MAW_WINDUP))
        self.assertEqual(DEFAULT_CONFIG.starting_hearts - 1, session.player.hearts)
        self.assertEqual("O monstro da mina te mordeu!", session.last_message)
        session.player.hearts = DEFAULT_CONFIG.starting_hearts
        mob = sleeper(session, self.here + GridPos(0, 3), self.here + GridPos(0, 4))
        mob.asleep = False
        life.grace = 0.
        run(life, STEP, session.player.position3d)
        self.assertEqual("charge", mob.attack)
        hearts = session.player.hearts
        for _ in range(round(2 / STEP)):
            session.update_mobs(STEP)
            if session.player.hearts < hearts:
                break
        self.assertEqual(hearts - BLOW_HEARTS["ram"], session.player.hearts)
        self.assertEqual("O monstro da mina te atropelou!", session.last_message)

    def test_a_dodged_charge_leaves_it_dazed(self):
        session, life = self.session, self.life
        mob = sleeper(session, self.here + GridPos(3, 0), self.here + GridPos(4, 0))
        mob.asleep = False
        run(life, STEP, session.player.position3d)
        self.assertEqual("charge", mob.attack)
        session.player.place(session.world.surface_position(self.here + GridPos(0, 2)))
        dazed = False
        for _ in range(round(2 / STEP)):
            self.assertFalse(life.tick(STEP, session.player.position3d))
            dazed |= mob.dazed > 0
        self.assertTrue(dazed)

    def test_left_behind_it_goes_back_to_sleep(self):
        session, life = self.session, self.life
        home = self.here + GridPos(4, 0)
        mob = sleeper(session, home, home + GridPos(1, 0))
        mob.asleep = False
        mob.walk(session.world.surface_position(home + GridPos(-2, 0)))
        mob.progress = 1.
        session.player.place(session.world.surface_position(self.here + GridPos(-GIVE_UP, -GIVE_UP)))
        self.assertGreater(chebyshev(mob.end, session.player.position3d), GIVE_UP)
        run(life, 6., session.player.position3d)
        self.assertEqual(home, mob.end.grid)
        self.assertTrue(mob.asleep)

    def test_it_falls_to_its_health_and_leaves_the_ore_of_its_vein(self):
        session = self.session
        mob = sleeper(session, self.here + GridPos(1, 0), self.here + GridPos(2, 0))
        first = session.attack_mob(mob.id)
        self.assertTrue(first.success)
        self.assertFalse(mob.asleep)
        for _ in range(-(-HEALTH[MobKind.MINE_MONSTER] // SWORD_DAMAGE) - 1):
            session.player.energy = session.player.max_energy
            result = session.attack_mob(mob.id)
        self.assertNotIn(mob.id, self.life.mobs)
        self.assertEqual(MONSTER_ORE, session.player.inventory.quantity("copper"))
        self.assertEqual(f"+{MONSTER_ORE} cobre.", result.message)


class MineIntegrationTests(unittest.TestCase):
    def test_falling_in_the_mine_brings_the_player_back_to_the_island_camp(self):
        session = GameSession.create(1234, DEFAULT_CONFIG, chunk_preview_size=128)
        island = session.world
        cave = enter_mine(session)
        life = session.wildlife
        mob = next(iter(life.mobs.values()))
        cell = next(mob.end.grid + d for d in (GridPos(1, 0), GridPos(0, 1), GridPos(-1, 0), GridPos(0, -1))
                    if cave.can_step(mob.end.grid + d, mob.end.grid) and mob.end.grid + d not in cave.objects)
        session.player.place(cave.surface_position(cell))
        session.player.hearts = 1
        revived = False
        for _ in range(round(6 / STEP)):
            if session.update_mobs(STEP):
                revived = True
                break
        self.assertTrue(revived)
        self.assertIs(island, session.world)
        self.assertIs(session.island_life, session.wildlife)
        self.assertEqual(island.spawn, session.player.position)
        self.assertEqual(island.space_id, session.player.space_id)
        self.assertEqual(DEFAULT_CONFIG.starting_hearts, session.player.hearts)
        self.assertEqual("Voce voltou ao acampamento.", session.last_message)

    def test_back_in_the_mine_every_monster_sleeps_in_its_bed(self):
        session = GameSession.create(7, DEFAULT_CONFIG, chunk_preview_size=128)
        enter_mine(session)
        life = session.wildlife
        mob = next(iter(life.mobs.values()))
        home = mob.home
        life.wake(mob)
        mob.walk(session.world.surface_position(home + GridPos(0, 0)))
        leave_mine(session)
        self.assertIs(session.island_life, session.wildlife)
        enter_mine(session)
        self.assertIs(life, session.wildlife)
        self.assertTrue(mob.asleep)
        self.assertEqual(home, mob.end.grid)


class MineMonsterArtTests(unittest.TestCase):
    STANCES = ("idle", "walk", "sleep", "strike_ready", "strike", "charge_ready", "charge", "dazed")

    def test_poses_fit_the_canvas_with_teeth_and_horns(self):
        for stance in self.STANCES:
            for stride in (0, 1):
                pixels = mine_monster(stride, stance)
                xs = [x for x, _ in pixels]
                ys = [y for _, y in pixels]
                with self.subTest(stance=stance, stride=stride):
                    self.assertGreaterEqual(min(xs), -ANCHOR[0])
                    self.assertLess(max(xs), CANVAS[0] - ANCHOR[0])
                    self.assertGreaterEqual(min(ys), -ANCHOR[1])
                    self.assertEqual(1, max(ys))
                    self.assertIn(INK, pixels.values())
                    self.assertIn(TOOTH, pixels.values())
                    self.assertGreater(sum(c in PURPLE for c in pixels.values()), 120)
        maw = {s: sum(c == MAW for c in mine_monster(0, s).values()) for s in self.STANCES}
        self.assertLess(maw["sleep"], maw["idle"])
        self.assertLess(maw["idle"], maw["strike_ready"])
        self.assertLess(maw["strike_ready"], maw["strike"])
        tops = {s: min(y for _, y in mine_monster(0, s)) for s in ("idle", "sleep")}
        self.assertGreater(tops["sleep"], tops["idle"])
        width = max(x for x, _ in mine_monster(0, "idle")) - min(x for x, _ in mine_monster(0, "idle")) + 1
        self.assertTrue(24 <= width <= 34, width)

    def test_drawn_in_both_renderers_with_its_sleep_marks(self):
        from spawnbound.prototype_art import PrototypeArtRenderer
        pygame.font.init()
        session = flat_session()
        here = session.player.position
        asleep = sleeper(session, here + GridPos(3, 2), here + GridPos(4, 2))
        awake = sleeper(session, here + GridPos(-2, 1), here + GridPos(-3, 1), uid=2)
        awake.asleep, awake.attack, awake.windup = False, "strike", .3
        self.assertTrue(pick_pixels(asleep) and pick_pixels(awake))
        art = PrototypeArtRenderer(pygame.Surface((960, 540)), DEFAULT_CONFIG, ROOT / "assets/native_32/manifest.json")
        plain = PlaceholderRenderer(pygame.Surface((960, 540)), DEFAULT_CONFIG)
        for renderer in (art, plain):
            renderer.draw_gameplay(session, debug=False)
            self.assertEqual(1, renderer._draw_sleep_marks(session, renderer._camera_origin(session, session.player.position3d)))


if __name__ == "__main__":
    unittest.main()
