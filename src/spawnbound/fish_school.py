import math
from dataclasses import dataclass
from functools import lru_cache

import pygame

from spawnbound.domain.schooling import narrow_water
from spawnbound.view import screen_center
from spawnbound.seabed import aquatic_glyph


@lru_cache(maxsize=96)
def _fish_sprite(heading, tail_up, scale):
    body = pygame.Surface((12, 7), pygame.SRCALPHA)
    tail = 1 if tail_up else 3
    pygame.draw.polygon(body, (49, 108, 116), [(0, tail), (4, 3), (0, tail + 3)])
    pygame.draw.polygon(body, (49, 105, 114), [(3, 3), (6, 1), (9, 1), (11, 3),
                                                (9, 5), (6, 5)])
    pygame.draw.line(body, (133, 176, 165), (6, 2), (9, 2))
    body.set_at((9, 3), (38, 87, 96))
    image = pygame.transform.rotate(body, -heading * 22.5)
    if scale != 1:
        image = pygame.transform.scale_by(image, scale)
    return image


@lru_cache(maxsize=8)
def _cover(width, height):
    leaves = aquatic_glyph("thicket", width, height)
    cover = pygame.Surface(leaves.get_size(), pygame.SRCALPHA)
    for dx in range(-2, 3):
        for dy in range(-2, 3):
            if abs(dx) + abs(dy) <= 2:
                cover.blit(leaves, (dx, dy), special_flags=pygame.BLEND_RGBA_MAX)
    return cover


@dataclass(slots=True)
class SchoolFrame:
    image: pygame.Surface
    rect: pygame.Rect
    scratch: pygame.Surface
    mask: pygame.Surface

    def paint_tile(self, screen, center, lift):
        tile = self.mask.get_rect(center=(center[0], center[1] - lift))
        if not self.rect.colliderect(tile):
            return
        self.scratch.fill((0, 0, 0, 0))
        self.scratch.blit(self.image, (self.rect.x - tile.x, self.rect.y - tile.y))
        self.scratch.blit(self.mask, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
        screen.blit(self.scratch, tile)


def school_frame(session, config, origin, viewport, water_mask):
    world = session.world
    visit = session.school
    home = visit.home
    direction = world.fish_refuges.get(home)
    if direction is None:
        return None
    hx, hy = screen_center(home, origin, config)
    hy -= config.water_lift
    if not viewport.inflate(config.tile_width * 8, config.tile_height * 8).collidepoint(hx, hy):
        return None
    narrow = narrow_water(world, home)
    sprites = []
    for i in range(5):
        along, across = visit.offset(i, narrow)
        if along == 0:
            continue
        before, beside = visit.offset(i, narrow, previous=True)
        vx = (along-before)*direction.x - (across-beside)*direction.y
        vy = (along-before)*direction.y + (across-beside)*direction.x
        angle = math.atan2((vx + vy) * config.tile_height, (vx - vy) * config.tile_width)
        sprite = _fish_sprite(round(angle * 8 / math.pi) % 16,
                              (int((visit.elapsed + visit.return_time) * 6) + i) % 2, config.pixel_scale)
        px = home.x + along*direction.x - across*direction.y
        py = home.y + along*direction.y + across*direction.x
        sx, sy = screen_center((px, py), origin, config)
        sprites.append((sprite, sprite.get_rect(center=(sx, sy - config.water_lift))))
    if not sprites:
        return None
    bounds = sprites[0][1].unionall([rect for _, rect in sprites[1:]])
    image = pygame.Surface(bounds.size, pygame.SRCALPHA)
    for sprite, rect in sprites:
        image.blit(sprite, (rect.x - bounds.x, rect.y - bounds.y))
    cover = _cover(config.tile_width, config.tile_height)
    cover_rect = cover.get_rect(center=(hx, hy))
    image.blit(cover, (cover_rect.x - bounds.x, cover_rect.y - bounds.y),
               special_flags=pygame.BLEND_RGBA_SUB)
    image.set_alpha(220)
    mask = water_mask()
    return SchoolFrame(image, bounds, pygame.Surface(mask.get_size(), pygame.SRCALPHA), mask)
