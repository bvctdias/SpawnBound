import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "dependencias")]
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame

from spawnbound import sea_chart
from spawnbound.config import DEFAULT_CONFIG
from spawnbound.dock_art import STRIPE, dock_sprite
from spawnbound.domain.archipelago import (HOME_ID, ISLANDS, OTHER_SIZE, IslandSpec, archipelago, build_island,
                                           dock_axis, dock_front, dock_landing, dock_restored)
from spawnbound.domain.coordinates import NEIGHBOR_DIRECTIONS, GridPos, WorldPos
from spawnbound.domain.crafting import DOCK_REPAIR
from spawnbound.domain.generation import WorldGenerator
from spawnbound.domain.model import ObjectKind, SpaceKind, TileKind
from spawnbound.domain.session import ActionCode, GameSession
from spawnbound.domain.terrain import reachable_surface
from spawnbound.input import InputFrame
from spawnbound.renderer import PlaceholderRenderer
from spawnbound.states import GameplayState
from spawnbound.view import SceneItem, camera_origin, object_contains, pick_world_point, scene_depth_key, screen_center

DAY, AFTERNOON, NIGHT = DEFAULT_CONFIG.phase_durations


def new_session(seed=1234):
    session = GameSession.create(seed, DEFAULT_CONFIG, chunk_preview_size=128)
    session.wildlife.mobs.clear()
    return session


def stand_at_dock(session):
    world = session.world
    landing = dock_landing(world)
    session.player.place(world.surface_position(landing))
    session.player.facing = world.dock - landing
    return world.objects[world.dock]


def repair_dock(session):
    stand_at_dock(session)
    session.player.inventory.add("wood", DOCK_REPAIR["wood"])
    session.player.inventory.add("stone", DOCK_REPAIR["stone"])
    return session.interact()


def finish_voyage(session):
    changed = False
    while session.voyage is not None:
        changed = session.update_mobs(.1) or changed
    return changed


def sail_to_second_island(session):
    repair_dock(session)
    session.sail_to("ilha-2")
    finish_voyage(session)
    return session.world


def beside(world, target, reach_from=None):
    for direction in NEIGHBOR_DIRECTIONS:
        cell = target - direction
        if (world.is_walkable(cell) and cell not in world.objects and cell not in world.portals
                and world.can_reach(cell, target, DEFAULT_CONFIG.max_step_height)):
            return cell, direction
    raise AssertionError(f"nowhere to stand by {target}")


def is_sea(world, cell):
    tile = world.tile_map.tile_at(cell)
    return tile is not None and tile.kind is TileKind.WATER


class ArchipelagoTests(unittest.TestCase):
    def test_the_same_seed_gives_the_same_islands(self):
        islands = archipelago(1234, 128)
        self.assertEqual(islands, archipelago(1234, 128))
        self.assertEqual(ISLANDS, len(islands))
        home, *others = islands
        self.assertTrue(home.home)
        self.assertEqual((HOME_ID, 1234, 128), (home.space_id, home.seed, home.size))
        for index, spec in enumerate(others, 2):
            self.assertEqual(f"ilha-{index}", spec.space_id)
            self.assertEqual(OTHER_SIZE, spec.size)
            self.assertNotEqual(1234, spec.seed)
            self.assertTrue(0 <= spec.bearing < 360)
            self.assertFalse(spec.home)
        self.assertEqual(len(islands), len({spec.name for spec in islands}))
        self.assertNotEqual(archipelago(7, 128)[1].seed, others[0].seed)


