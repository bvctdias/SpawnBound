import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "dependencias")]

from spawnbound.config import DEFAULT_CONFIG
from spawnbound.domain.coordinates import GridPos
from spawnbound.domain.inventory import Stack
from spawnbound.domain.mobs import HEALTH, SWORD_DAMAGE, Mob, MobKind
from spawnbound.domain.model import OBJECT_SPECS, ObjectKind, WorldObject
from spawnbound.domain.session import ActionCode, GameSession
from spawnbound.domain.tools import AXE_STRENGTH, HAND_STRENGTH

EAST = GridPos(1, 0)
HANDS = (None, "pickaxe", "sickle", "sword")


class ToolTests(unittest.TestCase):
    def setUp(self):
        self.session = GameSession.create(1234, DEFAULT_CONFIG, chunk_preview_size=16)
        self.session.world.objects.clear()
        self.session.wildlife.mobs.clear()
        self.bag = self.session.player.inventory
        self.cell = self.session.player.position + EAST
        self.session.player.facing = EAST

    def hold(self, item):
        self.bag.slots[0] = Stack(item, 1) if item else None
        self.bag.selected = 0

    def put(self, kind, variant="default"):
        world = self.session.world
        obj = WorldObject.create(self.cell, kind, variant=variant, elevation=world.elevation_at(self.cell))
        world.objects[self.cell] = obj
        return obj

    def test_the_axe_fells_wood_three_times_faster_than_the_hand_or_another_tool(self):
        self.assertEqual(3, AXE_STRENGTH // HAND_STRENGTH)
        for kind in (ObjectKind.TREE, ObjectKind.FALLEN_LOG):
            for item, strength in (("axe", AXE_STRENGTH), *((hand, HAND_STRENGTH) for hand in HANDS)):
                with self.subTest(kind=kind, item=item):
                    self.session.player.energy = self.session.player.max_energy
                    obj = self.put(kind)
                    self.hold(item)
                    self.assertIs(ActionCode.RESOURCE_HIT, self.session.primary_action(self.cell).code)
                    self.assertEqual(OBJECT_SPECS[kind].durability - strength, obj.durability)

    def test_a_cactus_bushes_and_mushrooms_come_off_with_anything(self):
        for item in ("axe", *HANDS):
            with self.subTest(item=item):
                self.hold(item)
                cactus = self.put(ObjectKind.CACTUS)
                self.session.primary_action(self.cell)
                self.assertEqual(OBJECT_SPECS[ObjectKind.CACTUS].durability - AXE_STRENGTH, cactus.durability)
                self.put(ObjectKind.MUSHROOM, "white_mushroom")
                self.assertIs(ActionCode.RESOURCE_GATHERED, self.session.primary_action(self.cell).code)
                self.put(ObjectKind.BERRY_BUSH)
                self.assertIs(ActionCode.RESOURCE_GATHERED, self.session.primary_action(self.cell).code)

    def test_stone_needs_a_pickaxe(self):
        for item in (None, "axe", "sickle", "sword"):
            with self.subTest(item=item):
                self.hold(item)
                self.put(ObjectKind.ROCK)
                self.assertIs(ActionCode.TOOL_REQUIRED, self.session.primary_action(self.cell).code)
        self.hold("pickaxe")
        self.assertIs(ActionCode.RESOURCE_HIT, self.session.primary_action(self.cell).code)

    def test_copper_asks_for_the_stone_pickaxe_and_quartz_for_the_copper_one(self):
        for variant, weaker, needed in (("copper_ore", "pickaxe", "stone_pickaxe"),
                                        ("quartz_ore", "stone_pickaxe", "copper_pickaxe")):
            with self.subTest(variant=variant):
                ore = self.put(ObjectKind.ROCK, variant)
                self.hold(weaker)
                result = self.session.primary_action(self.cell)
                self.assertIs(ActionCode.TOOL_UPGRADE_REQUIRED, result.code)
                self.assertEqual(result.message, self.session.notice)
                self.assertEqual(ore.spec.durability, ore.durability)
                self.hold(needed)
                self.assertIs(ActionCode.RESOURCE_HIT, self.session.primary_action(self.cell).code)
        self.put(ObjectKind.ROCK, "coal_ore")
        self.hold("pickaxe")
        self.assertIs(ActionCode.RESOURCE_HIT, self.session.primary_action(self.cell).code)

    def pig(self):
        location = self.session.world.surface_position(self.cell)
        mob = Mob(9, MobKind.PIG, HEALTH[MobKind.PIG], location, location, 0.)
        self.session.wildlife.mobs[9] = mob
        return mob

    def test_the_sword_is_the_best_weapon_and_the_rest_hurt_by_one(self):
        for item, damage in (("sword", SWORD_DAMAGE), (None, 1), ("axe", 1), ("pickaxe", 1), ("sickle", 1)):
            with self.subTest(item=item):
                self.session.player.energy = self.session.player.max_energy
                mob = self.pig()
                self.hold(item)
                self.assertIs(ActionCode.MOB_HIT, self.session.attack_mob(9).code)
                self.assertEqual(HEALTH[MobKind.PIG] - damage, mob.hp)

    def test_the_sword_needs_as_many_blows_as_before(self):
        before = {MobKind.CHICKEN: 1, MobKind.PIG: 2, MobKind.SKELETON: 4, MobKind.DEER: 7, MobKind.SNAKE: 3,
                  MobKind.SPIDER: 5, MobKind.ARMADILLO: 3, MobKind.MINE_MONSTER: 8}
        for kind, blows in before.items():
            self.assertEqual(blows, -(-HEALTH[kind] // SWORD_DAMAGE), kind)

    def test_the_sandworm_shell_by_tool(self):
        location = self.session.world.surface_position(self.cell)
        for item, damage in (("sword", 2), ("pickaxe", 1), ("stone_pickaxe", 2), ("copper_pickaxe", 3),
                             ("quartz_pickaxe", 4), ("axe", 1), (None, 1)):
            with self.subTest(item=item):
                self.session.player.energy = self.session.player.max_energy
                worm = Mob(5, MobKind.SANDWORM, HEALTH[MobKind.SANDWORM], location, location, 0.)
                self.session.wildlife.mobs[5] = worm
                self.hold(item)
                self.session.attack_mob(5)
                self.assertEqual(HEALTH[MobKind.SANDWORM] - damage, worm.hp)


if __name__ == "__main__":
    unittest.main()
