import os
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch

os.environ.setdefault("SDL_AUDIODRIVER", "dummy")
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "dependencias")]

from spawnbound.audio import AudioManager, STEP_VARIANTS, ambient_levels, background_at
from spawnbound.animation import MotionKind, PlayerPose
from spawnbound.domain.daylight import DayPhase
from spawnbound.config import DEFAULT_CONFIG
from spawnbound.domain.coordinates import GridPos, WorldPos
from spawnbound.domain.inventory import Stack
from spawnbound.domain.mobs import Mob, MobKind
from spawnbound.domain.model import Biome, ObjectKind, SpaceKind, TileKind, WorldObject
from spawnbound.domain.session import Afterimage, GameSession
from spawnbound.input import InputFrame
from spawnbound.menus import MainMenuState, layout
from spawnbound.states import ClickIntent, GameplayState, StateStack
from spawnbound.wear_art import TREE_LANDING_SECONDS


class AudioTests(unittest.TestCase):
    def setUp(self):
        self.audio = AudioManager()
        self.addCleanup(self.audio.close)
        session = GameSession.create(12, DEFAULT_CONFIG)
        self.game = GameplayState(session, DEFAULT_CONFIG, play_sound=self.audio.play)
        self.stack = StateStack(self.game)
        self.audio.enter(self.stack)

    def test_main_menu_uses_real_loop_game_and_pause_have_only_effects(self):
        from PPlay.sound import Music, Sound
        self.assertIsInstance(self.audio.music, Music)
        self.assertTrue(all(isinstance(effect, Sound) for effect in self.audio.sounds.values()))
        menu = SimpleNamespace(gameplay=None)
        self.audio.enter(menu)
        self.assertTrue(self.audio.music.is_playing())
        self.audio.enter(self.stack)
        # O mixer só conclui a parada no próximo bloco de áudio.
        import time
        deadline = time.monotonic() + .5
        while self.audio.music.is_playing() and time.monotonic() < deadline:
            time.sleep(.01)
        self.assertFalse(self.audio.music.is_playing())
        self.stack.step(InputFrame(pause_pressed=True), .016)
        self.audio.update(self.stack, .016)
        self.assertFalse(self.audio.music.is_playing())
        self.audio.enter(menu)
        self.assertTrue(self.audio.music.is_playing())

    def test_tree_cracks_lands_and_loot_flies_once_each(self):
        pos = self.game.session.player.position
        tree = WorldObject.create(pos, ObjectKind.TREE)
        effect = Afterimage(tree.position3d, self.game.session.world.space_id, tree, "wood", destroyed=True)
        self.game.session.afterimages.append(effect)
        with patch.object(self.audio, "play") as play:
            for elapsed in [0., .1, TREE_LANDING_SECONDS, TREE_LANDING_SECONDS, .76, .8]:
                effect.elapsed = elapsed
                self.audio.update(self.stack, .016)
            self.assertEqual([call.args[0] for call in play.call_args_list], ["wood_break", "tree_land", "pickup"])
            self.audio.enter(self.stack)
            play.reset_mock()
            self.audio.update(self.stack, .016)
            play.assert_not_called()

    def test_mining_plays_one_chip_per_hit_then_a_distinct_break(self):
        session = self.game.session
        target = next(p for p in session.world.objects if session.world.objects[p].kind is ObjectKind.ROCK)
        rock = session.world.objects[target]
        side = next(target + d for d in (GridPos(0, 1), GridPos(0, -1), GridPos(1, 0), GridPos(-1, 0))
                    if session.world.tile_map.is_walkable(target + d))
        session.player.place(session.world.surface_position(side))
        session.player.inventory.slots[0] = Stack("stone_pickaxe", 1)
        with patch.object(self.audio, "play") as play:
            self.assertTrue(session.primary_action(target).success)
            self.audio.update(self.stack, .016)
            self.audio.update(self.stack, .016)
            rock.durability = 1
            self.assertTrue(session.primary_action(target).success)
            self.audio.update(self.stack, .016)
            self.assertEqual([c.args[0] for c in play.call_args_list], ["stone_hit", "stone_break"])

    def test_menu_only_clicks_an_enabled_button(self):
        menu = MainMenuState(DEFAULT_CONFIG, Mock(), play_sound=Mock())
        menu.step(InputFrame(destination_click=(0, 0)), .016)
        menu.play_sound.assert_not_called()
        rects = layout(menu.items(), DEFAULT_CONFIG, menu.top)
        new = next(rect for item, rect in zip(menu.items(), rects) if item.key == "new")
        menu.step(InputFrame(destination_click=new.center), .016)
        menu.play_sound.assert_called_once_with("click")

    def test_ambient_distance_and_pause(self):
        world = self.game.session.world
        world.placed_fires.add(GridPos(10, 10))
        world.tile_map.ocean_island_size = 64
        world.sea_cells = {GridPos(10, 10)}
        for offset, volume in [(0, 20), (3, 10), (7, 0)]:
            point = WorldPos(10+offset, 10, 0)
            self.assertEqual({"fire": volume, "sea": volume}, ambient_levels(world, point))
        self.game.session.player.place(WorldPos(10, 10, 0))
        fire = self.audio.sounds["fire"] = Mock()
        self.audio.update(self.stack, .016)
        self.audio.update(self.stack, .2)
        fire.play.assert_called_once_with(-1)
        self.stack.step(InputFrame(inventory_pressed=True), .016)
        self.audio.update(self.stack, .016)
        fire.stop.assert_called_once()

    def test_steps_vary_and_swimming_has_one_wash_per_stroke(self):
        session = self.game.session
        cell = session.player.position
        for kind, biome, cue, count in (
                (TileKind.GRASS, Biome.FOREST, "step_grass", 12),
                (TileKind.GRASS, Biome.DRY, "step_sand", 12),
                (TileKind.CAVE_FLOOR, Biome.DRY, "step_stone", 12),
                (TileKind.WOOD_FLOOR, Biome.FOREST, "step_wood", 12),
                (TileKind.WATER, Biome.FOREST, "swim", 4)):
            with self.subTest(cue=cue), patch.object(self.audio, "play") as play:
                session.world.tile_map.add(cell, kind, biome=biome)
                self.audio.enter(self.stack)
                motion = MotionKind.SWIM if kind is TileKind.WATER else MotionKind.WALK
                actor = SimpleNamespace(session=session)
                for tick in range(240):
                    actor.visual_position = (cell.x + (tick + 1) / 60, cell.y)
                    actor.player_pose = PlayerPose(motion, session.player.facing, tick / 60)
                    self.audio._footsteps(actor, 1/60)
                names = [call.args[0] for call in play.call_args_list]
                self.assertEqual(count, len(names))
                self.assertTrue(set(names) <= set(STEP_VARIANTS[cue]))
                self.assertTrue(all(a != b for a, b in zip(names, names[1:])))
                play.reset_mock()
                for tick in range(180):
                    actor.player_pose = PlayerPose(motion, session.player.facing, tick / 60)
                    self.audio._footsteps(actor, 1/60)
                play.assert_not_called()

    def test_biome_daylight_mine_and_shelter_select_their_own_background(self):
        world = self.game.session.world
        cell = self.game.session.player.position
        for biome, day_sound in ((Biome.FOREST, "forest"), (Biome.MEADOW, "meadow"), (Biome.DRY, "dry_wind")):
            world.tile_map.add(cell, TileKind.GRASS, biome=biome)
            self.assertEqual(day_sound, background_at(world, cell, DayPhase.DAY))
            expected = "dry_wind" if biome is Biome.DRY else "night"
            self.assertEqual(expected, background_at(world, cell, DayPhase.NIGHT))
        world.tile_map.add(cell, TileKind.WATER)
        world.sea_cells = {cell}
        self.assertIsNone(background_at(world, cell, DayPhase.DAY))
        for space, cue in ((SpaceKind.CAVE, "cave"), (SpaceKind.INTERIOR, "shelter")):
            world.space_kind = space
            self.assertEqual(cue, background_at(world, cell, DayPhase.NIGHT))

    def test_crossing_a_biome_fades_previous_loop_and_pause_stops_both(self):
        world = self.game.session.world
        cell = self.game.session.player.position
        world.tile_map.add(cell, TileKind.GRASS, biome=Biome.FOREST)
        forest = self.audio.sounds["forest"] = Mock()
        desert = self.audio.sounds["dry_wind"] = Mock()
        for _ in range(7):
            self.audio.update(self.stack, .15)
        forest.play.assert_called_once_with(-1)
        initial = self.audio.ambient["forest"]
        world.tile_map.add(cell, TileKind.GRASS, biome=Biome.DRY)
        self.audio.update(self.stack, .15)
        self.assertLess(self.audio.ambient["forest"], initial)
        self.assertGreater(self.audio.ambient["forest"], 0)
        desert.play.assert_called_once_with(-1)
        self.stack.step(InputFrame(pause_pressed=True), .016)
        self.audio.update(self.stack, .016)
        self.assertFalse(self.audio.ambient)
        forest.stop.assert_called_once()
        desert.stop.assert_called_once()

    def test_enemy_sound_follows_attack_once_and_stays_in_its_world(self):
        session = self.game.session
        point = session.player.position3d
        mob = Mob(918, MobKind.SNAKE, 6, point, point, 0.)
        session.wildlife.mobs = {mob.id: mob}
        hiss = self.audio.sounds["snake_hiss"] = Mock()
        snap = self.audio.sounds["bite_snap"] = Mock()
        mob.windup = .3
        self.audio.update(self.stack, .016)
        self.audio.update(self.stack, .016)
        hiss.play.assert_called_once()
        mob.windup, mob.lunge = 0, .2
        self.audio.update(self.stack, .016)
        snap.play.assert_called_once()
        mob.end = WorldPos(point.x + 16, point.y, point.z)
        mob.windup = .3
        self.audio.update(self.stack, .016)
        mob.end = point
        self.audio.update(self.stack, .016)
        hiss.play.assert_called_once()
        self.audio.enter(self.stack)
        self.audio.update(self.stack, .016)
        hiss.play.assert_called_once()
        with patch.object(session.wildlife, "world", object()):
            mob.windup, mob.lunge = 0., .2
            self.audio.update(self.stack, .016)
            snap.play.assert_called_once()

    def test_worm_bite_guardian_landing_and_bow_match_the_visible_action(self):
        session = self.game.session
        pos = session.player.position3d
        worm = Mob(301, MobKind.SANDWORM, 12, pos, pos, 0., worm_phase="bite", worm_frame=25)
        boss = Mob(302, MobKind.GUARDIAN, 40, pos, pos, 0., boss=SimpleNamespace(stage="air"))
        archer = Mob(303, MobKind.SKELETON, 8, pos, pos, 0.)
        session.wildlife.mobs = {mob.id: mob for mob in (worm, boss, archer)}
        cues = [Mock(), Mock(), Mock()]
        for name, sound in zip(("bite_snap", "guardian_slam", "bow_release"), cues):
            self.audio.sounds[name] = sound
        self.audio.update(self.stack, .016)
        for sound in cues:
            sound.play.assert_not_called()
        worm.worm_frame, boss.boss.stage, archer.shot_time = 26, "landed", .42
        for _ in range(3):
            self.audio.update(self.stack, .016)
        for sound in cues:
            sound.play.assert_called_once()

    def test_blow_sound_matches_damage_block_and_defeat(self):
        session = self.game.session
        point = session.player.position3d
        for kind, hp, curled, cue in (
                (MobKind.SKELETON, 4, 0, "bone_hit"), (MobKind.SKELETON, 1, 0, "bone_fall"),
                (MobKind.ARMADILLO, 6, 1, "shell_block"), (MobKind.SNAKE, 6, 0, "snake_hit"),
                (MobKind.SHARK, 1, 0, None)):
            with self.subTest(kind=kind, hp=hp):
                mob = Mob(917, kind, hp, point, point, 0., curled=curled)
                session.wildlife.mobs[mob.id] = mob
                self.game._mob_id = mob.id
                self.game.play_sound = Mock()
                self.game._plan_target(point.grid, ClickIntent.PRIMARY_ACTION)
                if cue:
                    self.game.play_sound.assert_called_once_with(cue)
                else:
                    self.game.play_sound.assert_not_called()

    def test_missing_device_keeps_the_game_playable(self):
        with patch("PPlay.sound.SoundManager.inicializar", side_effect=RuntimeError("no device")):
            with self.assertLogs("spawnbound.audio", level="WARNING"):
                silent = AudioManager()
        silent.enter(self.stack)
        silent.play("click")
        silent.update(self.stack, .016)
        silent.close()
