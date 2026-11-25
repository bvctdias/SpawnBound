import os
import sys
import unittest
from collections import Counter
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "dependencias")]
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame

from spawnbound import item_icons
from spawnbound.config import DEFAULT_CONFIG
from spawnbound.domain import generation
from spawnbound.domain.coordinates import GridPos
from spawnbound.domain.model import MUSHROOMS, Biome, ObjectKind, TileKind, WorldObject, mushroom_caps
from spawnbound.domain.session import FOOD, LIGHT_FOOD, GameSession
from spawnbound.mushroom_art import FOOT, SIZE, mushroom, mushroom_look, placed_mushroom
from spawnbound.renderer import PlaceholderRenderer
from spawnbound.view import object_contains

SEEDS = (1234, 7, 39658298)
AROUND = [GridPos(dx, dy) for dx in (-1, 0, 1) for dy in (-1, 0, 1) if dx or dy]
SIDES = [GridPos(1, 0), GridPos(-1, 0), GridPos(0, 1), GridPos(0, -1)]


def _session(seed=1234):
    return GameSession.create(seed, DEFAULT_CONFIG, chunk_preview_size=128)


class MushroomArtTests(unittest.TestCase):
    def test_every_cell_draws_inside_its_sprite_and_stands_on_its_foot(self):
        for variant in MUSHROOMS:
            for caps in ((1,) if variant == "morel" else (2, 3)):
                for arrangement in (0, 1):
                    with self.subTest(variant=variant, caps=caps, arrangement=arrangement):
                        box = mushroom(variant, caps, arrangement).get_bounding_rect()
                        self.assertTrue(box.left > 0 and box.top > 0 and box.right < SIZE[0] and box.bottom < SIZE[1])
                        self.assertGreaterEqual(box.bottom, FOOT[1])
                        self.assertLessEqual(box.bottom, FOOT[1] + 6)

    def test_colours_white_caps_brown_caps_and_a_pitted_orange_morel(self):
        def tally(image, test):
            return sum(1 for x in range(SIZE[0]) for y in range(SIZE[1])
                       if image.get_at((x, y)).a and test(*image.get_at((x, y))[:3]))
        white = mushroom("white_mushroom", 3, 0)
        self.assertGreater(tally(white, lambda r, g, b: min(r, g, b) > 225), 30)
        brown = mushroom("brown_mushroom", 3, 0)
        self.assertGreater(tally(brown, lambda r, g, b: r > g + 30 > b + 40 and r < 230), 40)
        self.assertEqual(0, tally(brown, lambda r, g, b: min(r, g, b) > 225 and abs(r - b) < 12 and r > 250))
        morel = mushroom("morel", 1, 0)
        self.assertGreater(tally(morel, lambda r, g, b: r > 200 and 130 < g < 210 and b < 130), 20)
        self.assertGreater(tally(morel, lambda r, g, b: r < 100 and g < 60), 8)
        self.assertGreater(morel.get_bounding_rect().height, white.get_bounding_rect().height)

    def test_the_cell_picks_caps_and_arrangement_and_the_drop_matches_the_caps(self):
        caps = Counter(mushroom_caps("white_mushroom", GridPos(x, y)) for x in range(30) for y in range(30))
        self.assertEqual({2, 3}, set(caps))
        self.assertAlmostEqual(.5, caps[2] / sum(caps.values()), delta=.1)
        self.assertEqual(1, mushroom_caps("morel", GridPos(4, 9)))
        for variant in MUSHROOMS:
            obj = WorldObject.create(GridPos(3, 8), ObjectKind.MUSHROOM, variant=variant)
            self.assertEqual(((variant, mushroom_caps(variant, obj.position)),), obj.drops)
        looks = {mushroom_look("white_mushroom", GridPos(x, 0)) for x in range(12)}
        self.assertGreater(len(looks), 2)

    def test_both_renderers_draw_mushrooms_by_code(self):
        from spawnbound.prototype_art import PrototypeArtRenderer
        pygame.font.init()
        art = PrototypeArtRenderer(pygame.Surface((960, 540)), DEFAULT_CONFIG, ROOT / "assets/native_32/manifest.json")
        plain = PlaceholderRenderer(pygame.Surface((960, 540)), DEFAULT_CONFIG)
        for variant in MUSHROOMS:
            obj = WorldObject.create(GridPos(2, 5), ObjectKind.MUSHROOM, variant=variant)
            self.assertNotIn(art.object_name(obj), art.art.images)
            sprite, (fx, fy) = placed_mushroom(variant, obj.position)
            for renderer in (art, plain):
                with self.subTest(variant=variant, renderer=type(renderer).__name__):
                    body, foot = renderer._caster_image("object", obj)
                    region = pygame.Rect(foot[0] - fx, foot[1] - fy, *sprite.get_size())
                    self.assertEqual(pygame.image.tobytes(sprite, "RGBA"),
                                     pygame.image.tobytes(body.subsurface(region), "RGBA"))

    def test_a_click_on_or_just_beside_the_caps_picks_them(self):
        obj = WorldObject.create(GridPos(2, 5), ObjectKind.MUSHROOM, variant="white_mushroom")
        sprite, (fx, fy) = placed_mushroom(obj.variant, obj.position)
        box = sprite.get_bounding_rect()
        self.assertTrue(object_contains(obj, box.centerx - fx, box.centery - fy))
        self.assertTrue(object_contains(obj, box.left - 2 - fx, box.centery - fy))
        self.assertFalse(object_contains(obj, box.left - 8 - fx, box.centery - fy))
        self.assertFalse(object_contains(obj, 0, box.top - fy - 8))

    def test_icons_and_names(self):
        names = {"white_mushroom": "Cogumelo branco", "brown_mushroom": "Cogumelo pardo", "morel": "Morchella"}
        for item, name in names.items():
            self.assertEqual(name, item_icons.ITEMS[item][0])
            self.assertEqual((32, 32), item_icons.icon(item).get_size())


