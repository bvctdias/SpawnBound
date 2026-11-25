from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from spawnbound.animation import FrameSequence, MotionKind, PlayerPose
from spawnbound.config import GameConfig
from spawnbound.domain.coordinates import SOUTH_EAST as EAST, GridPos, NEIGHBOR_DIRECTIONS
from spawnbound.domain.model import ObjectKind, TileKind, WorldObject
from spawnbound.domain.session import GameSession
from spawnbound.input import InputFrame
from spawnbound.states import HOP_SECONDS, ClickIntent, GameplayState
from spawnbound.sprites import PlayerSprites


class AnimationTests(unittest.TestCase):
    def make_state(self):
        config = GameConfig(movement_seconds_per_cell=.40)
        session = GameSession.create(1234, config, chunk_preview_size=8)
        session.world.objects.clear()
        return GameplayState(session, config)

    def test_walk_clock_continues_across_tiles_and_returns_to_idle(self):
        state = self.make_state()
        p = state.session.player.position
        state._path = (p + EAST, p + GridPos(2, 0), p + GridPos(3, 0))
        state.step(InputFrame(), .2)
        self.assertEqual(MotionKind.WALK, state.player_pose.motion)
        self.assertAlmostEqual(.2, state.player_pose.elapsed)
        self.assertAlmostEqual(1 / 6, state.player_pose.progress)
        state.step(InputFrame(), 1.1)
        self.assertEqual(MotionKind.IDLE, state.player_pose.motion)

    def test_a_step_on_the_way_is_a_hop_in_both_directions(self):
        state = self.make_state()
        p = state.session.player.position
        high = p + EAST
        state.session.world.tile_map.add(high, TileKind.GRASS, elevation=1)
        state._path = (high,)
        state.step(InputFrame(), HOP_SECONDS / 2)
        self.assertEqual(MotionKind.JUMP, state.player_pose.motion)
        self.assertAlmostEqual(.5, state.player_pose.progress)
        self.assertEqual(high, state.session.player.position)
        state.step(InputFrame(), HOP_SECONDS / 2)
        state._path = (p,)
        state.step(InputFrame(), HOP_SECONDS / 2)
        self.assertEqual(MotionKind.JUMP, state.player_pose.motion)
        self.assertAlmostEqual(.5, state.player_pose.progress)

    def test_frame_sequence_loops_walk_and_synchronizes_steps(self):
        seq = FrameSequence(4, fps=10)
        self.assertEqual(1, seq.frame_index(PlayerPose(MotionKind.WALK, EAST, elapsed=.51)))
        self.assertEqual(2, seq.frame_index(PlayerPose(MotionKind.STEP_UP, EAST, progress=.5)))
        self.assertEqual(3, seq.frame_index(PlayerPose(MotionKind.STEP_DOWN, EAST, progress=1)))
        with self.assertRaises(ValueError):
            FrameSequence(0)

    def test_equipped_atlas_has_each_pose_direction_and_padding(self):
        manifest = Path(__file__).resolve().parents[1] / "assets/native_32/player/animation.json"
        clips = PlayerSprites.from_atlas(manifest).clips
        for motion in MotionKind:
            for direction in NEIGHBOR_DIRECTIONS:
                clip = clips[motion, direction]
                self.assertGreater(len(clip.frames), 1)
                for frame in clip.frames:
                    box = frame.get_bounding_rect()
                    self.assertGreater(box.width, 0)
                    self.assertTrue(frame.get_rect().inflate(-2, -2).contains(box), (motion, direction, box))

    def test_jump_keeps_support_and_allows_walking_to_continue(self):
        state = self.make_state()
        p = state.session.player.position
        state.step(InputFrame(jump_pressed=True), 0)
        state.step(InputFrame(jump_pressed=True), .24)
        self.assertEqual(MotionKind.JUMP, state.player_pose.motion)
        self.assertAlmostEqual(.5, state.player_pose.progress)
        self.assertEqual(p, state.session.player.position)
        state._path = (p + EAST, p + EAST + EAST)
        state.step(InputFrame(), .12)
        self.assertGreater(state.visual_position[0], p.x)
        state.step(InputFrame(), .16)
        self.assertEqual(MotionKind.WALK, state.player_pose.motion)

    def test_strike_only_plays_for_a_successful_hit_and_never_repeats_damage(self):
        state = self.make_state()
        target = state.session.player.position + EAST
        rock = WorldObject.create(target, ObjectKind.ROCK)
        state.session.world.objects[target] = rock
        state._plan_target(target, ClickIntent.PRIMARY_ACTION)
        self.assertEqual(MotionKind.STRIKE, state.player_pose.motion)
        self.assertEqual(EAST, state.player_pose.facing)
        state.step(InputFrame(), rock.spec.swing_seconds / 2)
        self.assertAlmostEqual(.5, state.player_pose.progress)
        state.step(InputFrame(), rock.spec.swing_seconds / 2)
        self.assertEqual(rock.spec.durability - 3, rock.durability)
        state.session.player.energy = 0
        state._plan_target(target, ClickIntent.PRIMARY_ACTION)
        self.assertEqual(MotionKind.IDLE, state.player_pose.motion)
