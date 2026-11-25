import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from spawnbound.config import DEFAULT_CONFIG
from spawnbound.domain.coordinates import GridPos, WorldPos
from spawnbound.domain.mobs import (ACTIVE_RADIUS, ARCHER_SECONDS, DESPAWN_RADIUS, HERD_KINDS, HERD_SPACING, HOME_RADIUS,
                                    REPLENISH_SECONDS, Arrow, MobKind, Wildlife, chebyshev)
from spawnbound.domain.model import SpaceKind
from spawnbound.domain.session import FOOD, GameSession
from spawnbound.input import InputFrame
from spawnbound.mob_art import mob_pixels
from spawnbound.states import GameplayState, StateStack
from spawnbound.view import camera_origin, pick_world_point, screen_center


class MobTests(unittest.TestCase):
    def setUp(self):
        self.session = GameSession.create(1234, DEFAULT_CONFIG, chunk_preview_size=24)
        self.session.player.inventory.selected = 3
        self.state = GameplayState(self.session, DEFAULT_CONFIG)
        self.life = self.session.wildlife

    def click(self, mob):
        origin = camera_origin(self.session, DEFAULT_CONFIG, self.state.visual_position3d)
        x, y = screen_center(mob.location, origin, DEFAULT_CONFIG)
        for dx, dy in mob_pixels(mob):
            point = (x+dx, y+dy)
            hit = pick_world_point(self.session, point, origin, DEFAULT_CONFIG)
            if hit is not None and hit.mob_id == mob.id:
                self.state.step(InputFrame(destination_click=point), 0)
                return
        self.fail("No visible creature pixel at the selected test site")

    def test_click_hunts_same_animal_after_it_moves_and_meat_is_consumable(self):
        s = self.session
        pig = next(m for m in self.life.mobs.values() if m.kind is MobKind.PIG)
        self.life.mobs = {pig.id: pig}
        from spawnbound.domain.model import TileKind
        start = s.player.position
        for p in tuple(s.world.tile_map.tiles):
            s.world.tile_map.add(p, TileKind.GRASS, elevation=s.player.elevation)
            s.world.objects.pop(p, None)
        pig.start = pig.end = s.world.surface_position(start + GridPos(4, 0))
        pig.wait = 10
        self.click(pig)
        self.assertEqual(self.state._mob_id, pig.id)
        pig.walk(s.world.surface_position(start + GridPos(4, 1)))
        for _ in range(150):
            self.state.step(InputFrame(), 1/60)
        self.assertEqual(2, pig.hp)
        self.assertGreater(pig.flee_time, 0.)
        self.assertEqual(s.config.starting_hearts, s.player.hearts)
        self.click(pig)
        for _ in range(360):
            self.state.step(InputFrame(), 1/60)
            if pig.id not in self.life.mobs:
                break
        self.assertNotIn(pig.id, self.life.mobs)
        self.assertEqual(2, s.player.inventory.quantity("meat"))
        energy = s.player.energy
        self.state.step(InputFrame(eat_pressed=True), 0)
        self.assertEqual((energy + FOOD["meat"], s.config.starting_hearts - 1), (s.player.energy, s.player.hearts))
        self.assertEqual(1, s.player.inventory.quantity("meat"))
        s.player.energy = s.player.max_energy
        self.state.step(InputFrame(eat_pressed=True), 0)
        self.assertEqual(1, s.player.inventory.quantity("meat"))

    def test_night_only_dawn_inside_a_mine_and_next_night(self):
        s = self.session
        passive = set(self.life.mobs)
        self.assertEqual({MobKind.CHICKEN, MobKind.PIG}, {m.kind for m in self.life.mobs.values()})
        s.advance_time(59.99)
        self.assertEqual(passive, set(self.life.mobs))
        s.advance_time(.02)
        enemies = set(self.life.mobs) - passive
        self.assertEqual(2, len(enemies))
        self.assertTrue(all(self.life.mobs[i].kind is MobKind.SKELETON for i in enemies))
        for mob in self.life.mobs.values():
            self.assertTrue(s.world.is_walkable(mob.end.grid))
        exterior = s.world
        entrance = next(p for p in exterior.portals.values() if p.target_kind is SpaceKind.CAVE)
        s.player.place(exterior.surface_position(entrance.approach))
        s.player.facing = entrance.position-entrance.approach
        s.interact()
        s.advance_time(30)
        self.assertEqual(passive, set(self.life.mobs))
        self.assertFalse(self.life.arrows)
        s.advance_time(60)
        self.assertEqual(passive, set(self.life.mobs))
        exit_portal = next(iter(s.world.portals.values()))
        s.player.place(s.world.surface_position(exit_portal.approach))
        s.player.facing = exit_portal.position-exit_portal.approach
        s.interact()
        s.advance_time(.01)
        self.assertEqual(2, sum(m.kind is MobKind.SKELETON for m in self.life.mobs.values()))

    def test_skeleton_fires_dodgeable_arrow_and_player_recovers_after_defeat(self):
        s = self.session
        s.advance_time(60)
        archer = next(m for m in self.life.mobs.values() if m.kind is MobKind.SKELETON)
        self.life.mobs = {archer.id: archer}
        from spawnbound.domain.model import TileKind
        start = s.player.position
        for x in range(5):
            p = start + GridPos(x, 0)
            s.world.tile_map.add(p, TileKind.GRASS, elevation=s.player.elevation)
            s.world.objects.pop(p, None)
        archer.start = archer.end = s.world.surface_position(start+GridPos(4, 0))
        archer.wait = archer.shoot_in = 0
        self.state.step(InputFrame(), .01)
        self.assertEqual(1, len(self.life.arrows))
        self.assertGreater(archer.shot_time, 0.)
        self.assertEqual(s.config.starting_hearts, s.player.hearts)
        s.player.place(s.world.surface_position(start+GridPos(0, 2)))
        self.life.tick(1, s.player.position3d)
        self.assertFalse(self.life.arrows)
        self.assertEqual(0, self.life.grace)
        s.player.hearts = 1
        self.life.arrows.append(Arrow(s.player.position3d, s.player.position3d, .2))
        self.state.step(InputFrame(), .02)
        self.assertEqual(s.world.spawn, s.player.position)
        self.assertGreater(s.hurt_time, 0.)
        self.assertEqual(s.config.starting_hearts, s.player.hearts)
        self.assertEqual(self.state.visual_position, (s.world.spawn.x, s.world.spawn.y))

    def test_pause_freezes_hostile_population_and_projectiles(self):
        s = self.session
        s.advance_time(89)
        stack = StateStack(self.state)
        stack.step(InputFrame(pause_pressed=True), 0)
        count = len(self.life.mobs)
        stack.step(InputFrame(), 3)
        self.assertEqual(count, len(self.life.mobs))
        self.assertEqual(89, s.cycle_seconds)
        stack.step(InputFrame(pause_pressed=True), 0)
        stack.step(InputFrame(), 1)
        self.assertFalse(any(m.kind is MobKind.SKELETON for m in self.life.mobs.values()))


class IslandWildlifeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.session = GameSession.create(1234, DEFAULT_CONFIG, chunk_preview_size=128)
        cls.state = GameplayState(cls.session, DEFAULT_CONFIG)

    def setUp(self):
        self.life = Wildlife(self.session.world)
        self.life.in_view = self.state._in_camera_view
        self.player = self.session.world.surface_position(self.session.world.spawn)

    def animals(self):
        return [m for m in self.life.mobs.values() if m.kind in HERD_KINDS]

    def test_herds_cover_the_island_and_wait_near_the_start(self):
        animals = self.animals()
        self.assertGreaterEqual(len(animals), 30)
        self.assertEqual({MobKind.CHICKEN, MobKind.PIG}, {m.kind for m in animals})
        spawn = self.session.world.spawn
        nearby = {m.kind for m in animals if chebyshev(m.end, spawn) <= 12}
        self.assertEqual({MobKind.CHICKEN, MobKind.PIG}, nearby)
        homes = {m.home for m in animals if chebyshev(m.home, spawn) >= 12}
        for a in homes:
            for b in homes - {a}:
                self.assertGreaterEqual(chebyshev(a, b), HERD_SPACING)
        sites = self.life._sites[::97]
        near = sum(any(chebyshev(m.end, p) <= 20 for m in animals) for p in sites)
        self.assertGreater(near / len(sites), .8)

    def test_herds_stay_home_and_persist_through_day_and_night(self):
        herd = min(self.animals(), key=lambda m: chebyshev(m.end, self.player))
        before = set(self.life.mobs)
        self.life.start_night(self.player)
        for _ in range(3000):
            self.life.tick(.1, self.player)
        self.life.dawn()
        self.assertTrue(before <= set(self.life.mobs))
        self.assertFalse(any(m.kind is MobKind.SKELETON for m in self.life.mobs.values()))
        for mob in self.animals():
            self.assertLessEqual(chebyshev(mob.end, mob.home), HOME_RADIUS)
        self.assertLessEqual(chebyshev(herd.end, herd.home), HOME_RADIUS)

    def test_far_creatures_stand_still(self):
        far = [m for m in self.animals() if chebyshev(m.end, self.player) > ACTIVE_RADIUS + 2]
        self.assertTrue(far)
        places = {m.id: m.end for m in far}
        for _ in range(100):
            self.life.tick(.1, self.player)
        self.assertEqual(places, {m.id: m.end for m in far})

    def test_archers_appear_out_of_view_and_leave_when_far(self):
        self.life.start_night(self.player)
        archers = [m for m in self.life.mobs.values() if m.kind is MobKind.SKELETON]
        self.assertEqual(2, len(archers))
        for archer in archers:
            self.assertFalse(self.state._in_camera_view(self.player, archer.end))
            self.assertLessEqual(chebyshev(archer.end, self.player), 30)
        world = self.session.world
        far_cell = max((p for p in world.tile_map.tiles if world.is_walkable(p)),
                       key=lambda p: (min(chebyshev(a.end, world.surface_position(p)) for a in archers), p))
        far_away = world.surface_position(far_cell)
        self.assertGreater(min(chebyshev(a.end, far_away) for a in archers), DESPAWN_RADIUS)
        self.life.tick(ARCHER_SECONDS, far_away)
        self.assertEqual(1, self.life.archer_count)
        newcomer = next(m for m in self.life.mobs.values() if m.kind is MobKind.SKELETON)
        self.assertLessEqual(chebyshev(newcomer.end, far_away), 30)

    def test_hunted_herds_come_back_out_of_view(self):
        target = self.life.target_animals
        hunted = sorted(self.animals(), key=lambda m: chebyshev(m.end, self.player))[:10]
        for mob in hunted:
            del self.life.mobs[mob.id]
        before = set(self.life.mobs)
        for _ in range(8):
            self.life.tick(REPLENISH_SECONDS, self.player)
        born = [self.life.mobs[i] for i in set(self.life.mobs) - before]
        self.assertTrue(born)
        self.assertLessEqual(self.life.animal_count, target + 1)
        self.assertGreaterEqual(self.life.animal_count, target - 1)
        for mob in born:
            self.assertFalse(self.state._in_camera_view(self.player, self.session.world.surface_position(mob.home)))
