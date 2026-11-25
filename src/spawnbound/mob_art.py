from functools import lru_cache

from spawnbound.paths import resource_dir
from spawnbound.domain.mobs import MobKind
from spawnbound.pplay_ui import Picture, draw_on
from spawnbound import armadillo_art, farm_art, guardian_art, mine_monster_art, shark_art, skeleton_art, wild_art

WORM_SIZE = (80, 64)
WORM_FOOT = (40, 59)


@lru_cache(maxsize=1)
def _worm_atlas():
    from spawnbound.pplay_media import load_image
    return load_image(resource_dir() / "assets/native_32/creatures/sandworm.png")


@lru_cache(maxsize=31)
def _worm_pixels(frame, _stance):
    atlas = _worm_atlas()
    width, height = WORM_SIZE
    ox, oy = frame % 8 * width, frame // 8 * height
    pixels = {}
    for y in range(height):
        for x in range(width):
            color = atlas.get_at((ox + x, oy + y))
            if color.a:
                pixels[WORM_FOOT[0] - x, y - WORM_FOOT[1]] = (color.r, color.g, color.b)
    return pixels


ART = {
    MobKind.CHICKEN: farm_art.chicken, MobKind.PIG: farm_art.pig,
    MobKind.SANDWORM: _worm_pixels,
    MobKind.DEER: wild_art.deer, MobKind.SNAKE: wild_art.snake, MobKind.SPIDER: wild_art.spider,
    MobKind.SKELETON: skeleton_art.archer, MobKind.ARMADILLO: armadillo_art.armadillo,
    MobKind.SHARK: shark_art.shark,
    MobKind.MINE_MONSTER: mine_monster_art.mine_monster,
    MobKind.GUARDIAN: guardian_art.guardian,
}
WINDUP_STANCE = {"kick": "kick_ready", "charge": "charge_ready", "strike": "strike_ready"}
CANVAS = (40, 36)
ANCHOR = (20, 32)


def mob_pose(mob):
    if mob.kind is MobKind.GUARDIAN:
        from spawnbound.domain.boss import stance
        return (mob.kind, mob.left, *stance(mob))
    if mob.kind is MobKind.SANDWORM:
        return mob.kind, mob.left, mob.worm_frame, "hurt" if mob.flash > 0 else "idle"
    moving = mob.progress < 1
    stride = int(mob.progress * (8 if mob.flee_time or mob.charge is not None else 4)) % 2 if moving else 0
    stance = "walk" if moving else "idle"
    if mob.curled > 0:
        stride = int(mob.lunge * 20) % 2 if mob.lunge > 0 else int(mob.progress * 4) % 2 if moving else 0
        return mob.kind, mob.left, stride, "ball_hurt" if mob.flash > 0 else "ball"
    if mob.asleep:
        return mob.kind, mob.left, 0, "sleep"
    if mob.flash > 0:
        stance = "hurt"
    elif mob.windup > 0:
        stance = WINDUP_STANCE[mob.attack]
        stride = int(mob.windup * 10) % 2
    elif mob.lunge > 0:
        stance = "kick" if mob.kind is MobKind.DEER else "strike"
    elif mob.charge is not None:
        stance = "charge"
    elif mob.dazed > 0:
        stance = "dazed"
    elif mob.shot_time > 0:
        stance = "release"
    elif mob.aiming and mob.shoot_in < .65:
        stance = "draw"
    elif moving and mob.flee_time > 0:
        stance = "run"
    elif mob.kind is MobKind.SNAKE and mob.anger > 0 and not moving:
        stance = "alert"
        stride = int(max(0., mob.wait) * 10) % 2
    elif not moving and int(max(0, mob.wait)*2) % 3 == 1:
        stance = "rest"
    return mob.kind, mob.left, stride, stance


def _tinted(color):
    return (min(255, 99 + color[0]*2//3), color[1]//3, color[2]//3)


@lru_cache(maxsize=256)
def posed_pixels(kind, left, stride, stance):
    result = {}
    base = {"hurt": "idle", "ball_hurt": "ball"}.get(stance, stance)
    for (x, y), color in ART[kind](stride, base).items():
        if stance == "hurt":
            x -= int(y < -3) + int(y < -8)
            y -= 1
        if stance in ("hurt", "ball_hurt"):
            color = _tinted(color)
        result[-x if left else x, y] = color
    return result


def mob_pixels(mob):
    return posed_pixels(*mob_pose(mob))


@lru_cache(maxsize=96)
def _pick(kind, left, stride, stance):
    if kind is MobKind.SHARK:
        return frozenset()
    body = posed_pixels(kind, left, stride, stance)
    if kind is not MobKind.SNAKE:
        return body
    return frozenset((x + dx, y + dy) for x, y in body for dx in (-1, 0, 1) for dy in (-1, 0, 1))


def pick_pixels(mob):
    return _pick(*mob_pose(mob))


def head_top(mob) -> tuple[int, int]:
    return min(mob_pixels(mob), key=lambda p: (p[1], abs(p[0])))


def sprite_layout(kind):
    if kind is MobKind.SANDWORM:
        return WORM_SIZE, WORM_FOOT
    if kind is MobKind.GUARDIAN:
        return guardian_art.SIZE, guardian_art.FOOT
    return CANVAS, ANCHOR


@lru_cache(maxsize=192)
def sprite(kind, left, stride, stance, scale):
    import pygame
    size, anchor = sprite_layout(kind)
    image = pygame.Surface(size, pygame.SRCALPHA)
    for (x, y), color in posed_pixels(kind, left, stride, stance).items():
        image.set_at((anchor[0]+x, anchor[1]+y), color)
    return pygame.transform.scale(image, (round(size[0]*scale), round(size[1]*scale)))


def draw_mob(screen, mob, foot, scale):
    image = sprite(*mob_pose(mob), scale)
    _, anchor = sprite_layout(mob.kind)
    draw_on(screen, Picture(image, (foot[0]-round(anchor[0]*scale), foot[1]-round(anchor[1]*scale))))
