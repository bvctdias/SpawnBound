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
from spawnbound.domain.generation import WorldGenerator
from spawnbound.domain.mobs import (HEALTH, SAFE_START, SHARK_AREA, SHARK_BITES, SHARK_SPACING, MobKind, Wildlife,
                                    chebyshev)
from spawnbound.domain.model import TileKind
from spawnbound.domain.session import DRAG_SECONDS, ActionCode
from spawnbound.mob_art import pick_pixels
from spawnbound.renderer import PlaceholderRenderer
from spawnbound.shark_art import BELLY, FIN, FOAM, INK, placed_shark, shark

sys.path.insert(0, str(ROOT / "tests"))
from test_wild_fauna import flat_session, put  # noqa: E402

STEP = 1 / 30


def sea_session():
    session = flat_session()
    world = session.world
    sea = [p for p in world.tile_map.tiles if p.y < 12]
    for p in sea:
        world.tile_map.add(p, TileKind.WATER, elevation=0)
    world.sea_cells = frozenset(sea)
    return session


def swim(session, cell):
    session.player.place(session.world.surface_position(cell))


class SharkPlacementTests(unittest.TestCase):
    SEEDS = (1234, 7, 39658298)

    @classmethod
    def setUpClass(cls):
        cls.islands = []
        for seed in cls.SEEDS:
            world = WorldGenerator().generate_chunk_preview(seed, 128)
            cls.islands.append((world, Wildlife(world)))

    def test_sharks_by_sea_area_in_open_water(self):
        for world, life in self.islands:
            sharks = [m for m in life.mobs.values() if m.kind is MobKind.SHARK]
            with self.subTest(seed=world.seed):
                self.assertGreaterEqual(len(sharks), 4)
                self.assertLessEqual(len(sharks), round(len(life._swimmable_sea()) / SHARK_AREA))
                for s in sharks:
                    cell = s.end.grid
                    self.assertTrue(life.is_open_sea(cell))
                    self.assertNotIn(cell, world.river_cells)
                    self.assertFalse(world.tile_map.tile_at(cell).deep_water)
                    self.assertGreaterEqual(chebyshev(cell, world.spawn), SAFE_START)
                    self.assertTrue(all(chebyshev(s.end, o.end) >= SHARK_SPACING for o in sharks if o is not s))
                    self.assertEqual(HEALTH[MobKind.SHARK], s.hp)

    def test_rivers_and_lakes_are_never_sea(self):
        rivers = 0
        for world, life in self.islands:
            size = world.tile_map.ocean_island_size
            with self.subTest(seed=world.seed):
                for cell in world.river_cells:
                    self.assertFalse(life.is_sea(cell))
                rivers += len(world.river_cells)
                inland = [p for p, t in world.tile_map.tiles.items()
                          if t.kind is TileKind.WATER and p not in world.sea_cells and 0 <= p.x < size and 0 <= p.y < size]
                for cell in inland:
                    self.assertFalse(life.is_sea(cell))
        self.assertGreater(rivers, 0)

    def test_patrolling_and_hunting_it_never_leaves_the_open_sea(self):
        world, life = self.islands[0]
        shark = min((m for m in life.mobs.values() if m.kind is MobKind.SHARK), key=lambda m: m.id)
        saved = dict(life.mobs)
        self.addCleanup(setattr, life, "mobs", saved)
        land = min((p for p in world.tile_map.tiles if world.is_walkable(p)), key=lambda p: chebyshev(p, shark.end))
        swimmer = min((p for p in life._swimmable_sea() if chebyshev(p, land) <= 2), key=lambda p: chebyshev(p, shark.end))
        life.mobs = {shark.id: shark}
        for spot in (land, swimmer):
            player = world.surface_position(spot)
            for _ in range(round(40 / STEP)):
                life.tick(STEP, player)
                life.grace = 1.
                self.assertTrue(life.is_open_sea(shark.end.grid), shark.end.grid)


