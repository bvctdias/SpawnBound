import unittest

from test_wild_fauna import flat_session, run
import pygame
from spawnbound.domain.coordinates import GridPos, WorldPos
from spawnbound.domain.inventory import Stack
from spawnbound.domain.mobs import MobKind, Wildlife
from spawnbound.domain.model import Biome, TileKind
from spawnbound.domain.session import ActionCode
from spawnbound.mob_art import head_top, pick_pixels, sprite, sprite_layout
from spawnbound.states import GameplayState
from spawnbound.input import InputFrame
from spawnbound.view import camera_origin, screen_center


class SandwormTests(unittest.TestCase):
    def setUp(self):
        self.s = flat_session()
        self.life = self.s.wildlife
        self.life._lairs = [(GridPos(10, 10), 0)]
        self.player = self.s.world.surface_position(GridPos(10, 10))

    def emerge(self):
        self.life.tick(.05, self.player)
        p = self.player
        self.player = WorldPos(p.x + .03, p.y, p.z)
        self.s.player.place(self.player)
        self.life.tick(.05, self.player)
        return self.life.mobs[self.life._worm_id]

    def test_only_connected_deserts_of_at_least_120_cells(self):
        world = self.s.world
        world.tile_map.tiles.clear()
        for i in range(119):
            world.tile_map.add(GridPos(30 + i % 12, 30 + i // 12), TileKind.GRASS, biome=Biome.DRY)
        world.tile_map.add(GridPos(90, 90), TileKind.GRASS, biome=Biome.DRY)
        self.assertFalse(Wildlife(world)._desert_of)
        world.tile_map.add(GridPos(41, 39), TileKind.GRASS, biome=Biome.DRY)
        life = Wildlife(world)
        self.assertEqual(120, len(life._desert_of))
        self.assertNotIn(GridPos(90, 90), life._desert_of)

    def test_motion_bite_retreat_and_return_with_same_health(self):
        run(self.life, 4., self.player)
        self.assertIsNone(self.life._worm_id)
        worm = self.emerge()
        self.assertTrue(run(self.life, 2.75, self.player))
        self.assertEqual("sandworm", self.life.last_blow)
        self.s.player.inventory.selected = 0
        self.s.attack_mob(worm.id)
        run(self.life, 1.5, self.player)
        self.assertNotIn(worm.id, self.life.mobs)
        self.assertEqual(0, self.s.player.inventory.quantity("sandworm_shell"))
        returned = self.emerge()
        self.assertEqual(11, returned.hp)

    def test_click_on_exposed_head_hits_with_equipped_pickaxe(self):
        worm = self.emerge()
        run(self.life, 1.2, self.player)
        self.s.player.inventory.selected = 0
        state = GameplayState(self.s, self.s.config)
        origin = camera_origin(self.s, self.s.config, state.visual_position3d)
        x, y = screen_center(worm.location, origin, self.s.config)
        dx, dy = head_top(worm)
        click = self.s.config.world_to_view((x + dx, y + dy))
        state.step(InputFrame(destination_click=click), 1/60)
        for _ in range(20):
            state.step(InputFrame(), 1/60)
        self.assertEqual(11, worm.hp)

    def test_pickaxe_tiers_sword_and_shell(self):
        worm = self.emerge()
        pack = self.s.player.inventory
        pack.selected = 0
        for _ in range(5):
            self.assertEqual(ActionCode.MOB_HIT, self.s.attack_mob(worm.id).code)
        self.assertEqual(7, worm.hp)
        for tool, damage in (("stone_pickaxe", 2), ("copper_pickaxe", 3), ("quartz_pickaxe", 4), ("sword", 2)):
            pack.slots[0] = Stack(tool, 1)
            worm.hp = 7
            self.s.attack_mob(worm.id)
            self.assertEqual(7 - damage, worm.hp)
        pack.selected = 1
        worm.hp = 7
        self.assertEqual(ActionCode.MOB_HIT, self.s.attack_mob(worm.id).code)
        self.assertEqual(6, worm.hp)
        pack.selected = 0
        worm.hp = 1
        for i in range(4, len(pack.slots)):
            pack.slots[i] = Stack("stone", 64)
        energy = self.s.player.energy
        self.s.attack_mob(worm.id)
        self.assertEqual((energy, 1), (self.s.player.energy, worm.hp))
        pack.slots[-1] = None
        self.assertEqual(ActionCode.MOB_DEFEATED, self.s.attack_mob(worm.id).code)
        self.assertEqual(1, pack.quantity("sandworm_shell"))
        self.assertNotIn(worm.id, self.life.mobs)
        self.life.tick(.05, self.player)
        self.assertIsNone(self.life._worm_id)
        self.assertEqual({0}, self.life._lair_dead, "killed, it never comes back (DEC-083)")
        self.s.player.place(self.player)
        self.life.tick(.05, WorldPos(self.player.x + .03, self.player.y, self.player.z))
        self.assertIsNone(self.life._worm_id)
        self.assertEqual(1, pack.quantity("sandworm_shell"))

    def test_all_animation_frames_match_click_mask_in_both_directions(self):
        worm = self.emerge()
        _, anchor = sprite_layout(worm.kind)
        for frame in range(31):
            for left in (False, True):
                worm.worm_frame, worm.left = frame, left
                body = sprite(MobKind.SANDWORM, left, frame, "idle", 1)
                pixels = pick_pixels(worm)
                self.assertTrue(pixels)
                self.assertTrue(all(body.get_at((anchor[0] + x, anchor[1] + y)).a for x, y in pixels))
                self.assertEqual(len(pixels), pygame.mask.from_surface(body).count())
