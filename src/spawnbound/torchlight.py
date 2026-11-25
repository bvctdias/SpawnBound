from __future__ import annotations

from functools import lru_cache

import pygame

from spawnbound.animation import JUMP_LIFT, MotionKind
from spawnbound.domain.daylight import DayPhase
from spawnbound.domain.model import SpaceKind
from spawnbound.view import screen_center
from spawnbound.house_art import light_room

TORCH_FLAME = 11
TORCH_RADIUS = 82


def carried_strength(session):
    if session.world.space_kind is SpaceKind.CAVE:
        return 1.0
    if session.world.space_kind is SpaceKind.OUTDOOR:
        light = session.daylight
        if light.phase is DayPhase.NIGHT:
            return 1 - light.blend
        if light.phase.following is DayPhase.NIGHT:
            return light.blend
    return 0.0


@lru_cache(maxsize=12)
def radial_mask(radius):
    height = max(1, round(radius * .70))
    mask = pygame.Surface((radius * 2 + 1, height * 2 + 1), pygame.SRCALPHA)
    for r in range(radius, 0, -1):
        t = 1 - r / radius
        alpha = round(255 * t * t * (3 - 2 * t))
        ry = max(1, round(height * r / radius))
        pygame.draw.ellipse(mask, (255, 255, 255, alpha),
                            (radius - r, height - ry, 2*r + 1, 2*ry + 1))
    return mask


GLASS = (116, 84, 58)
WICK = ((0, -3), (-1, -2), (0, -2), (-1, -1), (0, -1), (1, -1), (0, 0), (1, 0))


def guide_head(feet, scale):
    return feet[0] - round(6 * scale), feet[1] - round(10 * scale)


def draw_guide(target, feet, scale, direction):
    x, y = guide_head(feet, scale)
    s = max(1, round(scale))
    pygame.draw.rect(target, (56, 42, 35), (x-s, y, 3*s, 10*s))
    pygame.draw.line(target, (164, 120, 68), (x, y+2*s), (x, y+8*s), s)
    forward = pygame.Vector2(direction.x-direction.y, (direction.x+direction.y)*.5).normalize()
    side = pygame.Vector2(-forward.y, forward.x)
    base = pygame.Vector2(x, y+8*s)
    tip = base + forward*7*s
    pygame.draw.line(target, (210, 170, 96), base, tip, s)
    pygame.draw.polygon(target, (236, 195, 111),
                        [tip, tip-forward*4*s+side*2*s, tip-forward*4*s-side*2*s])
    for dx, dy in WICK:
        pygame.draw.rect(target, GLASS, (x+dx*s, y+dy*s, s, s))


@lru_cache(maxsize=8)
def _hand_lamp(scale):
    lamp = pygame.Surface((5, 7), pygame.SRCALPHA)
    pygame.draw.rect(lamp, (86, 58, 35), (0, 1, 5, 5))
    pygame.draw.rect(lamp, (240, 143, 46), (1, 2, 3, 3))
    lamp.set_at((2, 3), (255, 244, 172))
    pygame.draw.line(lamp, (198, 155, 87), (1, 0), (3, 0))
    pygame.draw.line(lamp, (112, 79, 51), (1, 6), (3, 6))
    return pygame.transform.scale(lamp, (max(1, round(5*scale)), max(1, round(7*scale))))


def hand_center(feet, scale, pose):
    facing = pose.facing
    flipped = facing.x < facing.y or (facing.x == facing.y and facing.x >= 0)
    side = 5 if flipped else -5
    lift = 0
    if pose.motion is MotionKind.JUMP:
        frame = min(7, int(pose.progress * 8))
        lift = JUMP_LIFT[frame]
    return feet[0] + round(side*scale), feet[1] - round((8+lift)*scale)


def draw_hand_lamp(target, feet, scale, strength, pose):
    if strength > 0:
        lamp = _hand_lamp(scale)
        lamp.set_alpha(round(255*strength))
        target.blit(lamp, lamp.get_rect(center=hand_center(feet, scale, pose)))


def draw_lighting(target, session, ambient, config, origin, player, pose, lantern=True):
    scale = config.world_art_scale
    torches = []
    for pos in session.world.placed_torches:
        x, y = screen_center(session.world.surface_position(pos), origin, config)
        torches.append((x, y - round(TORCH_FLAME * scale)))
    fires = []
    for pos in session.world.placed_fires:
        x, y = screen_center(session.world.surface_position(pos), origin, config)
        fires.append((x, y - round(12 * scale)))
    if session.world.space_kind is SpaceKind.INTERIOR:
        light_room(target, torches + fires, scale)
        return
    strength = carried_strength(session)
    if strength <= 0:
        ambient.draw(target, session)
        return
    feet = screen_center(player, origin, config)
    sources = [(hand_center(feet, scale, pose), max(1, round(96*scale)), strength)] if lantern else []
    sources.extend((center, max(1, round(TORCH_RADIUS*scale)), strength) for center in torches)
    sources.extend((center, max(1, round(108*scale)), strength) for center in fires)
    flames = []
    viewport = target.get_rect()
    for pos, level in session.world.guides.nearby(player).items():
        feet = screen_center(session.world.surface_position(pos), origin, config)
        x, y = guide_head(feet, scale)
        sources.append(((x, y), max(1, round(64*scale)), level))
        s = max(1, round(scale))
        for dx, dy in WICK:
            hot = (255, 233, 155) if dx == 0 and dy >= -1 else (255, 148, 49)
            rect = pygame.Rect(x+dx*s, y+dy*s, s, s).clip(viewport)
            for px in range(rect.left, rect.right):
                for py in range(rect.top, rect.bottom):
                    if target.get_at((px, py))[:3] == GLASS:
                        flames.append(((px, py), hot, level))

    patches = []
    for center, radius, level in sources:
        mask = radial_mask(radius)
        bounds = mask.get_rect(center=center)
        visible = bounds.clip(viewport)
        if not visible:
            continue
        patch = pygame.Surface(visible.size, pygame.SRCALPHA)
        patch.blit(target, (0, 0), visible)
        patch.fill((255, 222, 173), special_flags=pygame.BLEND_RGB_MULT)
        patch.blit(mask, (bounds.x-visible.x, bounds.y-visible.y), special_flags=pygame.BLEND_RGBA_MULT)
        patch.set_alpha(round(255*level))
        patches.append((patch, visible.topleft))
    ambient.draw(target, session)
    target.blits(patches, doreturn=False)
    for pixel, hot, level in flames:
        target.set_at(pixel, target.get_at(pixel).lerp(hot, min(1.0, level)))