class SharkBehaviourTests(unittest.TestCase):
    def setUp(self):
        self.session = sea_session()
        self.life = self.session.wildlife
        self.world = self.session.world

    def test_three_bites_then_the_drag_to_the_bottom(self):
        session, life = self.session, self.life
        shark = put(session, MobKind.SHARK, GridPos(12, 9))
        swim(session, GridPos(12, 5))
        start = session.player.hearts
        warnings = circled = 0
        dragged_at = None
        t = 0.
        while t < 60 and session.player.position != self.world.spawn:
            before, waiting = session.player.hearts, shark.windup > 0
            session.update_mobs(STEP)
            t += STEP
            if shark.windup > 0 and not waiting and dragged_at is None:
                warnings += 1
            if session.player.hearts < before and session.drag_time <= 0 and session.player.position != self.world.spawn:
                circled += 1
                self.assertGreater(shark.circle, 0)
                self.assertEqual(circled, life.shark_bites)
            if session.drag_time > 0 and dragged_at is None:
                dragged_at = t
                self.assertEqual(SHARK_BITES, circled)
                self.assertEqual(start - SHARK_BITES, session.player.hearts)
                self.assertEqual(shark.id, session.drag_shark)
                self.assertIn("arrastou", session.last_message)
        self.assertEqual(SHARK_BITES + 1, warnings)
        self.assertIsNotNone(dragged_at)
        self.assertEqual(self.world.spawn, session.player.position)
        self.assertEqual(DEFAULT_CONFIG.starting_hearts, session.player.hearts)
        self.assertIn("fundo do mar", session.last_message)
        self.assertGreaterEqual(t - dragged_at, DRAG_SECONDS - STEP)

    def test_land_starts_the_count_again(self):
        session, life = self.session, self.life
        put(session, MobKind.SHARK, GridPos(2, 2))
        swim(session, GridPos(20, 6))
        life.shark_bites = 2
        session.update_mobs(STEP)
        self.assertEqual(2, life.shark_bites)
        swim(session, GridPos(20, 13))
        session.update_mobs(STEP)
        self.assertEqual(0, life.shark_bites)

    def test_no_bite_on_land_nor_in_a_lake_or_a_river(self):
        session, life, world = self.session, self.life, self.world
        shark = put(session, MobKind.SHARK, GridPos(12, 10))
        session.player.place(world.surface_position(GridPos(12, 12)))
        for _ in range(round(8 / STEP)):
            self.assertFalse(life.tick(STEP, session.player.position3d))
            self.assertEqual(0, shark.windup)
        side = frozenset(p for p in world.sea_cells if p.x >= 18)
        for name, sea, rivers in (("lake", world.sea_cells - side, frozenset()), ("river", world.sea_cells, side)):
            with self.subTest(name):
                world.sea_cells, world.river_cells = sea, rivers
                shark = put(session, MobKind.SHARK, GridPos(16, 6))
                swim(session, GridPos(18, 6))
                self.assertFalse(life.swimming_in_sea(session.player.position3d))
                for _ in range(round(8 / STEP)):
                    self.assertFalse(life.tick(STEP, session.player.position3d))
                    self.assertTrue(life.is_sea(shark.end.grid))
                    self.assertLess(shark.end.grid.x, 18)
                world.sea_cells, world.river_cells = sea | side, frozenset()

    def test_it_cannot_be_struck_nor_picked(self):
        session = self.session
        shark = put(session, MobKind.SHARK, GridPos(12, 9))
        swim(session, GridPos(12, 8))
        result = session.attack_mob(shark.id)
        self.assertIs(ActionCode.BLOCKED, result.code)
        self.assertIn("tubarão", result.message)
        self.assertEqual(HEALTH[MobKind.SHARK], shark.hp)
        self.assertEqual(frozenset(), frozenset(pick_pixels(shark)))


class SharkArtTests(unittest.TestCase):
    STANCES = (("idle", 0), ("idle", 1), ("walk", 0), ("walk", 1), ("strike_ready", 0),
               ("strike", 0), ("strike", 1), ("drag", 0))

    def test_fins_out_of_the_water_the_body_under_it(self):
        for stance, stride in self.STANCES:
            pixels = shark(stride, stance)
            above = {p: c for p, c in pixels.items() if p[1] < 0}
            below = {p: c for p, c in pixels.items() if p[1] > 0}
            with self.subTest(stance=stance, stride=stride):
                self.assertTrue(above and below)
                self.assertIn(INK, above.values())
                self.assertNotIn(INK, below.values())
                self.assertIn(FOAM, pixels.values())
                grey = [c for c in above.values() if c in FIN]
                self.assertTrue(all(max(c) - min(c) <= 24 for c in grey))
                if stance in ("strike", "drag"):
                    self.assertLessEqual(min(y for _, y in above), -10)
                else:
                    self.assertTrue(set(FIN) & set(above.values()))
        body = {p: c for p, c in shark(0, "idle").items() if p[1] > 0}
        column = sorted((y, sum(c)) for (x, y), c in body.items() if x == 8)
        self.assertLess(column[0][1], column[-1][1])
        self.assertGreater(len({c for c in body.values() if sum(c) > sum(BELLY[0]) * .8}), 0)

    def test_the_layers_split_at_the_surface(self):
        for stance, stride in self.STANCES:
            for left in (False, True):
                whole, (ax, ay) = placed_shark(stance, stride, left, 2)
                above, anchor_a = placed_shark(stance, stride, left, 2, "above")
                below, anchor_b = placed_shark(stance, stride, left, 2, "below")
                with self.subTest(stance=stance, left=left):
                    self.assertEqual(whole.get_size(), above.get_size())
                    self.assertEqual((ax, ay), anchor_a)
                    self.assertEqual((ax, ay), anchor_b)
                    self.assertLessEqual(above.get_bounding_rect().bottom, ay + 2)
                    self.assertGreaterEqual(below.get_bounding_rect().top, ay + 2)

    def test_drawn_in_both_renderers_and_under_the_water(self):
        from spawnbound.prototype_art import PrototypeArtRenderer
        pygame.font.init()
        session = sea_session()
        shark = put(session, MobKind.SHARK, GridPos(12, 9))
        shark.attack = "strike"
        swim(session, GridPos(12, 7))
        art = PrototypeArtRenderer(pygame.Surface((960, 540)), DEFAULT_CONFIG, ROOT / "assets/native_32/manifest.json")
        plain = PlaceholderRenderer(pygame.Surface((960, 540)), DEFAULT_CONFIG)
        for renderer in (art, plain):
            for windup, lunge, drag in ((0., 0., 0.), (.3, 0., 0.), (0., .3, 0.), (0., 0., .8)):
                shark.windup, shark.lunge = windup, lunge
                session.drag_time, session.drag_shark = drag, (shark.id if drag else None)
                renderer.draw_gameplay(session, debug=False)
                with self.subTest(renderer=type(renderer).__name__, windup=windup, lunge=lunge, drag=drag):
                    self.assertEqual(1, len(renderer._sharks_below))


if __name__ == "__main__":
    unittest.main()
