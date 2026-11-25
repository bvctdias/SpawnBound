from spawnbound.domain.mobs import MobKind

WARNINGS = {
    MobKind.SNAKE: "snake_hiss",
    MobKind.SPIDER: "spider_chitter",
    MobKind.DEER: "deer_snort",
    MobKind.MINE_MONSTER: "mine_growl",
}

HURT_SOUNDS = {
    MobKind.SNAKE: "snake_hit",
    MobKind.SPIDER: "spider_hit",
    MobKind.MINE_MONSTER: "mine_hit",
    MobKind.SANDWORM: "worm_hit",
}

GUARDIAN_ACTIONS = {"windup": "rock_grind", "stuck": "guardian_slam", "landed": "guardian_slam",
                    "release": "claw_rush"}


def hit_sound(mob, previous_hp):
    if mob.hp == previous_hp:
        return "shell_block"
    if mob.kind is MobKind.SKELETON:
        return "bone_hit" if mob.hp else "bone_fall"
    if mob.kind is MobKind.GUARDIAN:
        return "stone_hit" if mob.hp else "stone_break"
    return HURT_SOUNDS.get(mob.kind, "strike") if mob.hp else "creature_fall"


def attack_sound(mob):
    if mob.kind is MobKind.GUARDIAN and mob.boss:
        return GUARDIAN_ACTIONS.get(mob.boss.stage)
    if mob.kind is MobKind.SANDWORM:
        if mob.worm_phase == "rise":
            return "sand_burst"
        if mob.worm_phase == "bite" and mob.worm_frame >= 26:
            return "bite_snap"
        return None
    if mob.kind is MobKind.SKELETON and mob.shot_time > 0:
        return "bow_release"
    if mob.windup > 0:
        return WARNINGS.get(mob.kind)
    if mob.kind is MobKind.SHARK and mob.lunge > 0:
        return "shark_surge"
    if mob.charge is not None or (mob.kind is MobKind.DEER and mob.lunge > 0):
        return "claw_rush"
    if mob.kind in (MobKind.SNAKE, MobKind.SPIDER, MobKind.MINE_MONSTER) and mob.lunge > 0:
        return "bite_snap"
    return None