class DockPlacementTests(unittest.TestCase):
    SEEDS = (1234, 7, 39658298)

    @classmethod
    def setUpClass(cls):
        cls.homes = {seed: WorldGenerator().generate_chunk_preview(seed, 128) for seed in cls.SEEDS}
        cls.spec = archipelago(1234, 128)[1]
        cls.other = build_island(cls.spec)

    def test_the_players_island_has_a_ruined_dock_on_its_coast(self):
        for seed, world in self.homes.items():
            with self.subTest(seed=seed):
                self.assertIsNotNone(world.dock)
                dock = world.objects[world.dock]
                self.assertIs(ObjectKind.DOCK, dock.kind)
                self.assertFalse(dock_restored(dock))
                step = dock_axis(dock)
                self.assertTrue(is_sea(world, world.dock + step) and is_sea(world, world.dock + step + step))
                across = GridPos(step.y, step.x)
                self.assertTrue(is_sea(world, world.dock + step + across)
                                and is_sea(world, world.dock + step + step + across))
                landing = dock_landing(world)
                self.assertIn(landing, reachable_surface(world))
                self.assertTrue(world.home_island)

    def test_small_islands_have_no_dock_and_no_voyages(self):
        session = GameSession.create(1234, DEFAULT_CONFIG, chunk_preview_size=48)
        self.assertIsNone(session.world.dock)
        self.assertEqual((), session.islands)
        self.assertIsNone(session.island)

    def test_the_second_island_has_its_mine_and_stone_but_no_base(self):
        world = self.other
        self.assertEqual(("ilha-2", OTHER_SIZE, False), (world.space_id, world.chunk_preview_size, world.home_island))
        self.assertIsNone(world.camp)
        kinds = [portal.target_kind for portal in world.portals.values()]
        self.assertEqual([SpaceKind.CAVE], kinds)
        self.assertFalse(any(obj.kind is ObjectKind.WINDMILL for obj in world.objects.values()))
        self.assertEqual(1, len(world.waystones))
        self.assertFalse(world.objects[world.waystones[0]].available)
        self.assertTrue(dock_restored(world.objects[world.dock]))
        again = build_island(self.spec)
        self.assertEqual((world.dock, world.waystones, set(world.portals)), (again.dock, again.waystones, set(again.portals)))


class VoyageTests(unittest.TestCase):
    def setUp(self):
        self.session = new_session()

    def test_the_dock_is_repaired_with_wood_and_stone(self):
        session = self.session
        dock = stand_at_dock(session)
        result = session.interact()
        self.assertIs(ActionCode.MISSING_MATERIALS, result.code)
        self.assertIn(f"Madeira 0/{DOCK_REPAIR['wood']}", session.last_message)
        self.assertIn("consertar o cais", session.primary_action(dock.position).message)
        self.assertIs(ActionCode.DOCK_REPAIRED, repair_dock(session).code)
        self.assertTrue(dock_restored(dock))
        self.assertEqual(0, session.player.inventory.quantity("wood"))
        self.assertIs(ActionCode.DOCK_OPENED, session.interact().code)
        self.assertTrue(session.at_dock())

    def test_sailing_starts_only_from_a_restored_dock(self):
        session = self.session
        self.assertIs(ActionCode.TARGET_OUT_OF_RANGE, session.sail_to("ilha-2").code)
        stand_at_dock(session)
        self.assertFalse(session.sail_to("ilha-2").success)
        repair_dock(session)
        self.assertIs(ActionCode.BLOCKED, session.sail_to("ilha-9").code)
        self.assertIs(ActionCode.NOTHING_HERE, session.sail_to(HOME_ID).code)
        self.assertIsNone(session.voyage)

    def test_a_voyage_loads_the_island_and_lands_the_player_at_its_dock(self):
        session = self.session
        home, home_life, home_survey = session.world, session.wildlife, session.survey
        repair_dock(session)
        self.assertIs(ActionCode.VOYAGE_STARTED, session.sail_to("ilha-2").code)
        self.assertIs(home, session.world)
        self.assertTrue(finish_voyage(session))
        world = session.world
        self.assertEqual("ilha-2", world.space_id)
        self.assertEqual(dock_landing(world), session.player.position)
        self.assertEqual("ilha-2", session.island.space_id)
        self.assertIn("ilha-2", session.visited)
        self.assertIsNot(home_life, session.wildlife)
        self.assertIs(world, session.wildlife.world)
        self.assertIs(session.wildlife, session.island_life)
        self.assertIsNot(home_survey, session.survey)
        self.assertEqual("ilha-2", session.survey.space_id)
        self.assertGreater(session.revive_time, 0)
        self.assertIn("chegou", session.last_message)
        stand_at_dock(session)
        self.assertTrue(session.sail_to(HOME_ID).success)
        finish_voyage(session)
        self.assertIs(home, session.world)
        self.assertIs(home_life, session.wildlife)
        self.assertTrue(dock_restored(home.objects[home.dock]))

    def test_the_waystones_join_the_islands(self):
        session = self.session
        world = sail_to_second_island(session)
        stone = world.waystones[0]
        cell, direction = beside(world, stone)
        session.player.place(world.surface_position(cell))
        session.player.facing = direction
        self.assertIs(ActionCode.WAYSTONE_ACTIVATED, session.interact().code)
        self.assertIs(ActionCode.WAYSTONE_TRAVEL, session.interact().code)
        self.assertEqual(HOME_ID, session.voyage.island.space_id)
        finish_voyage(session)
        self.assertIs(session.home_world, session.world)
        player = session.player
        self.assertIn(player.position + player.facing, session.world.waystones)
        self.assertIs(ActionCode.WAYSTONE_TRAVEL, session.interact().code)
        finish_voyage(session)
        self.assertIs(world, session.world)
        self.assertEqual(stone, session.player.position + session.player.facing)

    def test_falling_on_another_island_wakes_the_player_at_home(self):
        session = self.session
        sail_to_second_island(session)
        session.drag_time = .05
        self.assertTrue(session.update_mobs(.1))
        self.assertIs(session.home_world, session.world)
        self.assertEqual(session.world.spawn, session.player.position)
        self.assertIs(session.island_lives[HOME_ID], session.wildlife)

    def test_each_island_has_its_own_mine(self):
        session = self.session
        home_mine = next(p for p in session.world.portals.values() if p.target_kind is SpaceKind.CAVE)
        world = sail_to_second_island(session)
        entrance = next(p for p in world.portals.values() if p.target_kind is SpaceKind.CAVE)
        self.assertNotEqual(home_mine.target_space_id, entrance.target_space_id)
        session.player.place(world.surface_position(entrance.approach))
        session.player.facing = entrance.position - entrance.approach
        self.assertIs(ActionCode.SPACE_CHANGED, session.interact().code)
        self.assertIs(SpaceKind.CAVE, session.world.space_kind)
        self.assertEqual("ilha-2", session.island.space_id)
        exit_portal = next(iter(session.world.portals.values()))
        session.player.place(session.world.surface_position(exit_portal.approach))
        session.player.facing = exit_portal.position - exit_portal.approach
        session.interact()
        self.assertIs(world, session.world)

    def test_night_falls_on_the_island_the_player_is_on_and_dawn_on_all(self):
        session = self.session
        sail_to_second_island(session)
        here, home = session.island_life, session.island_lives[HOME_ID]
        session.cycle_seconds = DAY + AFTERNOON + .5
        session.advance_time(.1)
        self.assertTrue(here.night_spawned)
        self.assertFalse(home.night_spawned)
        home.night_spawned = True
        session.advance_time(NIGHT)
        self.assertFalse(here.night_spawned or home.night_spawned)


