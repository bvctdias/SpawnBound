from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
ROOT = Path(__file__).resolve().parents[1]
SOURCE_ROOT = ROOT / "src"
if str(SOURCE_ROOT) not in sys.path:
    sys.path.insert(0, str(SOURCE_ROOT))

import pygame

from spawnbound import wear_art
from spawnbound.animation import MotionKind, PlayerPose
from spawnbound.config import DEFAULT_CONFIG
from spawnbound.domain.coordinates import GridPos
from spawnbound.domain.inventory import Stack
from spawnbound.domain.mobs import Arrow
from spawnbound.domain.model import ObjectKind, TileKind, WorldObject
from spawnbound.domain.session import (HURT_SECONDS, IMPACT_SECONDS, REVIVE_SECONDS, ActionCode,
                                       GameSession)
from spawnbound.input import InputFrame
from spawnbound.inventory_hud import InventoryHUD
from spawnbound.pixel_font import PixelFont
from spawnbound.item_icons import HELD, ITEMS, held_tool, icon
from spawnbound.prototype_art import PrototypeArtRenderer
from spawnbound.sprites import PlayerSprites
from spawnbound.states import GameplayState

MANIFEST = ROOT / "assets/native_32/manifest.json"


def opaque(surface: pygame.Surface) -> int:
    return pygame.mask.from_surface(surface).count()


class StrikeEffectTests(unittest.TestCase):
    def setUp(self) -> None:
        self.session = GameSession.create(seed=1234, config=DEFAULT_CONFIG, chunk_preview_size=8)
        self.session.world.objects.clear()
        self.session.player.energy = self.session.player.max_energy = 10 ** 6

    def _strike(self, kind, variant="", side=GridPos(1, 0)):
        target = GridPos(3, 3)
        obj = WorldObject.create(target, kind, variant=variant)
        self.session.world.objects[target] = obj
        self.session.player.position = target - side
        bag = self.session.player.inventory
        bag.slots[bag.selected] = Stack("axe" if kind is ObjectKind.TREE else "stone_pickaxe", 1)
        return target, obj, self.session.primary_action(target)

    def test_a_strike_that_does_not_break_shakes_the_resource_away_from_the_player(self):
        for side, push in ((GridPos(1, 0), 1), (GridPos(0, 1), -1)):
            with self.subTest(side=side):
                self.session.afterimages.clear()
                target, tree, result = self._strike(ObjectKind.TREE, "broadleaf", side)
                self.assertEqual(ActionCode.RESOURCE_HIT, result.code)
                [effect] = self.session.afterimages
                self.assertTrue(effect.impact)
                self.assertIs(tree, effect.subject)
                self.assertIsNone(effect.loot)
                self.assertEqual(push, effect.push)
                self.session.advance_time(IMPACT_SECONDS - .01)
                self.assertEqual(1, len(self.session.afterimages))
                self.session.advance_time(.02)
                self.assertFalse(self.session.afterimages)

    def test_the_final_strike_records_only_the_break(self):
        target = GridPos(3, 3)
        rock = WorldObject.create(target, ObjectKind.ROCK)
        rock.durability = 1
        self.session.world.objects[target] = rock
        self.session.player.position = target - GridPos(1, 0)
        self.assertEqual(ActionCode.RESOURCE_GATHERED, self.session.primary_action(target).code)
        [effect] = self.session.afterimages
        self.assertTrue(effect.destroyed)
        self.assertFalse(effect.impact)

    def test_the_break_takes_over_from_strikes_still_playing(self):
        target, tree, result = self._strike(ObjectKind.TREE, "pine_dark")
        self.assertTrue(self.session.afterimages[0].impact)
        tree.durability = 1
        self.assertEqual(ActionCode.RESOURCE_GATHERED, self.session.primary_action(target).code)
        self.assertEqual([(True, False)], [(e.destroyed, e.impact) for e in self.session.afterimages])

    def test_a_mine_wall_strike_sheds_chips_without_a_body(self):
        world = self.session.world
        target = GridPos(3, 3)
        world.tile_map.add(target, TileKind.CAVE_WALL)
        self.session.player.position = target - GridPos(1, 0)
        self.assertEqual(ActionCode.RESOURCE_HIT, self.session.primary_action(target).code)
        [effect] = self.session.afterimages
        self.assertTrue(effect.impact)
        self.assertIsNone(effect.subject)


