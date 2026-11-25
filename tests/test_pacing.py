import math
import random
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from spawnbound.pacing import FramePacer

RATES = (50, 59.94, 60, 75, 90, 100, 120, 144, 165, 170, 175, 200, 240, 280, 300, 360, 480, 500)


def settle(pacer: FramePacer, cost: float, seconds: int = 6) -> None:
    for _ in range(seconds):
        for _ in range(FramePacer.WINDOW):
            pacer.record(cost, pacer.period)
        pacer.update()


class FramePacerTests(unittest.TestCase):
    def test_every_rate_gets_whole_refreshes_capped_and_with_headroom(self):
        for hz in RATES:
            for cost in (.001, .003, .005, .008, .012, .02, .035):
                with self.subTest(hz=hz, cost=cost):
                    pacer = FramePacer(144, hz)
                    settle(pacer, cost)
                    self.assertIsInstance(pacer.refreshes, int)
                    self.assertGreaterEqual(pacer.refreshes, 1)
                    self.assertAlmostEqual(pacer.refreshes / hz, pacer.period)
                    self.assertLessEqual(1 / pacer.period, 144 + 1e-6)
                    shown = cost + FramePacer.UPLOAD
                    self.assertLessEqual(shown * FramePacer.KEEP_MARGIN, pacer.period + 1e-9)
                    if pacer.refreshes > math.ceil(hz / 144 - 1e-9):
                        self.assertGreater(shown * FramePacer.FASTER_MARGIN, (pacer.refreshes - 1) / hz)

    def test_light_frames_run_at_the_monitor_rate_up_to_the_cap(self):
        expected = {60: 60, 75: 75, 120: 120, 144: 144, 240: 120, 300: 100, 360: 120}
        for hz, fps in expected.items():
            with self.subTest(hz=hz):
                pacer = FramePacer(144, hz)
                settle(pacer, .002)
                self.assertAlmostEqual(fps, 1 / pacer.period)

    def test_slows_at_once_and_speeds_up_only_after_agreeing_checks(self):
        pacer = FramePacer(144, 144)
        settle(pacer, .002)
        self.assertEqual(1, pacer.refreshes)
        for _ in range(FramePacer.WINDOW):
            pacer.record(.009, pacer.period)
        pacer.update()
        self.assertEqual(2, pacer.refreshes)
        for check in range(FramePacer.FASTER_AFTER):
            for _ in range(FramePacer.WINDOW):
                pacer.record(.002, pacer.period)
            pacer.update()
            expected = 1 if check == FramePacer.FASTER_AFTER - 1 else 2
            self.assertEqual(expected, pacer.refreshes)

    def test_costs_between_the_margins_keep_the_period(self):
        pacer = FramePacer(144, 144)
        settle(pacer, .002)
        settle(pacer, .0045, seconds=10)
        self.assertEqual(1, pacer.refreshes)
        pacer = FramePacer(144, 144)
        settle(pacer, .009)
        settle(pacer, .0045, seconds=10)
        self.assertEqual(2, pacer.refreshes)

    def test_frame_time_is_even_and_follows_the_wall_clock(self):
        pacer = FramePacer(144, 60)
        rng = random.Random(3)
        game, previous = 0.0, 0.0
        times, intervals = [], []
        for n in range(1, 6001):
            shown = n / 59.94
            stamp = shown + rng.uniform(-.001, .001)
            intervals.append(stamp - previous)
            dt = pacer.frame_time(stamp - previous)
            previous = stamp
            game += dt
            times.append(dt)
            self.assertLess(abs(game - shown), .0015)
        self.assertGreater(max(intervals) - min(intervals), .003)
        self.assertLess(max(times) - min(times), .0005)

    def test_frame_time_catches_up_a_hitch_at_once(self):
        pacer = FramePacer(144, 60)
        for _ in range(10):
            pacer.frame_time(1 / 60)
        self.assertAlmostEqual(.1, pacer.frame_time(.1))
        self.assertAlmostEqual(1 / 60, pacer.frame_time(1 / 60))

    def test_sync_that_does_not_wait_falls_back_to_the_timer(self):
        pacer = FramePacer(144, 60)
        pacer.vsync = True
        for _ in range(60):
            pacer.record(.003, .002)
        pacer.update()
        self.assertFalse(pacer.vsync)

    def test_slowing_down_does_not_mistake_old_intervals_for_missing_sync(self):
        pacer = FramePacer(144, 144)
        pacer.vsync = True
        settle(pacer, .002)
        self.assertEqual(1, pacer.refreshes)
        for _ in range(FramePacer.WINDOW):
            pacer.record(.009, 1 / 144)
        pacer.update()
        self.assertEqual(2, pacer.refreshes)
        for _ in range(40):
            pacer.record(.009, 2 / 144)
        pacer.update()
        self.assertTrue(pacer.vsync)

    def test_refresh_change_replans_from_measured_cost(self):
        pacer = FramePacer(144, 60)
        settle(pacer, .006)
        self.assertEqual(1, pacer.refreshes)
        pacer.set_refresh(240)
        self.assertEqual(3, pacer.refreshes)
        pacer.set_refresh(0)
        self.assertEqual(240, pacer.refresh_hz)

    def test_spare_time_tracks_the_measured_cost(self):
        pacer = FramePacer(144, 60)
        settle(pacer, .006)
        self.assertAlmostEqual(1 / 60 - .0075, pacer.spare)


if __name__ == "__main__":
    unittest.main()
