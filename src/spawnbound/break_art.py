from functools import lru_cache

import pygame

from spawnbound.item_icons import icon


DURATION = .50
FRAME_COUNT = 15
LOBES = ((-.91, -.27, .82), (-.54, -.81, .96), (.08, -.94, .83),
         (.75, -.69, .94), (1., .01, .83), (.52, .67, 1.),
         (-.18, .83, .90), (-.85, .49, .76))


@lru_cache(maxsize=128)
def dust_frame(phase: int, large: bool, scale: int) -> pygame.Surface:
    canvas = pygame.Surface((44, 34), pygame.SRCALPHA)
    size = 1.0 if large else .74
    spread = (2, 3, 4, 5, 6, 7, 8, 10, 13, 15, 16, 17, 18, 18, 19)[phase]
    radius = (3, 4, 5, 7, 8, 8, 7, 6, 4, 3, 3, 2, 2, 1, 1)[phase]
    cy = 23 - round(min(phase, 10) * .55)
    lobes = []
    for i, (dx, dy, weight) in enumerate(LOBES):
        if phase > 11 and (i * 3) % 7 < (phase - 11) * 1.5:
            continue
        x = 22 + round(dx * spread * size)
        y = cy + round(dy * spread * size * .75)
        r = max(1, round(radius * weight * size))
        if phase >= 10:
            side = max(1, round(r * 1.45))
            pygame.draw.rect(canvas, "#f3d6b3", (x-side//2, y-side//2, side, side))
        else:
            lobes.append((x, y, r))
    if phase < 6:
        lobes.insert(0, (22, cy, round((radius + 1) * size)))
    for x, y, r in lobes:
        pygame.draw.circle(canvas, "#c19b86", (x, y + 1), r)
    for x, y, r in lobes:
        pygame.draw.circle(canvas, "#e8c7a6", (x, y), r)
    for x, y, r in lobes:
        pygame.draw.circle(canvas, "#f7dcbb", (x - 1, y - 1), max(1, r - 2))
    return pygame.transform.scale_by(canvas, scale) if scale != 1 else canvas


@lru_cache(maxsize=48)
def outlined_drop(item: str, scale: int) -> pygame.Surface:
    native = icon(item, 1)
    sprite = pygame.Surface((18, 18), pygame.SRCALPHA)
    rim = pygame.mask.from_surface(native).to_surface(setcolor="#fff4dd", unsetcolor=(0, 0, 0, 0))
    for offset in ((0, 1), (2, 1), (1, 0), (1, 2)):
        sprite.blit(rim, offset)
    sprite.blit(native, (1, 1))
    return pygame.transform.scale_by(sprite, scale)
