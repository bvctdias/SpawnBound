from __future__ import annotations

import math
import random


class PerlinNoise:
    def __init__(self, seed: int) -> None:
        permutation = list(range(256))
        random.Random(seed).shuffle(permutation)
        self._permutation = permutation * 2

    def sample(self, x: float, y: float) -> float:
        ix, iy = math.floor(x), math.floor(y)
        dx, dy = x - ix, y - iy
        px, py = ix & 255, iy & 255
        p = self._permutation

        def gradient(h: int, gx: float, gy: float) -> float:
            vectors = ((1, 0), (-1, 0), (0, 1), (0, -1),
                       (.707106781, .707106781), (-.707106781, .707106781),
                       (.707106781, -.707106781), (-.707106781, -.707106781))
            vx, vy = vectors[h & 7]
            return vx * gx + vy * gy

        u = dx * dx * dx * (dx * (dx * 6 - 15) + 10)
        v = dy * dy * dy * (dy * (dy * 6 - 15) + 10)
        a = gradient(p[p[px] + py], dx, dy)
        b = gradient(p[p[px + 1] + py], dx - 1, dy)
        c = gradient(p[p[px] + py + 1], dx, dy - 1)
        d = gradient(p[p[px + 1] + py + 1], dx - 1, dy - 1)
        low, high = a + u * (b - a), c + u * (d - c)
        return max(0.0, min(1.0, .5 + .5 * (low + v * (high - low))))

    def fractal(self, x: float, y: float, *, scale: float = 24,
                octaves: int = 3, persistence: float = .5) -> float:
        if scale <= 0 or octaves < 1 or not 0 < persistence <= 1:
            raise ValueError("invalid noise scale, octaves or persistence")
        total = weight = 0.0
        amplitude, frequency = 1.0, 1.0 / scale
        for _ in range(octaves):
            total += self.sample(x * frequency, y * frequency) * amplitude
            weight += amplitude
            amplitude *= persistence
            frequency *= 2
        return total / weight
