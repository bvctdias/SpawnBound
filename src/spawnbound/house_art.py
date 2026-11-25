from functools import lru_cache
from math import exp

import pygame


@lru_cache(maxsize=256)
def plank_tile(gx, gy, scale, left_drop, right_drop):
    surface = pygame.Surface((33, 17 + max(left_drop, right_drop)), pygame.SRCALPHA)
    for drop, a, b, color in ((left_drop, (0, 8), (16, 16), (115, 64, 49)),
                              (right_drop, (16, 16), (32, 8), (91, 51, 45))):
        if drop:
            for depth in range(drop, 0, -1):
                factor = 1 - .35 * depth / drop
                pygame.draw.line(surface, tuple(round(c * factor) for c in color),
                                 (a[0], a[1]+depth), (b[0], b[1]+depth))
    for y in range(17):
        span = 16 - 2 * abs(8 - y)
        for x in range(16 - span, 17 + span):
            sx, sy = (gx - gy)*16 + x - 16, (gx + gy)*8 + y - 8
            board, across = divmod(2*sy + sx, 13)
            segment, along = divmod(2*sy - sx + (board*47) % 103, 103)
            grain = (board*7 + segment*11) % 17 - 3
            grain -= 37 if across <= 1 or along < 2 else 0
            if across == 3:
                grain += 9
            if (board + 3*segment) % 7 == 1 and abs(across-6)*4 + abs(along-51) < 17:
                grain -= 66
            surface.set_at((x, y), (229 + grain, 109 + grain, 62 + grain//2))
    if scale != 1:
        return pygame.transform.scale(surface, tuple(round(n*scale) for n in surface.get_size()))
    return surface


@lru_cache(maxsize=8)
def _light_map(size, flames, scale):
    step = max(2, round(4 * scale))
    small = pygame.Surface(((size[0]+step-1)//step, (size[1]+step-1)//step))
    for y in range(small.get_height()):
        for x in range(small.get_width()):
            px, py = (x+.5)*step, (y+.5)*step
            light = sum(exp(-(((px-fx)/(155*scale))**2 + ((py-fy)/(110*scale))**2))
                        for fx, fy in flames)
            light = min(1., light)
            small.set_at((x, y), (round(62+193*light), round(67+178*light), round(75+154*light)))
    return pygame.transform.smoothscale(small, size)


def light_room(target, flames, scale):
    if flames:
        target.blit(_light_map(target.get_size(), tuple(sorted(flames)), scale), (0, 0),
                    special_flags=pygame.BLEND_RGB_MULT)
    else:
        target.fill((62, 67, 75), special_flags=pygame.BLEND_RGB_MULT)
