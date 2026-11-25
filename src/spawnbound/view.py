from __future__ import annotations

import math
from collections.abc import Iterator
from dataclasses import dataclass

from spawnbound.config import GameConfig
from spawnbound.domain.inventory import CHEST_COLUMNS, CHEST_SIZE, HOTBAR_SIZE, SLOT_COUNT
from spawnbound.domain.coordinates import GridPos, WorldPos, grid_to_screen, screen_to_grid, screen_to_grid_cell
from spawnbound.domain.archipelago import dock_front, pier_cells
from spawnbound.domain.crafting import MIRRORED
from spawnbound.domain.session import GameSession
from spawnbound.mob_art import pick_pixels
from spawnbound.domain.model import OCEAN_WIDTH, PALMS, ObjectKind, Portal, SpaceKind, TileKind, TreeVariant, World, WorldObject


MINIMAP_WIDTH = 214
MINIMAP_TOP = 108
MINIMAP_BOTTOM = 224


GridPoint = GridPos | WorldPos | tuple[float, float] | tuple[float, float, float]


def camera_origin(
    session: GameSession,
    config: GameConfig,
    player_position: GridPoint | None = None,
) -> tuple[float, float]:
    if config.camera_zoom != 1:
        return config.world_to_view(camera_origin(session, config.world_view_config, player_position))
    if session.world.space_kind is SpaceKind.INTERIOR:
        return config.virtual_width / 2, config.virtual_height * .455 - 5.5 * config.tile_height
    preview_size = session.world.chunk_preview_size
    if preview_size is not None:
        player_x, player_y = project_grid_point(
            player_position or session.player.position3d,
            config,
        )
        desired_x = config.virtual_width / 2 - player_x
        desired_y = config.virtual_height / 2 - player_y

        half_width = config.tile_width / 2
        half_height = config.tile_height / 2
        margin = OCEAN_WIDTH if session.world.tile_map.ocean_island_size else 0
        world_right = (preview_size + 2 * margin) * half_width
        world_left = -world_right
        world_top = -margin * config.tile_height - half_height
        world_bottom = (preview_size - 1 + margin) * config.tile_height + half_height

        min_x = 24 - world_right
        max_x = config.virtual_width - 24 - world_left
        min_y = config.virtual_height * (430 / 540) - world_bottom
        max_y = config.virtual_height * (136 / 540) - world_top
        return (
            max(min_x, min(desired_x, max_x)),
            max(min_y, min(desired_y, max_y)),
        )

    projected = [
        grid_to_screen(position, config.tile_width, config.tile_height)
        for position in session.world.tile_map.tiles
    ]
    projected.extend(
        grid_to_screen(position, config.tile_width, config.tile_height)
        for position in session.world.bridge.cells
    )
    min_x = min(point[0] for point in projected)
    max_x = max(point[0] for point in projected)
    min_y = min(point[1] for point in projected)
    max_y = max(point[1] for point in projected)
    world_width = (max_x - min_x) + config.tile_width
    world_height = (max_y - min_y) + config.tile_height
    origin_x = (config.virtual_width - world_width) / 2 - min_x
    origin_y = config.virtual_height * (122 / 540) + (config.virtual_height * (285 / 540) - world_height) / 2 - min_y
    return origin_x, origin_y


def screen_center(
    position: GridPoint,
    origin: tuple[float, float],
    config: GameConfig,
) -> tuple[int, int]:
    local_x, local_y = project_grid_point(position, config)
    return round(origin[0] + local_x), round(origin[1] + local_y)


def project_grid_point(position: GridPoint, config: GameConfig) -> tuple[float, float]:
    if config.camera_zoom != 1:
        return config.world_to_view(project_grid_point(position, config.world_view_config))
    if isinstance(position, GridPos):
        return grid_to_screen(position, config.tile_width, config.tile_height)
    if isinstance(position, WorldPos):
        x, y, z = position.x, position.y, position.z
    else:
        x, y = position[:2]
        z = position[2] if len(position) == 3 else 0
    return (
        (x - y) * (config.tile_width / 2),
        (x + y) * (config.tile_height / 2) - z * config.height_unit_pixels,
    )


