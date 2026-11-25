from __future__ import annotations

import random

import pygame

import spawnbound.pplay_media  # noqa: F401
from PPlay.effects import ScreenEffects
from PPlay.particles import ParticleEmitter
from PPlay.window import Window
from spawnbound.domain.model import WorldObject
from spawnbound.pplay_ui import draw_on, window
from spawnbound.view import screen_center

SHAKES = {"landed": (2, .3), "stuck": (1, .2)}
HURT_SHAKE = (1, .15)

WOOD = ((120, 82, 48), (156, 108, 62), (190, 142, 88))
STONE = ((112, 112, 122), (146, 146, 156), (182, 182, 190))
LEAVES = {"pine_dark": (46, 92, 58), "pine_light": (70, 128, 70), "broadleaf": (78, 142, 62),
          "autumn_gold": (222, 168, 58), "autumn_red": (196, 76, 52), "palm_small": (92, 156, 70),
          "palm_medium": (92, 156, 70), "palm_tall": (92, 156, 70), "tree": (78, 142, 62)}
ORE = {"copper": (206, 116, 62), "quartz": (238, 220, 232), "coal": (42, 40, 44)}
PLANTS = {"cactus": ((70, 136, 72), (104, 168, 90)), "berry_bush": ((64, 120, 60), (180, 48, 70)),
          "mushroom": ((210, 72, 60), (236, 222, 200)), "red": ((200, 56, 56), (70, 128, 66)),
          "purple": ((150, 92, 196), (70, 128, 66)), "pink": ((232, 132, 182), (70, 128, 66))}
WATER = ((150, 206, 232), (206, 236, 248), (255, 255, 255))


def chip_colours(thing: WorldObject) -> tuple[tuple[int, int, int], ...]:
    kind = getattr(thing.kind, "value", str(thing.kind))
    variant = str(getattr(thing, "variant", "") or "")
    if kind == "tree":
        return WOOD + (LEAVES.get(variant, LEAVES["tree"]),)
    if kind == "rock":
        ore = next((colour for name, colour in ORE.items() if name in variant), None)
        return STONE + ((ore, ore) if ore else ())
    return PLANTS.get(kind) or PLANTS.get(variant) or WOOD


class Chips(ParticleEmitter):
    def __init__(self, x: float, y: float, colours, *, size: int = 1, speed: float = 40.,
                 rise: float = 60., gravity: float = 300., life: float = .45) -> None:
        super().__init__(x, y)
        self.colours, self.rise, self.gravity = tuple(colours), rise, gravity
        self.tamanho_base, self.vida_base = max(1, round(size)), life
        self.spread_x, self.spread_y = speed, speed * .5
        self.origin = (0., 0.)
        self._dots: dict = {}

    def explodir(self, quantidade: int = 20) -> None:
        first = len(self.particulas)
        super().explodir(quantidade)
        for particle in self.particulas[first:]:
            particle.vy = -abs(particle.vy) - self.rise
            particle.cor = random.choice(self.colours)

    def update(self) -> None:
        dt = Window.get_instance().delta_time()
        for particle in self.particulas:
            particle.vy += self.gravity * dt
        super().update()

    def draw(self) -> None:
        screen = Window.get_screen()
        ox, oy = self.origin
        for particle in self.particulas:
            dot = self._dots.get((particle.cor, particle.tamanho))
            if dot is None:
                dot = self._dots[(particle.cor, particle.tamanho)] = pygame.Surface((particle.tamanho,) * 2)
                dot.fill(particle.cor)
            dot.set_alpha(int(255 * max(0., particle.vida_restante) / particle.vida_max))
            screen.blit(dot, (round(particle.x + ox), round(particle.y + oy)))

    def bounds(self) -> pygame.Rect | None:
        if not self.particulas:
            return None
        ox, oy = self.origin
        xs = [round(p.x + ox) for p in self.particulas]
        ys = [round(p.y + oy) for p in self.particulas]
        size = self.tamanho_base
        return pygame.Rect(min(xs), min(ys), max(xs) - min(xs) + size, max(ys) - min(ys) + size)


def shake_offset() -> tuple[int, int]:
    if ScreenEffects._shake_time <= 0:
        return 0, 0
    strength = ScreenEffects._shake_intensity
    return round(random.uniform(-strength, strength)), round(random.uniform(-strength, strength))


def advance_shake() -> None:
    window()
    ScreenEffects.update()


class WorldFeel:
    def __init__(self) -> None:
        self.emitters: list[Chips] = []
        self._world = None
        self._seen: set[int] = set()
        self._stages: dict[int, str] = {}
        self._hurt = 0.

    def follow(self, session, origin, surface: pygame.Surface, config) -> None:
        if session.world is not self._world:
            self._world, self.emitters, self._stages = session.world, [], {}
            self._seen = {id(effect) for effect in session.afterimages}
        self._shakes(session)
        self._breaks(session, origin, config)
        for emitter in self.emitters:
            emitter.update()
        self.emitters = [emitter for emitter in self.emitters if emitter.particulas]
        for emitter in self.emitters:
            emitter.origin = origin
        if self.emitters:
            draw_on(surface, *self.emitters)

    def _shakes(self, session) -> None:
        if session.hurt_time > self._hurt:
            ScreenEffects.shake(*HURT_SHAKE)
        self._hurt = session.hurt_time
        wildlife = getattr(session, "wildlife", None)
        for mob in (wildlife.mobs.values() if wildlife is not None else ()):
            guardian = getattr(mob, "boss", None)
            if guardian is None:
                continue
            stage = guardian.stage
            if stage != self._stages.get(id(mob)) and stage in SHAKES:
                ScreenEffects.shake(*SHAKES[stage])
            self._stages[id(mob)] = stage

    def _breaks(self, session, origin, config) -> None:
        current = {id(effect): effect for effect in session.afterimages}
        scale = config.world_art_scale
        for key in current.keys() - self._seen:
            effect = current[key]
            if not (effect.destroyed and isinstance(effect.subject, WorldObject)):
                continue
            x, y = screen_center(effect.location, origin, config)
            chips = Chips(x - origin[0], y - origin[1] - 8 * scale, chip_colours(effect.subject), size=2 * scale,
                          speed=60 * scale, rise=110 * scale, gravity=380 * scale, life=.55)
            chips.explodir(18)
            self.emitters.append(chips)
        self._seen = set(current)


class Splash:
    def __init__(self) -> None:
        self.emitter: Chips | None = None
        self._phase = None

    def follow(self, surface: pygame.Surface, run, water, origin, zoom: float) -> pygame.Rect | None:
        if run.phase == "bite" and self._phase != "bite" and water is not None:
            self.emitter = Chips(water[0] - origin[0], water[1] - origin[1], WATER, size=zoom,
                                 speed=30 * zoom, rise=45 * zoom, gravity=260 * zoom, life=.4)
            self.emitter.explodir(10)
        self._phase = run.phase
        if self.emitter is None:
            return None
        self.emitter.update()
        self.emitter.origin = origin
        if not self.emitter.particulas:
            self.emitter = None
            return None
        draw_on(surface, self.emitter)
        return self.emitter.bounds()


__all__ = ["Chips", "Splash", "WorldFeel", "advance_shake", "chip_colours", "shake_offset"]
