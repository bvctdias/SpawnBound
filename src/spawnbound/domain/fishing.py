from __future__ import annotations

import math
import random
from dataclasses import dataclass, field

from spawnbound.domain.coordinates import GridPos
from spawnbound.domain.fish import Fish, Swim

CHARGE_SECONDS = .9
REACH = (1.5, 6.)
SWING_SECONDS = .3
FLIGHT_SECONDS = .45
HOOK_SECONDS = .25
BITE_DELAY = (1.6, 6.)
SHELTER_SPEEDUP = .55
SHELTER_RADIUS = 4
BITE_WINDOW = .9
SHOW_SECONDS = 1.4

BAR = .30
LIFT = 3.1
GRAVITY = 2.5
TOP_SPEED = 1.5
BOUNCE = .45
START = .3
GAIN = .24
LOSS = .16


def power_at(held: float) -> float:
    phase = (held / CHARGE_SECONDS) % 2
    return phase if phase <= 1 else 2 - phase


def landing(start: GridPos, aim: GridPos, power: float) -> GridPos:
    dx, dy = aim.x - start.x, aim.y - start.y
    distance = math.hypot(dx, dy)
    reach = REACH[0] + (REACH[1] - REACH[0]) * max(0., min(1., power))
    if distance <= reach or distance == 0:
        return aim
    scale = reach / distance
    return GridPos(start.x + round(dx * scale), start.y + round(dy * scale))


def bite_delay(rng: random.Random, near_shelter: bool) -> float:
    delay = rng.uniform(*BITE_DELAY)
    return delay * SHELTER_SPEEDUP if near_shelter else delay


def near_shelter(world, cell: GridPos) -> bool:
    return any(max(abs(cell.x - s.x), abs(cell.y - s.y)) <= SHELTER_RADIUS for s in world.fish_refuges)


@dataclass(slots=True)
class Minigame:
    fish: Fish
    rng: random.Random = field(default_factory=random.Random)
    # As posições na barra vão de 0, no fundo, a 1, no topo.
    bar: float = 0.
    bar_speed: float = 0.
    fish_y: float = .5
    fish_speed: float = 0.
    target: float = .5
    progress: float = START
    elapsed: float = 0.

    @property
    def inside(self) -> bool:
        return self.bar <= self.fish_y <= self.bar + BAR

    @property
    def difficulty(self) -> float:
        return self.fish.difficulty / 100

    def step(self, seconds: float, holding: bool) -> str | None:
        dt = max(0., min(seconds, .05))
        self.elapsed += dt
        self._move_bar(dt, holding)
        self._move_fish(dt)
        if self.inside:
            self.progress += GAIN * dt
        else:
            self.progress -= (LOSS + .15 * self.difficulty) * dt
        if self.progress >= 1:
            self.progress = 1.
            return "caught"
        if self.progress <= 0:
            self.progress = 0.
            return "escaped"
        return None

    def _move_bar(self, dt: float, holding: bool) -> None:
        self.bar_speed += (LIFT if holding else -GRAVITY) * dt
        self.bar_speed = max(-TOP_SPEED, min(TOP_SPEED, self.bar_speed))
        self.bar += self.bar_speed * dt
        if self.bar < 0:
            self.bar = 0.
            self.bar_speed = -self.bar_speed * BOUNCE if self.bar_speed < -.3 else 0.
        elif self.bar > 1 - BAR:
            self.bar = 1 - BAR
            self.bar_speed = min(0., self.bar_speed)

    def _move_fish(self, dt: float) -> None:
        d, swim, rng = self.difficulty, self.fish.swim, self.rng
        rate = .5 + 2.4 * d
        if swim is Swim.SMOOTH:
            rate *= .6
        elif swim is Swim.DART:
            rate *= 1.3
        if rng.random() < rate * dt:
            span = .2 + .6 * d
            if swim is Swim.DART and rng.random() < .5:
                span = .9
            target = self.fish_y + rng.uniform(-span, span)
            if swim is Swim.SINKER:
                target = min(target, self.fish_y) - .15 * d
            elif swim is Swim.FLOATER:
                target = max(target, self.fish_y) + .15 * d
            self.target = max(.04, min(.96, target))
        stiffness = 4 + 10 * d
        damping = 3.5
        if swim is Swim.SMOOTH:
            stiffness, damping = stiffness * .5, 2.4
        elif swim is Swim.DART:
            stiffness *= 1.8
        elif swim is Swim.MIXED and rng.random() < 2 * dt:
            self.fish_speed += rng.uniform(-.6, .6) * d
        self.fish_speed += ((self.target - self.fish_y) * stiffness - self.fish_speed * damping) * dt
        limit = .6 + 1.6 * d
        self.fish_speed = max(-limit, min(limit, self.fish_speed))
        self.fish_y += self.fish_speed * dt
        if not .02 <= self.fish_y <= .98:
            self.fish_y = max(.02, min(.98, self.fish_y))
            self.fish_speed = 0.


@dataclass(slots=True)
class FishingRun:
    aim: GridPos
    rng: random.Random
    phase: str = "charging"
    held: float = 0.
    power: float = 0.
    bobber: GridPos | None = None
    water: str | None = None
    clock: float = 0.
    bite_at: float = 0.
    fish: Fish | None = None
    game: Minigame | None = None

    def enter(self, phase: str) -> None:
        self.phase, self.clock = phase, 0.