def grid_cell_at_view_point(
    point: tuple[float, float],
    origin: tuple[float, float],
    config: GameConfig,
) -> GridPos:
    if config.camera_zoom != 1:
        return grid_cell_at_view_point(config.view_to_world(point), config.view_to_world(origin),
                                       config.world_view_config)
    return screen_to_grid_cell(
        point[0] - origin[0],
        point[1] - origin[1],
        config.tile_width,
        config.tile_height,
    )


SLOT_SIZE = 36
SLOT_PITCH = 39
HUD_HEADROOM = 28


def hotbar_rect(config: GameConfig) -> tuple[int, int, int, int]:
    width = (HOTBAR_SIZE - 1) * SLOT_PITCH + SLOT_SIZE
    return (config.virtual_width // 2 - width // 2, config.virtual_height - 46, width, SLOT_SIZE)


PACK_PITCH = 56
PACK_SLOT = 52
PACK_GAP = 24


def inventory_panel(config: GameConfig, chest: bool = False) -> tuple[int, int, int, int]:
    width = HOTBAR_SIZE * PACK_PITCH - 4
    if chest:
        width += PACK_GAP + CHEST_COLUMNS * PACK_PITCH - 4
    return (config.virtual_width - width) // 2, (config.virtual_height - 280) // 2, width, 280


def slot_rect(config: GameConfig, index: int, backpack: bool, chest: bool = False) -> tuple[int, int, int, int]:
    left, top, _, _ = hotbar_rect(config)
    if backpack:
        left, top, _, _ = inventory_panel(config, chest)
        top += 48
        if index >= SLOT_COUNT:
            row, col = divmod(index - SLOT_COUNT, CHEST_COLUMNS)
        else:
            if chest:
                left += CHEST_COLUMNS * PACK_PITCH - 4 + PACK_GAP
            row, col = divmod(index, HOTBAR_SIZE)
            if row == 0:
                row, top = 3, top + 9
            else:
                row -= 1
        return left + col * PACK_PITCH, top + row * PACK_PITCH, PACK_SLOT, PACK_SLOT
    return left + (index % HOTBAR_SIZE) * SLOT_PITCH, top, SLOT_SIZE, SLOT_SIZE


def slot_at(config: GameConfig, point: tuple[float, float], backpack: bool, chest: bool = False) -> int | None:
    from spawnbound.pplay_ui import pointed
    if pointed(inventory_panel(config, chest) if backpack else hotbar_rect(config), point):
        count = SLOT_COUNT + CHEST_SIZE if chest else SLOT_COUNT
        for index in range(count if backpack else HOTBAR_SIZE):
            sx, sy, size, _ = slot_rect(config, index, backpack, chest)
            if pointed((sx, sy, size, size), point):
                return index
    return None


def is_world_view_point(point: tuple[float, float], config: GameConfig, *, debug: bool = False) -> bool:
    x, y = point
    if not (0 <= x < config.virtual_width and 0 <= y < config.virtual_height):
        return False
    left, top, width, height = hotbar_rect(config)
    if left - 1 <= x < left + width + 1 and top - HUD_HEADROOM <= y < top + height + 1:
        return False
    if debug and y < 92:
        return False
    return not (debug and
        x >= config.virtual_width - MINIMAP_WIDTH
        and MINIMAP_TOP <= y < MINIMAP_BOTTOM
    )


def visible_grid_positions(origin: tuple[float, float], config: GameConfig,
                           *, object_height: int = 0,
                           bounds: tuple[int, int, int, int] | None = None) -> Iterator[GridPos]:
    min_depth, max_depth, min_side, max_side = bounds or visible_grid_bounds(origin, config, object_height)
    for depth in range(min_depth, max_depth + 1):
        first = min_side + ((depth - min_side) % 2)
        for side in range(first, max_side + 1, 2):
            yield GridPos((depth + side) // 2, (depth - side) // 2)


def visible_grid_bounds(origin: tuple[float, float], config: GameConfig,
                        object_height: int = 0) -> tuple[int, int, int, int]:
    if config.camera_zoom != 1:
        return visible_grid_bounds(config.view_to_world(origin), config.world_view_config, object_height)
    half_w, half_h = config.tile_width / 2, config.tile_height / 2
    min_depth = math.floor((-config.tile_height - origin[1]) / half_h)
    max_depth = math.ceil((config.virtual_height + object_height - origin[1]) / half_h)
    side_padding = config.tile_width
    min_side = math.floor((-side_padding - origin[0]) / half_w)
    max_side = math.ceil((config.virtual_width + side_padding - origin[0]) / half_w)
    return min_depth, max_depth, min_side, max_side


def grid_bounds_for_rect(world: World, origin: tuple[float, float], config: GameConfig,
                         rect: tuple[float, float, float, float]) -> tuple[int, int, int, int]:
    left, top, right, bottom = rect
    w, h = config.tile_width, config.tile_height
    half_w, half_h = w / 2, h / 2
    max_elevation = world.tile_map.max_elevation
    lift = max_elevation * config.height_unit_pixels
    drop = (max_elevation + 1) * config.height_unit_pixels
    sprite = config.world_sprite_padding + h
    side = w + sprite // 2
    return (math.floor((top - h - drop - origin[1]) / half_h),
            math.ceil((bottom + sprite + lift - origin[1]) / half_h),
            math.floor((left - side - origin[0]) / half_w),
            math.ceil((right + side - origin[0]) / half_w))


@dataclass(frozen=True, slots=True)
class SceneItem:
    kind: str
    position: GridPos | WorldPos
    payload: object = None


SCENE_PRIORITY = {"tile": 0, "goal": 1, "torch": 1, "object": 2, "crop": 2, "portal": 3, "fire": 3,
                  "sails": 3, "mob": 4, "player": 5, "arrow": 6, "effect": 4}


CREATURE_VIEW_RADIUS = 48


def creature_items(session):
    if session.world is not session.wildlife.world:
        return []
    player = session.player.position
    return [SceneItem("mob", m.location.grid, m) for m in session.wildlife.mobs.values()
            if max(abs(m.end.x - player.x), abs(m.end.y - player.y)) <= CREATURE_VIEW_RADIUS]


def scene_depth_key(item: SceneItem) -> tuple[float, float, int]:
    p = item.position
    if item.kind == "object" and item.payload.kind is ObjectKind.DOCK:
        p = dock_front(item.payload)
    return p.x + p.y, p.x, SCENE_PRIORITY[item.kind]


def scene_items(session: GameSession, origin: tuple[float, float], config: GameConfig,
                player_position: WorldPos | None = None,
                bounds: tuple[int, int, int, int] | None = None) -> list[SceneItem]:
    world = session.world
    padding = config.world_sprite_padding + world.tile_map.max_elevation * config.height_unit_pixels
    items = []
    dock = world.objects.get(world.dock) if world.dock is not None else None
    reach = pier_cells(dock) if dock is not None and dock.kind is ObjectKind.DOCK else ()
    dock_seen = False
    for p in visible_grid_positions(origin, config, object_height=padding, bounds=bounds):
        tile = world.tile_map.tile_at(p)
        if tile is None:
            continue
        items.append(SceneItem("tile", p, tile))
        if p in world.guides.toward_exit:
            items.append(SceneItem("torch", p))
        if reach and p in reach:
            dock_seen = True
        obj = world.object_at(p)
        if obj is not None and obj is not dock:
            items.append(SceneItem("object", p, obj))
        portal = world.portals.get(p)
        if portal is not None:
            items.append(SceneItem("portal", p, portal))
        if p == world.goal and world.chunk_preview_size is None:
            items.append(SceneItem("goal", p))
    if dock_seen:
        items.append(SceneItem("object", dock.position, dock))
    if player_position is not None:
        items.append(SceneItem("player", player_position))
    items.sort(key=scene_depth_key)
    return items


def terrain_polygons(world: World, p: GridPos, origin: tuple[float, float],
                     config: GameConfig) -> tuple[list[tuple[int, int]], ...]:
    if config.camera_zoom != 1:
        polygons = terrain_polygons(world, p, config.view_to_world(origin), config.world_view_config)
        return tuple([tuple(round(v) for v in config.world_to_view(point)) for point in polygon]
                     for polygon in polygons)
    x, y = screen_center(world.surface_position(p), origin, config)
    w, h = config.tile_width // 2, config.tile_height // 2
    top = [(x, y - h), (x + w, y), (x, y + h), (x - w, y)]
    faces = [top]
    for neighbor, edge in ((p + GridPos(0, 1), ((x - w, y), (x, y + h))),
                           (p + GridPos(1, 0), ((x, y + h), (x + w, y)))):
        tile = world.tile_map.tile_at(neighbor)
        neighbor_height = tile.elevation if tile is not None else -1
        drop = (world.elevation_at(p) - neighbor_height) * config.height_unit_pixels
        if drop > 0:
            a, b = edge
            faces.append([a, b, (b[0], b[1] + drop), (a[0], a[1] + drop)])
    return tuple(faces)


def polygon_contains(point: tuple[float, float], polygon: tuple | list) -> bool:
    if not polygon:
        return False
    x, y = point
    crosses = [(bx - ax) * (y - ay) - (by - ay) * (x - ax)
               for (ax, ay), (bx, by) in zip(polygon, (*polygon[1:], polygon[0]))]
    return all(c >= 0 for c in crosses) or all(c <= 0 for c in crosses)


def portal_contains(portal: Portal, dx: float, dy: float) -> bool:
    if portal.target_kind is SpaceKind.INTERIOR:
        from spawnbound.cottage_art import PIVOT, cottage
        p = (round(dx+PIVOT[0]), round(dy+PIVOT[1]))
        image = cottage()
        return image.get_rect().collidepoint(p) and image.get_at(p).a > 0
    return -16 <= dx <= 16 and -31 <= dy <= 4


def object_contains(obj: WorldObject, dx: float, dy: float, seconds: float = 0.0) -> bool:
    if obj.variant == "right" and obj.kind.value in MIRRORED:
        dx = -dx
    if obj.kind is ObjectKind.DOCK:
        from spawnbound.dock_art import dock_sprite
        sprite, (fx, fy) = dock_sprite(obj.variant, obj.elevation)
        local = round(dx) + fx, round(dy) + fy
        return sprite.get_rect().collidepoint(local) and sprite.get_at(local).a > 0
    if obj.kind is ObjectKind.WAYSTONE:
        from spawnbound.waystone_art import waystone_sprite
        sprite, (fx, fy) = waystone_sprite(obj.variant, obj.available)
        local = round(dx) + fx, round(dy) + fy
        return sprite.get_rect().collidepoint(local) and sprite.get_at(local).a > 0
    if obj.kind is ObjectKind.WINDMILL:
        from spawnbound.sprites import sail_frame, windmill_sails, windmill_sprite
        restored = obj.variant == "restored"
        if restored:
            sails, (fx, fy) = windmill_sails(sail_frame(seconds))
            local = round(dx) + fx, round(dy) + fy
            if sails.get_rect().collidepoint(local) and sails.get_at(local).a:
                return True
        sprite, (fx, fy) = windmill_sprite(restored=restored)
        local = round(dx) + fx, round(dy) + fy
        return sprite.get_rect().collidepoint(local) and sprite.get_at(local).a > 0
    if obj.kind in (ObjectKind.KILN, ObjectKind.BENCH):
        from spawnbound.kiln_workbench_art import placed_kiln, placed_workbench
        placed = placed_kiln if obj.kind is ObjectKind.KILN else placed_workbench
        sprite, (fx, fy) = placed(obj.variant == "right")
        local = round(dx) + fx, round(dy) + fy
        return sprite.get_rect().collidepoint(local) and sprite.get_at(local).a > 0
    if obj.kind is ObjectKind.CAMPFIRE:
        from spawnbound.campfire_art import placed_campfire, placed_flame
        body, (fx, fy) = placed_campfire()
        area = body.get_bounding_rect().union(placed_flame(0)[0].get_bounding_rect())
        return area.collidepoint(round(dx) + fx, round(dy) + fy)
    if obj.production is not None or obj.kind in (ObjectKind.BED, ObjectKind.TORCH):
        from spawnbound.craft_art import station_sprite
        sprite = station_sprite(obj.kind.value)
        local = round(dx) + sprite.get_width() // 2, round(dy) + sprite.get_height() - 3
        return sprite.get_rect().collidepoint(local) and sprite.get_at(local).a > 0
    if obj.kind is ObjectKind.TREE and obj.variant in PALMS:
        from spawnbound.palm_art import placed_palm
        sprite, (fx, fy) = placed_palm(obj.variant)
        local = round(dx) + fx, round(dy) + fy
        return sprite.get_rect().collidepoint(local) and sprite.get_at(local).a > 0
    if obj.kind is ObjectKind.MUSHROOM:
        from spawnbound.mushroom_art import placed_mushroom
        sprite, (fx, fy) = placed_mushroom(obj.variant, obj.position)
        return sprite.get_bounding_rect().inflate(6, 6).collidepoint(round(dx) + fx, round(dy) + fy)
    if obj.kind is ObjectKind.ROCK:
        from spawnbound.rock_art import placed_rock, rock_shape
        sprite, (fx, fy) = placed_rock(obj.variant, rock_shape(obj.position))
        local = round(dx) + fx, round(dy) + fy
        return sprite.get_rect().collidepoint(local) and sprite.get_at(local).a > 0
    if obj.kind is ObjectKind.CACTUS:
        from spawnbound.desert_art import cactus
        x, y = round(dx+21), round(dy+45)
        return 0 <= x < 42 and 0 <= y < 48 and cactus(obj.variant).get_at((x,y)).a > 0
    if obj.kind is ObjectKind.CHEST:
        return polygon_contains((dx, dy), ((-14, -15), (1, -22), (14, -16), (14, -4), (0, 3), (-14, -3)))
    hit = False
    if obj.kind is ObjectKind.TREE:
        hit = -4 <= dx <= 4 and -32 <= dy <= 0
        if obj.variant in (TreeVariant.PINE_DARK.value, TreeVariant.PINE_LIGHT.value):
            triangles = ((-72, -36, 19), (-59, -22, 22)) if obj.variant == TreeVariant.PINE_DARK.value else ((-69, -35, 18), (-56, -21, 21))
            hit |= any(top <= dy <= bottom and abs(dx) <= radius * (dy - top) / (bottom - top)
                       for top, bottom, radius in triangles)
        else:
            hit |= any((dx - ox) ** 2 + (dy - oy) ** 2 <= radius ** 2
                       for ox, oy, radius in ((-10, -43, 17), (11, -42, 16), (0, -55, 18), (-4, -35, 15)))
    elif obj.kind is ObjectKind.BERRY_BUSH:
        hit = any((dx - ox) ** 2 + (dy - oy) ** 2 <= radius ** 2
                  for ox, oy, radius in ((-8, -11, 9), (7, -12, 10), (0, -17, 9)))
    else:
        ax, bx = (-20, 20) if obj.variant == "northwest" else (20, -20)
        vx, vy = bx - ax, 19
        t = max(0, min(1, ((dx - ax) * vx + (dy + 18) * vy) / (vx * vx + vy * vy)))
        hit = (dx - ax - t * vx) ** 2 + (dy + 18 - t * vy) ** 2 <= 36
    return hit


@dataclass(frozen=True, slots=True)
class WorldHit:
    position: GridPos
    kind: str
    surface: bool = True
    mob_id: int | None = None


def walk_point_from_hit(hit: WorldHit, point: tuple[float, float],
                        origin: tuple[float, float], world: World, config: GameConfig) -> WorldPos:
    if config.camera_zoom != 1:
        return walk_point_from_hit(hit, config.view_to_world(point), config.view_to_world(origin),
                                   world, config.world_view_config)
    if not hit.surface:
        return world.surface_position(hit.position)
    z = world.elevation_at(hit.position)
    water_lift = config.water_lift if hit.kind == "water" else 0
    x, y = screen_to_grid(point[0] - origin[0],
                          point[1] - origin[1] + z * config.height_unit_pixels + water_lift,
                          config.tile_width, config.tile_height)
    x = min(hit.position.x + .5 - 1e-9, max(hit.position.x - .5, x))
    y = min(hit.position.y + .5 - 1e-9, max(hit.position.y - .5, y))
    return WorldPos(x, y, z)


def station_outputs(session: GameSession, origin, config):
    scale = config.world_art_scale
    for position in session.world.placed_stations:
        obj = session.world.objects[position]
        job = obj.production
        if job is None:
            continue
        job.refresh(session.production_seconds)
        kinds = len(job.outputs)
        if kinds:
            x, y = screen_center(obj.position3d, origin, config)
            size = round(20 * scale)
            width = size + (kinds - 1) * round(16 * scale)
            yield obj, (x - width // 2, y - round(44 * scale), width, size)


def pick_world_point(session: GameSession, point: tuple[float, float],
                     origin: tuple[float, float], config: GameConfig, art_hit_test=None) -> WorldHit | None:
    if config.camera_zoom != 1:
        return pick_world_point(session, config.view_to_world(point), config.view_to_world(origin),
                                config.world_view_config, art_hit_test)
    for obj, (x, y, w, h) in station_outputs(session, origin, config):
        if x <= point[0] < x + w and y <= point[1] < y + h:
            return WorldHit(obj.position, "object")
    padding = config.world_sprite_padding + session.world.tile_map.max_elevation * config.height_unit_pixels
    view = visible_grid_bounds(origin, config, padding)
    near = grid_bounds_for_rect(session.world, origin, config, (point[0], point[1], point[0] + 1, point[1] + 1))
    bounds = (max(view[0], near[0]), min(view[1], near[1]), max(view[2], near[2]), min(view[3], near[3]))
    items = scene_items(session, origin, config, bounds=bounds)
    items.extend(creature_items(session))
    items.sort(key=scene_depth_key)
    for item in reversed(items):
        p = item.position
        if not isinstance(p, GridPos):
            continue
        center = screen_center(item.payload.location if item.kind == "mob" else session.world.surface_position(p),
                               origin, config)
        dx, dy = point[0] - center[0], point[1] - center[1]
        if item.kind == "mob":
            pixel = (round(dx/config.world_art_scale), round(dy/config.world_art_scale))
            if pixel in pick_pixels(item.payload):
                return WorldHit(p, "mob", mob_id=item.payload.id)
            continue
        if item.kind == "portal" and session.world.space_kind is SpaceKind.INTERIOR:
            if polygon_contains(point, terrain_polygons(session.world, p, origin, config)[0]):
                return WorldHit(p, "portal")
            continue
        if art_hit_test is not None and item.kind in ('object', 'portal'):
            opaque = art_hit_test(item.kind, item.payload, dx, dy)
            if opaque is not None:
                if opaque:
                    return WorldHit(p, item.kind)
                continue
        dx, dy = dx / config.world_art_scale, dy / config.world_art_scale
        if item.kind == "object" and object_contains(item.payload, dx, dy, session.production_seconds):
            return WorldHit(p, "object")
        if item.kind == "portal" and portal_contains(item.payload, dx, dy):
            return WorldHit(p, "portal")
        if item.kind == "tile":
            polygons = terrain_polygons(session.world, p, origin, config)
            if item.payload.kind is TileKind.WATER:
                if polygon_contains((point[0], point[1] + config.water_lift), polygons[0]):
                    return WorldHit(p, "water")
                continue
            if polygon_contains(point, polygons[0]):
                return WorldHit(p, "tile")
            if any(polygon_contains(point, face) for face in polygons[1:]):
                return WorldHit(p, "tile", surface=False)
    return None


def object_at_view_point(session: GameSession, point: tuple[float, float],
                         origin: tuple[float, float], config: GameConfig) -> GridPos | None:
    hit = pick_world_point(session, point, origin, config)
    return hit.position if hit is not None and hit.kind == "object" else None