class WearArtTests(unittest.TestCase):
    def setUp(self) -> None:
        import json
        self.spec = json.loads(MANIFEST.read_text(encoding="utf-8"))

    def _sprite(self, name):
        entry = self.spec["sprites"][name]
        return pygame.image.load(str(MANIFEST.parent / entry["file"])), tuple(entry["pivot"])

    def test_wear_grows_with_each_stage_and_stays_inside_the_silhouette(self):
        for name, kind in (("tree_pine_dark", ObjectKind.TREE), ("tree_broadleaf", ObjectKind.TREE),
                           ("rock_surface", ObjectKind.ROCK), ("rock_cave", ObjectKind.ROCK),
                           ("log_northwest", ObjectKind.FALLEN_LOG), ("cactus_column", ObjectKind.CACTUS)):
            body, foot = self._sprite(name)
            silhouette = pygame.mask.from_surface(body, 127)
            counts = []
            for stage in (1, 2, 3, 4):
                overlay = wear_art.wear_overlay(body, foot, kind, stage, 17, 1)
                painted = pygame.mask.from_surface(overlay)
                counts.append(painted.count())
                with self.subTest(sprite=name, stage=stage):
                    self.assertGreater(painted.count(), 0)
                    self.assertEqual(painted.count(), painted.overlap_area(silhouette, (0, 0)))
            with self.subTest(sprite=name):
                self.assertEqual(sorted(counts), counts)
                self.assertGreater(counts[-1], counts[0])
            self.assertEqual(pygame.image.tobytes(wear_art.wear_overlay(body, foot, kind, 2, 5, 1), "RGBA"),
                             pygame.image.tobytes(wear_art.wear_overlay(body, foot, kind, 2, 5, 1), "RGBA"))

    def test_a_struck_body_flashes_sways_from_the_foot_and_comes_to_rest(self):
        body, foot = self._sprite("tree_broadleaf")
        rest = pygame.image.tobytes(body, "RGBA")
        flash = wear_art.struck(body, foot, ObjectKind.TREE, 0., 1, 1)
        self.assertNotEqual(rest, pygame.image.tobytes(flash, "RGBA"))
        swayed = wear_art.struck(body, foot, ObjectKind.TREE, wear_art.FLASH_SECONDS + .02, 1, 1)
        rows = body.get_bounding_rect()
        top = pygame.Rect(0, rows.top, body.get_width(), 8)
        base = pygame.Rect(0, foot[1] - 3, body.get_width(), 3)
        self.assertNotEqual(pygame.image.tobytes(body.subsurface(top), "RGBA"),
                            pygame.image.tobytes(swayed.subsurface(top), "RGBA"))
        self.assertEqual(pygame.image.tobytes(body.subsurface(base), "RGBA"),
                         pygame.image.tobytes(swayed.subsurface(base), "RGBA"))
        settled = wear_art.struck(body, foot, ObjectKind.TREE, wear_art.SHAKE_SECONDS, 1, 1)
        self.assertEqual(rest, pygame.image.tobytes(settled, "RGBA"))

    def test_a_shattered_rock_flies_apart_and_fades(self):
        body, foot = self._sprite("rock_surface")
        early = wear_art.burst_pieces(body, foot, .02, 1, 1)
        late = wear_art.burst_pieces(body, foot, .30, 1, 1)
        self.assertEqual(4, len(early))
        spread = lambda pieces: max(p[1][0] for p in pieces) - min(p[1][0] for p in pieces)
        self.assertGreater(spread(late), spread(early))
        self.assertLess(late[0][0].get_alpha(), 255)


