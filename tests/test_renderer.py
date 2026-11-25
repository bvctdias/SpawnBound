import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
import pygame
from spawnbound.config import GameConfig
from spawnbound.domain.coordinates import GridPos, WorldPos
from spawnbound.domain.daylight import DayPhase
from spawnbound.domain.model import Biome, ObjectKind, TileKind, TreeVariant, WorldObject
from spawnbound.domain.session import GameSession
from spawnbound.renderer import PlaceholderRenderer
from spawnbound.seabed import sandbank_at
from spawnbound.animation import MotionKind, PlayerPose
from spawnbound.sprites import PlayerSprites, SpriteClip


DEFAULT_CONFIG = GameConfig(camera_zoom=1)


class RendererTests(unittest.TestCase):
    def test_dust_opens_into_separate_puffs_and_then_specks(self):
        from spawnbound.break_art import dust_frame

        for large in (False, True):
            for scale in (1, 2):
                masks = [pygame.mask.from_surface(dust_frame(i, large, scale)) for i in (4, 9, 14)]
                cloud, ring, specks = masks
                self.assertEqual(1, len(cloud.get_bounding_rects()))
                self.assertGreaterEqual(len(ring.get_bounding_rects()), 6)
                self.assertLess(specks.count(), ring.count() // 8)
                self.assertGreater(specks.count(), 0)
                self.assertIs(dust_frame(4, large, scale), dust_frame(4, large, scale))

    def test_damage_and_break_frames_use_native_art_after_removal(self):
        from spawnbound.domain.mobs import Mob, MobKind
        from spawnbound.domain.session import Afterimage
        from spawnbound.prototype_art import PrototypeArtRenderer
        from spawnbound.view import SceneItem

        pygame.font.init()
        session = GameSession.create(71, DEFAULT_CONFIG, chunk_preview_size=8)
        target = pygame.Surface((180, 180), pygame.SRCALPHA)
        manifest = Path(__file__).resolve().parents[1] / "assets/native_32/manifest.json"
        renderer = PrototypeArtRenderer(target, DEFAULT_CONFIG, manifest)
        renderer._player_pose = PlayerPose(MotionKind.IDLE, session.player.facing)
        location = session.player.position3d
        x, y = renderer._screen_center(location, (0, 0))
        origin = (90-x, 110-y)
        actors = [SceneItem("player", location.grid, location)]
        for kind in MobKind:
            mob = Mob(1, kind, 0, location, location, 0)
            effect = Afterimage(location, session.world.space_id, mob, None)
            actors.append(SceneItem("effect", location.grid, effect))
        for kind, variant in ((ObjectKind.ROCK, "quartz_ore"), (ObjectKind.ROCK, "copper_ore"),
                              (ObjectKind.CACTUS, "column"), (ObjectKind.TREE, "broadleaf")):
            obj = WorldObject.create(location.grid, kind, variant=variant)
            effect = Afterimage(location, session.world.space_id, obj, obj.drops[0][0], destroyed=True)
            actors.append(SceneItem("effect", location.grid, effect))
        for actor in actors:
            with self.subTest(subject=actor.payload):
                frames = []
                for t in (0, .24, .31):
                    session.hurt_time = t
                    if actor.kind == "effect":
                        actor.payload.elapsed = t
                    target.fill((0,0,0,0))
                    renderer._draw_actor(session, actor, origin)
                    self.assertGreater(target.get_bounding_rect().width, 0)
                    frames.append(pygame.image.tobytes(target, "RGBA"))
                self.assertGreater(len(set(frames)), 1)

    def test_rear_height_changes_refresh_cached_contact_shading(self):
        pygame.font.init()
        session = GameSession.create(1234, DEFAULT_CONFIG, chunk_preview_size=8)
        session.world.objects.clear()
        p = session.world.spawn + GridPos(2, 0)
        session.world.tile_map.add(p, TileKind.GRASS)
        screen = pygame.Surface((960, 540))
        renderer = PlaceholderRenderer(screen, DEFAULT_CONFIG)
        w, h = DEFAULT_CONFIG.tile_width, DEFAULT_CONFIG.tile_height
        for direction, pixel in ((GridPos(-1, 0), (w // 4, h // 4)), (GridPos(0, -1), (3 * w // 4, h // 4))):
            with self.subTest(direction=direction):
                rear = p + direction
                session.world.tile_map.add(rear, TileKind.GRASS, elevation=0)
                renderer.draw_gameplay(session, debug=False)
                before = renderer._prepared_tiles[p].surface.get_at(pixel)
                session.world.tile_map.add(rear, TileKind.GRASS, elevation=1)
                renderer.draw_gameplay(session, debug=False)
                after = renderer._prepared_tiles[p].surface.get_at(pixel)
                self.assertLess(sum(after[:3]), sum(before[:3]))

    def test_biome_boundary_does_not_create_a_false_height_edge(self):
        pygame.font.init()
        session = GameSession.create(1234, DEFAULT_CONFIG, chunk_preview_size=8)
        p = session.player.position
        session.world.tile_map.add(p, TileKind.GRASS)
        renderer = PlaceholderRenderer(pygame.Surface((960, 540)), DEFAULT_CONFIG)
        before = renderer._prepare_tile(session, p, session.world.tile_map.tile_at(p)).surface
        session.world.tile_map.add(p + GridPos(-1, 0), TileKind.GRASS, biome=Biome.DRY, elevation=0)
        after = renderer._prepare_tile(session, p, session.world.tile_map.tile_at(p)).surface
        self.assertEqual(pygame.image.tobytes(before, "RGBA"), pygame.image.tobytes(after, "RGBA"))

    def test_higher_top_has_different_shading_for_the_same_material(self):
        pygame.font.init()
        session = GameSession.create(1234, DEFAULT_CONFIG, chunk_preview_size=8)
        p = session.player.position
        renderer = PlaceholderRenderer(pygame.Surface((960, 540)), DEFAULT_CONFIG)
        session.world.tile_map.add(p, TileKind.CAVE_FLOOR, elevation=0)
        low = renderer._prepare_tile(session, p, session.world.tile_map.tile_at(p)).surface.get_at((32, 16))
        session.world.tile_map.add(p, TileKind.CAVE_FLOOR, elevation=1)
        high = renderer._prepare_tile(session, p, session.world.tile_map.tile_at(p)).surface.get_at((32, 16))
        self.assertGreater(sum(high[:3]), sum(low[:3]))

    def test_floor_does_not_cover_body_when_standing_off_center(self):
        pygame.font.init()
        session = GameSession.create(1234, DEFAULT_CONFIG, chunk_preview_size=8)
        session.world.objects.clear()
        screen = pygame.Surface((960, 540))
        renderer = PlaceholderRenderer(screen, DEFAULT_CONFIG)
        p = session.player.position
        session.player.facing = GridPos(-1, -1)
        for dx, dy in ((-.4, -.4), (.4, -.4), (-.4, .4), (.4, .4), (.5, .5)):
            with self.subTest(offset=(dx, dy)):
                session.player.place(WorldPos(p.x + dx, p.y + dy, 0))
                renderer.draw_gameplay(session, debug=False)
                x, y = renderer._screen_center(session.player.position3d, renderer._camera_origin(session))
                self.assertEqual((53, 151, 171), tuple(screen.get_at((x + 2, y - 7)))[:3])

    def test_large_terrain_keeps_character_and_shadow_small(self):
        pygame.font.init()
        session = GameSession.create(1234, DEFAULT_CONFIG, chunk_preview_size=8)
        session.player.facing = GridPos(-1, -1)
        screen = pygame.Surface((960, 540), pygame.SRCALPHA)
        renderer = PlaceholderRenderer(screen, DEFAULT_CONFIG)
        position = WorldPos(0, 0, 0)
        renderer._draw_player(session, (480, 270), position)
        self.assertEqual((32, 16), (DEFAULT_CONFIG.tile_width, DEFAULT_CONFIG.tile_height))
        s = DEFAULT_CONFIG.player_art_scale
        at = lambda dx, dy: screen.get_at((480 + round(dx * s), 270 + round(dy * s)))
        self.assertEqual((53, 151, 171), tuple(at(8, -20))[:3])
        self.assertEqual((224, 181, 137), tuple(at(0, -37))[:3])
        self.assertEqual(0, at(14, -20).a)
        self.assertEqual(0, at(0, -70).a)
        self.assertEqual(0, at(20, 2).a)
        self.assertLess(round(45 * s), DEFAULT_CONFIG.tile_width)

    def test_registered_frames_draw_with_foot_pivot_and_missing_clip_falls_back(self):
        pygame.font.init()
        session = GameSession.create(1234, DEFAULT_CONFIG, chunk_preview_size=8)
        session.world.objects.clear()
        screen = pygame.Surface((960, 540))
        frames = tuple(pygame.Surface((12, 24), pygame.SRCALPHA) for _ in range(2))
        frames[0].fill((215, 31, 93))
        frames[1].fill((30, 215, 93))
        facing = session.player.facing
        sprites = PlayerSprites({(MotionKind.WALK, facing): SpriteClip(frames, (6, 24), fps=10)})
        renderer = PlaceholderRenderer(screen, DEFAULT_CONFIG, player_sprites=sprites)
        x, y = renderer._ground_center(session, session.player.position, renderer._camera_origin(session))
        body = (x + 2, y - round(18 * DEFAULT_CONFIG.player_art_scale))
        renderer.draw_gameplay(session, debug=False,
                               player_pose=PlayerPose(MotionKind.WALK, facing, elapsed=.1))
        self.assertEqual((30, 215, 93), tuple(screen.get_at(body))[:3])
        renderer.draw_gameplay(session, debug=False,
                               player_pose=PlayerPose(MotionKind.IDLE, facing))
        self.assertEqual((53, 151, 171), tuple(screen.get_at(body))[:3])

    def test_foreground_cliff_occludes_the_player_body(self):
        pygame.font.init()
        session = GameSession.create(1234, DEFAULT_CONFIG, chunk_preview_size=8)
        session.world.objects.clear()
        screen = pygame.Surface((960, 540))
        renderer = PlaceholderRenderer(screen, DEFAULT_CONFIG)
        p = session.player.position
        x, y = renderer._ground_center(session, p, renderer._camera_origin(session))
        renderer.draw_gameplay(session, debug=False)
        body = (x + 2, y - round(18 * DEFAULT_CONFIG.player_art_scale))
        self.assertEqual((53, 151, 171), tuple(screen.get_at(body))[:3])
        session.world.tile_map.add(p + GridPos(1, 0), TileKind.GRASS, elevation=3)
        renderer.draw_gameplay(session, debug=False)
        self.assertNotEqual((53, 151, 171), tuple(screen.get_at(body))[:3])

    def test_replacing_a_tile_without_changing_map_size_updates_pixels(self):
        pygame.font.init()
        session = GameSession.create(1234, DEFAULT_CONFIG, chunk_preview_size=16)
        session.world.objects.clear()
        screen = pygame.Surface((960, 540))
        renderer = PlaceholderRenderer(screen, DEFAULT_CONFIG)
        position = session.world.spawn + GridPos(0, -2)
        renderer.draw_gameplay(session, debug=False)
        x, y = renderer._ground_center(session, position, renderer._camera_origin(session))
        before = screen.get_at((x, y))
        count = len(session.world.tile_map.tiles)
        session.world.tile_map.add(position, TileKind.BRIDGE, elevation=session.world.elevation_at(position))
        renderer.draw_gameplay(session, debug=False)
        self.assertEqual(count, len(session.world.tile_map.tiles))
        self.assertNotEqual(before, screen.get_at((x, y)))
        self.assertEqual((142, 98, 57), tuple(screen.get_at((x, y)))[:3])

    def test_adjacent_identical_tiles_have_no_checkerboard_tone(self):
        pygame.font.init()
        session = GameSession.create(1234, DEFAULT_CONFIG, chunk_preview_size=8)
        p = session.player.position
        for q in (p, p + GridPos(1, 0)):
            session.world.tile_map.add(q, TileKind.GRASS, elevation=0)
        renderer = PlaceholderRenderer(pygame.Surface((960, 540)), DEFAULT_CONFIG)
        center = (32, 16)
        a = renderer._prepare_tile(session, p, session.world.tile_map.tile_at(p)).surface.get_at(center)
        b = renderer._prepare_tile(session, p + GridPos(1, 0),
                                   session.world.tile_map.tile_at(p + GridPos(1, 0))).surface.get_at(center)
        self.assertEqual(a, b)

    def test_grid_darkens_only_rear_edges_and_can_be_disabled(self):
        pygame.font.init()
        session = GameSession.create(1234, DEFAULT_CONFIG, chunk_preview_size=8)
        p = session.player.position
        session.world.tile_map.add(p, TileKind.CAVE_FLOOR, elevation=0)
        for direction in ((0, 1), (1, 0), (0, -1), (-1, 0)):
            session.world.tile_map.add(p + GridPos(*direction), TileKind.CAVE_FLOOR, elevation=0)
        tile = session.world.tile_map.tile_at(p)
        grid = PlaceholderRenderer(pygame.Surface((960, 540)), DEFAULT_CONFIG)._prepare_tile(session, p, tile).surface
        plain_config = GameConfig(camera_zoom=1, terrain_grid_strength=0)
        plain = PlaceholderRenderer(pygame.Surface((960, 540)), plain_config)._prepare_tile(session, p, tile).surface
        w, h = DEFAULT_CONFIG.tile_width, DEFAULT_CONFIG.tile_height
        center = (w // 2, h // 2)
        interior = plain.get_at(center)
        rear_edge = (w // 4, h // 4)
        front_edge = (w // 4, 3 * h // 4 - 1)
        self.assertEqual(interior, plain.get_at(rear_edge))
        self.assertLess(sum(grid.get_at(rear_edge)[:3]), sum(interior[:3]))
        self.assertEqual(interior, grid.get_at(front_edge))
        self.assertEqual(grid.get_at(center), interior)

    def _raised_meadow_tile(self, lower_front: bool):
        pygame.font.init()
        session = GameSession.create(1234, DEFAULT_CONFIG, chunk_preview_size=8)
        p = session.player.position
        session.world.tile_map.add(p, TileKind.GRASS, biome=Biome.MEADOW, elevation=1)
        for direction in ((1, 0), (0, -1), (-1, 0)):
            session.world.tile_map.add(p + GridPos(*direction), TileKind.GRASS, biome=Biome.MEADOW, elevation=1)
        session.world.tile_map.add(p + GridPos(0, 1), TileKind.GRASS, biome=Biome.MEADOW,
                                   elevation=0 if lower_front else 1)
        renderer = PlaceholderRenderer(pygame.Surface((960, 540)), DEFAULT_CONFIG)
        return renderer, renderer._prepare_tile(session, p, session.world.tile_map.tile_at(p)).surface

    def _face_point(self, x: int, depth: int) -> tuple[int, int]:
        return x, DEFAULT_CONFIG.tile_height // 2 + x // 2 + depth

    def test_cliff_face_is_continuous_without_outline(self):
        _renderer, surface = self._raised_meadow_tile(lower_front=True)
        w = DEFAULT_CONFIG.tile_width
        lip = 3 * max(1, DEFAULT_CONFIG.tile_height // 16)
        depth = lip + 3
        samples = [surface.get_at(self._face_point(x, depth)) for x in (0, w // 4, w // 2 - 2)]
        self.assertEqual(samples[0], samples[1])
        self.assertEqual(samples[1], samples[2])

    def test_grass_cliff_has_a_grass_lip_above_earth(self):
        _renderer, surface = self._raised_meadow_tile(lower_front=True)
        lip_depth = 3 * max(1, DEFAULT_CONFIG.tile_height // 16)
        x = DEFAULT_CONFIG.tile_width // 8
        lip = surface.get_at(self._face_point(x, 1))
        earth = surface.get_at(self._face_point(x, lip_depth + 3))
        self.assertGreater(lip.g, lip.r)
        self.assertGreater(earth.r, earth.g)

    def test_raised_front_edge_gets_rim_light(self):
        renderer, raised = self._raised_meadow_tile(lower_front=True)
        _renderer, level = self._raised_meadow_tile(lower_front=False)
        _first, last = renderer._top_outline()
        column = DEFAULT_CONFIG.tile_width // 4
        edge = (column, last[column])
        self.assertGreater(sum(raised.get_at(edge)[:3]), sum(level.get_at(edge)[:3]))

    def _flat_world_with_tree(self, config=DEFAULT_CONFIG):
        pygame.font.init()
        session = GameSession.create(1234, config, chunk_preview_size=8)
        session.world.objects.clear()
        session.world.camp = GridPos(-50, -50)
        p = GridPos(2, 5)
        session.world.objects[p] = WorldObject.create(p, ObjectKind.TREE, variant=TreeVariant.BROADLEAF.value)
        renderer = PlaceholderRenderer(pygame.Surface((960, 540)), config)
        return session, renderer, p

    def test_player_behind_a_tree_keeps_a_silhouette(self):
        session, renderer, tree = self._flat_world_with_tree()

        def frame(player, tint):
            session.player.position = player
            renderer.PLAYER_SILHOUETTE = tint
            renderer.draw_gameplay(session, debug=False)
            return renderer._world_screen.copy()

        clear = PlaceholderRenderer.PLAYER_SILHOUETTE[:3] + (0,)
        behind = tree - GridPos(1, 1)
        hidden = frame(behind, PlaceholderRenderer.PLAYER_SILHOUETTE)
        self.assertNotEqual(pygame.image.tobytes(hidden, "RGB"), pygame.image.tobytes(frame(behind, clear), "RGB"))
        in_front = tree + GridPos(1, 1)
        shown = frame(in_front, PlaceholderRenderer.PLAYER_SILHOUETTE)
        self.assertEqual(pygame.image.tobytes(shown, "RGB"), pygame.image.tobytes(frame(in_front, clear), "RGB"))

    def test_animals_and_archers_behind_a_tree_keep_a_silhouette(self):
        from spawnbound.domain.mobs import Mob, MobKind
        session, renderer, tree = self._flat_world_with_tree()
        session.player.position = GridPos(6, 1)
        clear = (0, 0, 0, 0)

        def frame(kind, cell, tints):
            location = session.world.surface_position(cell)
            session.wildlife.mobs = {1: Mob(1, kind, 1, location, location, 9.)}
            renderer.ANIMAL_SILHOUETTE, renderer.HOSTILE_SILHOUETTE = tints
            renderer.draw_gameplay(session, debug=False)
            return pygame.image.tobytes(renderer._world_screen, "RGB")

        colours = (PlaceholderRenderer.ANIMAL_SILHOUETTE, PlaceholderRenderer.HOSTILE_SILHOUETTE)
        for kind in MobKind:
            with self.subTest(kind=kind):
                behind = tree - GridPos(1, 1)
                self.assertNotEqual(frame(kind, behind, colours), frame(kind, behind, (clear, clear)))
                in_front = tree + GridPos(1, 1)
                self.assertEqual(frame(kind, in_front, colours), frame(kind, in_front, (clear, clear)))

    def _decal(self, renderer, session, position):
        return renderer._build_tile_shadow(session, position, session.world.tile_map.tile_at(position))

    def test_tree_casts_shadow_to_the_right_only(self):
        session, renderer, p = self._flat_world_with_tree()
        right = p + GridPos(1, -1)
        left = p + GridPos(-1, 1)
        decal = self._decal(renderer, session, right)
        self.assertIsNotNone(decal)
        shaded = sum(decal.get_at((x, y))[:3] != (255, 255, 255)
                     for x in range(decal.get_width()) for y in range(decal.get_height()))
        self.assertGreater(shaded, 0)
        self.assertIsNone(self._decal(renderer, session, left))

    def test_overlapping_shadows_apply_one_uniform_shade(self):
        session, renderer, p = self._flat_world_with_tree()
        second = p + GridPos(0, -1)
        session.world.objects[second] = WorldObject.create(second, ObjectKind.TREE,
                                                           variant=TreeVariant.BROADLEAF.value)
        decal = self._decal(renderer, session, p + GridPos(1, -1))
        colors = {tuple(decal.get_at((x, y))[:3]) for x in range(decal.get_width())
                  for y in range(decal.get_height())}
        self.assertEqual(2, len(colors))

    def test_shadow_stops_at_a_height_change(self):
        session, renderer, p = self._flat_world_with_tree()
        right = p + GridPos(1, -1)
        session.world.tile_map.add(right, TileKind.GRASS, elevation=1)
        self.assertIsNone(self._decal(renderer, session, right))

    def test_removing_a_caster_clears_its_shadow(self):
        session, renderer, p = self._flat_world_with_tree()
        right = p + GridPos(1, -1)
        renderer.draw_gameplay(session, debug=False)
        self.assertIsNotNone(renderer._prepared_tiles[right].shadows[DayPhase.DAY])
        session.world.remove_object(p)
        renderer.draw_gameplay(session, debug=False)
        self.assertIsNone(renderer._prepared_tiles[right].shadows[DayPhase.DAY])

    def test_afternoon_shadow_extends_and_night_keeps_only_contact(self):
        session, renderer, p = self._flat_world_with_tree()
        tree = session.world.objects[p]
        extent = []
        for seconds in (0, 30, 60):
            session.cycle_seconds = seconds
            renderer.draw_gameplay(session, debug=False)
            if seconds < 60:
                image, (left, _) = renderer._cast_shadow("object", tree)
                extent.append(left + image.get_bounding_rect().right)
        self.assertGreater(extent[1], extent[0])
        from unittest.mock import patch
        night = PlaceholderRenderer(pygame.Surface((960, 540)), DEFAULT_CONFIG)
        with patch.object(night, "_build_tile_shadow", side_effect=AssertionError("sun at night")), \
             patch.object(night, "_draw_contact_shadow", wraps=night._draw_contact_shadow) as contact:
            night.draw_gameplay(session, debug=False)
            self.assertTrue(contact.called)

    def _detail(self, renderer, session, position):
        tile = session.world.tile_map.tile_at(position)
        return renderer._build_tile_detail(session, position, tile, (110, 150, 90))

    def test_ground_details_are_deterministic_and_skip_occupied_cells(self):
        session, renderer, tree = self._flat_world_with_tree()
        cells = [p for p in session.world.tile_map.tiles if p != tree]
        details = {p: self._detail(renderer, session, p) for p in cells}
        decorated = [p for p, surface in details.items() if surface is not None]
        self.assertTrue(decorated)
        again = self._detail(PlaceholderRenderer(pygame.Surface((960, 540)), DEFAULT_CONFIG), session, decorated[0])
        self.assertEqual(pygame.image.tobytes(details[decorated[0]], "RGBA"), pygame.image.tobytes(again, "RGBA"))
        self.assertIsNone(self._detail(renderer, session, tree))

    def test_ground_details_stay_inside_the_top_and_can_be_disabled(self):
        session, renderer, tree = self._flat_world_with_tree()
        alpha = renderer._top_alpha()
        for p in session.world.tile_map.tiles:
            surface = self._detail(renderer, session, p)
            if surface is None:
                continue
            for x in range(surface.get_width()):
                for y in range(surface.get_height()):
                    if surface.get_at((x, y)).a:
                        self.assertTrue(alpha.get_at((x, y)).a, (p, x, y))
        config = GameConfig(camera_zoom=1, ground_detail_density=0)
        session, renderer, tree = self._flat_world_with_tree(config)
        self.assertTrue(all(self._detail(renderer, session, p) is None for p in session.world.tile_map.tiles))

    def test_water_surface_is_translucent_raised_and_foamed_at_the_shore(self):
        pygame.font.init()
        session = GameSession.create(1234, DEFAULT_CONFIG, chunk_preview_size=8)
        session.world.objects.clear()
        p = session.player.position + GridPos(1, 1)
        session.world.tile_map.add(p, TileKind.WATER, elevation=0)
        for direction in ((0, 1), (1, 0), (0, -1), (-1, 0)):
            session.world.tile_map.add(p + GridPos(*direction), TileKind.GRASS, elevation=1)
        renderer = PlaceholderRenderer(pygame.Surface((960, 540)), DEFAULT_CONFIG)
        prepared = renderer._prepare_tile(session, p, session.world.tile_map.tile_at(p))
        overlay = prepared.water
        w, h = DEFAULT_CONFIG.tile_width, DEFAULT_CONFIG.tile_height
        body = overlay.get_at((w // 2, h // 2))
        self.assertTrue(0 < body.a < 255)
        self.assertGreater(body.b, body.r)
        first, _last = renderer._top_outline()
        self.assertEqual(renderer.WATER_FOAM, tuple(overlay.get_at((w // 4, first[w // 4]))))
        self.assertTrue(0 < renderer._water_lift() < DEFAULT_CONFIG.height_unit_pixels)

    def test_estuary_banks_vary_on_shared_ocean_tiles_and_preserve_deep_water(self):
        pygame.font.init()
        session = GameSession.create(817, DEFAULT_CONFIG, chunk_preview_size=128)
        world = session.world
        renderer = PlaceholderRenderer(pygame.Surface((960, 540)), DEFAULT_CONFIG)
        mouth = world.river_mouth
        size = world.tile_map.ocean_island_size
        out = next(d for d in (GridPos(-1, 0), GridPos(1, 0), GridPos(0, -1), GridPos(0, 1))
                   if mouth + d not in world.tile_map.tiles)

        def water_at(position):
            tile = world.tile_map.tile_at(position)
            return renderer._prepare_tile(session, position, tile).water

        positions = [GridPos(mouth.x + out.x * n, mouth.y + out.y * n) for n in range(1, 13)]
        surfaces = [water_at(p) for p in positions]
        self.assertIs(world.tile_map.tile_at(positions[0]), world.tile_map.tile_at(positions[-1]))
        self.assertGreaterEqual(len({tuple(s.get_at((12, 8))) for s in surfaces}), 3)
        self.assertIs(surfaces[0], water_at(positions[0]))
        lakes = {p for p,tile in world.tile_map.tiles.items()
                 if tile.kind is TileKind.WATER and p not in world.river_cells and p not in world.sea_cells}
        ocean = [GridPos(x, y) for x in range(-12, 0) for y in range(size)]
        for area in (world.river_cells, lakes, ocean):
            levels, faces = set(), 0
            for p in area:
                neighbors = tuple(world.tile_map.tile_at(p+d) for d in (GridPos(0,1), GridPos(1,0)))
                bank = sandbank_at(world, p, neighbors, renderer._bed_levels)
                levels.add(bank.level if bank else 0)
                faces += bool(bank and (bank.left_drop or bank.right_drop))
            self.assertGreater(len(levels), 1)
            self.assertGreater(faces, 0)
        deep = GridPos(mouth.x + out.x * 14, mouth.y + out.y * 14)
        self.assertEqual((32, 78, 122, 220), tuple(water_at(deep).get_at((16, 8))))

    def test_low_object_shadow_starts_against_its_base(self):
        session, renderer, tree = self._flat_world_with_tree()
        rock = WorldObject.create(tree + GridPos(2, 0), ObjectKind.ROCK)
        image, (foot_x, foot_y) = renderer._caster_image("object", rock)
        mask = pygame.mask.from_surface(image)
        lowest_side = min(max(y for y in range(image.get_height()) if mask.get_at((x, y)))
                          for x in range(image.get_width())
                          if any(mask.get_at((x, y)) for y in range(image.get_height())))
        _shadow, (_left, top) = renderer._cast_shadow("object", rock)
        self.assertLess(lowest_side, foot_y)
        self.assertLessEqual(top, lowest_side - foot_y)

    def test_cast_shadows_can_be_disabled(self):
        config = GameConfig(camera_zoom=1, cast_shadow_strength=0)
        session, renderer, p = self._flat_world_with_tree(config)
        self.assertIsNone(self._decal(renderer, session, p + GridPos(1, -1)))