class SailingStateTests(unittest.TestCase):
    def test_the_chart_opens_at_the_dock_and_a_click_sets_sail(self):
        session = new_session()
        repair_dock(session)
        state = GameplayState(session, DEFAULT_CONFIG)
        state.step(InputFrame(interact_pressed=True), 0)
        self.assertTrue(state.chart_open)
        state.step(InputFrame(pause_pressed=True), 0)
        self.assertFalse(state.chart_open)
        state.step(InputFrame(interact_pressed=True), 0)
        panel, entries = sea_chart.layout(DEFAULT_CONFIG, session.islands)
        state.step(InputFrame(destination_click=(panel.left + 4, panel.top + 4)), 0)
        self.assertTrue(state.chart_open)
        self.assertIsNone(session.voyage)
        state.step(InputFrame(destination_click=entries["ilha-2"].center), 0)
        self.assertFalse(state.chart_open)
        self.assertIsNotNone(session.voyage)
        state.step(InputFrame(interact_pressed=True, inventory_pressed=True), .1)
        self.assertFalse(state.chart_open or state.inventory_open)
        while session.voyage is not None:
            state.step(InputFrame(), .1)
        self.assertEqual("ilha-2", session.world.space_id)
        p = session.player.position
        self.assertEqual((p.x, p.y), state._visual_position[:2])
        renderer = PlaceholderRenderer(pygame.Surface((960, 540)), DEFAULT_CONFIG)
        session.sail_to(HOME_ID)
        state.draw(renderer)
        state.step(InputFrame(), 0)

    def test_a_click_on_the_pier_over_the_sea_picks_the_dock(self):
        session = new_session()
        dock = stand_at_dock(session)
        origin = camera_origin(session, DEFAULT_CONFIG, session.player.position3d)
        foot = screen_center(dock.position3d, origin, DEFAULT_CONFIG)
        here = dock.position3d
        unit = screen_center(WorldPos(here.x + 1, here.y, here.z), origin, DEFAULT_CONFIG)[0] - foot[0]
        step = dock_axis(dock)
        along = (16 if step.x else -16, 8)
        point = (foot[0] + along[0] * 1.6 * unit / 16, foot[1] + (along[1] * 1.6 - 2) * unit / 16)
        hit = pick_world_point(session, point, origin, DEFAULT_CONFIG)
        self.assertEqual((dock.position, "object"), (hit.position, hit.kind))


