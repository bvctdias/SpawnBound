from __future__ import annotations

import pygame


class WorldPrimitives:
    def __init__(self, anchor: tuple[int, int], scale: float) -> None:
        self.anchor = anchor
        self.scale = scale

    def point(self, value: tuple[float, float]) -> tuple[int, int]:
        return tuple(round(a + (p - a) * self.scale) for a, p in zip(self.anchor, value))

    def size(self, value: float) -> int:
        return round(value * self.scale)

    def rect(self, target, color, rectangle, width=0):
        x, y, w, h = rectangle
        return pygame.draw.rect(target, color, (*self.point((x, y)), self.size(w), self.size(h)), self.size(width))

    def circle(self, target, color, center, radius, width=0):
        return pygame.draw.circle(target, color, self.point(center), self.size(radius), self.size(width))

    def polygon(self, target, color, points, width=0):
        return pygame.draw.polygon(target, color, [self.point(p) for p in points], self.size(width))

    def line(self, target, color, start, end, width=1):
        return pygame.draw.line(target, color, self.point(start), self.point(end), self.size(width))

    def lines(self, target, color, closed, points, width=1):
        return pygame.draw.lines(target, color, closed, [self.point(p) for p in points], self.size(width))
