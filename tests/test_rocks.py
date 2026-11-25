import os
import sys
import unittest
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "dependencias")]
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame

from spawnbound import wear_art
from spawnbound.config import DEFAULT_CONFIG
from spawnbound.domain.coordinates import GridPos
from spawnbound.domain.generation import desert_rock
from spawnbound.domain.model import Biome, ObjectKind, SpaceKind, WorldObject
from spawnbound.domain.session import GameSession
from spawnbound.renderer import PlaceholderRenderer
from spawnbound.rock_art import FOOT, LOOKS, SHAPES, SIZE, placed_rock, rock, rock_shape
from spawnbound.view import object_contains

VARIANTS = tuple(LOOKS)


class RockArtTests(unittest.TestCase):
    def test_every_material_and_shape_fits_its_canvas_small_and_without_sprouts(self):
        for variant in VARIANTS:
            for shape in range(len(SHAPES)):
                with self.subTest(variant=variant, shape=shape):
                    image = rock(variant, shape)
                    self.assertEqual(SIZE, image.get_size())
                    box = image.get_bounding_rect()
                    self.assertTrue(box.left > 0 and box.top > 0 and box.right < SIZE[0] and box.bottom < SIZE[1])
                    self.assertGreater(image.get_at((FOOT[0], FOOT[1] - 3)).a, 0)
                    self.assertLessEqual(box.width, 32)
                    self.assertLessEqual(FOOT[1] - box.top, 26 if variant == "quartz_ore" else 18)
                    pixels = [tuple(image.get_at((x, y))) for x in range(SIZE[0]) for y in range(SIZE[1])]
                    self.assertFalse(any(a and g > r + 40 and g > b + 40 for r, g, b, a in pixels))

    def test_each_material_looks_different_and_each_cell_picks_a_shape(self):
        for shape in range(len(SHAPES)):
            images = {pygame.image.tobytes(rock(v, shape), "RGBA") for v in VARIANTS if v != "cave_stone"}
            self.assertEqual(len(VARIANTS) - 1, len(images))
        self.assertEqual(pygame.image.tobytes(rock("default", 0), "RGBA"),
                         pygame.image.tobytes(rock("cave_stone", 0), "RGBA"))
        shapes = Counter(rock_shape(GridPos(x, y)) for x in range(30) for y in range(30))
        self.assertEqual(set(range(len(SHAPES))), set(shapes))
        self.assertGreater(min(shapes.values()), 200)
        image, foot = placed_rock("sandstone", 1, 2.)
        self.assertEqual((SIZE[0] * 2, SIZE[1] * 2), image.get_size())
        self.assertEqual((FOOT[0] * 2, FOOT[1] * 2), foot)

    def test_coal_lumps_crystals_and_copper_show_their_colours(self):
        def colors(variant):
            image = rock(variant, 0)
            return {tuple(image.get_at((x, y)))[:3] for x in range(SIZE[0]) for y in range(SIZE[1])
                    if image.get_at((x, y)).a}
        dark = lambda c: sum(c) < 120
        self.assertGreater(sum(map(dark, colors("sandstone_coal"))), sum(map(dark, colors("sandstone"))))
        self.assertTrue(any(r > 220 and g < 170 and b < 130 for r, g, b in colors("copper_ore")))
        self.assertTrue(any(r > 220 and b > 180 and g < 210 for r, g, b in colors("quartz_ore")))
        self.assertLess(rock("quartz_ore", 0).get_bounding_rect().top, rock("default", 0).get_bounding_rect().top - 4)

    def test_a_click_hits_the_rock_pixels_and_misses_above_it(self):
        for variant in ("default", "sandstone_coal", "quartz_ore"):
            for position in (GridPos(0, 0), GridPos(1, 0), GridPos(2, 0)):
                obj = WorldObject.create(position, ObjectKind.ROCK, variant=variant)
                image = rock(variant, rock_shape(position))
                box = image.get_bounding_rect()
                with self.subTest(variant=variant, shape=rock_shape(position)):
                    self.assertTrue(object_contains(obj, 0, -6))
                    self.assertFalse(object_contains(obj, 0, box.top - FOOT[1] - 3))
                    self.assertFalse(object_contains(obj, box.right - FOOT[0] + 3, -6))

    def test_wear_stays_on_the_stone_and_grows_with_each_stage(self):
        for variant in VARIANTS:
            body = rock(variant, 1)
            silhouette = pygame.mask.from_surface(body, 127)
            counts = []
            for stage in (1, 2, 3, 4):
                painted = pygame.mask.from_surface(wear_art.wear_overlay(body, FOOT, ObjectKind.ROCK, stage, 9, 1))
                counts.append(painted.count())
                self.assertEqual(painted.count(), painted.overlap_area(silhouette, (0, 0)))
            with self.subTest(variant=variant):
                self.assertEqual(sorted(counts), counts)
                self.assertGreater(counts[-1], counts[0])
            self.assertEqual(4, len(wear_art.burst_pieces(body, FOOT, .02, 1, 1)))

    def test_chips_follow_the_material(self):
        self.assertIs(wear_art.SANDSTONE, wear_art.materials(ObjectKind.ROCK, "sandstone_coal"))
        self.assertIs(wear_art.STONE, wear_art.materials(ObjectKind.ROCK, "cave_stone", cave=True))
        self.assertIs(wear_art.CAVE_STONE, wear_art.materials(None, cave=True))
        self.assertIn("coal_ore", wear_art.ORE_GLINTS)

    def test_both_renderers_draw_the_rock_by_code_with_a_shadow_per_shape(self):
        from spawnbound.prototype_art import PrototypeArtRenderer
        pygame.font.init()
        manifest = ROOT / "assets/native_32/manifest.json"
        art = PrototypeArtRenderer(pygame.Surface((960, 540)), DEFAULT_CONFIG, manifest)
        plain = PlaceholderRenderer(pygame.Surface((960, 540)), DEFAULT_CONFIG)
        a = WorldObject.create(GridPos(0, 0), ObjectKind.ROCK, variant="sandstone")
        b = next(WorldObject.create(GridPos(x, 0), ObjectKind.ROCK, variant="sandstone")
                 for x in range(1, 9) if rock_shape(GridPos(x, 0)) != rock_shape(a.position))
        self.assertEqual("rock", art.object_name(a))
        self.assertNotIn("rock", art.art.images)
        self.assertIsNone(art.hit_test("object", a, 0, -6))
        for renderer in (art, plain):
            with self.subTest(renderer=type(renderer).__name__):
                self.assertNotEqual(renderer._caster_key("object", a), renderer._caster_key("object", b))
                body, foot = renderer._caster_image("object", a)
                sprite, (fx, fy) = placed_rock("sandstone", rock_shape(a.position))
                region = pygame.Rect(foot[0] - fx, foot[1] - fy, *sprite.get_size())
                self.assertEqual(pygame.image.tobytes(sprite, "RGBA"),
                                 pygame.image.tobytes(body.subsurface(region), "RGBA"))


