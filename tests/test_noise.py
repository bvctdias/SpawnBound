import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from spawnbound.domain.noise import PerlinNoise


class NoiseTests(unittest.TestCase):
    def test_seeded_noise_is_smooth_bounded_and_nonconstant(self):
        a, b, other = PerlinNoise(123), PerlinNoise(123), PerlinNoise(456)
        points = [(x / 7 - 8.3, y / 11 - 4.1) for x in range(30) for y in range(30)]
        values = [a.fractal(x, y, scale=2) for x, y in points]
        self.assertEqual(values, [b.fractal(x, y, scale=2) for x, y in points])
        self.assertNotEqual(values, [other.fractal(x, y, scale=2) for x, y in points])
        self.assertTrue(all(0 <= value <= 1 for value in values))
        self.assertGreater(max(values) - min(values), .1)
        for x, y in points:
            self.assertLess(abs(a.sample(x, y) - a.sample(x + .001, y)), .005)

    def test_noise_configuration_is_validated(self):
        for args in ({"scale": 0}, {"octaves": 0}, {"persistence": -1}):
            with self.assertRaises(ValueError):
                PerlinNoise(1).fractal(1, 2, **args)
