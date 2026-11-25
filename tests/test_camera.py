import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import pygame
from spawnbound.config import GameConfig
from spawnbound.domain.coordinates import GridPos, WorldPos
from spawnbound.domain.model import TileKind, ObjectKind, TreeVariant, WorldObject
from spawnbound.domain.session import GameSession
from spawnbound.input import InputFrame
from spawnbound.renderer import PlaceholderRenderer
from spawnbound.states import GameplayState
from spawnbound.view import camera_origin, screen_center, terrain_polygons, pick_world_point, hotbar_rect
from spawnbound.sprites import PlayerSprites, SpriteClip
from spawnbound.animation import MotionKind


class CameraTests(unittest.TestCase):
    def test_zoomed_clicks_reach_subcell_positions_and_cliff_faces(self):
        for zoom in (1, .7, 1.125):
            config = GameConfig(camera_zoom=zoom)
            session = GameSession.create(1234, config, chunk_preview_size=8)
            session.world.objects.clear()
            state = GameplayState(session, config)
            p = session.player.position
            target = WorldPos(p.x + .25, p.y + .125, 0)
            origin = camera_origin(session, config, state.visual_position3d)
            click = screen_center(target, origin, config)
            state.step(InputFrame(destination_click=click), 1)
            self.assertAlmostEqual(target.x, session.player.position3d.x, delta=.04)
            self.assertAlmostEqual(target.y, session.player.position3d.y, delta=.04)
            high = p + GridPos(1, 0)
            session.world.tile_map.add(high, TileKind.GRASS, elevation=1)
            origin = camera_origin(session, config, state.visual_position3d)
            face = terrain_polygons(session.world, high, origin, config)[1]
            click = tuple(sum(v[axis] for v in face) / len(face) for axis in (0, 1))
            hit = pick_world_point(session, click, origin, config)
            self.assertEqual(high, hit.position)
            self.assertFalse(hit.surface)
            state.step(InputFrame(destination_click=click), 1)
            self.assertEqual(session.world.surface_position(high), session.player.position3d)

    def test_picking_nearby_items_matches_searching_the_whole_view(self):
        import random
        from unittest.mock import patch
        from spawnbound import view

        config = GameConfig(camera_zoom=.5)
        session = GameSession.create(1234, config, chunk_preview_size=64)
        origin = camera_origin(session, config, session.player.position3d)
        whole_view = lambda *args: (-10**6, 10**6, -10**6, 10**6)
        rng = random.Random(4)
        for _ in range(250):
            point = (rng.uniform(0, 960), rng.uniform(0, 540))
            got = pick_world_point(session, point, origin, config)
            with patch.object(view, "grid_bounds_for_rect", whole_view):
                expected = pick_world_point(session, point, origin, config)
            self.assertEqual(expected, got, point)

    def test_tree_canopy_hit_uses_zoomed_geometry(self):
        config = GameConfig(camera_zoom=.7)
        session = GameSession.create(1234, config, chunk_preview_size=8)
        session.world.objects.clear()
        p = session.player.position + GridPos(2, 0)
        session.world.objects[p] = WorldObject.create(p, ObjectKind.TREE, variant=TreeVariant.BROADLEAF.value)
        native = config.world_view_config
        origin = camera_origin(session, config)
        x, y = screen_center(session.world.surface_position(p), config.view_to_world(origin), native)
        s = config.world_art_scale
        hit = pick_world_point(session, config.world_to_view((x + round(25 * s), y - round(42 * s))), origin, config)
        self.assertEqual((p, "object"), (hit.position, hit.kind))

    def test_zoom_shows_more_world_and_scales_registered_frames_with_fixed_hud(self):
        pygame.font.init()
        session = GameSession.create(1234, GameConfig(), chunk_preview_size=64)
        session.world.objects.clear()
        frame = pygame.Surface((12, 24), pygame.SRCALPHA)
        color = (213, 31, 93)
        frame.fill(color)
        sprites = PlayerSprites({(MotionKind.IDLE, session.player.facing): SpriteClip((frame,), (6, 24))})
        counts, bounds, hud_pixels = [], [], []
        for zoom in (1, .7):
            config = GameConfig(camera_zoom=zoom, scene_cache=False)
            screen = pygame.Surface((960, 540))
            renderer = PlaceholderRenderer(screen, config, player_sprites=sprites)
            renderer.draw_gameplay(session, debug=False)
            counts.append(renderer.last_draw_counts["tiles"])
            bounds.append(pygame.mask.from_threshold(screen, color, (5, 5, 5, 255)).get_bounding_rects()[0])
            left, top, _, _ = hotbar_rect(config)
            hud_pixels.append(pygame.image.tobytes(renderer._ui_screen.subsurface((left + 5, top + 5, 34, 34)), "RGBA"))
            self.assertEqual((32, 16, 10), (config.tile_width, config.tile_height, config.height_unit_pixels))
        self.assertGreater(counts[1], counts[0])
        self.assertAlmostEqual(.7 * bounds[0].width, bounds[1].width, delta=2)
        self.assertAlmostEqual(.7 * bounds[0].height, bounds[1].height, delta=2)
        self.assertEqual(hud_pixels[0], hud_pixels[1])


if __name__ == "__main__":
    unittest.main()
