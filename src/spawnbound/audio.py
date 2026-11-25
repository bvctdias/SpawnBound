from __future__ import annotations

import logging
import math
import random

from spawnbound.paths import resource_dir
from spawnbound.animation import MotionKind
from spawnbound.combat_audio import attack_sound
from spawnbound.domain.coordinates import GridPos
from spawnbound.domain.daylight import DayPhase
from spawnbound.domain.model import Biome, ObjectKind, SpaceKind, TileKind
from spawnbound.domain.session import AFTERIMAGE_SECONDS
from spawnbound.wear_art import TREE_LANDING_SECONDS

ASSETS = resource_dir() / "assets" / "audio"
MUSIC_VOLUME = 20
SFX_VOLUME = 20
# Os ganhos são relativos ao volume geral dos efeitos.
GRASS_STEP_GAIN = 0.50
SAND_STEP_GAIN = 0.50
PROGRESS_GAIN = 1.25
AMBIENT_RADIUS = 6
BACKGROUNDS = frozenset(("forest", "meadow", "dry_wind", "night", "cave", "shelter"))
STEP_VARIANTS = {
    name: (name, *(f"{name}_{n}" for n in range(2, count + 1)))
    for name, count in (("step_grass", 3), ("step_sand", 3), ("step_wood", 2), ("step_stone", 3), ("swim", 3))
}


def quiet(_cue: str) -> None:
    pass


def ambient_levels(world, point):
    x, y = point.x, point.y
    fire = min((math.hypot(p.x-x, p.y-y) for p in world.placed_fires), default=AMBIENT_RADIUS)
    size = world.tile_map.ocean_island_size
    sea = AMBIENT_RADIUS
    if size:
        # O oceano começa uma célula além da borda. As baías também contam para o som do mar.
        sea = max(0, min(sea, x+1, y+1, size-x, size-y))
        grid = point.grid
        for dx in range(-AMBIENT_RADIUS, AMBIENT_RADIUS+1):
            for dy in range(-AMBIENT_RADIUS, AMBIENT_RADIUS+1):
                cell = GridPos(grid.x+dx, grid.y+dy)
                if cell in world.sea_cells:
                    sea = min(sea, math.hypot(cell.x-x, cell.y-y))
    return {name: round(SFX_VOLUME * max(0., 1-distance/AMBIENT_RADIUS))
            for name, distance in (("sea", sea), ("fire", fire))}


def background_at(world, cell, phase):
    if world.space_kind is SpaceKind.CAVE:
        return "cave"
    if world.space_kind is SpaceKind.INTERIOR:
        return "shelter"
    tile = world.tile_map.tile_at(cell)
    if tile is None:
        return None
    if tile.kind is TileKind.WATER:
        if cell in world.sea_cells or cell not in world.tile_map.tiles:
            return None
        return "night" if phase is DayPhase.NIGHT else "meadow"
    if tile.biome is Biome.DRY:
        return "dry_wind"
    if phase is DayPhase.NIGHT:
        return "night"
    return "forest" if tile.biome is Biome.FOREST else "meadow"


def impact_cue(effect):
    kind = effect.subject.kind if effect.subject is not None else None
    if kind in (ObjectKind.CACTUS, ObjectKind.BERRY_BUSH) or (
            kind is None and effect.destroyed and effect.loot != "stone"):
        return "foliage"
    material = "stone" if kind in (None, ObjectKind.ROCK, ObjectKind.KILN) else "wood"
    return material + ("_break" if effect.destroyed else "_hit")


