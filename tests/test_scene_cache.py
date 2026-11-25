import dataclasses
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import pygame
from spawnbound.config import GameConfig
from spawnbound.domain.model import ObjectKind
from spawnbound.domain.navigation import find_path
from spawnbound.domain.session import GameSession
from spawnbound.input import InputFrame
from spawnbound.renderer import BACKGROUND, PlaceholderRenderer
from spawnbound.states import GameplayState
from spawnbound.view import scene_items

BORDER = 96


def _interior(surface: pygame.Surface) -> bytes:
    w, h = surface.get_size()
    return pygame.image.tobytes(surface.subsurface((BORDER, BORDER, w - 2 * BORDER, h - 2 * BORDER)), "RGB")


class SceneCacheTests(unittest.TestCase):
    def test_daylight_transitions_and_harvest_keep_all_shadow_caches_current(self):
        pygame.font.init()
        cfg = GameConfig()
        session = GameSession.create(7, cfg, chunk_preview_size=32)
        cached = PlaceholderRenderer(pygame.Surface((960, 540)), cfg)
        session.last_message = "Destino"
        hud = None
        for t in (0, 27, 30, 57, 60, 87, 90, 120):
            session.advance_time((t - session.cycle_seconds) % 90)
            if t == 60:
                tree = min((o for o in session.world.objects.values() if o.kind is ObjectKind.TREE),
                           key=lambda o: abs(o.position.x - session.player.position.x)
                           + abs(o.position.y - session.player.position.y))
                session.world.remove_object(tree.position)
            cached.draw_gameplay(session, debug=False)
            fresh = PlaceholderRenderer(pygame.Surface((960, 540)), cfg)
            fresh.draw_gameplay(session, debug=False)
            self.assertEqual(_interior(fresh._world_screen), _interior(cached._world_screen), t)
            current_hud = pygame.image.tobytes(cached._ui_screen, "RGBA")
            if hud is None:
                hud = current_hud
            self.assertEqual(hud, current_hud, t)

    def test_cached_frames_match_direct_frames_while_walking_and_harvesting(self):
        pygame.font.init()
        for seed in (1234, 0):
            with self.subTest(seed=seed):
                self._walk_and_compare(seed)

    def _walk_and_compare(self, seed):
        cached_config = GameConfig(camera_zoom=1)
        direct_config = dataclasses.replace(cached_config, scene_cache=False)
        session = GameSession.create(seed, cached_config, chunk_preview_size=128)
        session.player.position = session.world.spawn
        goal, path = far_walk(session)
        cached = PlaceholderRenderer(pygame.Surface((960, 540)), cached_config)
        direct = PlaceholderRenderer(pygame.Surface((960, 540)), direct_config)
        state = GameplayState(session, cached_config)
        state._path = path
        state._destination = goal
        self.assertTrue(state._path)
        compared = 0
        for frame in range(150):
            state.step(InputFrame(), 1 / 30)
            if frame == 60:
                tree = min((p for p, o in session.world.objects.items() if o.kind is ObjectKind.TREE),
                           key=lambda p: abs(p.x - session.player.position.x) + abs(p.y - session.player.position.y))
                session.world.remove_object(tree)
            if frame % 5:
                continue
            for renderer in (cached, direct):
                renderer.draw_gameplay(session, debug=False, player_position=state.visual_position3d,
                                       player_pose=state.player_pose)
            if any(max(abs(p.x - session.player.position.x), abs(p.y - session.player.position.y)) <= 4
                   for p in session.world.portals):
                continue
            with self.subTest(frame=frame):
                self.assertEqual(_interior(direct._world_screen), _interior(cached._world_screen))
            compared += 1
        self.assertGreater(compared, 20)

    def test_blocks_are_reused_and_prepared_ahead_of_the_view(self):
        pygame.font.init()
        config = GameConfig(camera_zoom=1)
        session = GameSession.create(1234, config, chunk_preview_size=64)
        renderer = PlaceholderRenderer(pygame.Surface((960, 540)), config)
        renderer.PREFETCH_BUDGET = 10.0
        renderer.draw_gameplay(session, debug=False)
        first = dict(renderer._chunks)
        rendered = []
        original = renderer._render_chunk
        renderer._render_chunk = lambda s, key, bg: (rendered.append((*key, renderer._phase)), original(s, key, bg))[1]
        p = session.player.position
        z = session.player.position3d.z
        renderer.draw_gameplay(session, debug=False, player_position=(p.x + 1, p.y - 1, z))
        visible_again = [key for key in first if renderer._chunks.get(key) is first[key]]
        self.assertTrue(visible_again)
        self.assertEqual([], [key for key in rendered if key in first])

    def test_blocks_prepared_in_small_steps_match_blocks_drawn_at_once(self):
        pygame.font.init()
        config = GameConfig(camera_zoom=1)
        session = GameSession.create(1234, config, chunk_preview_size=64)
        session.advance_time(20)
        sliced = PlaceholderRenderer(pygame.Surface((960, 540)), config)
        sliced.frame_spare = 0.0
        for _ in range(400):
            sliced.draw_gameplay(session, debug=False)
        prefetched = {key: surface for key, surface in sliced._chunks.items()}
        self.assertTrue(any(phase is not session.daylight.phase for *_, phase in prefetched))
        whole = PlaceholderRenderer(pygame.Surface((960, 540)), config)
        whole.draw_gameplay(session, debug=False)
        background = BACKGROUND
        whole.screen, whole.config = whole._world_screen, whole._world_config
        for (i, j, phase), surface in prefetched.items():
            whole._phase = phase
            expected = whole._render_chunk(session, (i, j), background)
            self.assertEqual(pygame.image.tobytes(expected, "RGB"), pygame.image.tobytes(surface, "RGB"),
                             (i, j, phase))

    def test_removing_an_object_redraws_only_nearby_blocks(self):
        pygame.font.init()
        config = GameConfig(camera_zoom=1)
        session = GameSession.create(1234, config, chunk_preview_size=64)
        renderer = PlaceholderRenderer(pygame.Surface((960, 540)), config)
        renderer.draw_gameplay(session, debug=False)
        before = set(renderer._chunks)
        tree = min(session.world.objects, key=lambda p: abs(p.x - session.player.position.x)
                   + abs(p.y - session.player.position.y))
        session.world.remove_object(tree)
        renderer.draw_gameplay(session, debug=False)
        kept = [key for key in before if key in renderer._chunks]
        self.assertTrue(kept)
        self.assertLess(len(before) - len(kept), len(before) // 2)


class ActorRepaintTests(unittest.TestCase):
    def test_actor_repaint_lists_only_items_reaching_its_box(self):
        pygame.font.init()
        config = GameConfig(camera_zoom=1)
        session = GameSession.create(1234, config, chunk_preview_size=128)
        renderer = PlaceholderRenderer(pygame.Surface((960, 540)), config)
        renderer.draw_gameplay(session, debug=False)
        origin = renderer._camera_origin(session, session.player.position3d)
        camera = (round(origin[0]), round(origin[1]))
        x, y = renderer._screen_center(session.player.position3d, origin)
        box = pygame.Rect(x - 20, y - 44, 40, 56)
        local = box.move(-camera[0], -camera[1])
        items = renderer._static_items_in(session, local)
        padded = scene_items(session, origin, config, bounds=renderer._grid_bounds_for_rect(session, origin, box))
        self.assertTrue(items)
        self.assertLess(len(items), len(padded) // 2)
        for item in items:
            left, top, right, bottom = renderer._item_bounds(session, item)
            self.assertTrue(left < local.right and right > local.left and top < local.bottom and bottom > local.top)
        listed = {(i.kind, i.position) for i in items}
        for item in padded:
            if (item.kind, item.position) not in listed:
                left, top, right, bottom = renderer._item_bounds(session, item)
                self.assertFalse(left < local.right and right > local.left
                                 and top < local.bottom and bottom > local.top, item)

    def test_shadow_receivers_match_a_full_window_scan(self):
        pygame.font.init()
        config = GameConfig(camera_zoom=1)
        session = GameSession.create(1234, config, chunk_preview_size=64)
        world = session.world
        renderer = PlaceholderRenderer(pygame.Surface((960, 540)), config)
        receivers = renderer._shadow_receivers(world)
        for position in sorted(world.tile_map.tiles)[::7]:
            scanned = {position - delta for delta in renderer._shadow_window()
                       if renderer._caster_at(world, position - delta) is not None}
            indexed = {p for p in receivers.get((position.x, position.y), ())
                       if renderer._caster_at(world, p) is not None}
            self.assertEqual(scanned, indexed, position)


def far_walk(session):
    world, spawn = session.world, session.world.spawn
    ring = [p for p in world.tile_map.tiles
            if 10 <= max(abs(p.x - spawn.x), abs(p.y - spawn.y)) <= 14 and world.is_walkable(p)]
    portals = list(world.portals)
    ring.sort(key=lambda p: (-min(max(abs(p.x - q.x), abs(p.y - q.y)) for q in portals), p.x + p.y, p.x))
    for goal in ring:
        path = find_path(spawn, goal, world.is_walkable, session.can_step)
        if path:
            return goal, path
    raise AssertionError("no walkable cell 10-14 cells from the spawn")


if __name__ == "__main__":
    unittest.main()
