from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
import json
import math
from pathlib import Path

import pygame

from spawnbound.paths import resource_dir
from spawnbound.animation import FrameSequence, MotionKind, PlayerPose
from spawnbound.pplay_media import load_image
from spawnbound.pplay_ui import Strip, draw_on
from spawnbound.domain.coordinates import GridPos


@lru_cache(maxsize=8)
def soil_texture(stage: int, scale: float) -> pygame.Surface:
    if scale != 1:
        return pygame.transform.scale_by(soil_texture(stage, 1), scale)
    filename = {1: "soil_loosened.png", 2: "soil_ready.png"}[stage]
    return load_image(resource_dir() / "assets/farming" / filename)


@lru_cache(maxsize=8)
def windmill_sprite(scale: float = 1.0, restored: bool = False) -> tuple[pygame.Surface, tuple[int, int]]:
    if scale == 1:
        filename = "windmill_restored_tower.png" if restored else "windmill_ruined.png"
        image = load_image(resource_dir() / "assets/buildings" / filename)
    else:
        image = pygame.transform.scale_by(windmill_sprite(restored=restored)[0], scale)
    return image, (round(22 * scale), round((67 if restored else 75) * scale))


def sail_frame(seconds: float) -> int:
    # As quatro pás têm a mesma silhueta a cada quarto de volta.
    return int(seconds * 12) % 18


@lru_cache(maxsize=72)
def windmill_sails(frame: int, scale: float = 1.0) -> tuple[pygame.Surface, tuple[int, int]]:
    # O eixo fica 9 pixels à direita e 45 acima do ponto de apoio da torre.
    pivot = round(18 * scale), round(77 * scale)
    if scale != 1:
        return pygame.transform.scale_by(windmill_sails(frame)[0], scale), pivot
    image = pygame.Surface((55, 65), pygame.SRCALPHA)
    ink, wood, linen = (80, 48, 41), (155, 96, 59), (249, 222, 186)
    for arm in range(4):
        angle = math.tau * (arm / 4 + frame / 72) + .24
        sine, cosine = math.sin(angle), math.cos(angle)

        def point(radius, width):
            u = radius * cosine - width * sine
            v = radius * sine + width * cosine
            return round(27 + .80 * u), round(32 + v - .30 * u)

        corners = [point(8, 0), point(29, 0), point(28, 6), point(9, 4)]
        pygame.draw.polygon(image, linen, corners)
        pygame.draw.lines(image, (184, 142, 106), True, corners)
        pygame.draw.line(image, ink, point(0, 0), point(30, 0), 2)
        pygame.draw.line(image, wood, point(2, 1), point(29, 1))
    pygame.draw.rect(image, ink, (25, 30, 5, 5))
    pygame.draw.rect(image, wood, (26, 31, 3, 3))
    return image, pivot


@dataclass(frozen=True, slots=True)
class SpriteClip:
    frames: tuple[pygame.Surface, ...]
    pivot: tuple[int, int]
    fps: float = 8.0
    loop: bool = True
    sequence: FrameSequence = field(init=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "sequence", FrameSequence(len(self.frames), self.fps, self.loop))


@dataclass(slots=True)
class PlayerSprites:
    clips: dict[tuple[MotionKind, GridPos], SpriteClip] = field(default_factory=dict)
    unarmed: dict[tuple[MotionKind, GridPos], SpriteClip] = field(default_factory=dict)
    upgrades: dict[str, dict] = field(default_factory=dict)
    strips: dict[int, Strip] = field(default_factory=dict, repr=False, compare=False)

    @classmethod
    def from_atlas(cls, manifest: Path) -> PlayerSprites:
        spec = json.loads(manifest.read_text(encoding="utf-8"))
        equipped = cls._load_clips(manifest.parent / spec["sheet"], spec)
        unarmed = cls._load_clips(manifest.parent / spec["unarmed_sheet"], spec) if "unarmed_sheet" in spec else {}
        upgrades = {item: cls._load_clips(manifest.parent / path, spec)
                    for item, path in spec.get("upgrades", {}).items()}
        return cls(equipped, unarmed, upgrades)

    @staticmethod
    def _load_clips(path, spec):
        sheet = load_image(path)
        width, height = spec["frame_size"]
        pivot = tuple(spec["pivot"])
        clips = {}
        for row, direction in enumerate(spec["directions"]):
            for name, clip in spec["clips"].items():
                frames = tuple(sheet.subsurface((col * width, row * height, width, height))
                               for col in range(clip["start"], clip["start"] + clip["count"]))
                clips[MotionKind(name), GridPos(*direction)] = SpriteClip(
                    frames, pivot, clip["fps"], clip["loop"])
        return clips

    def draw(self, target: pygame.Surface, pose: PlayerPose, feet: tuple[int, int], *, equipped=True) -> bool:
        clips = self.upgrades.get(equipped, self.clips) if equipped or not self.unarmed else self.unarmed
        clip = clips.get((pose.motion, pose.facing))
        if clip is None:
            return False
        strip = self.strips.get(id(clip))
        if strip is None:
            strip = self.strips[id(clip)] = Strip(clip.frames)
        strip.set_curr_frame(clip.sequence.frame_index(pose))
        strip.set_position(feet[0] - clip.pivot[0], feet[1] - clip.pivot[1])
        draw_on(target, strip)
        return True
