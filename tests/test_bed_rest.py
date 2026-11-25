from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "dependencias")]

from spawnbound.config import DEFAULT_CONFIG
from spawnbound.domain.coordinates import NEIGHBOR_DIRECTIONS
from spawnbound.domain.session import REST_HEARTS, ActionCode, GameSession
from spawnbound.input import InputFrame
from spawnbound.states import GameplayState

DAY, AFTERNOON, NIGHT = DEFAULT_CONFIG.phase_durations


class BedRestTests(unittest.TestCase):
    def setUp(self):
        self.session = GameSession.create(1234, DEFAULT_CONFIG, chunk_preview_size=128)
        self.session.wildlife.mobs.clear()
        bag = self.session.player.inventory
        bag.add("bed", 1)
        bag.selected = next(i for i, s in enumerate(bag.slots) if s and s.item == "bed")
        player = self.session.player
        side = next(d for d in NEIGHBOR_DIRECTIONS if self.session.can_place(player.position + d)
                    and self.session.world.can_reach(player.position, player.position + d,
                                                     DEFAULT_CONFIG.max_step_height))
        self.bed = player.position + side
        self.assertTrue(self.session.place_furniture(self.bed, "bed").success)

    def test_the_bed_is_found_beside_the_player(self):
        self.assertEqual(self.bed, self.session.bed_beside())

    def test_at_night_the_bed_sleeps_to_the_morning_and_the_screen_opens_again(self):
        session = self.session
        session.cycle_seconds = DAY + AFTERNOON + NIGHT * .3
        session.player.hearts -= 2
        hearts = session.player.hearts
        result = session.rest()
        self.assertEqual(ActionCode.RESTED, result.code)
        self.assertEqual(0., session.cycle_seconds, "morning")
        self.assertGreater(session.revive_time, 0, "the screen goes dark and comes back")
        self.assertEqual(hearts + REST_HEARTS, session.player.hearts)

    def test_in_the_afternoon_too(self):
        self.session.cycle_seconds = DAY + AFTERNOON * .5
        self.assertEqual(ActionCode.RESTED, self.session.rest().code)
        self.assertEqual(0., self.session.cycle_seconds)

    def test_by_day_the_bed_is_still_a_nap(self):
        session = self.session
        session.cycle_seconds = DAY * .5
        session.player.energy = 1
        self.assertEqual(ActionCode.RESTED, session.rest().code)
        self.assertEqual(DAY * .5, session.cycle_seconds, "no sleep through the day")
        self.assertEqual(0, session.revive_time)
        self.assertGreater(session.player.energy, 1)

    def test_r_beside_the_bed_sleeps_in_the_game(self):
        self.session.cycle_seconds = DAY + AFTERNOON + NIGHT * .5
        state = GameplayState(self.session, DEFAULT_CONFIG)
        state.step(InputFrame(rest_pressed=True), 1 / 60)
        self.assertEqual(0., self.session.cycle_seconds)
        self.assertGreater(self.session.revive_time, 0)


if __name__ == "__main__":
    unittest.main()