class RockPlacementTests(unittest.TestCase):
    def test_desert_rocks_are_sandstone_and_about_a_quarter_hold_coal(self):
        coal = Counter(desert_rock(GridPos(x, y)) for x in range(-40, 40) for y in range(-40, 40))
        self.assertEqual({"sandstone", "sandstone_coal"}, set(coal))
        self.assertAlmostEqual(.25, coal["sandstone_coal"] / sum(coal.values()), delta=.03)
        for seed in (1234, 7, 39658298):
            session = GameSession.create(seed, DEFAULT_CONFIG, chunk_preview_size=128)
            world = session.world
            found = Counter()
            for p, obj in world.objects.items():
                if obj.kind is not ObjectKind.ROCK:
                    continue
                desert = world.tile_map.tile_at(p).biome is Biome.DRY
                with self.subTest(seed=seed, cell=p):
                    self.assertEqual(desert_rock(p) if desert else "default", obj.variant)
                found[obj.variant] += 1
            with self.subTest(seed=seed):
                self.assertGreater(found["default"], 0)
                self.assertGreater(found["sandstone"], 0)
                self.assertGreater(found["sandstone_coal"], 0)

    def test_desert_coal_breaks_with_the_starting_pickaxe_and_gives_coal(self):
        session = GameSession.create(1234, DEFAULT_CONFIG, chunk_preview_size=128)
        world = session.world
        rock_cell = next(p for p, o in sorted(world.objects.items()) if o.variant == "sandstone_coal"
                         and any(world.is_walkable(p + d) and world.can_reach(p + d, p)
                                 for d in (GridPos(1, 0), GridPos(-1, 0), GridPos(0, 1), GridPos(0, -1))))
        stand = next(rock_cell + d for d in (GridPos(1, 0), GridPos(-1, 0), GridPos(0, 1), GridPos(0, -1))
                     if world.is_walkable(rock_cell + d) and world.can_reach(rock_cell + d, rock_cell))
        session.player.position = stand
        for _ in range(12):
            if rock_cell not in world.objects:
                break
            session.primary_action(rock_cell)
        self.assertNotIn(rock_cell, world.objects)
        self.assertEqual(1, session.player.inventory.quantity("coal"))
        self.assertEqual(0, session.player.inventory.quantity("stone"))


if __name__ == "__main__":
    unittest.main()
