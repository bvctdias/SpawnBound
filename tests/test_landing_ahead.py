import os
import shutil
import sys
import tempfile
import time
import unittest
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import pygame

from spawnbound import menus
from spawnbound.config import DEFAULT_CONFIG
from spawnbound.domain.archipelago import dock_landing
from spawnbound.domain.model import ObjectKind, SpaceKind
from spawnbound.domain.session import GameSession, Voyage
from spawnbound.input import InputFrame
from spawnbound.renderer import PlaceholderRenderer
from spawnbound.states import LANDING_WAIT, GameplayState, TransitionKind

pygame.init()
SIZE = 48
DOCKS = 64


def session_of(size=SIZE, seed=1234):
    session = GameSession.create(seed, DEFAULT_CONFIG, chunk_preview_size=size)
    session.wildlife.mobs.clear()
    session.spaces.prepare(session.world)
    return session


def renderer_ahead():
    renderer = PlaceholderRenderer(pygame.Surface((960, 540)), DEFAULT_CONFIG)
    renderer.PREFETCH_BUDGET = 1.
    return renderer


def count_drawn_on_the_spot(renderer):
    drawn = []
    plain = renderer._render_chunk

    def counted(session, key, background):
        drawn.append(key)
        return plain(session, key, background)

    renderer._render_chunk = counted
    return drawn


def door(session, kind):
    return next(p for p in session.world.portals.values() if p.target_kind is kind)


def stand_at_door_and_enter(state, renderer, kind, frames=3):
    session = state.session
    portal = door(session, kind)
    session.player.place(session.world.surface_position(portal.position))
    state._sync_space()
    for _ in range(frames):
        state.step(InputFrame(), 1 / 60)
        state.draw(renderer)
    state.step(InputFrame(interact_pressed=True), 1 / 60)


def differs(a: pygame.Surface, b: pygame.Surface) -> float:
    small = [pygame.transform.smoothscale(s, (160, 90)) for s in (a, b)]
    return sum(1 for x in range(160) for y in range(90)
               if sum(abs(p - q) for p, q in zip(small[0].get_at((x, y))[:3], small[1].get_at((x, y))[:3])) > 60
               ) / (160 * 90)


class SpacesBehindTests(unittest.TestCase):
    def test_the_mine_is_made_with_its_island_as_its_door_would_make_it(self):
        early = GameSession.create(1234, DEFAULT_CONFIG, chunk_preview_size=SIZE)
        late = GameSession.create(1234, DEFAULT_CONFIG, chunk_preview_size=SIZE)
        entrance = door(early, SpaceKind.CAVE)
        behind = early.spaces.build_behind(early.world)
        self.assertNotIn(entrance.target_space_id, early.spaces.worlds)
        self.assertEqual({entrance.target_space_id, door(early, SpaceKind.INTERIOR).target_space_id},
                         {world.space_id for world in behind})
        early.spaces.prepare(early.world)
        kept = early.spaces.worlds[entrance.target_space_id]
        made, _ = late.spaces.resolve(late.world, door(late, SpaceKind.CAVE))
        self.assertEqual(made.space_id, kept.space_id)
        self.assertEqual(dict(made.tile_map.tiles), dict(kept.tile_map.tiles))
        self.assertEqual({p: (o.kind, o.variant) for p, o in made.objects.items()},
                         {p: (o.kind, o.variant) for p, o in kept.objects.items()})
        count = len(early.spaces.worlds)
        entered, _ = early.spaces.resolve(early.world, entrance)
        self.assertIs(kept, entered)
        self.assertEqual(count, len(early.spaces.worlds))

    def test_a_new_game_and_a_loaded_one_come_with_their_mines(self):
        session = GameSession.create(1234, DEFAULT_CONFIG, chunk_preview_size=SIZE)
        menus.prepare_session(session)
        self.assertIn(door(session, SpaceKind.CAVE).target_space_id, session.spaces.worlds)
        self.assertIn(session.world.space_id, session._navigation)