class AudioManager:
    def __init__(self) -> None:
        import spawnbound.pplay_media
        from PPlay.sound import Music, Sound, SoundManager

        self.music = None
        self.sounds = {}
        self.ambient = {}
        self.in_menu = False
        self._world = None
        self._rng = random.Random()
        self._last_sample = {}
        self._effects = {}
        self._position = None
        self._contact = None
        self._ambient_wait = 0.
        try:
            SoundManager.inicializar()
        except RuntimeError as error:
            logging.getLogger(__name__).warning("Áudio indisponível: %s", error)
            return
        SoundManager.set_music_volume(MUSIC_VOLUME)
        SoundManager.set_sfx_volume(SFX_VOLUME)
        self.music = Music(str(ASSETS / "menu.wav"))
        self.sounds = {p.stem: Sound(str(p)) for p in ASSETS.glob("*.wav") if p.stem != "menu"}

        for surface, gain in (("step_grass", GRASS_STEP_GAIN), ("step_sand", SAND_STEP_GAIN)):
            for name in STEP_VARIANTS[surface]:
                self.sounds[name].set_volume(min(100, round(SFX_VOLUME * gain)))
        self.sounds["progress"].set_volume(min(100, round(SFX_VOLUME * PROGRESS_GAIN)))

    def play(self, cue: str) -> None:
        if self.music is not None:
            self.sounds[cue].play()

    def enter(self, states) -> None:
        self._silence_ambient()
        game = states.gameplay
        menu = game is None
        if self.music is not None and menu != self.in_menu:
            if menu:
                self.music.play(loops=-1, fade_in_ms=350)
            else:
                self.music.stop(fade_out_ms=0)
        self.in_menu = menu
        self._world = None
        self._effects.clear()
        if game is not None:
            self._enter_world(game)

    def _enter_world(self, game) -> None:
        session = game.session
        self._silence_ambient()
        self._world = session.world
        self._position = game.visual_position
        self._contact = None
        self._step_wait = 0.
        self._mob_actions = {mob.id: self._mob_action(mob) for mob in session.wildlife.mobs.values()}
        self._hurt = session.hurt_time
        self._level = session.player.level
        self._bag = game.inventory_open
        self._slot = session.player.inventory.selected
        # Retoma no instante salvo para evitar repetir sons que já tocaram.
        self._effects = {id(e): (e, e.elapsed) for e in session.afterimages}

    def _silence_ambient(self) -> None:
        for name in self.ambient:
            self.sounds[name].stop()
        self.ambient.clear()
        self._ambient_wait = 0.

    def update(self, states, dt: float) -> None:
        game = states.gameplay
        if self.music is None or game is None:
            return
        session = game.session
        if session.world is not self._world:
            self._enter_world(game)
        if self._bag != game.inventory_open:
            self.play("bag")
        elif self._slot != session.player.inventory.selected:
            self.play("slot")
        self._bag, self._slot = game.inventory_open, session.player.inventory.selected
        if (states.top is not game or self._bag or game.map_open or game.rest_open or game.chart_open
                or game.repair_open is not None or game.ending_open or session.voyage is not None):
            self._silence_ambient()
            return
        if session.hurt_time > self._hurt:
            self.play("hurt")
        if session.player.level > self._level:
            self.play("progress")
        self._hurt, self._level = session.hurt_time, session.player.level
        self._afterimages(session.afterimages)
        self._creatures(session)
        self._footsteps(game, dt)
        self._ambient_wait -= dt
        if self._ambient_wait <= 0:
            self._ambient_wait = .12
            levels = ambient_levels(session.world, session.player.position3d)
            background = background_at(session.world, session.player.position, session.daylight.phase)
            if background:
                levels[background] = round(.80 * SFX_VOLUME)
            self._mix_ambient(levels)

    def _mix_ambient(self, levels) -> None:
        for name in self.ambient.keys() | levels.keys():
            previous = self.ambient.get(name, 0)
            volume = levels.get(name, 0)
            if name in BACKGROUNDS:
                volume = max(previous - 3, min(previous + 3, volume))
            if previous == volume:
                continue
            sound = self.sounds[name]
            if volume:
                sound.set_volume(volume)
                if not previous:
                    sound.play(-1)
                self.ambient[name] = volume
            else:
                sound.stop()
                del self.ambient[name]

    @staticmethod
    def _mob_action(mob):
        return "sleep" if mob.asleep else attack_sound(mob)

    def _creatures(self, session) -> None:
        # Registrar ataques distantes evita tocá-los atrasados quando o jogador se aproxima.
        if session.wildlife.world is not session.world:
            return
        player = session.player.position3d
        actions = {}
        nearest = {}
        for mob in session.wildlife.mobs.values():
            action = self._mob_action(mob)
            previous = self._mob_actions.get(mob.id)
            if action is not None:
                actions[mob.id] = action
            if action == previous or action == "sleep":
                continue
            cue = action
            if cue is None and previous == "sleep":
                cue = "rock_grind" if mob.boss is not None else "mine_growl"
            if cue is None:
                continue
            point = mob.location
            distance = math.dist((point.x, point.y, point.z), (player.x, player.y, player.z))
            if distance < 10:
                nearest[cue] = min(distance, nearest.get(cue, 10))
        self._mob_actions = actions
        for cue, distance in nearest.items():
            sound = self.sounds[cue]
            sound.set_volume(round(SFX_VOLUME * min(1., (10 - distance) / 7)))
            sound.play()

    def _afterimages(self, effects) -> None:
        current = {}
        for effect in effects:
            key = id(effect)
            previous = self._effects[key][1] if key in self._effects else -1.
            if previous < 0 and (effect.destroyed or effect.impact):
                self.play(impact_cue(effect))
            if (effect.destroyed and getattr(effect.subject, "kind", None) is ObjectKind.TREE
                    and previous < TREE_LANDING_SECONDS <= effect.elapsed):
                self.play("tree_land")
            if effect.loot and previous < AFTERIMAGE_SECONDS - .10 <= effect.elapsed:
                self.play("pickup")
            current[key] = effect, effect.elapsed
        self._effects = current

    def _footsteps(self, game, dt: float) -> None:
        self._step_wait = max(0., self._step_wait - dt)
        pose = game.player_pose
        moving = game.visual_position != self._position
        self._position = game.visual_position
        contact = None
        if pose.motion is MotionKind.JUMP and pose.progress >= .75:
            contact = ("land",)
        elif moving and pose.motion in (MotionKind.WALK, MotionKind.SWIM):
            # Cada braçada ocupa oito quadros. Em terra há dois passos por ciclo.
            beat = pose.elapsed * (7 / 8 if pose.motion is MotionKind.SWIM else 12 / 4)
            contact = (pose.motion, int(beat))
        if contact is not None and contact != self._contact and self._step_wait == 0:
            session = game.session
            tile = session.world.tile_map.tile_at(session.player.position)
            if tile is not None:
                if tile.kind is TileKind.WATER:
                    cue = "swim"
                elif tile.kind in (TileKind.BRIDGE, TileKind.WOOD_FLOOR):
                    cue = "step_wood"
                elif tile.kind is TileKind.CAVE_FLOOR:
                    cue = "step_stone"
                else:
                    cue = "step_sand" if tile.biome is Biome.DRY else "step_grass"
                options = [s for s in STEP_VARIANTS[cue] if s != self._last_sample.get(cue)]
                sample = self._rng.choice(options)
                self._last_sample[cue] = sample
                self.play(sample)
                self._step_wait = .78 if cue == "swim" else .20
        self._contact = contact

    def close(self) -> None:
        self._silence_ambient()
        if self.in_menu and self.music is not None:
            self.music.stop(fade_out_ms=0)