class StrikeRenderingTests(unittest.TestCase):
    def setUp(self) -> None:
        pygame.font.init()
        self.session = GameSession.create(seed=1234, config=DEFAULT_CONFIG, chunk_preview_size=16)
        self.session.wildlife.mobs.clear()
        world = self.session.world
        self.target = world.spawn + GridPos(2, -2)
        for dx in range(-2, 3):
            for dy in range(-2, 3):
                world.objects.pop(self.target + GridPos(dx, dy), None)
        self.session.player.inventory.selected = 1
        self.tree = WorldObject.create(self.target, ObjectKind.TREE, variant="broadleaf")
        self.tree.elevation = world.elevation_at(self.target)
        world.objects[self.target] = self.tree
        self.session.player.place(world.surface_position(self.target + GridPos(0, 1)))
        self.session.player.energy = self.session.player.max_energy = 10 ** 6

    def _frame(self, renderer):
        renderer.draw_gameplay(self.session, debug=False)
        return pygame.image.tobytes(renderer._world_screen, "RGB")

    def test_the_shake_is_drawn_live_and_never_baked_into_the_cached_scene(self):
        screen = pygame.Surface((960, 540))
        renderer = PrototypeArtRenderer(screen, DEFAULT_CONFIG, MANIFEST)
        rest = self._frame(renderer)
        self.assertEqual(ActionCode.RESOURCE_HIT, self.session.primary_action(self.target).code)
        self.session.advance_time(wear_art.FLASH_SECONDS + .02)
        self.assertNotEqual(rest, self._frame(renderer))
        self.session.advance_time(IMPACT_SECONDS)
        self.assertFalse(self.session.afterimages)
        settled = self._frame(renderer)
        fresh = PrototypeArtRenderer(pygame.Surface((960, 540)), DEFAULT_CONFIG, MANIFEST)
        self.assertEqual(self._frame(fresh), settled)

    def test_every_break_animates_until_the_body_is_gone(self):
        renderer = PrototypeArtRenderer(pygame.Surface((960, 540)), DEFAULT_CONFIG, MANIFEST)
        for kind, variant in ((ObjectKind.TREE, "pine_light"), (ObjectKind.ROCK, "quartz_ore"),
                              (ObjectKind.FALLEN_LOG, "northwest"), (ObjectKind.CACTUS, "paddle")):
            with self.subTest(kind=kind):
                self.session.afterimages.clear()
                obj = WorldObject.create(self.target, kind, variant=variant)
                obj.elevation = self.session.world.elevation_at(self.target)
                obj.durability = 1
                self.session.world.objects[self.target] = obj
                bag = self.session.player.inventory
                bag.slots[bag.selected] = Stack("quartz_pickaxe" if kind is ObjectKind.ROCK else "axe", 1)
                self.assertEqual(ActionCode.RESOURCE_GATHERED, self.session.primary_action(self.target).code)
                frames = []
                for _ in range(5):
                    frames.append(self._frame(renderer))
                    self.session.advance_time(.1)
                self.assertEqual(5, len(set(frames)))