class KeptWorldsTests(unittest.TestCase):
    def test_the_mine_drawn_ahead_from_its_door_opens_without_drawing(self):
        session = session_of()
        renderer = renderer_ahead()
        state = GameplayState(session, DEFAULT_CONFIG)
        drawn = count_drawn_on_the_spot(renderer)
        stand_at_door_and_enter(state, renderer, SpaceKind.CAVE)
        self.assertIs(SpaceKind.CAVE, session.world.space_kind)
        drawn.clear()
        state.draw(renderer)
        self.assertEqual([], drawn)
        fresh = PlaceholderRenderer(pygame.Surface((960, 540)), DEFAULT_CONFIG)
        state.draw(fresh)
        self.assertLess(differs(renderer._world_screen, fresh._world_screen), .02)

    def test_going_back_out_keeps_the_island_view_and_draws_it_as_new(self):
        session = session_of()
        renderer = renderer_ahead()
        state = GameplayState(session, DEFAULT_CONFIG)
        drawn = count_drawn_on_the_spot(renderer)
        stand_at_door_and_enter(state, renderer, SpaceKind.CAVE)
        stand_at_door_and_enter(state, renderer, SpaceKind.OUTDOOR)
        self.assertIs(SpaceKind.OUTDOOR, session.world.space_kind)
        drawn.clear()
        state.draw(renderer)
        self.assertEqual([], drawn)
        fresh = PlaceholderRenderer(pygame.Surface((960, 540)), DEFAULT_CONFIG)
        state.draw(fresh)
        self.assertLess(differs(renderer._world_screen, fresh._world_screen), .02)

    def test_a_tree_cut_while_away_is_gone_on_coming_back(self):
        session = session_of()
        renderer = renderer_ahead()
        state = GameplayState(session, DEFAULT_CONFIG)
        island = session.world
        stand_at_door_and_enter(state, renderer, SpaceKind.CAVE)
        here = door(session, SpaceKind.OUTDOOR).arrival or island.spawn
        tree = min((o for o in island.objects.values() if o.kind is ObjectKind.TREE),
                   key=lambda o: abs(o.position.x - here.x) + abs(o.position.y - here.y))
        island.remove_object(tree.position)
        stand_at_door_and_enter(state, renderer, SpaceKind.OUTDOOR)
        state.draw(renderer)
        fresh = PlaceholderRenderer(pygame.Surface((960, 540)), DEFAULT_CONFIG)
        state.draw(fresh)
        self.assertLess(differs(renderer._world_screen, fresh._world_screen), .02)

    def test_a_change_where_the_player_is_leaves_the_block_drawn_elsewhere_alone(self):
        session = session_of()
        renderer = PlaceholderRenderer(pygame.Surface((960, 540)), DEFAULT_CONFIG)
        renderer.draw_gameplay(session, debug=False)
        cave = session.spaces.worlds[door(session, SpaceKind.CAVE).target_space_id]
        renderer.PREFETCH_BUDGET = .0005
        renderer.last_prefetch_seconds = 0.
        renderer.prepare_arrival(session, cave, cave.spawn)
        kept = renderer._kept_worlds[id(cave)][1]
        generation, job = kept["_static_generation"], kept["_block_job"]
        self.assertIsNotNone(job)
        tree = next(o for o in session.world.objects.values() if o.kind is ObjectKind.TREE)
        session.world.remove_object(tree.position)
        renderer.draw_gameplay(session, debug=False)
        self.assertEqual(generation, renderer._kept_worlds[id(cave)][1]["_static_generation"])
        renderer.last_prefetch_seconds = 0.
        renderer.prepare_arrival(session, cave, cave.spawn)
        self.assertIs(job[1], renderer._kept_worlds[id(cave)][1]["_block_job"][1])

    def test_only_the_last_worlds_left_are_kept(self):
        renderer = PlaceholderRenderer(pygame.Surface((960, 540)), DEFAULT_CONFIG)
        sessions = [session_of(32, seed) for seed in range(renderer.KEPT_WORLDS + 2)]
        for session in sessions:
            renderer.draw_gameplay(session, debug=False)
        self.assertEqual(renderer.KEPT_WORLDS, len(renderer._kept_worlds))
        self.assertEqual([id(s.world) for s in sessions[-renderer.KEPT_WORLDS - 1:-1]], list(renderer._kept_worlds))


class StubRenderer:
    def __init__(self, ready_after=None):
        self.ready_after, self.asked = ready_after, 0

    def draw_gameplay(self, session, **kwargs):
        pass

    def prepare_arrival(self, session, world, position, *, veiled=False):
        self.asked += 1
        return self.ready_after is not None and self.asked > self.ready_after


def sail(session):
    world = session.world
    session.player.place(world.surface_position(dock_landing(world)))
    dock = world.objects[world.dock]
    dock.variant = dock.variant.replace("ruined", "restored")
    target = next(spec.space_id for spec in session.islands if spec.space_id != world.space_id)
    return session.sail_to(target).success


