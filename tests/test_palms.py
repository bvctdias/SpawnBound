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
from spawnbound.domain.generation import desert_palm
from spawnbound.domain.model import PALMS, Biome, ObjectKind, WorldObject
from spawnbound.domain.session import GameSession
from spawnbound.island_map import TREES
from spawnbound.palm_art import FOOT, SIZE, palm, placed_palm
from spawnbound.renderer import PlaceholderRenderer
from spawnbound.view import object_contains

ORDER = ("palm_small", "palm_medium", "palm_tall")


class PalmArtTests(unittest.TestCase):
    def test_three_sizes_share_the_crown_and_grow_by_the_trunk(self):
        boxes = [palm(v).get_bounding_rect() for v in ORDER]
        for variant, box in zip(ORDER, boxes):
            with self.subTest(variant=variant):
                self.assertTrue(box.left >= 0 and box.top > 0 and box.right <= SIZE[0] and box.bottom <= SIZE[1])
                self.assertGreater(palm(variant).get_at((FOOT[0], FOOT[1] - 2)).a, 0)
                self.assertLessEqual(FOOT[1] - box.top, 78)
        self.assertEqual(1, len({b.width for b in boxes}))
        heights = [b.height for b in boxes]
        self.assertEqual(sorted(heights), heights)
        self.assertGreaterEqual(heights[-1] - heights[0], 14)
        self.assertTrue(55 <= heights[1] <= 75)

    def test_green_crown_brown_trunk_and_a_crown_left_of_the_foot(self):
        image = palm("palm_medium")
        green = brown = 0
        for x in range(SIZE[0]):
            for y in range(SIZE[1]):
                r, g, b, a = image.get_at((x, y))
                if a and g > r + 30 and g > b + 20:
                    green += 1
                elif a and r > g + 30 and r > b + 20:
                    brown += 1
        self.assertGreater(green, 600)
        self.assertGreater(brown, 200)
        crown = [x for x in range(SIZE[0]) for y in range(25, 35) if image.get_at((x, y)).a]
        self.assertLess((min(crown) + max(crown)) / 2, FOOT[0])

    def test_a_click_hits_the_crown_and_trunk_and_misses_beside_them(self):
        obj = WorldObject.create(GridPos(5, 5), ObjectKind.TREE, variant="palm_tall")
        box = palm("palm_tall").get_bounding_rect()
        self.assertTrue(object_contains(obj, 0, -8))
        self.assertTrue(object_contains(obj, -4, -60))
        self.assertFalse(object_contains(obj, 0, box.top - FOOT[1] - 2))
        self.assertFalse(object_contains(obj, 12, -12))

    def test_wear_cuts_the_trunk_and_the_leaves_fall_green(self):
        body = palm("palm_medium")
        silhouette = pygame.mask.from_surface(body, 127)
        counts = []
        for stage in (1, 2, 3, 4):
            overlay = pygame.mask.from_surface(wear_art.wear_overlay(body, FOOT, ObjectKind.TREE, stage, 3, 1))
            counts.append(overlay.count())
            self.assertEqual(overlay.count(), overlay.overlap_area(silhouette, (0, 0)))
            rows = [y for x in range(SIZE[0]) for y in range(SIZE[1]) if overlay.get_at((x, y))]
            self.assertGreater(min(rows), FOOT[1] - 30)
        self.assertEqual(sorted(counts), counts)
        for variant in ORDER:
            self.assertIs(wear_art.PALM_LEAVES, wear_art.LEAVES[variant])
            self.assertIn(variant, TREES)

    def test_both_renderers_draw_the_palm_by_code(self):
        from spawnbound.prototype_art import PrototypeArtRenderer
        pygame.font.init()
        art = PrototypeArtRenderer(pygame.Surface((960, 540)), DEFAULT_CONFIG, ROOT / "assets/native_32/manifest.json")
        plain = PlaceholderRenderer(pygame.Surface((960, 540)), DEFAULT_CONFIG)
        obj = WorldObject.create(GridPos(0, 0), ObjectKind.TREE, variant="palm_small")
        self.assertNotIn(art.object_name(obj), art.art.images)
        self.assertIsNone(art.hit_test("object", obj, 0, -8))
        sprite, (fx, fy) = placed_palm("palm_small")
        for renderer in (art, plain):
            with self.subTest(renderer=type(renderer).__name__):
                body, foot = renderer._caster_image("object", obj)
                region = pygame.Rect(foot[0] - fx, foot[1] - fy, *sprite.get_size())
                self.assertEqual(pygame.image.tobytes(sprite, "RGBA"),
                                 pygame.image.tobytes(body.subsurface(region), "RGBA"))


class PalmPlacementTests(unittest.TestCase):
    def test_about_half_the_desert_plants_are_palms_in_three_sizes(self):
        picks = Counter(desert_palm(GridPos(x, y)) for x in range(-40, 40) for y in range(-40, 40))
        self.assertAlmostEqual(.5, picks[None] / sum(picks.values()), delta=.03)
        self.assertEqual(set(ORDER), set(picks) - {None})
        for seed in (1234, 7, 39658298):
            session = GameSession.create(seed, DEFAULT_CONFIG, chunk_preview_size=128)
            world = session.world
            found = Counter()
            for p, obj in world.objects.items():
                desert = world.tile_map.tile_at(p).biome is Biome.DRY
                if obj.kind is ObjectKind.TREE and obj.variant in PALMS:
                    with self.subTest(seed=seed, cell=p):
                        self.assertTrue(desert)
                        self.assertEqual(desert_palm(p), obj.variant)
                    found[obj.variant] += 1
                elif obj.kind is ObjectKind.CACTUS:
                    with self.subTest(seed=seed, cell=p):
                        self.assertIsNone(desert_palm(p))
                    found["cactus"] += 1
            with self.subTest(seed=seed):
                self.assertTrue(all(found[v] > 0 for v in ORDER + ("cactus",)))

    def test_a_palm_falls_to_the_axe_and_gives_wood(self):
        session = GameSession.create(1234, DEFAULT_CONFIG, chunk_preview_size=128)
        world = session.world
        sides = (GridPos(1, 0), GridPos(-1, 0), GridPos(0, 1), GridPos(0, -1))
        cell = next(p for p, o in sorted(world.objects.items()) if o.variant in PALMS
                    and any(world.is_walkable(p + d) and world.can_reach(p + d, p) for d in sides))
        session.player.position = next(cell + d for d in sides
                                       if world.is_walkable(cell + d) and world.can_reach(cell + d, cell))
        session.player.inventory.selected = 1
        before = session.player.inventory.quantity("wood")
        for _ in range(20):
            if cell not in world.objects:
                break
            session.player.energy = session.player.max_energy
            session.primary_action(cell)
        self.assertNotIn(cell, world.objects)
        self.assertEqual(before + 2, session.player.inventory.quantity("wood"))
        self.assertTrue(any(a.destroyed for a in session.afterimages))


if __name__ == "__main__":
    unittest.main()