class HurtTests(unittest.TestCase):
    def setUp(self) -> None:
        pygame.font.init()
        self.session = GameSession.create(seed=1234, config=DEFAULT_CONFIG, chunk_preview_size=16)
        self.session.wildlife.mobs.clear()
        self.state = GameplayState(self.session, DEFAULT_CONFIG)

    def _arrow_hit(self, hearts=3):
        s = self.session
        s.player.hearts = hearts
        start = s.player.position3d
        s.wildlife.arrows.append(Arrow(start, start, .2))
        self.state.step(InputFrame(), .02)

    def test_an_arrow_plays_the_hurt_pose_then_the_body_blinks_while_guarded(self):
        self._arrow_hit()
        self.assertEqual(MotionKind.HURT, self.state.player_pose.motion)
        self.assertGreater(self.session.wildlife.grace, 0)
        self.state.step(InputFrame(), HURT_SECONDS)
        self.assertNotEqual(MotionKind.HURT, self.state.player_pose.motion)

    def test_every_atlas_has_a_hurt_clip_in_all_eight_directions(self):
        sprites = PlayerSprites.from_atlas(MANIFEST.parent / "player/animation.json")
        for clips in (sprites.clips, sprites.unarmed, *sprites.upgrades.values()):
            hurt = [key for key in clips if key[0] is MotionKind.HURT]
            self.assertEqual(8, len(hurt))
            for key in hurt:
                self.assertEqual(4, len(clips[key].frames))

    def test_the_hit_reaction_flashes_knocks_back_and_returns(self):
        screen = pygame.Surface((960, 540))
        renderer = PrototypeArtRenderer(screen, DEFAULT_CONFIG, MANIFEST)
        s = self.session
        frames = {}
        for label, hurt, grace in (("rest", 0., 0.), ("flash", HURT_SECONDS * .95, 1.4),
                                   ("red", .25, 1.3), ("guard", 0., .85)):
            s.hurt_time, s.wildlife.grace, s.hurt_from = hurt, grace, (1., 0.)
            pose = self.state.player_pose
            renderer.draw_gameplay(s, debug=False, player_pose=pose)
            frames[label] = pygame.image.tobytes(renderer._world_screen, "RGB")
        self.assertEqual(4, len(set(frames.values())))

    def test_the_lost_heart_bursts_in_the_bar(self):
        hud = InventoryHUD(PixelFont())
        player = self.session.player
        player.hearts = 2
        images = []
        for hurt in (0., 1., .4):
            surface = pygame.Surface((960, 540), pygame.SRCALPHA)
            hud.draw_bar(surface, DEFAULT_CONFIG, player, hurt=hurt)
            images.append(pygame.image.tobytes(surface, "RGBA"))
        self.assertEqual(3, len(set(images)))

    def test_losing_the_last_heart_fades_back_in_at_the_camp(self):
        self._arrow_hit(hearts=1)
        s = self.session
        self.assertEqual(s.world.spawn, s.player.position)
        self.assertGreater(s.revive_time, REVIVE_SECONDS - .1)
        renderer = PrototypeArtRenderer(pygame.Surface((960, 540)), DEFAULT_CONFIG, MANIFEST)
        renderer.draw_gameplay(s, debug=False)
        dark = pygame.transform.average_color(renderer._world_screen)
        s.advance_time(REVIVE_SECONDS)
        renderer.draw_gameplay(s, debug=False)
        light = pygame.transform.average_color(renderer._world_screen)
        self.assertLess(sum(dark[:3]), sum(light[:3]) / 3)


class InventoryArtTests(unittest.TestCase):
    def test_icons_are_chunky_outlined_shapes(self):
        for item in ITEMS:
            image = icon(item, 1)
            with self.subTest(item=item):
                self.assertEqual((16, 16), image.get_size())
                self.assertGreater(opaque(image), 60)
                mask = pygame.mask.from_surface(image)
                for x, y in mask.outline():
                    self.assertLess(sum(image.get_at((x, y))[:3]), 120)

    def test_the_held_pickaxe_is_the_lighter_version_of_its_icon(self):
        from spawnbound.domain.tools import PICKAXES, TOOLS
        self.assertEqual(TOOLS, set(HELD))
        for tool in PICKAXES:
            with self.subTest(tool=tool):
                self.assertLess(opaque(held_tool(tool)), opaque(icon(tool, 1)))
                self.assertGreater(opaque(held_tool(tool)), 30)


if __name__ == "__main__":
    unittest.main()