class CrossingTests(unittest.TestCase):
    def test_a_voyage_waits_for_its_landing(self):
        voyage = Voyage(island=None, remaining=0.)
        self.assertTrue(voyage.built and voyage.ready)
        voyage.landing_ready = False
        self.assertTrue(voyage.built)
        self.assertFalse(voyage.ready)

    def cross(self, renderer, limit=30.):
        session = session_of(DOCKS)
        state = GameplayState(session, DEFAULT_CONFIG)
        self.assertTrue(sail(session))
        played, built_at, start = 0., None, time.perf_counter()
        while session.voyage is not None and time.perf_counter() - start < limit:
            if built_at is None and session.voyage.built:
                built_at = played
            if not session.voyage.built:
                time.sleep(.002)
            state.step(InputFrame(), 1 / 60)
            state.draw(renderer)
            played += 1 / 60
        self.assertIsNone(session.voyage)
        return session, played - (built_at or 0.)

    def test_the_boat_lands_only_once_the_view_is_drawn(self):
        renderer = StubRenderer(ready_after=40)
        session, _ = self.cross(renderer)
        self.assertGreater(renderer.asked, 40)
        self.assertIsNot(session.home_world, session.world)
        self.assertTrue(any(world.space_kind is SpaceKind.CAVE and world.space_id.startswith(session.world.space_id)
                            for world in session.spaces.worlds.values()))

    def test_the_boat_lands_anyway_after_a_while(self):
        _, waited = self.cross(StubRenderer(ready_after=None))
        self.assertGreater(waited, LANDING_WAIT - .1)
        self.assertLess(waited, LANDING_WAIT + .5)

    def test_the_landing_view_is_drawn_under_the_veil(self):
        renderer = renderer_ahead()
        drawn = count_drawn_on_the_spot(renderer)
        session = session_of(DOCKS)
        state = GameplayState(session, DEFAULT_CONFIG)
        state.draw(renderer)
        self.assertTrue(sail(session))
        while True:
            if not session.voyage.built:
                time.sleep(.002)
            state.step(InputFrame(), 1 / 60)
            if session.voyage is None:
                break
            state.draw(renderer)
        drawn.clear()
        state.draw(renderer)
        self.assertEqual([], drawn)


class MenuSceneLater:
    ready, session, elapsed, veil, cover, clock = False, None, 0., 1., 0., 0.
    view_ready = None

    def __init__(self, built):
        self.built = built

    def backdrop(self, renderer):
        return None

    def capture(self):
        return None

    def update(self, seconds):
        self.elapsed += seconds

    def camera_over(self, world):
        return world.surface_position(world.camp or world.spawn)


class MenuAheadTests(unittest.TestCase):
    def setUp(self):
        self.folder = Path(tempfile.mkdtemp(prefix="spawnbound-saves-"))
        self.addCleanup(shutil.rmtree, self.folder, ignore_errors=True)

    def test_a_new_game_starts_once_its_first_view_is_drawn(self):
        scene = MenuSceneLater(session_of(32))
        menu = menus.MainMenuState(DEFAULT_CONFIG, scene, island_size=32, folder=self.folder)
        renderer = StubRenderer(ready_after=None)
        renderer.draw_menu = lambda *args, **kwargs: None
        menu.seed_text = "7"
        menu._start_new_game()
        menu.draw(renderer)
        self.assertFalse(menu._view_ready)
        for _ in range(600):
            if menu._builder is None or not menu._builder.is_alive():
                break
            time.sleep(.01)
        for _ in range(5):
            self.assertIs(TransitionKind.NONE, menu.step(InputFrame(), 1 / 60).kind)
            menu.draw(renderer)
        self.assertFalse(scene.view_ready)
        renderer.ready_after = 0
        menu.draw(renderer)
        transition = menu.step(InputFrame(), 1 / 60)
        self.assertIs(TransitionKind.START, transition.kind)
        self.assertEqual(7, transition.session.home_world.seed)

    def test_the_menu_island_fades_in_again_after_a_game(self):
        scene = menus.MenuScene(DEFAULT_CONFIG, size=32)
        scene._thread.join()
        scene.update(.1)
        self.assertTrue(scene.ready)
        shown = scene.session
        scene.update(5.)
        scene.hide()
        self.assertFalse(scene.ready)
        self.assertIs(shown, scene.built)
        self.assertEqual(menus.SCENE_START, shown.cycle_seconds)
        scene.update(.1)
        self.assertFalse(scene.ready)
        scene.view_ready = True
        scene.update(.1)
        self.assertTrue(scene.ready)
        self.assertEqual(1., scene.veil)


if __name__ == "__main__":
    unittest.main()