class DockArtTests(unittest.TestCase):
    def test_four_looks_along_both_axes(self):
        for variant in ("restored-x", "ruined-x", "restored-y", "ruined-y"):
            with self.subTest(variant=variant):
                image, (fx, fy) = dock_sprite(variant, 1)
                self.assertTrue(image.get_rect().collidepoint(fx, fy))
                self.assertGreater(image.get_width(), 40)
                colours = {image.get_at((x, y))[:3] for x in range(image.get_width())
                           for y in range(image.get_height()) if image.get_at((x, y)).a}
                self.assertEqual(variant.startswith("restored"), STRIPE in colours)
                box = image.get_bounding_rect()
                out = box.right - fx if variant.endswith("x") else fx - box.left
                self.assertGreater(out, 36)
        big, foot = dock_sprite("restored-x", 1, 2.0)
        self.assertEqual(dock_sprite("restored-x", 1)[0].get_width() * 2, big.get_width())

    def test_the_renderer_draws_the_dock_by_code_and_sorts_it_after_the_sea(self):
        from spawnbound.prototype_art import PrototypeArtRenderer
        pygame.font.init()
        world = WorldGenerator().generate_chunk_preview(1234, 128)
        dock = world.objects[world.dock]
        art = PrototypeArtRenderer(pygame.Surface((960, 540)), DEFAULT_CONFIG, ROOT / "assets/native_32/manifest.json")
        self.assertEqual("dock", art.object_name(dock))
        self.assertNotIn("dock", art.art.images)
        plain = PlaceholderRenderer(pygame.Surface((960, 540)), DEFAULT_CONFIG)
        sprite, (fx, fy) = dock_sprite(dock.variant, dock.elevation)
        body, foot = plain._caster_image("object", dock)
        region = pygame.Rect(foot[0] - fx, foot[1] - fy, *sprite.get_size())
        self.assertEqual(pygame.image.tobytes(sprite, "RGBA"), pygame.image.tobytes(body.subsurface(region), "RGBA"))
        step = dock_axis(dock)
        across = GridPos(step.y, step.x)
        key = scene_depth_key(SceneItem("object", dock.position, dock))
        for cell in (dock.position + step, dock.position + step + step, dock.position + step + across,
                     dock.position + step + step + across):
            tile = world.tile_map.tile_at(cell)
            self.assertLess(scene_depth_key(SceneItem("tile", cell, tile)), key)
        self.assertEqual(dock_front(dock), dock.position + step + step + across)
        self.assertTrue(object_contains(dock, (16 if step.x else -16) * 1.6, 8 * 1.6 - 2))
        self.assertFalse(object_contains(dock, 0, -30))


class SeaChartTests(unittest.TestCase):
    def test_the_islands_lie_apart_inside_the_chart_and_answer_clicks(self):
        islands = archipelago(1234, 128)
        panel, entries = sea_chart.layout(DEFAULT_CONFIG, islands)
        rects = list(entries.values())
        self.assertEqual(len(islands), len(rects))
        for i, rect in enumerate(rects):
            self.assertTrue(panel.contains(rect))
            self.assertFalse(any(rect.colliderect(other) for other in rects[i + 1:]))
        for space_id, rect in entries.items():
            self.assertEqual(space_id, sea_chart.island_at(DEFAULT_CONFIG, islands, rect.center))
        self.assertIsNone(sea_chart.island_at(DEFAULT_CONFIG, islands, None))
        self.assertIsNone(sea_chart.island_at(DEFAULT_CONFIG, islands, (panel.left + 2, panel.top + 2)))
        home = islands[0]
        for bearing in range(0, 360, 5):
            other = IslandSpec("ilha-2", "Ilha Verde", 1, OTHER_SIZE, float(bearing))
            panel, entries = sea_chart.layout(DEFAULT_CONFIG, (home, other))
            with self.subTest(bearing=bearing):
                self.assertTrue(panel.contains(entries[HOME_ID]) and panel.contains(entries["ilha-2"]))
                self.assertFalse(entries[HOME_ID].colliderect(entries["ilha-2"]))

    def test_a_visited_island_shows_its_outline_and_the_chart_draws(self):
        pygame.font.init()
        session = new_session()
        image = sea_chart.outline(session.world)
        self.assertGreater(image.get_bounding_rect().width, 90)
        self.assertGreater(image.get_width(), image.get_height())
        renderer = PlaceholderRenderer(pygame.Surface((960, 540)), DEFAULT_CONFIG)
        renderer.draw_gameplay(session, debug=False, chart_view=(None,))
        renderer.draw_gameplay(session, debug=False, chart_view=("ilha-2",))


if __name__ == "__main__":
    unittest.main()