class MushroomPlacementTests(unittest.TestCase):
    def test_groups_beside_rocks_white_in_the_desert_brown_in_the_forest_and_rare_morels(self):
        total = Counter()
        for seed in SEEDS:
            world = _session(seed).world
            found = Counter()
            for cell, obj in world.objects.items():
                if obj.kind is not ObjectKind.MUSHROOM:
                    continue
                tile = world.tile_map.tile_at(cell)
                with self.subTest(seed=seed, cell=cell):
                    self.assertIs(TileKind.GRASS, tile.kind)
                    self.assertEqual(tile.elevation, obj.elevation)
                    self.assertTrue(world.is_walkable(cell))
                    expected = {Biome.DRY: "white_mushroom", Biome.FOREST: "brown_mushroom"}[tile.biome]
                    self.assertIn(obj.variant, (expected, "morel"))
                    rocks = [cell + d for d in AROUND if (o := world.objects.get(cell + d)) is not None
                             and o.kind is ObjectKind.ROCK and world.tile_map.tile_at(cell + d).biome is tile.biome]
                    self.assertTrue(rocks)
                    self.assertTrue(any(generation.mushroom_patch(r) is not None for r in rocks))
                found[obj.variant] += 1
            with self.subTest(seed=seed):
                self.assertGreater(found["white_mushroom"], 8)
                self.assertGreater(found["brown_mushroom"], 4)
                self.assertLess(found["morel"], found["brown_mushroom"])
            total.update(found)
        self.assertGreater(total["morel"], 0)

    def test_mushrooms_leave_the_rest_of_the_island_as_it_was(self):
        with_mushrooms = _session(7).world
        with mock.patch.object(generation, "scatter_mushrooms", lambda world: None):
            without = _session(7).world
        kept = {p: (o.kind, o.variant) for p, o in with_mushrooms.objects.items() if o.kind is not ObjectKind.MUSHROOM}
        self.assertEqual({p: (o.kind, o.variant) for p, o in without.objects.items()}, kept)
        self.assertEqual(without.tile_map.tiles, with_mushrooms.tile_map.tiles)


class MushroomUseTests(unittest.TestCase):
    def _beside_a_mushroom(self, session, variant):
        world = session.world
        cell = next(p for p, o in sorted(world.objects.items()) if o.kind is ObjectKind.MUSHROOM
                    and o.variant == variant and any(world.is_walkable(p + d) and world.can_reach(p + d, p)
                                                     and world.object_at(p + d) is None for d in SIDES))
        session.player.position = next(cell + d for d in SIDES if world.is_walkable(cell + d)
                                       and world.can_reach(cell + d, cell) and world.object_at(cell + d) is None)
        return cell

    def test_one_click_picks_a_cell_without_a_tool_or_energy(self):
        session = _session()
        cell = self._beside_a_mushroom(session, "white_mushroom")
        caps = session.world.objects[cell].drops[0][1]
        session.player.energy = 30
        result = session.primary_action(cell)
        self.assertTrue(result.success)
        self.assertNotIn(cell, session.world.objects)
        self.assertEqual(caps, session.player.inventory.quantity("white_mushroom"))
        self.assertEqual(30, session.player.energy)
        self.assertIn("cogumelo branco", result.message)
        self.assertTrue(any(a.loot == "white_mushroom" and not a.destroyed for a in session.afterimages))

    def test_white_and_brown_give_a_little_energy_and_the_morel_more_and_a_heart(self):
        self.assertTrue(FOOD["white_mushroom"] < FOOD["brown_mushroom"] < FOOD["morel"] <= FOOD["cooked_meat"])
        self.assertEqual({"white_mushroom", "brown_mushroom", "berry", "carrot", "turnip", "pumpkin"},
                         set(LIGHT_FOOD))
        session = _session()
        player, bag = session.player, session.player.inventory
        bag.add("white_mushroom", 2)
        player.energy, player.hearts = 50, 5
        self.assertTrue(session.eat().success)
        self.assertEqual((50 + FOOD["white_mushroom"], 5), (player.energy, player.hearts))
        player.energy = player.max_energy
        self.assertFalse(session.eat().success)
        self.assertEqual(1, bag.quantity("white_mushroom"))
        bag.add("morel")
        player.energy = 50
        bag.selected = next(i for i, s in enumerate(bag.slots) if s and s.item == "morel")
        self.assertTrue(session.eat().success)
        self.assertEqual((50 + FOOD["morel"], 6), (player.energy, player.hearts))


if __name__ == "__main__":
    unittest.main()
