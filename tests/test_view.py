import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from spawnbound.config import GameConfig
from spawnbound.domain.coordinates import GridPos
from spawnbound.domain.model import ObjectKind, TileKind, WorldObject, TreeVariant
from spawnbound.domain.session import GameSession
from spawnbound.view import camera_origin, is_world_view_point, pick_world_point, screen_center, visible_grid_positions, scene_items


DEFAULT_CONFIG = GameConfig(camera_zoom=1)


class ViewTests(unittest.TestCase):
    def test_native_cell_is_32_by_16_with_a_shallow_step(self):
        self.assertEqual((32, 16), (DEFAULT_CONFIG.tile_width, DEFAULT_CONFIG.tile_height))
        self.assertEqual(1, DEFAULT_CONFIG.world_art_scale)
        self.assertLess(DEFAULT_CONFIG.height_unit_pixels, DEFAULT_CONFIG.tile_height)

    def test_canopy_click_uses_the_same_scale_as_drawing(self):
        session = GameSession.create(1234, DEFAULT_CONFIG, chunk_preview_size=8)
        session.world.objects.clear()
        p = session.player.position + GridPos(2, 0)
        session.world.objects[p] = WorldObject.create(p, ObjectKind.TREE, variant=TreeVariant.BROADLEAF.value)
        origin = camera_origin(session, DEFAULT_CONFIG)
        x, y = screen_center(session.world.surface_position(p), origin, DEFAULT_CONFIG)
        s = DEFAULT_CONFIG.world_art_scale
        hit = pick_world_point(session, (x + round(25 * s), y - round(42 * s)), origin, DEFAULT_CONFIG)
        self.assertEqual((p, "object"), (hit.position, hit.kind))

    def test_culling_keeps_enlarged_tree_with_base_below_screen(self):
        session = GameSession.create(1234, DEFAULT_CONFIG, chunk_preview_size=64)
        session.world.objects.clear()
        p = session.world.spawn
        session.world.objects[p] = WorldObject.create(p, ObjectKind.TREE,
            variant=TreeVariant.PINE_DARK.value, elevation=session.world.elevation_at(p))
        sx, sy = screen_center(session.world.surface_position(p), (0, 0), DEFAULT_CONFIG)
        below = DEFAULT_CONFIG.world_sprite_padding * 3 // 4
        origin = (480 - sx, DEFAULT_CONFIG.virtual_height + below - sy)
        self.assertTrue(any(item.kind == "object" and item.position == p
                            for item in scene_items(session, origin, DEFAULT_CONFIG)))

    def test_foreground_cliff_prevents_picking_a_hidden_object(self):
        session = GameSession.create(1234, DEFAULT_CONFIG, chunk_preview_size=8)
        session.world.objects.clear()
        p = session.player.position
        foreground = p + GridPos(1, 0)
        session.world.objects[p] = WorldObject.create(p, ObjectKind.ROCK)
        session.world.tile_map.add(foreground, TileKind.GRASS, elevation=3)
        origin = camera_origin(session, DEFAULT_CONFIG)
        x, y = screen_center(session.world.surface_position(p), origin, DEFAULT_CONFIG)
        hit = pick_world_point(session, (x + 2, y - 18), origin, DEFAULT_CONFIG)
        self.assertEqual(foreground, hit.position)
        self.assertEqual("tile", hit.kind)
        self.assertFalse(hit.surface)

    def test_only_visible_ui_blocks_world_clicks(self):
        for point in ((50, 50), (850, 150), (50, 510)):
            self.assertTrue(is_world_view_point(point, DEFAULT_CONFIG))
        self.assertFalse(is_world_view_point((480, 504), DEFAULT_CONFIG))
        self.assertFalse(is_world_view_point((850, 150), DEFAULT_CONFIG, debug=True))

    def test_culling_keeps_visible_tiles_and_tall_sprite_bases(self):
        origin = (480, -400)
        visible = set(visible_grid_positions(origin, DEFAULT_CONFIG, object_height=80))
        for x in range(-25, 100):
            for y in range(-25, 100):
                p = GridPos(x, y)
                sx, sy = screen_center(p, origin, DEFAULT_CONFIG)
                if -16 <= sx <= 976 and -8 <= sy <= 615:
                    self.assertIn(p, visible)
