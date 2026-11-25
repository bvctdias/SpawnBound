from functools import lru_cache

import pygame

from spawnbound.paths import resource_dir
from spawnbound.pplay_media import load_image
from spawnbound.view import screen_center


@lru_cache(maxsize=1)
def _source():
    return load_image(resource_dir() / "assets/buildings/waystone.png")


@lru_cache(maxsize=64)
def waystone_sprite(variant, active, scale=1.0):
    if scale != 1:
        image = pygame.transform.scale_by(waystone_sprite(variant, active)[0], scale)
    else:
        image = _source().copy()
        hue = 305 if variant == "default" else int(variant)
        for y in range(15):
            for x in range(image.get_width()):
                color = image.get_at((x, y))
                if color.a:
                    _, saturation, value, _ = color.hsva
                    color.hsva = (hue, saturation if active else 10, value if active else value * .53, 100)
                    image.set_at((x, y), color)
    return image, (round(13 * scale), round(40 * scale))


@lru_cache(maxsize=64)
def _halo(variant, radius, height, strength):
    halo = pygame.Surface((radius * 2 + 1, height * 2 + 1))
    tint = pygame.Color(0, 0, 0)
    tint.hsva = (int(variant), 65, 100, 100)
    for r in range(radius, 0, -1):
        amount = strength * (1 - (r - 1) / radius) ** 2
        color = tuple(round(channel * amount) for channel in (tint.r, tint.g, tint.b))
        h = max(1, round(height * r / radius))
        pygame.draw.ellipse(halo, color, (radius-r, height-h, 2*r+1, 2*h+1))
    return halo


def draw_waystone_lights(screen, world, origin, config):
    scale = config.world_art_scale
    for stone in world.active_waystones():
        x, y = screen_center(stone.position3d, origin, config)
        for lift, radius, height, strength in ((2, 42, 19, .22), (33, 20, 21, .63)):
            halo = _halo(stone.variant, max(1, round(radius*scale)), max(1, round(height*scale)), strength)
            screen.blit(halo, halo.get_rect(center=(x, y-round(lift*scale))), special_flags=pygame.BLEND_RGB_ADD)
