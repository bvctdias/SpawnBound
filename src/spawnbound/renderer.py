from __future__ import annotations

import bisect
import itertools
import math
import random
import time
from typing import Protocol
from dataclasses import dataclass, field, replace

import pygame

from spawnbound import torchlight
from spawnbound.waystone_art import draw_waystone_lights, waystone_sprite
from spawnbound import break_art
from spawnbound import wear_art
from spawnbound import cottage_art, house_art
from spawnbound.desert_art import cactus
from spawnbound.ambient_life import AmbientLife
from spawnbound.fish_school import school_frame
from spawnbound.seabed import SAND, Sandbank, aquatic_glyph, paint_sandbank, sandbank_at, shore_depth, water_decoration
from spawnbound.mob_art import sprite_layout, draw_mob, head_top, mob_pixels, mob_pose, sprite as mob_sprite
from spawnbound.wild_art import SPIDER_EYE
from spawnbound.kiln_workbench_art import placed_kiln, placed_workbench
from spawnbound.dock_art import dock_sprite
from spawnbound.rock_art import placed_rock, rock_shape
from spawnbound.palm_art import placed_palm
from spawnbound.mushroom_art import mushroom_look, placed_mushroom
from spawnbound.campfire_art import FRAMES as FLAME_FRAMES, Flame, flame_frame, placed_campfire, placed_flame
from spawnbound.crop_art import CropView, crop_sprite, phase_of, wind_frame
from spawnbound.domain.farming import stage as crop_stage
from spawnbound import guardian_art, rest_menu
from spawnbound.domain import boss as guardian_rules
from spawnbound.item_icons import icon
from spawnbound.craft_art import station_sprite
from spawnbound.domain.crafting import MIRRORED
from spawnbound.crafting_view import CraftPanel
from spawnbound.config import GameConfig
from spawnbound.animation import MotionKind, PlayerPose
from spawnbound.inventory_hud import InventoryHUD
from spawnbound.island_map import IslandMap
from spawnbound.sea_chart import SeaChart
from spawnbound.domain.inventory import Inventory
from spawnbound.pixel_font import PixelFont
from spawnbound.sprites import PlayerSprites, sail_frame, soil_texture, windmill_sails, windmill_sprite
from spawnbound.world_primitives import WorldPrimitives
from spawnbound.domain.coordinates import GridPos, WorldPos, grid_to_screen
from spawnbound.domain.daylight import DayPhase
from spawnbound.domain.mobs import MobKind
from spawnbound.domain.spaces import exit_from
from spawnbound.domain.terrain import mill_site
from spawnbound.domain.model import (
    BerryColor,
    Biome,
    GrassVariant,
    ObjectKind,
    Portal,
    SpaceKind,
    Tile,
    TileKind,
    TreeVariant,
    PALMS,
    WorldObject,
)
from spawnbound.domain.model import OBJECT_SPECS
from spawnbound.domain.session import DRAG_SECONDS, HURT_SECONDS, REVIVE_SECONDS, GameSession
from spawnbound.shark_art import placed_shark
from spawnbound.world_effects import WorldFeel, shake_offset
from spawnbound.pplay_ui import show
from spawnbound.view import SceneItem, creature_items, GridPoint, camera_origin, project_grid_point, screen_center, visible_grid_positions, visible_grid_bounds, scene_items, scene_depth_key, station_outputs


BACKGROUND = (29, 35, 42)
VEIL = (10, 8, 14)
VEIL_OPAQUE = .35
# Forçar RGB evita que o alfa da superfície da janela deixe o cenário transparente.
RGB_MASKS = (0xFF0000, 0x00FF00, 0x0000FF, 0)


def opaque_surface(size: tuple[int, int]) -> pygame.Surface:
    return pygame.Surface(size, depth=32, masks=RGB_MASKS)
BRIDGE = (142, 98, 57)
BRIDGE_EDGE = (86, 57, 37)
TEXT = (238, 238, 226)
MUTED_TEXT = (180, 187, 177)
PANEL = (20, 24, 29)
PANEL_EDGE = (68, 76, 82)
ACCENT = (247, 200, 78)
TEXT_SHADOW = (14, 16, 20)
DEBUG_LABEL_CELLS = 6
SLOT = (16, 22, 24, 196)

SHADOW_UNSET = object()

# Cada mundo invalida seus próprios blocos. Uma árvore que rebrota na ilha não invalida a mina.
WORLD_CACHE = ("_chunks", "_chunk_items", "_chunk_signature", "_prepared_map", "_prepared_revision",
               "_prepared_tiles", "_bed_levels", "_shadow_signature", "_shadow_snapshot", "_seen_chips",
               "_block_job", "_prewarm_job", "_static_generation")
GENERATIONS = itertools.count(1)


def fresh_world_cache() -> dict[str, object]:
    return {"_chunks": {}, "_chunk_items": {}, "_chunk_signature": None, "_prepared_map": None,
            "_prepared_revision": -1, "_prepared_tiles": {}, "_bed_levels": {}, "_shadow_signature": None,
            "_shadow_snapshot": {}, "_seen_chips": 0, "_block_job": None, "_prewarm_job": None,
            "_static_generation": next(GENERATIONS)}


class Elsewhere:
    __slots__ = ("_session", "world")

    def __init__(self, session: GameSession, world) -> None:
        self._session = session
        self.world = world

    def __getattr__(self, name: str):
        return getattr(self._session, name)


def background_of(world) -> tuple[int, int, int]:
    return {SpaceKind.CAVE: (8, 8, 12), SpaceKind.INTERIOR: (0, 0, 0)}.get(world.space_kind, BACKGROUND)


@dataclass(slots=True)
class PreparedTerrain:
    tile: Tile
    neighbors: tuple[GridPos, ...]
    neighbor_tiles: tuple[Tile | None, ...]
    surface: pygame.Surface
    local_x: float
    local_y: float
    faces: int
    tone: tuple[int, int, int] = (0, 0, 0)
    shadows: dict[DayPhase, pygame.Surface | None] = field(default_factory=dict)
    detail: object = SHADOW_UNSET
    water: pygame.Surface | None = None


class LightingRenderer(Protocol):
    def draw(self, target: pygame.Surface, session: GameSession) -> None: ...


class NoOpLightingRenderer:
    def draw(self, target: pygame.Surface, session: GameSession) -> None:
        del target, session


class AmbientLighting:
    SKY = {
        DayPhase.DAY: ((255, 255, 255), (0, 0, 0), 0.0),
        DayPhase.AFTERNOON: ((255, 239, 214), (0xEF, 0x82, 0x06), 0.16),
        DayPhase.NIGHT: ((131, 151, 198), (0x31, 0x27, 0x83), 0.24),
    }

    def draw(self, target: pygame.Surface, session: GameSession) -> None:
        if session.world.space_kind is SpaceKind.CAVE:
            target.fill((42, 46, 62), special_flags=pygame.BLEND_RGB_MULT)
            target.fill((3, 4, 8), special_flags=pygame.BLEND_RGB_ADD)
            return
        if session.world.space_kind is not SpaceKind.OUTDOOR:
            return
        light = session.daylight
        if light.phase is DayPhase.DAY and not light.blend:
            return
        gain = [0.0, 0.0, 0.0]
        offset = [0.0, 0.0, 0.0]
        for phase, weight in ((light.phase, 1 - light.blend), (light.phase.following, light.blend)):
            exposure, sky_color, opacity = self.SKY[phase]
            for i in range(3):
                gain[i] += weight * exposure[i] * (1 - opacity)
                offset[i] += weight * sky_color[i] * opacity
        target.fill(tuple(map(round, gain)), special_flags=pygame.BLEND_RGB_MULT)
        target.fill(tuple(map(round, offset)), special_flags=pygame.BLEND_RGB_ADD)


class PlaceholderRenderer:
    def __init__(
        self,
        screen: pygame.Surface,
        config: GameConfig,
        lighting: LightingRenderer | None = None,
        player_sprites: PlayerSprites | None = None,
    ) -> None:
        self.screen = screen
        self.config = config
        self._world_config = config.world_view_config
        self._world_screen = pygame.Surface((self._world_config.virtual_width,
                                             self._world_config.virtual_height), depth=32, masks=RGB_MASKS)
        self._ui_screen = pygame.Surface(screen.get_size(), pygame.SRCALPHA)
        self._ui_bounds = self._ui_screen.get_rect()
        self.direct_presentation = False
        self._presentation_surface = None
        self._fitted_picture: tuple[tuple, pygame.Surface] | None = None
        self._scaled_ui = None
        self._ui_cache_key = None
        self._blurred_scene_key = None
        self.lighting = lighting or AmbientLighting()
        self._phase = DayPhase.DAY
        self._transition_screen: pygame.Surface | None = None
        self.player_sprites = player_sprites
        self._player_pose: PlayerPose | None = None
        self._world_feel = WorldFeel()
        self.font_small = pygame.font.Font(None, 20)
        self.font_world = pygame.font.Font(None, round(20 * self.config.world_art_scale))
        self.font = pygame.font.Font(None, 25)
        self.font_large = pygame.font.Font(None, 48)
        self.pixel_font = PixelFont()
        self.hud = InventoryHUD(self.pixel_font)
        self.island_map = IslandMap(self.pixel_font)
        self.sea_chart = SeaChart(self.pixel_font)
        self._tile_surfaces: dict[tuple, pygame.Surface] = {}
        self._shadow_surfaces: dict[tuple[int, int], pygame.Surface] = {}
        self._placement_sprites = {}
        self._grid_overlays: dict[tuple[int, int, float], pygame.Surface] = {}
        self._top_outlines: dict[tuple[int, int], tuple[dict[int, int], dict[int, int]]] = {}
        self._edge_cue_overlays: dict[tuple, tuple[pygame.Surface, pygame.Surface]] = {}
        self._cast_shadows: dict[tuple, tuple[pygame.Surface, tuple[int, int]] | None] = {}
        self._shadow_signature: tuple | None = None
        self._seen_chips = 0
        self._shadow_snapshot: dict[GridPos, tuple] = {}
        self._shadow_windows: dict[tuple, tuple[GridPos, ...]] = {}
        self._top_alphas: dict[tuple[int, int], pygame.Surface] = {}
        self._tile_tones: dict[tuple, tuple[int, int, int]] = {}
        self._detail_glyphs: dict[tuple, pygame.Surface] = {}
        self._water_overlays: dict[tuple, pygame.Surface] = {}
        self._school = None
        self._sharks_below: list[tuple[pygame.Surface, pygame.Rect]] = []
        self._shark_scratch: pygame.Surface | None = None
        self._swimmer_cut: tuple | None = None
        self.scenery = False
        self.ambient = AmbientLife()
        self.ambient_drawn = (0, 0)
        self._outlines: dict[tuple, tuple[pygame.Surface, tuple[int, int]]] = {}
        self._notice_seen: tuple[int, int] | None = None
        self._message_until = 0
        self.last_draw_counts: dict[str, int] = {}
        self._bed_levels = {}
        self._prepared_map = None
        self._prepared_revision = -1
        self._prepared_tiles: dict[GridPos, PreparedTerrain] = {}
        self._scene_key = None
        self._scene = []
        self._scene_keys: list[tuple] = []
        self._scene_prepared: list[PreparedTerrain | None] = []
        self._chunks: dict[tuple[int, int, DayPhase], pygame.Surface] = {}
        self._chunk_signature: tuple | None = None
        self._chunk_items: dict[tuple[int, int], list[tuple]] = {}
        self._caster_extents: dict[tuple, tuple[int, int, int, int]] = {}
        self._receivers: dict[int, tuple] = {}
        self._actor_boxes: dict[DayPhase, dict[tuple, pygame.Surface]] = {}
        self._still_silhouettes: dict[tuple, pygame.Surface | None] = {}
        self._static_generation = next(GENERATIONS)
        # Os blocos guardam os recursos em repouso. O tremor de cada golpe entra no desenho do quadro.
        self._live_impacts: dict[GridPos, object] = {}
        self._wear_images: dict[tuple, tuple[pygame.Surface, tuple[int, int]]] = {}
        self.frame_spare: float | None = None
        self.last_prefetch_seconds = 0.0
        self._block_job: tuple | None = None
        self._cache_world = None
        self._view_blocks: tuple[range, range] | None = None
        self._kept_worlds: dict[int, tuple[object, dict[str, object]]] = {}
        self._arrival_view: tuple | None = None
        self._prewarm_job = None
        self._defer_prewarm = False

    def draw_gameplay(
        self,
        session: GameSession,
        *,
        debug: bool,
        path: tuple[GridPos, ...] = (),
        player_position: tuple[float, float, float] | tuple[float, float] | None = None,
        action_target: GridPos | None = None,
        player_pose: PlayerPose | None = None,
        inventory_view: (tuple[int | None, int | None, Inventory | None]
                         | tuple[int | None, int | None, Inventory | None, CraftPanel] | None) = None,
        map_view: bool = False,
        placement_preview: tuple[GridPos, str, bool] | None = None,
        rest_view: tuple[bool, str | None] | None = None,
        chart_view: tuple[str | None] | None = None,
        overlay=None,
        scenery: bool = False,
        hud_overlay=None,
    ) -> None:
        self.scenery = scenery
        if player_pose is None:
            in_water = session.world.tile_map.kind_at(session.player.position) is TileKind.WATER
            player_pose = PlayerPose(MotionKind.SWIM if in_water else MotionKind.IDLE, session.player.facing)
        self._player_pose = player_pose
        self.last_prefetch_seconds = 0.0
        paused = (inventory_view is not None or map_view or rest_view is not None or chart_view is not None
                  or overlay is not None)
        if paused:
            key = (id(session), id(session.world), self.config.camera_zoom, self._world_screen.get_size())
            if self._blurred_scene_key == key:
                self._draw_overlay(session, inventory_view, rest_view, chart_view, overlay)
                return
        else:
            self._blurred_scene_key = None
        if player_position is None:
            visual_player = session.player.position3d
        else:
            z = player_position[2] if len(player_position) == 3 else session.world.elevation_at(session.player.position)
            visual_player = WorldPos(player_position[0], player_position[1], z)
        display_screen, display_config = self.screen, self.config
        try:
            self.screen, self.config = self._world_screen, self._world_config
            origin = self._camera_origin(session, visual_player)
            if session.voyage is not None and session.voyage.progress >= VEIL_OPAQUE:
                self.screen.fill(VEIL)
            else:
                self._school = school_frame(session, self.config, origin, self.screen.get_rect(), self._top_alpha)
                self._sharks_below = self._shark_layers(session, origin, visual_player)
                light = session.daylight
                outdoors = session.world.space_kind is SpaceKind.OUTDOOR
                self._phase = light.phase if outdoors else DayPhase.NIGHT
                background = background_of(session.world)
                self.screen.fill(background)
                draw_scene = self._draw_cached_scene if self.config.scene_cache else self._draw_scene
                self._live_impacts = self._impacts_now(session)
                draw_scene(session, origin, visual_player, path, action_target, debug)
                if outdoors and light.blend:
                    size = self.screen.get_size()
                    if self._transition_screen is None or self._transition_screen.get_size() != size:
                        self._transition_screen = pygame.Surface(size, depth=32, masks=RGB_MASKS)
                    self.screen = self._transition_screen
                    self.screen.fill(background)
                    self._phase = light.phase.following
                    draw_scene(session, origin, visual_player, path, action_target, debug)
                    self.screen.set_alpha(round(255 * light.blend))
                    self._world_screen.blit(self.screen, (0, 0))
                    self.screen = self._world_screen
                if debug:
                    self._draw_chunk_boundary(session, origin)
                self._draw_bridge_preview(session, origin)
                ground = self.ambient.draw_ground(self.screen, session, origin, self.config)
                torchlight.draw_lighting(self.screen, session, self.lighting, self.config, origin,
                                         visual_player, self._player_pose, lantern=not scenery)
                draw_waystone_lights(self.screen, session.world, origin, self.config)
                self.ambient_drawn = (ground, self.ambient.draw_glow(self.screen, session, origin, self.config))
                self._draw_spider_eyes(session, origin)
                self._draw_guardian_effects(session, origin)
                self._world_feel.follow(session, origin, self.screen, self.config)
                self._draw_sleep_marks(session, origin)
                self._live_impacts = {}
                self._draw_silhouettes(session, origin, visual_player)
                self._draw_station_outputs(session, origin)
                if not scenery:
                    self._draw_rest_hint(session, origin)
                    self._draw_repair_labels(session, origin)
                if placement_preview:
                    self._draw_placement(session, origin, *placement_preview)
                if session.revive_time > 0:
                    self._draw_revive_fade(session.revive_time)
            if session.voyage is not None:
                self._draw_voyage_veil(session.voyage.progress)
        finally:
            self._live_impacts = {}
            self.screen, self.config = display_screen, display_config
        if paused:
            # O desfoque da pausa só deve atingir o cenário. O texto e os ícones entram depois.
            size = self._world_screen.get_size()
            reduced = pygame.transform.smoothscale(self._world_screen, tuple(max(1, n // 16) for n in size))
            pygame.transform.smoothscale(reduced, size, self._world_screen)
            self._blurred_scene_key = key
            self._draw_overlay(session, inventory_view, rest_view, chart_view, overlay)
            return
        origin = self.config.world_to_view(origin)
        self._ui_screen.fill((0, 0, 0, 0))
        try:
            self.screen = self._ui_screen
            if scenery:
                self._ui_bounds = pygame.Rect(0, 0, 0, 0)
                return
            self._ui_bounds = self.hud.draw_bar(self.screen, self.config, session.player,
                                                hurt=session.hurt_time / HURT_SECONDS)
            notice_bounds = self._draw_notice(session)
            if notice_bounds is not None:
                self._ui_bounds.union_ip(notice_bounds)
            if hud_overlay is not None:
                self._ui_bounds.union_ip(hud_overlay(self.screen, self.config, self.pixel_font))
            guardian_bar = self._draw_guardian_health(session)
            if guardian_bar is not None:
                self._ui_bounds.union_ip(guardian_bar)
            if session.voyage is not None:
                self._ui_bounds.union_ip(self._draw_voyage_caption(session.voyage))
            if debug:
                self._ui_bounds = self._ui_screen.get_rect()
                self._draw_debug(session, origin, path, visual_player)
                self._draw_help(session)
                self._draw_chunk_minimap(session, visual_player)
            if session.completed:
                self._ui_bounds = self._ui_screen.get_rect()
                self._draw_completion_banner(session)
        finally:
            self.screen = display_screen
        if not self.direct_presentation:
            self._present_world()
            self.screen.blit(self._ui_screen, (0, 0))

    def _draw_overlay(self, session, inventory_view, rest_view=None, chart_view=None, overlay=None):
        self._ui_screen.fill((0, 0, 0, 0))
        if overlay is not None:
            self._ui_bounds = overlay(self._ui_screen, self.config, self.pixel_font)
        elif chart_view is not None:
            self._ui_bounds = self.sea_chart.draw(self._ui_screen, self.config, session, *chart_view)
        elif rest_view is not None:
            self._ui_bounds = rest_menu.draw(self._ui_screen, self.config, self.pixel_font, *rest_view)
        elif inventory_view is not None:
            self._ui_bounds = self.hud.draw_pack(self._ui_screen, self.config, session.player.inventory,
                                                 *inventory_view)
        else:
            self._ui_bounds = self.island_map.draw(self._ui_screen, self.config, session)
        if not self.direct_presentation:
            self._present_world()
            self.screen.blit(self._ui_screen, (0, 0))

    def _present_world(self) -> None:
        self._scale_layer(self._world_screen, self.screen)

    @staticmethod
    def _scale_layer(source: pygame.Surface, target: pygame.Surface) -> None:
        source_size = source.get_size()
        target_size = target.get_size()
        if source_size == target_size:
            target.blit(source, (0, 0))
        elif (target_size[0] % source_size[0] == 0
              and target_size[1] % source_size[1] == 0
              and target_size[0] // source_size[0] == target_size[1] // source_size[1]):
            pygame.transform.scale(source, target_size, target)
        else:
            # Na redução fracionária, a média dos pixels evita cintilação durante o movimento da câmera.
            pygame.transform.smoothscale(source, target_size, target)

    def set_camera_zoom(self, zoom: float) -> None:
        if zoom == self.config.camera_zoom:
            return
        self.config = replace(self.config, camera_zoom=zoom)
        self._world_config = self.config.world_view_config
        size = (self._world_config.virtual_width, self._world_config.virtual_height)
        if self._world_screen.get_size() != size:
            self._world_screen = pygame.Surface(size, depth=32, masks=RGB_MASKS)
        self._scene_key = None
        self._static_generation = next(GENERATIONS)

    @property
    def interface_layer(self) -> pygame.Surface:
        return self._ui_screen

    def present_to(self, target: pygame.Surface) -> None:
        width, height = target.get_size()
        ratio = min(width / self.config.virtual_width, height / self.config.virtual_height)
        size = (max(1, int(self.config.virtual_width * ratio)),
                max(1, int(self.config.virtual_height * ratio)))
        offset = ((width - size[0]) // 2, (height - size[1]) // 2)
        target.fill((0, 0, 0))
        exact = self.config.camera_zoom * ratio
        scale = round(exact)
        interface_offset = offset
        shake_x, shake_y = shake_offset()
        offset = (offset[0] + round(shake_x * exact), offset[1] + round(shake_y * exact))
        if scale >= 1 and abs(exact - scale) < 1e-6:
            if scale == 1:
                target.blit(self._world_screen, offset, pygame.Rect(0, 0, *size))
            else:
                world_size = (self._world_screen.get_width() * scale, self._world_screen.get_height() * scale)
                if self._presentation_surface is None or self._presentation_surface.get_size() != world_size:
                    self._presentation_surface = pygame.Surface(world_size, depth=32, masks=RGB_MASKS)
                pygame.transform.scale(self._world_screen, world_size, self._presentation_surface)
                target.blit(self._presentation_surface, offset, pygame.Rect(0, 0, *size))
        else:
            if self._presentation_surface is None or self._presentation_surface.get_size() != size:
                self._presentation_surface = pygame.Surface(size, depth=32, masks=RGB_MASKS)
            self._scale_layer(self._world_screen, self._presentation_surface)
            target.blit(self._presentation_surface, offset)
        self._compose_ui(target, size, interface_offset)

    def _compose_ui(self, target: pygame.Surface, size: tuple[int, int], offset: tuple[int, int]) -> None:
        # O HUD ocupa pouca área. Recortar aqui evita compor uma superfície transparente de tela inteira.
        bounds = self._ui_bounds.clip(self._ui_screen.get_rect())
        if bounds.width and bounds.height:
            bounds = bounds.inflate(2, 2).clip(self._ui_screen.get_rect())
            ui = self._ui_screen.subsurface(bounds)
            key = (size, tuple(bounds), pygame.image.tobytes(ui, 'RGBA'))
            x_scale = size[0] / self.config.virtual_width
            y_scale = size[1] / self.config.virtual_height
            x, y = round(bounds.left*x_scale), round(bounds.top*y_scale)
            ui_size = (max(1, round(bounds.right*x_scale)-x),
                       max(1, round(bounds.bottom*y_scale)-y))
            if key != self._ui_cache_key:
                self._scaled_ui = pygame.Surface(ui_size, pygame.SRCALPHA)
                self._scale_layer(ui, self._scaled_ui)
                self._ui_cache_key = key
            target.blit(self._scaled_ui, (offset[0] + x, offset[1] + y))

    def picture_key(self) -> str:
        width, height = self._world_screen.get_size()
        return f"{type(self).__name__}-{width}x{height}"

    def draw_menu(self, session, camera, paint, veil: float = 0., *, backdrop=None, cover: float = 0.,
                  capture=None) -> None:
        if backdrop is not None and backdrop.get_size() != self._world_screen.get_size():
            backdrop = self._fit_picture(backdrop)
        if session is None:
            if backdrop is not None:
                self._world_screen.blit(backdrop, (0, 0))
            else:
                self._world_screen.fill((10, 14, 26))
        else:
            direct, self.direct_presentation = self.direct_presentation, True
            try:
                self.draw_gameplay(session, debug=False, player_position=camera, scenery=True)
            finally:
                self.direct_presentation = direct
                self.scenery = False
            if capture is not None:
                capture(self._world_screen.copy())
            if backdrop is not None and cover > 0:
                backdrop.set_alpha(round(255 * min(1., cover)))
                self._world_screen.blit(backdrop, (0, 0))
                backdrop.set_alpha(None)
        if veil > 0 and (session is not None or backdrop is not None):
            shade = pygame.Surface(self._world_screen.get_size())
            shade.fill((10, 14, 26))
            shade.set_alpha(round(255 * min(1., veil)))
            self._world_screen.blit(shade, (0, 0))
        self._ui_screen.fill((0, 0, 0, 0))
        self._ui_bounds = paint(self._ui_screen, self.config, self.pixel_font)
        if not self.direct_presentation:
            self._present_world()
            self.screen.blit(self._ui_screen, (0, 0))

    def _fit_picture(self, picture: pygame.Surface) -> pygame.Surface:
        size = self._world_screen.get_size()
        key = (id(picture), picture.get_size(), size)
        if self._fitted_picture is None or self._fitted_picture[0] != key:
            width, height = picture.get_size()
            factor = max(size[0] / width, size[1] / height, 1.)
            image = picture
            if factor > 1.:
                scale = pygame.transform.smoothscale if picture.get_bitsize() >= 24 else pygame.transform.scale
                image = scale(picture, (math.ceil(width * factor), math.ceil(height * factor)))
            left = (image.get_width() - size[0]) // 2
            top = (image.get_height() - size[1]) // 2
            self._fitted_picture = key, image.subsurface((left, top, *size)).copy()
        return self._fitted_picture[1]

    def draw_pause(self) -> None:
        display_screen = self.screen
        try:
            self.screen = self._ui_screen
            self._ui_bounds = self._ui_screen.get_rect()
            overlay = pygame.Surface(self.screen.get_size(), pygame.SRCALPHA)
            overlay.fill((6, 8, 12, 185))
            self.screen.blit(overlay, (0, 0))
            self._center_pixel_text("PAUSADO", TEXT, self.config.virtual_height // 2 - 34, scale=4)
            self._center_pixel_text("ESC para continuar", MUTED_TEXT, self.config.virtual_height // 2 + 14, scale=2)
            self._center_pixel_text("F para alternar janela / tela cheia", MUTED_TEXT, self.config.virtual_height // 2 + 40, scale=2)
        finally:
            self.screen = display_screen
        if not self.direct_presentation:
            self._present_world()
            self.screen.blit(self._ui_screen, (0, 0))

    def _camera_origin(
        self,
        session: GameSession,
        player_position: GridPoint | None = None,
    ) -> tuple[float, float]:
        return camera_origin(session, self.config, player_position)

    def _screen_center(self, position: GridPoint, origin: tuple[float, float]) -> tuple[int, int]:
        return screen_center(position, origin, self.config)

    def _diamond(self, center: tuple[int, int]) -> list[tuple[int, int]]:
        x, y = center
        half_width = self.config.tile_width // 2
        half_height = self.config.tile_height // 2
        return [
            (x, y - half_height),
            (x + half_width, y),
            (x, y + half_height),
            (x - half_width, y),
        ]

    def _ground_center(self, session: GameSession, position: GridPos,
                       origin: tuple[float, float]) -> tuple[int, int]:
        return self._screen_center(session.world.surface_position(position), origin)

    def _draw_scene(self, session: GameSession, origin: tuple[float, float],
                    visual_player: WorldPos, path: tuple[GridPos, ...],
                    action_target: GridPos | None, debug: bool = False) -> None:
        path_cells = set(path) if debug else set(path[-1:])
        world = session.world
        outlined = action_target is not None and (action_target in world.objects or
                   (world.space_kind is not SpaceKind.INTERIOR and action_target in world.portals))
        self._use_world(world)
        if self._prepared_map is not world.tile_map or self._prepared_revision != world.tile_map.revision:
            self._prepared_map = world.tile_map
            self._prepared_revision = world.tile_map.revision
            self._prepared_tiles.clear()
            self._bed_levels.clear()
            self._scene_key = None
        self._sync_shadow_casters(world)
        padding = self.config.world_sprite_padding + world.tile_map.max_elevation * self.config.height_unit_pixels
        bounds = self._snapped_bounds(visible_grid_bounds(origin, self.config, padding))
        scene_key = (id(world), world.tile_map.revision, len(world.tile_map.tiles),
                     len(world.objects), len(world.portals), *bounds)
        if scene_key != self._scene_key:
            self._scene_key = scene_key
            self._scene = scene_items(session, origin, self.config, bounds=bounds)
            self._scene_keys = [scene_depth_key(item) for item in self._scene]
            self._scene_prepared = [None] * len(self._scene)
        counts = {"tiles": 0, "objects": 0, "faces": 0}
        self.last_draw_counts = counts
        insertions = {}
        for actor in self._actors(session, visual_player):
            index = bisect.bisect_right(self._scene_keys, scene_depth_key(actor))
            insertions.setdefault(index, []).append(actor)
        wall_damage = world.wall_damage
        for index, item in enumerate(self._scene):
            for actor in insertions.get(index, ()):
                self._draw_actor(session, actor, origin)
            kind = item.kind
            if kind == "tile":
                position = item.position
                center = self._draw_scene_tile(session, index, item, origin)
                if self._school and item.payload.kind is TileKind.WATER:
                    self._school.paint_tile(self.screen, center, self._water_lift())
                if self._sharks_below and item.payload.kind is TileKind.WATER:
                    self._paint_sharks_below(center, self._scene_keys[index])
                counts["tiles"] += 1
                if path_cells and position in path_cells:
                    if position == path[-1]:
                        self._draw_destination_marker(center)
                    else:
                        pygame.draw.polygon(self.screen, (91, 194, 219), self._diamond(center), 1)
                if action_target is not None and position == action_target and not outlined:
                    pygame.draw.polygon(self.screen, (236, 116, 74), self._diamond(center), 1)
                if wall_damage and position in wall_damage:
                    self._draw_wall_wear(center, wall_damage[position])
            elif kind == "object":
                counts["objects"] += 1
                world_object = world.objects[item.position]
                self._draw_world_object(world_object, origin)
                if outlined and item.position == action_target:
                    self._draw_outline("object", world_object, self._screen_center(world_object.position3d, origin))
            elif kind == "player":
                self._draw_equipped_player(session, origin, visual_player)
            elif kind == "portal":
                self._draw_portal(session, item.payload, origin)
                if outlined and item.position == action_target:
                    self._draw_outline("portal", item.payload, self._ground_center(session, item.position, origin))
            else:
                self._draw_marker(session, item.position, kind, origin)

        for actor in insertions.get(len(self._scene), ()):
            self._draw_actor(session, actor, origin)

    CHUNK = 128
    PREFETCH_BUDGET = .004
    PREFETCH_MIN = .0005
    MAX_CHUNKS = 600

    @property
    def prefetch_budget(self) -> float:
        if self.frame_spare is None:
            return self.PREFETCH_BUDGET
        return min(self.PREFETCH_BUDGET, max(self.PREFETCH_MIN, .5 * self.frame_spare))

    def _draw_cached_scene(self, session: GameSession, origin: tuple[float, float],
                           visual_player: WorldPos, path: tuple[GridPos, ...],
                           action_target: GridPos | None, debug: bool) -> None:
        world = session.world
        self._use_world(world)
        background = self.screen.get_at((0, 0))
        self._check_world_cache(world, background)
        self.last_draw_counts = {"tiles": 0, "objects": 0, "faces": 0, "chunks": 0, "chunks_rendered": 0}
        columns, rows = self._view_blocks = self._blocks_in_view(origin)
        size = self.CHUNK
        camera = (round(origin[0]), round(origin[1]))
        for i in columns:
            for j in rows:
                self.screen.blit(self._chunk(session, (i, j), background), (i * size + camera[0], j * size + camera[1]))
        self.last_draw_counts["chunks"] = len(columns) * len(rows)
        self._prefetch_chunks(session, columns, rows, background)
        self._draw_player_with_occluders(session, origin, visual_player, background)
        self._draw_scene_overlays(session, camera, path, action_target, debug)
        for portal in world.portals.values():
            self._draw_portal_label(session, portal, camera)

    def _blocks_in_view(self, origin: tuple[float, float]) -> tuple[range, range]:
        camera = (round(origin[0]), round(origin[1]))
        size = self.CHUNK
        width, height = self.screen.get_size()
        return (range((-camera[0]) // size, (width - camera[0] - 1) // size + 1),
                range((-camera[1]) // size, (height - camera[1] - 1) // size + 1))

    def _check_world_cache(self, world, background) -> None:
        if self._prepared_map is not world.tile_map or self._prepared_revision != world.tile_map.revision:
            self._prepared_map = world.tile_map
            self._prepared_revision = world.tile_map.revision
            self._prepared_tiles.clear()
            self._bed_levels.clear()
            self._scene_key = None
        signature = (id(world), world.tile_map.revision, len(world.portals),
                     tuple(sorted(world.wall_damage.items())), tuple(background), self.config.tile_width,
                     self.config.height_unit_pixels)
        if signature != self._chunk_signature:
            self._chunks.clear()
            self._chunk_items.clear()
            self._static_generation = next(GENERATIONS)
            self._chunk_signature = signature
        self._sync_shadow_casters(world)

    # Cabem a ilha, a mina e o cenário do menu para que o retorno reaproveite a última vista.
    KEPT_WORLDS = 3
    LANDING_BUDGET = .012
    LANDING_BUDGET_DARK = .025
    LANDING_NEXT_LIGHT = .6

    def _use_world(self, world) -> None:
        if self._cache_world is world:
            return
        left = self._cache_world
        if left is not None:
            state = self._world_cache()
            if self._view_blocks is not None:
                columns, rows = self._view_blocks
                near = lambda i, j, margin: (columns.start - margin <= i < columns.stop + margin
                                             and rows.start - margin <= j < rows.stop + margin)
                state["_chunks"] = {key: block for key, block in self._chunks.items() if near(key[0], key[1], 1)}
                state["_chunk_items"] = {key: items for key, items in self._chunk_items.items() if near(*key, 2)}
            state["_block_job"] = None
            self._keep_world(left, state)
        kept = self._kept_worlds.pop(id(world), None)
        self._set_world_cache(kept[1] if kept is not None and kept[0] is world else fresh_world_cache())
        self._cache_world = world
        self._view_blocks = None
        if self._prewarm_job is not None:
            for _ in self._prewarm_job:
                pass
            self._prewarm_job = None
        self._static_generation = next(GENERATIONS)
        self._scene_key = None

    def _world_cache(self) -> dict[str, object]:
        return {name: getattr(self, name) for name in WORLD_CACHE}

    def _set_world_cache(self, state: dict[str, object]) -> None:
        for name, value in state.items():
            setattr(self, name, value)

    def _keep_world(self, world, state: dict[str, object]) -> None:
        self._kept_worlds.pop(id(world), None)
        self._kept_worlds[id(world)] = (world, state)
        while len(self._kept_worlds) > self.KEPT_WORLDS:
            del self._kept_worlds[next(iter(self._kept_worlds))]

    def prepare_arrival(self, session: GameSession, world, position: GridPos | WorldPos, *,
                        veiled: bool = False) -> bool:
        if not self.config.scene_cache or world is self._cache_world:
            return True
        start = time.perf_counter()
        if not veiled:
            budget = self.prefetch_budget - self.last_prefetch_seconds
        elif session.voyage is not None and session.voyage.progress >= VEIL_OPAQUE:
            budget = self.LANDING_BUDGET_DARK
        else:
            budget = self.LANDING_BUDGET
        deadline = start + budget
        place = Elsewhere(session, world)
        current, current_world = self._world_cache(), self._cache_world
        kept = self._kept_worlds.get(id(world))
        display = (self.screen, self.config, self._phase, self.last_draw_counts)
        self.screen, self.config = self._world_screen, self._world_config
        self.last_draw_counts = {}
        try:
            self._set_world_cache(kept[1] if kept is not None and kept[0] is world else fresh_world_cache())
            self._cache_world = world
            background = pygame.Color(self.screen.unmap_rgb(self.screen.map_rgb(background_of(world))))
            self._defer_prewarm = True
            try:
                self._check_world_cache(world, background)
            finally:
                self._defer_prewarm = False
            while self._prewarm_job is not None:
                if time.perf_counter() >= deadline:
                    return False
                try:
                    next(self._prewarm_job)
                except StopIteration:
                    self._prewarm_job = None
            where = (id(world), position, self.screen.get_size(), self.config.camera_zoom)
            if self._arrival_view is None or self._arrival_view[0] != where:
                point = position if isinstance(position, WorldPos) else world.surface_position(position)
                origin = camera_origin(place, self.config, point)
                columns, rows = self._blocks_in_view(origin)
                middle = ((columns.start + columns.stop - 1) / 2, (rows.start + rows.stop - 1) / 2)
                blocks = sorted(((i, j) for i in columns for j in rows),
                                key=lambda k: abs(k[0] - middle[0]) + abs(k[1] - middle[1]))
                self._arrival_view = (where, blocks)
            blocks = self._arrival_view[1]
            if world.space_kind is SpaceKind.OUTDOOR:
                light = session.daylight
                later = light.progress >= self.LANDING_NEXT_LIGHT
                phases = (light.phase, light.phase.following) if later else (light.phase,)
            else:
                phases = (DayPhase.NIGHT,)
            for phase in phases:
                for key in blocks:
                    if (*key, phase) in self._chunks:
                        continue
                    if time.perf_counter() >= deadline:
                        return False
                    if not self._prepare_block(place, key, phase, background, deadline):
                        return False
            return True
        finally:
            self._keep_world(world, self._world_cache())
            self._set_world_cache(current)
            self._cache_world = current_world
            self.screen, self.config, self._phase, self.last_draw_counts = display
            self.last_prefetch_seconds += time.perf_counter() - start

    def _chunk(self, session: GameSession, key: tuple[int, int], background) -> pygame.Surface:
        surface = self._chunks.get((*key, self._phase))
        if surface is None:
            job = self._block_job
            if job is not None and job[0] == (key, self._phase, self._static_generation):
                self._prepare_block(session, key, self._phase, background, math.inf)
                surface = self._chunks.get((*key, self._phase))
        if surface is None:
            surface = self._render_chunk(session, key, background)
        return surface

    def _render_chunk(self, session: GameSession, key: tuple[int, int], background) -> pygame.Surface:
        size = self.CHUNK
        surface = opaque_surface((size, size))
        surface.fill(background)
        origin = (-key[0] * size, -key[1] * size)
        entries = self._chunk_items.get(key)
        if entries is None:
            entries = self._index_chunk_items(session, key)
        previous, self.screen = self.screen, surface
        impacts, self._live_impacts = self._live_impacts, {}
        try:
            self._draw_static_items(session, [entry[4] for entry in entries], origin)
        finally:
            self.screen = previous
            self._live_impacts = impacts
        self._store_chunk(key, self._phase, surface, entries)
        return surface

    def _store_chunk(self, key: tuple[int, int], phase: DayPhase, surface: pygame.Surface,
                     entries: list[tuple]) -> None:
        if len(self._chunks) >= self.MAX_CHUNKS:
            self._chunks.clear()
            self._chunk_items.clear()
            self._static_generation = next(GENERATIONS)
        self._chunks[(*key, phase)] = surface
        self._chunk_items[key] = entries
        self.last_draw_counts["chunks_rendered"] = self.last_draw_counts.get("chunks_rendered", 0) + 1

    def _prefetch_chunks(self, session: GameSession, columns: range, rows: range, background) -> None:
        light = session.daylight
        outdoors = session.world.space_kind is SpaceKind.OUTDOOR
        if outdoors and self._phase is not light.phase:
            return
        start = time.perf_counter()
        deadline = start + self.prefetch_budget
        center = ((columns.start + columns.stop - 1) / 2, (rows.start + rows.stop - 1) / 2)
        ring = [(i, j) for i in range(columns.start - 1, columns.stop + 1)
                for j in range(rows.start - 1, rows.stop + 1)]
        ring.sort(key=lambda k: abs(k[0] - center[0]) + abs(k[1] - center[1]))
        phases = (light.phase, light.phase.following) if outdoors and light.progress >= 0.4 else (self._phase,)
        try:
            job = self._block_job
            if job is not None:
                key, phase, generation = job[0]
                if (generation == self._static_generation and phase in phases and key in ring
                        and (*key, phase) not in self._chunks):
                    if not self._prepare_block(session, key, phase, background, deadline):
                        return
                else:
                    self._block_job = None
            for phase in phases:
                for key in ring:
                    if (*key, phase) in self._chunks:
                        continue
                    if not self._prepare_block(session, key, phase, background, deadline):
                        return
        finally:
            self.last_prefetch_seconds += time.perf_counter() - start

    def _prepare_block(self, session: GameSession, key: tuple[int, int], phase: DayPhase,
                       background, deadline: float) -> bool:
        tag = (key, phase, self._static_generation)
        job = self._block_job
        if job is None or job[0] != tag:
            job = self._block_job = (tag, self._block_steps(session, key, phase, background))
        current, self._phase = self._phase, phase
        try:
            while time.perf_counter() < deadline:
                try:
                    next(job[1])
                except StopIteration:
                    self._block_job = None
                    return True
            return False
        finally:
            self._phase = current

    def _block_steps(self, session: GameSession, key: tuple[int, int], phase: DayPhase, background):
        size = self.CHUNK
        left, top = key[0] * size, key[1] * size
        origin = (-left, -top)
        entries = self._chunk_items.get(key)
        if entries is None:
            bounds = self._grid_bounds_for_rect(session, origin, pygame.Rect(0, 0, size, size))
            items = scene_items(session, origin, self.config, bounds=bounds)
            yield
            entries = []
            for n, item in enumerate(items, 1):
                l, t, r, b = self._item_bounds(session, item)
                if l < left + size and r > left and t < top + size and b > top:
                    entries.append((l, t, r, b, item))
                if n % 8 == 0:
                    yield
            self._chunk_items[key] = entries
        surface = opaque_surface((size, size))
        surface.fill(background)
        items = [entry[4] for entry in entries]
        for i in range(0, len(items), 4):
            yield
            previous, self.screen = self.screen, surface
            impacts, self._live_impacts = self._live_impacts, {}
            try:
                self._draw_static_items(session, items[i:i + 4], origin)
            finally:
                self.screen = previous
                self._live_impacts = impacts
        self._store_chunk(key, phase, surface, entries)

    def _invalidate_chunks_around(self, world, position: GridPos, *, chip=False) -> None:
        self._static_generation = next(GENERATIONS)
        if not self._chunks:
            return
        w, h = self.config.tile_width, self.config.tile_height
        x, y = project_grid_point(world.surface_position(position), self._world_config)
        sprite = self.config.world_sprite_padding
        reach = sprite * self.AFTERNOON_SHADOW_RUN + w
        rect = pygame.Rect(round(x - sprite // 2 - w), round(y - sprite - h),
                           round(sprite + 2 * w + reach), round(sprite + sprite * self.SHADOW_FALL + 3 * h))
        if chip:
            rect = pygame.Rect(round(x-w), round(y-h*2), 2*w, h*4)
        size = self.CHUNK
        for i in range(rect.left // size, rect.right // size + 1):
            for j in range(rect.top // size, rect.bottom // size + 1):
                if not chip:
                    self._chunk_items.pop((i, j), None)
                for phase in DayPhase:
                    self._chunks.pop((i, j, phase), None)

    def _grid_bounds_for_rect(self, session: GameSession, origin: tuple[int, int],
                              rect: pygame.Rect) -> tuple[int, int, int, int]:
        w, h = self.config.tile_width, self.config.tile_height
        half_w, half_h = w / 2, h / 2
        max_elevation = session.world.tile_map.max_elevation
        lift = max_elevation * self.config.height_unit_pixels
        drop = (max_elevation + 1) * self.config.height_unit_pixels
        sprite = self.config.world_sprite_padding
        side = w + sprite // 2
        return (math.floor((rect.top - h - drop - origin[1]) / half_h),
                math.ceil((rect.bottom + sprite + lift - origin[1]) / half_h),
                math.floor((rect.left - side - origin[0]) / half_w),
                math.ceil((rect.right + side - origin[0]) / half_w))

    def _draw_static_items(self, session: GameSession, items, origin: tuple[float, float], school=None,
                           sharks: bool = False) -> None:
        world = session.world
        wall_damage = world.wall_damage
        counts = self.last_draw_counts
        for key in ("tiles", "objects", "faces"):
            counts.setdefault(key, 0)
        for item in items:
            kind = item.kind
            if kind == "tile":
                center = self._draw_tile(session, item.position, item.payload, origin)
                if school and item.payload.kind is TileKind.WATER:
                    school.paint_tile(self.screen, center, self._water_lift())
                if sharks and item.payload.kind is TileKind.WATER:
                    self._paint_sharks_below(center, scene_depth_key(item))
                counts["tiles"] += 1
                if wall_damage and item.position in wall_damage:
                    self._draw_wall_wear(center, wall_damage[item.position])
            elif kind == "object":
                counts["objects"] += 1
                self._draw_world_object(world.objects[item.position], origin)
            elif kind == "portal":
                self._draw_portal_static(session, item.payload, origin)
            elif kind in ("mob", "arrow", "player", "effect", "fire", "sails", "crop"):
                self._draw_actor(session, item, origin)
            else:
                self._draw_marker(session, item.position, kind, origin)

    def _draw_scene_overlays(self, session: GameSession, origin: tuple[int, int], path: tuple[GridPos, ...],
                             action_target: GridPos | None, debug: bool) -> None:
        world = session.world
        cells = path if debug else path[-1:]
        for position in cells:
            if world.tile_map.tile_at(position) is None:
                continue
            center = self._ground_center(session, position, origin)
            if position == path[-1]:
                self._draw_destination_marker(center)
            else:
                pygame.draw.polygon(self.screen, (91, 194, 219), self._diamond(center), 1)
        if action_target is None:
            return
        if action_target in world.objects:
            obj = world.objects[action_target]
            self._draw_outline("object", obj, self._screen_center(obj.position3d, origin))
        elif action_target in world.portals and world.space_kind is not SpaceKind.INTERIOR:
            self._draw_outline("portal", world.portals[action_target], self._ground_center(session, action_target, origin))
        elif world.tile_map.tile_at(action_target) is not None:
            center = self._ground_center(session, action_target, origin)
            pygame.draw.polygon(self.screen, (236, 116, 74), self._diamond(center), 1)

    PLAYER_SILHOUETTE = (236, 240, 255, 160)
    HOSTILE_SILHOUETTE = (240, 70, 56, 170)
    ANIMAL_SILHOUETTE = (255, 232, 168, 180)

    def _draw_spider_eyes(self, session: GameSession, origin) -> int:
        if session.world is not session.wildlife.world:
            return 0
        light = session.daylight
        dark = {DayPhase.NIGHT: 1 - light.blend, DayPhase.AFTERNOON: light.blend}.get(light.phase, 0.0)
        if dark <= 0:
            return 0
        scale = self.config.world_art_scale
        px = max(1, round(scale))
        view = self.screen.get_rect().inflate(64 * px, 64 * px)
        glow = _eye_glow(px, round(dark * 4))
        drawn = 0
        for mob in session.wildlife.mobs.values():
            if mob.kind is not MobKind.SPIDER:
                continue
            x, y = self._screen_center(mob.location, origin)
            if not view.collidepoint(x, y):
                continue
            for (ex, ey), color in mob_pixels(mob).items():
                if color == SPIDER_EYE:
                    center = (x + round(ex * scale) + px // 2, y + round(ey * scale) + px // 2)
                    self.screen.blit(glow, glow.get_rect(center=center), special_flags=pygame.BLEND_ADD)
                    drawn += 1
        return drawn

    SLEEP_INK, SLEEP_FILL = (43, 32, 44), (222, 214, 246)
    SLEEP_Z = ("####", "..#.", ".#..", "####")

    def _draw_sleep_marks(self, session: GameSession, origin) -> int:
        if session.world is not session.wildlife.world:
            return 0
        scale = self.config.world_art_scale
        px = max(1, round(scale))
        view = self.screen.get_rect().inflate(64 * px, 64 * px)
        drawn = 0
        for mob in session.wildlife.mobs.values():
            if not mob.asleep:
                continue
            x, y = self._screen_center(mob.location, origin)
            if not view.collidepoint(x, y):
                continue
            hx, hy = head_top(mob)
            for k in range(3):
                rise = (session.cycle_seconds * .45 + mob.id * .37 + k / 3) % 1
                left = x + (hx + 2 + round(rise * 6)) * px
                top = y + (hy - 3 - round(rise * 12)) * px
                cells = [(c, r) for r, line in enumerate(self.SLEEP_Z) for c, ch in enumerate(line) if ch == "#"]
                for c, r in cells:
                    for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1)):
                        if (c + dx, r + dy) not in cells:
                            self.screen.fill(self.SLEEP_INK, (left + (c + dx) * px, top + (r + dy) * px, px, px))
                for c, r in cells:
                    self.screen.fill(self.SLEEP_FILL, (left + c * px, top + r * px, px, px))
            drawn += 1
        return drawn

    def _draw_silhouettes(self, session: GameSession, origin, visual_player: WorldPos) -> None:
        scale = self.config.world_art_scale
        screen_rect = self.screen.get_rect()
        counts = dict(self.last_draw_counts)
        kept: dict[tuple, pygame.Surface | None] = {}
        try:
            for actor in self._actors(session, visual_player):
                key = None
                if actor.kind == "player":
                    color, position = self.PLAYER_SILHOUETTE, actor.payload
                elif actor.kind == "mob":
                    mob = actor.payload
                    color = self.HOSTILE_SILHOUETTE if mob.hostile else self.ANIMAL_SILHOUETTE
                    position = mob.location
                    if self._actor_state(session, actor, origin, (0, 0)) is not None:
                        key = (id(session.world), mob.id, mob_pose(mob), position, self._static_generation, color)
                else:
                    continue
                x, y = self._screen_center(position, origin)
                full = pygame.Rect(x - round(20 * scale), y - round(44 * scale), round(40 * scale), round(56 * scale))
                if actor.kind == "mob" and mob.kind in (MobKind.SANDWORM, MobKind.GUARDIAN):
                    full = self._worm_box(x, y, scale, mob.kind)
                if not full.colliderect(screen_rect):
                    continue
                if key is not None and key in self._still_silhouettes:
                    tint = kept[key] = self._still_silhouettes[key]
                    if tint is not None:
                        self.screen.blit(tint, full)
                    continue
                box = full if key is not None else full.clip(screen_rect)
                tint = self._hidden_tint(session, actor, position, origin, box, color)
                if key is not None:
                    kept[key] = tint
                if tint is not None:
                    self.screen.blit(tint, box)
        finally:
            self.last_draw_counts = counts
            self._still_silhouettes = kept

    @staticmethod
    def _worm_box(x, y, scale, kind=MobKind.SANDWORM):
        size, anchor = sprite_layout(kind)
        box = pygame.Rect(x-round(anchor[0]*scale), y-round(anchor[1]*scale),
                          round(size[0]*scale), round(size[1]*scale))
        if kind is MobKind.GUARDIAN:
            box.union_ip(box.move(0, -round(40 * scale)))
        return box

    def _hidden_tint(self, session, actor, position, origin, box, color) -> pygame.Surface | None:
        front = self._occluders(session, actor, position)
        if not front:
            return None
        body = pygame.mask.from_surface(self._paint_layer(session, [actor], origin, box))
        cover = pygame.mask.from_surface(self._paint_layer(session, front, origin, box))
        hidden = body.overlap_mask(cover, (0, 0))
        if hidden.count() < max(4, body.count() // 8):
            return None
        rim = pygame.mask.Mask(hidden.get_size())
        for offset in ((1, 0), (-1, 0), (0, 1), (0, -1)):
            rim.draw(hidden, offset)
        rim.erase(body, (0, 0))
        rim = rim.overlap_mask(cover, (0, 0))
        tint = rim.to_surface(setcolor=(*(round(c * .22) for c in color[:3]), 210), unsetcolor=(0, 0, 0, 0))
        tint.blit(hidden.to_surface(setcolor=color, unsetcolor=(0, 0, 0, 0)), (0, 0))
        return tint

    def _occluders(self, session: GameSession, actor: SceneItem, position) -> list[SceneItem]:
        world = session.world
        depth = scene_depth_key(actor)
        cx, cy = math.floor(position.x + .5), math.floor(position.y + .5)
        found = []
        for row in range(0, 9):
            for column in range(-3, 4):
                if (row + column) % 2 or (row == 0 and column <= 0):
                    continue
                p = GridPos(cx + (row + column) // 2, cy + (row - column) // 2)
                if row <= 5:
                    obj = world.objects.get(p)
                    if obj is not None:
                        found.append(SceneItem("object", p, obj))
                    portal = world.portals.get(p)
                    if portal is not None:
                        found.append(SceneItem("portal", p, portal))
                tile = world.tile_map.tile_at(p)
                if tile is not None and tile.elevation >= position.z + 2:
                    found.append(SceneItem("tile", p, tile))
        dock = world.objects.get(world.dock) if world.dock is not None else None
        if (dock is not None and abs(world.dock.x - cx) + abs(world.dock.y - cy) <= 6
                and all(item.payload is not dock for item in found)):
            found.append(SceneItem("object", world.dock, dock))
        return [item for item in found if scene_depth_key(item) > depth]

    def _paint_layer(self, session: GameSession, items, origin, box: pygame.Rect) -> pygame.Surface:
        layer = pygame.Surface(box.size, pygame.SRCALPHA)
        previous, self.screen = self.screen, layer
        try:
            self._draw_static_items(session, items, (origin[0] - box.x, origin[1] - box.y))
        finally:
            self.screen = previous
        return layer

    def _actors(self, session, visual_player):
        actors = creature_items(session)
        actors.extend(SceneItem("effect", e.location.grid, e) for e in session.afterimages
                      if e.space_id == session.world.space_id)
        if session.world is session.wildlife.world:
            actors.extend(SceneItem("arrow", a.location.grid, a) for a in session.wildlife.arrows)
        world = session.world
        actors.extend(SceneItem("fire", p, Flame(world.surface_position(p), (p.x * 7 + p.y * 3) % FLAME_FRAMES))
                      for p in world.placed_fires)
        if world.crops:
            now, day = session.production_seconds, session.day_seconds
            actors.extend(SceneItem("crop", cell, CropView(world.surface_position(cell), crop.kind,
                                                           crop_stage(crop, now, day), phase_of(cell)))
                          for cell, crop in world.crops.items())
        site = mill_site(world.spawn, world.chunk_preview_size)
        mill = world.objects.get(site)
        if mill is not None and mill.kind is ObjectKind.WINDMILL and mill.variant == "restored":
            actors.append(SceneItem("sails", site, mill.position3d))
        if not self.scenery:
            actors.append(SceneItem("player", visual_player.grid, visual_player))
        return sorted(actors, key=scene_depth_key)

    def _draw_actor(self, session, item, origin):
        if item.kind == "player":
            self._draw_equipped_player(session, origin, item.payload)
            return
        if item.kind == "sails":
            x, y = self._screen_center(item.payload, origin)
            sprite, (fx, fy) = windmill_sails(sail_frame(session.production_seconds), self.config.world_art_scale)
            show(self.screen, sprite, topleft=(x - fx, y - fy))
            return
        actor = item.payload
        x, y = self._screen_center(actor.location, origin)
        scale = self.config.world_art_scale
        if item.kind == "fire":
            sprite, (fx, fy) = placed_flame(flame_frame(session.cycle_seconds, actor.seed), scale)
            show(self.screen, sprite, topleft=(x - fx, y - fy))
            return
        if item.kind == "crop":
            sprite, (fx, fy) = crop_sprite(actor.kind, actor.stage, wind_frame(session.cycle_seconds, actor.phase), scale)
            show(self.screen, sprite, topleft=(x - fx, y - fy))
            return
        if item.kind == "effect":
            self._draw_afterimage(session, actor, origin, x, y)
            return
        if item.kind == "mob" and actor.kind is MobKind.SHARK:
            self._draw_shark(session, actor, x, y, scale)
            return
        if item.kind == "mob" and actor.kind is MobKind.GUARDIAN:
            self._draw_guardian(session, actor, x, y, scale)
            return
        if item.kind == "mob":
            self._draw_contact_shadow((x, y), self.MOB_SHADOW.get(actor.kind, 12), scale)
            draw_mob(self.screen, actor, (x, y), scale)
            if actor.windup > 0 or actor.dazed > 0:
                self._draw_mob_cue(actor, x, y, scale, session.cycle_seconds)
            if actor.kind is MobKind.SKELETON and session.daylight.phase is DayPhase.NIGHT:
                sunrise = session.daylight.blend
                if sunrise > .05:
                    for offset in (-4, 1, 5):
                        flicker = math.sin(session.cycle_seconds*12 + actor.id + offset)
                        height = round((6 + 2*flicker)*sunrise*scale)
                        base = (x + round(offset*scale), y - round(5*scale))
                        if height:
                            pygame.draw.line(self.screen, (233, 121, 42), base,
                                             (base[0], base[1]-height), max(1, round(2*scale)))
                            pygame.draw.circle(self.screen, (255, 209, 96), base, max(1, round(scale)))
        else:
            a = self._screen_center(actor.start, origin)
            b = self._screen_center(actor.end, origin)
            direction = pygame.Vector2(b) - a
            if direction.length_squared():
                direction.scale_to_length(7 * scale)
            tip = (x, y - round(9 * scale))
            tail = (round(x-direction.x), round(tip[1]-direction.y))
            pygame.draw.line(self.screen, (220, 176, 112), tail, tip, max(1, round(scale)))
            pygame.draw.circle(self.screen, (238, 227, 192), tip, max(1, round(scale)))

    def _draw_guardian(self, session, mob, x, y, scale):
        lift = round(mob.boss.lift * self.config.height_unit_pixels) if mob.boss is not None else 0
        shrink = max(.45, 1 - lift / 90)
        self._draw_contact_shadow((x, y), round(self.MOB_SHADOW[MobKind.GUARDIAN] * shrink), scale)
        draw_mob(self.screen, mob, (x, y - lift), scale)
        if mob.windup > 0 or mob.dazed > 0:
            self._draw_mob_cue(mob, x, y - lift, scale, session.cycle_seconds)

    def _draw_guardian_effects(self, session, origin):
        if session.wildlife.world is not session.world:
            return
        world, scale = session.world, self.config.world_art_scale
        tw, th = self.config.tile_width, self.config.tile_height
        for mob in session.wildlife.mobs.values():
            g = mob.boss
            if mob.kind is not MobKind.GUARDIAN or g is None or mob.asleep:
                continue
            if g.marked and g.stage == "windup":
                total = guardian_rules.PUNCH_WINDUP[1 if guardian_rules.wrath(mob) else 0]
                urgency = max(0., min(1., 1 - g.timer / total))
                for cell in g.marked:
                    if cell in world.tile_map.tiles:
                        center = self._screen_center(world.surface_position(cell), origin)
                        guardian_art.draw_mark(self.screen, center, tw, th, urgency, session.cycle_seconds)
            for ring in g.rings:
                if ring.radius > .3:
                    center = self._screen_center(ring.center, origin)
                    guardian_art.draw_ring(self.screen, center, ring.radius * tw / math.sqrt(2),
                                           ring.radius * th / math.sqrt(2))
            for rock in g.rocks:
                t = rock.progress
                at = WorldPos(rock.start.x + (rock.target.x - rock.start.x) * t,
                              rock.start.y + (rock.target.y - rock.start.y) * t,
                              rock.start.z + (rock.target.z - rock.start.z) * t + 4 * math.sin(math.pi * t))
                guardian_art.draw_falling_rock(self.screen, self._screen_center(at, origin),
                                               self._screen_center(rock.target, origin), t, scale)
            if g.stage in guardian_rules.OPENINGS and g.impact < .6:
                where = mob.location
                if g.stage == "stuck" and g.marked:
                    middle = g.marked[len(g.marked) // 2]
                    where = world.surface_position(middle)
                guardian_art.draw_dust(self.screen, self._screen_center(where, origin), g.impact, scale, mob.id)

    def _draw_guardian_health(self, session) -> pygame.Rect | None:
        if session.wildlife.world is not session.world:
            return None
        for mob in session.wildlife.mobs.values():
            if mob.kind is MobKind.GUARDIAN and not mob.asleep:
                return guardian_art.draw_health(self.screen, self.pixel_font, mob.hp, guardian_rules.HEALTH,
                                                guardian_rules.wrath(mob), guardian_rules.NAME)
        return None

    def _shark_pose(self, session, mob):
        _, left, stride, stance = mob_pose(mob)
        sink = 0
        if session.drag_shark == mob.id and session.drag_time > 0:
            stance = "drag"
            sink = round((1 - session.drag_time / DRAG_SECONDS) * 10 * self.config.world_art_scale)
        if stance in ("idle", "rest", "drag", "strike"):
            stride = int(session.cycle_seconds * 3 + mob.id) % 2
        return stance, stride, left, sink

    def _shark_box(self, session, mob, x, y):
        stance, stride, left, sink = self._shark_pose(session, mob)
        image, (ax, ay) = placed_shark(stance, stride, left, self.config.world_art_scale)
        box = image.get_rect(topleft=(x - ax, y - self.config.water_lift - ay + sink))
        if mob.windup > 0:
            box.union_ip(pygame.Rect(x - 8, y - self.config.water_lift - ay - round(14 * self.config.world_art_scale), 16, ay))
        return box.inflate(4, 4)

    def _shark_layers(self, session, origin, visual_player):
        self._swimmer_cut = None
        if session.world is not session.wildlife.world:
            return []
        layers = []
        view = self.screen.get_rect()
        for mob in session.wildlife.mobs.values():
            if mob.kind is not MobKind.SHARK:
                continue
            x, y = self._screen_center(mob.location, origin)
            stance, stride, left, sink = self._shark_pose(session, mob)
            image, (ax, ay) = placed_shark(stance, stride, left, self.config.world_art_scale, "below")
            rect = image.get_rect(topleft=(x - ax, y - self.config.water_lift - ay + sink))
            if rect.colliderect(view):
                layers.append((image, rect))
        if layers and self._player_pose.motion is MotionKind.SWIM and session.drag_time <= 0:
            # A cabeça do nadador fica acima da água mesmo quando outra célula é desenhada por cima.
            feet = self._screen_center(visual_player, origin)
            size = self.config.world_sprite_padding
            silhouette = pygame.mask.from_surface(self._player_layer(session, origin, visual_player, feet))
            cut = silhouette.to_surface(setcolor=(0, 0, 0, 0), unsetcolor=(255, 255, 255, 255))
            self._swimmer_cut = (cut, (feet[0] - size, feet[1] - size),
                                 scene_depth_key(SceneItem("player", visual_player.grid, visual_player)))
        return layers

    def _paint_sharks_below(self, center, depth):
        mask = self._top_alpha()
        tile = mask.get_rect(center=(center[0], center[1] - self._water_lift()))
        scratch = self._shark_scratch
        swimmer = self._swimmer_cut if self._swimmer_cut and depth > self._swimmer_cut[2] else None
        for image, rect in self._sharks_below:
            if not rect.colliderect(tile):
                continue
            if scratch is None or scratch.get_size() != mask.get_size():
                scratch = self._shark_scratch = pygame.Surface(mask.get_size(), pygame.SRCALPHA)
            scratch.fill((0, 0, 0, 0))
            scratch.blit(image, (rect.x - tile.x, rect.y - tile.y))
            scratch.blit(mask, (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
            if swimmer is not None:
                cut, (cx, cy), _ = swimmer
                scratch.blit(cut, (cx - tile.x, cy - tile.y), special_flags=pygame.BLEND_RGBA_MULT)
            self.screen.blit(scratch, tile)

    def _draw_shark(self, session, mob, x, y, scale):
        y -= self.config.water_lift
        stance, stride, left, sink = self._shark_pose(session, mob)
        image, (ax, ay) = placed_shark(stance, stride, left, scale, "above")
        if sink:
            visible = max(0, ay - sink + round(2 * scale))
            self.screen.blit(image, (x - ax, y - ay + sink), (0, 0, image.get_width(), visible))
        else:
            self.screen.blit(image, (x - ax, y - ay))
        if mob.windup > 0:
            self._draw_mob_cue(mob, x, y, scale, session.cycle_seconds)

    def _draw_sinking_player(self, session, origin, visual_player):
        feet = self._screen_center(visual_player, origin)
        px = max(1, round(self.config.world_art_scale))
        sunk = 1 - session.drag_time / DRAG_SECONDS
        surface = feet[1] - self.config.water_lift + px
        layer = self._player_layer(session, origin, visual_player, feet)
        size = self.config.world_sprite_padding
        previous = self.screen.get_clip()
        self.screen.set_clip(pygame.Rect(0, 0, self.screen.get_width(), surface).clip(previous))
        self.screen.blit(layer, (feet[0] - size, feet[1] - size + round(sunk * 22 * px)))
        self.screen.set_clip(previous)
        for k in range(5):
            rise = (sunk * 3 + k * .37) % 1
            bx = feet[0] + round(math.sin(k * 2.3 + sunk * 9) * 6 * px)
            by = surface - round(rise * 14 * px)
            pygame.draw.circle(self.screen, (226, 246, 248), (bx, by), px + (k % 2) * px // 2 + 1, max(1, px // 2 + 1))

    BODY_SECONDS = .55

    def _impacts_now(self, session) -> dict:
        impacts = {}
        objects = session.world.objects
        for effect in session.afterimages:
            subject = effect.subject
            if (effect.impact and effect.elapsed < wear_art.SHAKE_SECONDS and isinstance(subject, WorldObject)
                    and objects.get(subject.position) is subject):
                impacts[subject.position] = effect
        return impacts

    @staticmethod
    def _effect_seed(effect) -> int:
        p = effect.location
        return (round(p.x * 8) * 92821 ^ round(p.y * 8) * 68917 ^ round(p.z) * 131) & 0xFFFFFF

    def _impact_point(self, kind, x, y, push, px):
        height = {ObjectKind.TREE: 9, ObjectKind.CACTUS: 14, ObjectKind.FALLEN_LOG: 7}.get(kind, 9)
        return x - push * 5 * px, y - height * px

    def _draw_impact(self, session, effect, x, y):
        px = max(1, round(self.config.world_art_scale))
        t = effect.elapsed
        obj = effect.subject
        seed = self._effect_seed(effect)
        if obj is None:
            point, ground = (x - effect.push * 6 * px, y + 10 * px), y + 22 * px
            wear_art.draw_spark(self.screen, t, point, px)
            wear_art.draw_chips(self.screen, wear_art.CAVE_STONE, t, point, ground, effect.push, px, seed)
            return
        if not isinstance(obj, WorldObject):
            return
        point = self._impact_point(obj.kind, x, y, effect.push, px)
        ground = y + 2 * px
        colors = wear_art.materials(obj.kind, obj.variant, session.world.space_kind is SpaceKind.CAVE)
        ore = obj.variant in wear_art.ORE_GLINTS
        if obj.kind is ObjectKind.ROCK:
            wear_art.draw_spark(self.screen, t, point, px)
        wear_art.draw_chips(self.screen, colors, t, point, ground, effect.push, px, seed, count=5 if ore else 6)
        if ore:
            wear_art.draw_chips(self.screen, wear_art.ORE_GLINTS[obj.variant], t, point, ground,
                                effect.push, px, seed ^ 0x0EE, count=3)
        if obj.kind is ObjectKind.TREE:
            leaves = wear_art.LEAVES.get(obj.variant, wear_art.LEAVES["broadleaf"])
            wear_art.draw_leaves(self.screen, leaves, t, (x, y - 46 * px), ground, px, seed)

    def _draw_afterimage(self, session, effect, origin, x, y):
        if effect.impact:
            self._draw_impact(session, effect, x, y)
            return
        scale = self.config.world_art_scale
        px = max(1, round(scale))
        t = effect.elapsed
        obj = effect.subject
        seed = self._effect_seed(effect)
        if isinstance(obj, WorldObject):
            body, foot = self._caster_image("object", obj)
            colors = wear_art.materials(obj.kind, obj.variant, session.world.space_kind is SpaceKind.CAVE)
            if obj.kind in (ObjectKind.TREE, ObjectKind.CACTUS):
                if t < wear_art.TOPPLE_SECONDS:
                    progress = t / wear_art.TOPPLE_SECONDS
                    angle = -effect.push * 88 * progress * progress
                    rect = body.get_bounding_rect()
                    offset = (pygame.Vector2(rect.center) - foot).rotate(-angle)
                    piece = pygame.transform.rotate(body.subsurface(rect), angle)
                    piece.set_alpha(255 if progress < .72 else round(255 * (1 - progress) / .28))
                    self.screen.blit(piece, piece.get_rect(center=(x + offset.x, y + offset.y)))
                if obj.kind is ObjectKind.TREE and t >= wear_art.TREE_LANDING_SECONDS:
                    landing = (x + effect.push * 34 * px, y - 6 * px)
                    leaves = wear_art.LEAVES.get(obj.variant, wear_art.LEAVES["broadleaf"])
                    since_landing = t - wear_art.TREE_LANDING_SECONDS
                    wear_art.draw_chips(self.screen, leaves + leaves[:1], since_landing, landing,
                                        y + 4 * px, -effect.push, px, seed, count=9, spread=1.3)
                wear_art.draw_chips(self.screen, colors, t, self._impact_point(obj.kind, x, y, effect.push, px),
                                    y + 2 * px, effect.push, px, seed ^ 0x77, count=5)
            elif t < self.BODY_SECONDS:
                for piece, (dx, dy) in wear_art.burst_pieces(body, foot, t, effect.push, px):
                    self.screen.blit(piece, (x + dx, y + dy))
                wear_art.draw_chips(self.screen, colors, t, (x, y - 8 * px), y + 3 * px, effect.push, px,
                                    seed, count=10, spread=1.4)
                if obj.variant in wear_art.ORE_GLINTS:
                    glints = wear_art.ORE_GLINTS[obj.variant]
                    wear_art.draw_chips(self.screen, glints, t, (x, y - 9 * px), y + 3 * px, -effect.push, px,
                                        seed ^ 0x0EE, count=5, spread=1.2)
                    wear_art.draw_twinkles(self.screen, glints, t, (x, y - 4 * px), px, seed)
        elif obj is not None and t < .36:
            progress = t / .36
            stance = "hurt" if t < .15 else "idle"
            frame = obj.worm_frame if obj.kind is MobKind.SANDWORM else 0
            body = mob_sprite(obj.kind, obj.left, frame, stance, scale)
            _, anchor = sprite_layout(obj.kind)
            foot = (round(anchor[0]*scale), round(anchor[1]*scale))
            rect = body.get_bounding_rect()
            angle = -65*progress*progress
            offset = (pygame.Vector2(rect.center)-foot).rotate(-angle)
            piece = pygame.transform.rotate(body.subsurface(rect), angle)
            piece.set_alpha(min(255, round(480*(1-progress))))
            self.screen.blit(piece, piece.get_rect(center=(x+offset.x, y+offset.y)))
        elif obj is None and effect.destroyed:
            wear_art.draw_chips(self.screen, wear_art.CAVE_STONE, t, (x, y + 10 * px), y + 22 * px,
                                effect.push, px, seed, count=10, spread=1.4)
        pixels = px
        if effect.destroyed and t < break_art.DURATION:
            phase = int(t / break_art.DURATION * break_art.FRAME_COUNT)
            dust = break_art.dust_frame(phase, isinstance(obj, WorldObject) and obj.kind is ObjectKind.TREE, pixels)
            self.screen.blit(dust, (x - 22*pixels, y - 28*pixels))
        launch = 0. if effect.destroyed else .18
        if effect.loot and t >= launch:
            fly = min(1., max(0., (t-.45)/.40))**2
            px, py = self._screen_center(session.player.position3d, origin)
            duration, height = (.42, 22) if effect.destroyed else (.36, 15)
            hop = math.sin(math.pi*min(1., (t-launch)/duration)) * height*scale
            center = (round(x+(px-x)*fly), round(y-6*scale+(py-y-9*scale)*fly-hop))
            if effect.destroyed:
                shadow = pygame.Rect(0, 0, (8 if hop < 10*scale else 5)*pixels, 2*pixels)
                shadow.center = (center[0], round(y+(py-y)*fly))
                pygame.draw.ellipse(self.screen, (86, 73, 66), shadow)
                image = break_art.outlined_drop(effect.loot, pixels)
            else:
                image = icon(effect.loot, pixels)
            self.screen.blit(image, image.get_rect(center=center))

    def _draw_player_with_occluders(self, session, origin, visual_player, background):
        # Redesenhar os corpos sobrepostos juntos preserva a ordem de oclusão.
        actors = self._actors(session, visual_player)
        visible = []
        for actor in actors:
            pos = actor.payload if actor.kind in ("player", "sails") else actor.payload.location
            x, y = self._screen_center(pos, origin)
            scale = self.config.world_art_scale
            bounds = pygame.Rect(x-round(20*scale), y-round(44*scale), round(40*scale), round(56*scale))
            if actor.kind == "sails":
                sprite, (fx, fy) = windmill_sails(sail_frame(session.production_seconds), scale)
                bounds = sprite.get_rect(topleft=(x - fx, y - fy))
            if actor.kind == "effect":
                effect = actor.payload
                if effect.elapsed < self.BODY_SECONDS and isinstance(effect.subject, WorldObject):
                    radius = self.config.world_sprite_padding
                    bounds = pygame.Rect(x-radius, y-radius, 2*radius, 2*radius)
                if effect.destroyed and effect.elapsed < break_art.DURATION:
                    pixels = max(1, round(scale))
                    bounds.union_ip(pygame.Rect(x-22*pixels, y-28*pixels, 44*pixels, 34*pixels))
                elif effect.elapsed >= self.BODY_SECONDS and not effect.loot:
                    continue
                if effect.loot and effect.elapsed >= .45:
                    px, py = self._screen_center(session.player.position3d, origin)
                    bounds.union_ip(pygame.Rect(px-round(10*scale), py-round(32*scale),
                                                round(20*scale), round(40*scale)))
            subject = actor.payload.subject if actor.kind == "effect" else actor.payload
            if getattr(subject, "kind", None) in (MobKind.SANDWORM, MobKind.GUARDIAN):
                bounds.union_ip(self._worm_box(x, y, scale, subject.kind))
            if actor.kind == "mob" and actor.payload.kind is MobKind.SHARK:
                bounds = self._shark_box(session, actor.payload, x, y)
            box = bounds.clip(self.screen.get_rect())
            if box:
                visible.append((actor, box))
        counts = dict(self.last_draw_counts)
        camera = (round(origin[0]), round(origin[1]))
        # A transição de luz combina imagens de duas posições do sol.
        previous = self._actor_boxes.get(self._phase, {})
        kept: dict[tuple, pygame.Surface] = {}
        try:
            boxes = [box for _, box in visible]
            if self._school:
                fish_box = self._school.rect.clip(self.screen.get_rect())
                if fish_box:
                    boxes.append(fish_box)
            for box in boxes:
                local = box.move(-camera[0], -camera[1])
                overlapping = [actor for actor, rect in visible if box.colliderect(rect)]
                states = tuple(self._actor_state(session, actor, origin, camera) for actor in overlapping)
                school = self._school if self._school and self._school.rect.colliderect(box) else None
                key = None if school or None in states else (self._static_generation, tuple(local), states)
                cached = previous.get(key) if key is not None else None
                if cached is not None:
                    self.screen.blit(cached, box)
                    kept[key] = cached
                    continue
                self.screen.set_clip(box)
                self.screen.fill(background, box)
                items = self._static_items_in(session, local)
                items.extend(overlapping)
                items.sort(key=scene_depth_key)
                self._draw_static_items(session, items, origin, school, sharks=bool(self._sharks_below))
                self.screen.set_clip(None)
                if key is not None:
                    snapshot = self.screen.subsurface(box).copy()
                    snapshot.set_alpha(None)
                    kept[key] = snapshot
        finally:
            self.screen.set_clip(None)
            self.last_draw_counts = counts
        self._actor_boxes[self._phase] = kept

    MOB_SHADOW = {MobKind.DEER: 17, MobKind.SNAKE: 11, MobKind.SPIDER: 18, MobKind.ARMADILLO: 13,
                  MobKind.MINE_MONSTER: 16, MobKind.GUARDIAN: 40}
    CUE_INK = (43, 32, 44)
    CUE_FILL = (255, 220, 78)
    WARNING = ("kkk", "kyk", "kyk", "kyk", "kkk", "kyk", "kkk")

    def _draw_mob_cue(self, mob, x, y, scale, clock):
        px = max(1, round(scale))
        hx, hy = head_top(mob)
        left, top = x + hx * px, y + hy * px
        if mob.windup > 0:
            bob = px if int(clock * 10) % 2 else 0
            for row, line in enumerate(self.WARNING):
                for column, cell in enumerate(line):
                    color = self.CUE_INK if cell == "k" else self.CUE_FILL
                    self.screen.fill(color, (left + (column - 1) * px, top + (row - 10) * px - bob, px, px))
            return
        for k in range(3):
            angle = clock * 7 + k * 2.09
            sx = left + round(math.cos(angle) * 5) * px
            sy = top - 3 * px + round(math.sin(angle) * 1.5) * px
            for dx, dy in ((0, 0), (1, 0), (-1, 0), (0, 1), (0, -1)):
                color = (255, 250, 214) if (dx, dy) == (0, 0) else self.CUE_FILL
                self.screen.fill(color, (sx + dx * px, sy + dy * px, px, px))

    def _actor_state(self, session: GameSession, actor: SceneItem, origin, camera) -> tuple | None:
        if actor.kind == "sails":
            x, y = self._screen_center(actor.payload, origin)
            return ("sails", sail_frame(session.production_seconds), x - camera[0], y - camera[1])
        if actor.kind == "fire":
            x, y = self._screen_center(actor.payload.location, origin)
            return ("fire", flame_frame(session.cycle_seconds, actor.payload.seed), x - camera[0], y - camera[1])
        if actor.kind == "crop":
            crop = actor.payload
            x, y = self._screen_center(crop.location, origin)
            return ("crop", crop.kind, crop.stage, wind_frame(session.cycle_seconds, crop.phase),
                    x - camera[0], y - camera[1])
        if actor.kind != "mob":
            return None
        mob = actor.payload
        if mob.kind is MobKind.SHARK:
            return None
        if mob.progress < 1 or (mob.kind is MobKind.SKELETON and session.daylight.phase is DayPhase.NIGHT
                                and session.daylight.blend > .05):
            return None
        if mob.windup > 0 or mob.dazed > 0:
            return None
        x, y = self._screen_center(mob.location, origin)
        return (mob.id, mob_pose(mob), x - camera[0], y - camera[1])

    def _static_items_in(self, session: GameSession, rect: pygame.Rect) -> list[SceneItem]:
        size = self.CHUNK
        left, top, right, bottom = rect.left, rect.top, rect.right, rect.bottom
        found: dict[tuple, SceneItem] = {}
        for i in range(left // size, (right - 1) // size + 1):
            for j in range(top // size, (bottom - 1) // size + 1):
                entries = self._chunk_items.get((i, j))
                if entries is None:
                    entries = self._chunk_items[(i, j)] = self._index_chunk_items(session, (i, j))
                for l, t, r, b, item in entries:
                    if l < right and r > left and t < bottom and b > top:
                        found[(item.kind, item.position)] = item
        return list(found.values())

    def _index_chunk_items(self, session: GameSession, key: tuple[int, int]) -> list[tuple]:
        size = self.CHUNK
        left, top = key[0] * size, key[1] * size
        right, bottom = left + size, top + size
        origin = (-left, -top)
        bounds = self._grid_bounds_for_rect(session, origin, pygame.Rect(0, 0, size, size))
        items = scene_items(session, origin, self.config, bounds=bounds)
        entries = []
        for item in items:
            l, t, r, b = self._item_bounds(session, item)
            if l < right and r > left and t < bottom and b > top:
                entries.append((l, t, r, b, item))
        return entries

    def _item_bounds(self, session: GameSession, item: SceneItem) -> tuple[int, int, int, int]:
        world = session.world
        w, h = self.config.tile_width, self.config.tile_height
        scale = max(1.0, self.config.world_art_scale)
        if item.kind == "tile":
            prepared = self._prepared_tiles.get(item.position)
            if prepared is None or prepared.tile is not item.payload:
                prepared = self._prepare_tile(session, item.position, item.payload)
                self._prepared_tiles[item.position] = prepared
            x, y = round(prepared.local_x), round(prepared.local_y)
            left, top = x - w // 2, y - h // 2
            width, height = prepared.surface.get_size()
            lift = self._water_lift() if item.payload.kind is TileKind.WATER else 0
            return (min(left, x - 8), top - lift,
                    max(left + width, left + w + 1, x + 4), max(top + height, top + h + 1, y + 25))
        if item.kind == "object":
            x, y = screen_center(item.payload.position3d, (0, 0), self.config)
            body = self._caster_bounds("object", item.payload)
            half_w, half_h = round(24 * scale) + 1, round(6 * scale) + 1
            return (x + min(body[0], -half_w), y + min(body[1], -half_h),
                    x + max(body[2], half_w), y + max(body[3], half_h))
        x, y = screen_center(world.surface_position(item.position), (0, 0), self.config)
        if item.kind == "portal":
            body = self._caster_bounds("portal", item.payload)
            return x + body[0], y + body[1], x + body[2], y + body[3]
        if item.kind == "torch":
            return x - 20 * scale, y - 18 * scale, x + 10 * scale, y + 16 * scale
        return x - 12 * scale, y - 32 * scale, x + 12 * scale, y + 9 * scale

    def _caster_bounds(self, kind: str, payload: object) -> tuple[int, int, int, int]:
        key = self._caster_key(kind, payload)
        bounds = self._caster_extents.get(key)
        if bounds is None:
            image, (foot_x, foot_y) = self._caster_image(kind, payload)
            rect = image.get_bounding_rect()
            bounds = (rect.left - foot_x - 1, rect.top - foot_y - 1, rect.right - foot_x + 1, rect.bottom - foot_y + 1)
            self._caster_extents[key] = bounds
        return bounds

    OUTLINE = (250, 250, 242, 235)

    def _draw_outline(self, kind: str, payload: object, foot: tuple[int, int]) -> None:
        key = self._caster_key(kind, payload)
        cached = self._outlines.get(key)
        if cached is None:
            image, (foot_x, foot_y) = self._caster_image(kind, payload)
            mask = pygame.mask.from_surface(image)
            ring = mask.convolve(pygame.mask.Mask((3, 3), fill=True))
            ring.erase(mask, (1, 1))
            cached = (ring.to_surface(setcolor=self.OUTLINE, unsetcolor=(0, 0, 0, 0)), (-foot_x - 1, -foot_y - 1))
            self._outlines[key] = cached
        surface, (dx, dy) = cached
        self.screen.blit(surface, (foot[0] + dx, foot[1] + dy))

    def _draw_destination_marker(self, center: tuple[int, int]) -> None:
        x, y = center
        hw, hh = self.config.tile_width // 2, self.config.tile_height // 2
        color = self.OUTLINE[:3]
        for (ax, ay), (bx, by) in (((x - hw, y), (x - hw // 2, y - hh // 2)), ((x - hw, y), (x - hw // 2, y + hh // 2)),
                                   ((x + hw, y), (x + hw // 2, y - hh // 2)), ((x + hw, y), (x + hw // 2, y + hh // 2))):
            pygame.draw.line(self.screen, color, (ax, ay), (bx, by))

    SCENE_SNAP = 4

    def _snapped_bounds(self, bounds: tuple[int, int, int, int]) -> tuple[int, int, int, int]:
        snap = self.SCENE_SNAP
        min_depth, max_depth, min_side, max_side = bounds
        return (min_depth // snap * snap, -(-max_depth // snap) * snap,
                min_side // snap * snap, -(-max_side // snap) * snap)

    def _draw_scene_tile(self, session: GameSession, index: int, item, origin: tuple[float, float]) -> tuple[int, int]:
        prepared = self._scene_prepared[index]
        tile = item.payload
        if prepared is None or prepared.tile is not tile:
            prepared = self._prepared_tiles.get(item.position)
            if prepared is None or prepared.tile is not tile:
                prepared = self._prepare_tile(session, item.position, tile)
                self._prepared_tiles[item.position] = prepared
            self._scene_prepared[index] = prepared
        return self._blit_prepared(session, item.position, tile, prepared, origin)

    def _draw_tile(self, session: GameSession, position: GridPos, tile: Tile,
                   origin: tuple[float, float]) -> tuple[int, int]:
        prepared = self._prepared_tiles.get(position)
        if prepared is None or prepared.tile is not tile:
            prepared = self._prepare_tile(session, position, tile)
            self._prepared_tiles[position] = prepared
        return self._blit_prepared(session, position, tile, prepared, origin)

    def _blit_prepared(self, session: GameSession, position: GridPos, tile: Tile,
                       prepared: PreparedTerrain, origin: tuple[float, float]) -> tuple[int, int]:
        x = round(origin[0] + prepared.local_x)
        y = round(origin[1] + prepared.local_y)
        self.last_draw_counts["faces"] += prepared.faces
        corner = (x - self.config.tile_width // 2, y - self.config.tile_height // 2)
        self.screen.blit(prepared.surface, corner)
        if prepared.detail is SHADOW_UNSET:
            prepared.detail = self._build_tile_detail(session, position, tile, prepared.tone)
        if prepared.detail is not None:
            self.screen.blit(prepared.detail, corner)
        stage = session.world.tilled_soil.get(position)
        if stage:
            self.screen.blit(soil_texture(stage, self.config.world_art_scale), corner)
        if self._phase is not DayPhase.NIGHT:
            if self._phase not in prepared.shadows:
                prepared.shadows[self._phase] = self._build_tile_shadow(session, position, tile)
            shadow = prepared.shadows[self._phase]
            if shadow is not None:
                self.screen.blit(shadow, corner, special_flags=pygame.BLEND_RGB_MULT)
        if prepared.water is not None:
            lift = self._water_lift()
            self.screen.blit(prepared.water, (corner[0], corner[1] - lift))
        return x, y

    WATER_BODY = (62, 138, 168, 158)
    WATER_DEPTHS = (WATER_BODY, (50, 121, 157, 170), (40, 104, 144, 184))
    WATER_FOAM = (214, 240, 236, 225)
    WATER_RIPPLE = (150, 210, 220, 170)
    WATER_SHEET = (48, 112, 140, 190)

    def _water_lift(self) -> int:
        return self.config.water_lift

    def _water_overlay(self, prepared: PreparedTerrain, bank: Sandbank | None = None, decoration=None,
                       depth: int = 1) -> pygame.Surface:
        w, h = self.config.tile_width, self.config.tile_height
        lift = self._water_lift()
        tiles = prepared.neighbor_tiles
        relations = tuple(0 if t is None else (prepared.tile.elevation > t.elevation) - (prepared.tile.elevation < t.elevation)
                          for t in tiles)
        open_front = tuple(t is None for t in tiles[:2])
        land = tuple(t is not None and t.kind is not TileKind.WATER for t in tiles)
        key = (w, h, lift, relations, open_front, land, prepared.tile.deep_water, bank, decoration, depth)
        overlay = self._water_overlays.get(key)
        if overlay is None:
            first, last = self._top_outline()
            half = w // 2
            overlay = pygame.Surface((w + 1, h + 1 + lift), pygame.SRCALPHA)
            for side, is_open in enumerate(open_front):
                if is_open:
                    columns = range(0, half + 1) if side == 0 else range(half, w + 1)
                    for x in columns:
                        pygame.draw.line(overlay, self.WATER_SHEET, (x, last[x]), (x, last[x] + lift))
            depths = self.WATER_DEPTHS
            body = (32, 78, 122, 220) if prepared.tile.deep_water else depths[min(depth, len(depths)) - 1]
            if bank:
                body = SAND[bank.level - 1]
            pygame.draw.polygon(overlay, body, [(half, 0), (w, h // 2), (half, h), (0, h // 2)])
            if bank:
                paint_sandbank(overlay, bank, first, last, w, h)
            if decoration:
                overlay.blit(aquatic_glyph(decoration, w, h), (0, 0))
            sides = ((last, range(0, half + 1)), (last, range(half, w + 1)),
                     (first, range(half, w + 1)), (first, range(0, half + 1)))
            for index, ((pixels, columns), is_land) in enumerate(zip(sides, land)):
                if is_land:
                    inward = 1 if index >= 2 else -1
                    for x in columns:
                        overlay.set_at((x, pixels[x]), self.WATER_FOAM)
                        if overlay.get_at((x, pixels[x] + inward)) == body:
                            overlay.set_at((x, pixels[x] + inward), self.WATER_RIPPLE)
            self._water_overlays[key] = overlay
        return overlay

    def _prepare_tile(self, session: GameSession, position: GridPos, tile: Tile) -> PreparedTerrain:
        world = session.world
        directions = (GridPos(0, 1), GridPos(1, 0), GridPos(0, -1), GridPos(-1, 0))
        neighbors = tuple(position + direction for direction in directions)
        neighbor_tiles = tuple(world.tile_map.tile_at(p) for p in neighbors)
        heights = tuple(neighbor.elevation if neighbor is not None else -1 for neighbor in neighbor_tiles)
        drops = tuple(max(0, tile.elevation - height) * self.config.height_unit_pixels for height in heights[:2])
        if tile.kind is TileKind.WOOD_FLOOR:
            scale = self.config.world_art_scale
            deck = house_art.plank_tile(position.x, position.y, scale, *(round(d/scale) for d in drops))
            x, y = project_grid_point(world.surface_position(position), self.config)
            return PreparedTerrain(tile, neighbors, neighbor_tiles, deck, x, y, sum(d > 0 for d in drops))
        relations = tuple((tile.elevation > height) - (tile.elevation < height) for height in heights)
        height_tone = min(tile.elevation, 6) * 4
        key = (tile.kind, tile.variant, tile.biome, height_tone, *drops, relations)
        surface = self._tile_surfaces.get(key)
        if surface is None:
            w, h = self.config.tile_width, self.config.tile_height
            surface = pygame.Surface((w + 1, h + max(drops) + 1), pygame.SRCALPHA)
            center = (w // 2, h // 2)
            if tile.kind is TileKind.GRASS:
                base = {Biome.FOREST: (76, 125, 83), Biome.MEADOW: (116, 154, 84),
                        Biome.DRY: (184, 161, 104)}[tile.biome]
                left, right = (124, 84, 53), (92, 62, 44)
            elif tile.kind is TileKind.BRIDGE:
                base, left, right = BRIDGE, BRIDGE_EDGE, (71, 47, 32)
            elif tile.kind is TileKind.CAVE_FLOOR:
                base, left, right = (163, 118, 101), (119, 80, 65), (91, 60, 50)
            elif tile.kind is TileKind.CAVE_WALL:
                base, left, right = (114, 105, 123), (90, 82, 98), (64, 59, 74)
            elif tile.kind is TileKind.WATER:
                base, left, right = (78, 112, 98), (58, 86, 78), (46, 70, 64)
            else:
                base, left, right = (160, 143, 113), (126, 107, 80), (99, 84, 64)
            color = base if tile.kind is TileKind.BRIDGE else tuple(min(255, c + height_tone) for c in base)
            texture = self._terrain_texture(tile, position)
            top_tone = color if texture is None else tuple(
                pygame.transform.average_color(texture, consider_alpha=True))[:3]
            self._tile_tones[key] = top_tone
            for side, (drop, face_color) in enumerate(zip(drops, (left, right))):
                if drop:
                    self._draw_cliff_face(surface, side, drop, tile, top_tone, face_color)
            top = [(w // 2, 0), (w, h // 2), (w // 2, h), (0, h // 2)]
            pygame.draw.polygon(surface, color, top)
            if texture is not None:
                surface.blit(texture, (0, 0))
            self._apply_grid_lines(surface)
            if tile.kind is TileKind.GRASS and texture is None:
                self._draw_grass_detail(center, tile.variant, surface, tile.biome)
            self._apply_edge_cues(surface, relations)
            self._tile_surfaces[key] = surface
        local_x = (position.x - position.y) * self.config.tile_width / 2
        local_y = (position.x + position.y) * self.config.tile_height / 2 - tile.elevation * self.config.height_unit_pixels
        prepared = PreparedTerrain(tile, neighbors, neighbor_tiles, surface, local_x, local_y,
                                   sum(drop > 0 for drop in drops), tone=self._tile_tones[key])
        if tile.kind is TileKind.WATER:
            bank = None if tile.deep_water else sandbank_at(world, position, neighbor_tiles, self._bed_levels)
            depth = 1 if bank or tile.deep_water else shore_depth(world, position, len(self.WATER_DEPTHS))
            prepared.water = self._water_overlay(prepared, bank, water_decoration(world, position, tile), depth)
        return prepared

    # Na máscara, d e l são tons do chão, f e y formam a flor e p e q sombreiam as pedras.
    DETAIL_GLYPHS = {
        "agave": ("...s...", "s..s..s", ".tstst.", ".sstss.", "..ttt.."),
        "dry_twigs": ("..l..", "l.d.l", ".ddd.", "..d.."),
        "tuft": ("l.l.l", "d.d.d", ".ddd.", "..d.."),
        "tuft_small": ("l.l", "d.d", ".d."),
        "flowers": (".f...", "fyf.f", ".f.fyf", ".d..f.", ".d..d."),
        "pebble": (".oo.", "oqpo", ".oo."),
    }
    DETAIL_MIX = {
        Biome.FOREST: ({"tuft": 5, "tuft_small": 3, "pebble": 1}, (0, 1, 1, 2)),
        Biome.MEADOW: ({"tuft": 4, "tuft_small": 3, "flowers": 2, "pebble": 1}, (0, 1, 1, 2)),
        Biome.DRY: ({"agave": 3, "dry_twigs": 2, "pebble": 2}, (0, 0, 1, 1)),
    }
    PETALS = ((241, 239, 224), (242, 209, 92), (233, 138, 160))

    def _detail_glyph(self, name: str, tone: tuple[int, int, int], petal: tuple[int, int, int]) -> pygame.Surface:
        key = (name, tone, petal)
        glyph = self._detail_glyphs.get(key)
        if glyph is None:
            colors = {
                "s": (139, 156, 107), "t": (85, 111, 83),
                "d": tuple(round(c * f) for c, f in zip(tone, (.70, .78, .70))),
                "l": tuple(min(255, round(c * 1.16)) for c in tone),
                "f": petal,
                "y": (242, 209, 92) if petal != (242, 209, 92) else (241, 239, 224),
                "o": (98, 102, 96),
                "p": (146, 150, 140),
                "q": (186, 188, 176),
            }
            rows = self.DETAIL_GLYPHS[name]
            glyph = pygame.Surface((max(map(len, rows)), len(rows)), pygame.SRCALPHA)
            for y, row in enumerate(rows):
                for x, key_char in enumerate(row):
                    if key_char != ".":
                        glyph.set_at((x, y), colors[key_char])
            self._detail_glyphs[key] = glyph
        return glyph

    def _build_tile_detail(self, session: GameSession, position: GridPos, tile: Tile,
                           tone: tuple[int, int, int]) -> pygame.Surface | None:
        density = self.config.ground_detail_density
        world = session.world
        if density <= 0 or world.space_kind is not SpaceKind.OUTDOOR:
            return None
        if tile.kind is not TileKind.GRASS or tile.biome not in self.DETAIL_MIX:
            return None
        if position in world.objects or position in world.portals:
            return None
        weights, counts = self.DETAIL_MIX[tile.biome]
        value = (world.seed * 1_103_515_245 + position.x * 73_856_093
                 + position.y * 19_349_663 + 0x5DEECE66D) & 0xFFFFFFFF
        rng = random.Random(value)
        count = round(rng.choice(counts) * density)
        if count <= 0:
            return None
        w, h = self.config.tile_width, self.config.tile_height
        surface = pygame.Surface((w + 1, h + 1), pygame.SRCALPHA)
        names = tuple(weights)
        for _ in range(count):
            name = rng.choices(names, weights=tuple(weights.values()))[0]
            glyph = self._detail_glyph(name, tone, rng.choice(self.PETALS))
            u, v = rng.uniform(.22, .78), rng.uniform(.22, .78)
            x = round((u - v) * w / 2 + w / 2)
            y = round((u + v) * h / 2)
            surface.blit(glyph, (x - glyph.get_width() // 2, y - glyph.get_height() + 1))
        surface.blit(self._top_alpha(), (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
        return surface

    def _apply_grid_lines(self, surface: pygame.Surface) -> None:
        strength = self.config.terrain_grid_strength
        if strength <= 0:
            return
        w, h = self.config.tile_width, self.config.tile_height
        key = (w, h, strength)
        overlay = self._grid_overlays.get(key)
        if overlay is None:
            first, _last = self._top_outline()
            overlay = pygame.Surface((w + 1, h + 1))
            overlay.fill((255, 255, 255))
            shade = (round(255 * (1 - strength)),) * 3
            for x, y in first.items():
                overlay.set_at((x, y), shade)
            self._grid_overlays[key] = overlay
        surface.blit(overlay, (0, 0), special_flags=pygame.BLEND_RGB_MULT)

    def _top_outline(self) -> tuple[dict[int, int], dict[int, int]]:
        w, h = self.config.tile_width, self.config.tile_height
        outline = self._top_outlines.get((w, h))
        if outline is None:
            fill = pygame.Surface((w + 1, h + 1), pygame.SRCALPHA)
            pygame.draw.polygon(fill, (255, 255, 255), [(w // 2, 0), (w, h // 2), (w // 2, h), (0, h // 2)])
            mask = pygame.mask.from_surface(fill)
            first: dict[int, int] = {}
            last: dict[int, int] = {}
            for x in range(w + 1):
                ys = [y for y in range(h + 1) if mask.get_at((x, y))]
                if ys:
                    first[x], last[x] = ys[0], ys[-1]
            outline = (first, last)
            self._top_outlines[(w, h)] = outline
        return outline

    # O padrão ocupa meio ladrilho para casar nas emendas do paredão.
    LIP_TEETH = (0, 1, 0, 2, 1, 0, 0, 1, 2, 0, 1, 0, 0, 2, 1, 0)

    def _draw_cliff_face(self, surface: pygame.Surface, side: int, drop: int, tile: Tile,
                         top_tone: tuple[int, int, int], face_color: tuple[int, int, int]) -> None:
        w, h = self.config.tile_width, self.config.tile_height
        half = w // 2
        unit = max(1, h // 16)
        lip_color, light, mid, dark = self._cliff_palette(tile, top_tone, side, face_color)

        def band(start: int, end: int) -> list[tuple[int, int]]:
            if side == 0:
                return [(0, h // 2 + start), (half, h + start), (half, h + end), (0, h // 2 + end)]
            return [(half, h + start), (w, h // 2 + start), (w, h // 2 + end), (half, h + end)]

        foot = min(drop, 2 * unit)
        light_end = min(drop - foot, 3 * unit + round(self.config.height_unit_pixels * .35))
        pygame.draw.polygon(surface, dark, band(0, drop))
        pygame.draw.polygon(surface, mid, band(0, drop - foot))
        pygame.draw.polygon(surface, light, band(0, light_end))
        if lip_color is None:
            return
        lip = min(3 * unit, drop - foot)
        pygame.draw.polygon(surface, lip_color, band(0, lip))
        offset = 0 if side == 0 else 5
        for pair in range(half // 2):
            extra = self.LIP_TEETH[(pair + offset) % len(self.LIP_TEETH)] * unit
            if not extra:
                continue
            x = 2 * pair + (0 if side == 0 else half)
            edge_y = h // 2 + x // 2 if side == 0 else h - (x - half) // 2
            height = min(extra + 1, drop - foot - lip + 1)
            pygame.draw.rect(surface, lip_color, (x, edge_y + lip - 1, 2, height))

    @staticmethod
    def _cliff_palette(tile: Tile, top_tone: tuple[int, int, int], side: int,
                       face_color: tuple[int, int, int]):
        if tile.kind is TileKind.GRASS:
            light = (((204, 126, 70), (168, 100, 56)) if tile.biome is Biome.DRY
                     else ((170, 100, 58), (134, 76, 46)))[side]
        elif tile.kind is TileKind.CAVE_FLOOR:
            light = ((132, 92, 76), (102, 70, 58))[side]
        else:
            light = face_color
        mid = tuple(round(c * .88) for c in light)
        dark = tuple(round(c * .70) for c in light)
        if tile.kind not in (TileKind.GRASS, TileKind.CAVE_FLOOR):
            return None, light, mid, dark
        if tile.kind is TileKind.CAVE_FLOOR:
            factors = (.80, .78, .78)
        elif tile.biome is Biome.DRY:
            factors = (.86, .80, .70)
        else:
            factors = (.58, .70, .66)
        shade = 1 if side == 0 else .88
        lip = tuple(max(0, min(255, round(c * f * shade))) for c, f in zip(top_tone, factors))
        return lip, light, mid, dark

    def _apply_edge_cues(self, surface: pygame.Surface, relations: tuple[int, ...]) -> None:
        if not any(relations):
            return
        w, h = self.config.tile_width, self.config.tile_height
        key = (w, h, relations)
        overlays = self._edge_cue_overlays.get(key)
        if overlays is None:
            first, last = self._top_outline()
            half = w // 2
            darken = pygame.Surface((w + 1, h + 1))
            darken.fill((255, 255, 255))
            lighten = pygame.Surface((w + 1, h + 1))
            lighten.fill((0, 0, 0))
            top = [(half, 0), (w, h // 2), (half, h), (0, h // 2)]
            edges = ((top[3], top[2]), (top[2], top[1]), (top[1], top[0]), (top[0], top[3]))
            sides = ((last, range(0, half + 1)), (last, range(half, w + 1)),
                     (first, range(half, w + 1)), (first, range(0, half + 1)))
            center = (half, h // 2)
            for (a, b), relation in zip(edges, relations):
                if relation < 0:
                    inner_a = tuple(round(v + (c - v) * .14) for v, c in zip(a, center))
                    inner_b = tuple(round(v + (c - v) * .14) for v, c in zip(b, center))
                    pygame.draw.polygon(darken, (206, 206, 206), (a, b, inner_b, inner_a))
            for index, ((pixels, columns), relation) in enumerate(zip(sides, relations)):
                if relation <= 0:
                    continue
                for x in columns:
                    if x not in pixels:
                        continue
                    if index < 2:
                        lighten.set_at((x, pixels[x]), (30, 30, 30))
                    else:
                        darken.set_at((x, pixels[x]), (172, 172, 172))
            overlays = (darken, lighten)
            self._edge_cue_overlays[key] = overlays
        darken, lighten = overlays
        surface.blit(darken, (0, 0), special_flags=pygame.BLEND_RGB_MULT)
        surface.blit(lighten, (0, 0), special_flags=pygame.BLEND_RGB_ADD)

    SHADOW_RUN = 0.9
    AFTERNOON_SHADOW_RUN = 1.45
    SHADOW_FALL = 0.3

    def _caster_at(self, world, position: GridPos) -> tuple[str, object] | None:
        world_object = world.objects.get(position)
        if world_object is not None:
            return "object", world_object
        portal = world.portals.get(position)
        if portal is not None:
            return "portal", portal
        return None

    def _caster_key(self, kind: str, payload: object) -> tuple:
        if kind == "object":
            if payload.kind is ObjectKind.ROCK:
                return ("object", payload.kind, payload.variant, rock_shape(payload.position))
            if payload.kind is ObjectKind.MUSHROOM:
                return ("object", payload.kind, mushroom_look(payload.variant, payload.position))
            return ("object", payload.kind, payload.variant, payload.available)
        return ("portal", payload.target_kind)

    def _caster_image(self, kind: str, payload: object) -> tuple[pygame.Surface, tuple[int, int]]:
        size = self.config.world_sprite_padding
        surface = pygame.Surface((2 * size, size + size // 2), pygame.SRCALPHA)
        foot = (size, size)
        previous, self.screen = self.screen, surface
        try:
            if kind == "object":
                self._draw_object_body(payload, *foot)
            else:
                self._draw_portal_body(payload, *foot)
        finally:
            self.screen = previous
        return surface, foot

    def _cast_shadow(self, kind: str, payload: object) -> tuple[pygame.Surface, tuple[int, int]] | None:
        run = self.AFTERNOON_SHADOW_RUN if self._phase is DayPhase.AFTERNOON else self.SHADOW_RUN
        key = (self._caster_key(kind, payload), run)
        if key in self._cast_shadows:
            return self._cast_shadows[key]
        image, (foot_x, foot_y) = self._caster_image(kind, payload)
        mask = pygame.mask.from_surface(image)
        rects = mask.get_bounding_rects()
        if not rects:
            self._cast_shadows[key] = None
            return None
        box = rects[0].unionall(rects[1:])
        hug = self.SHADOW_GROUND_HUG
        strokes = []
        for x in range(box.left, box.right):
            column = [y for y in range(box.top, box.bottom) if mask.get_at((x, y))]
            if not column:
                continue
            ground = column[-1] if foot_y - column[-1] <= hug else foot_y
            stroke = []
            for y in column:
                if stroke and y != previous + 1:
                    strokes.append(stroke)
                    stroke = []
                height = max(0, ground - y)
                stroke.append((x - foot_x + height * run, ground - foot_y + height * self.SHADOW_FALL))
                previous = y
            strokes.append(stroke)
        points = [point for stroke in strokes for point in stroke]
        left = math.floor(min(px for px, _py in points))
        top = math.floor(min(py for _px, py in points))
        right = math.ceil(max(px for px, _py in points)) + 2
        bottom = math.ceil(max(py for _px, py in points)) + 2
        shadow = pygame.Surface((right - left, bottom - top), pygame.SRCALPHA)
        black = (0, 0, 0, 255)
        for stroke in strokes:
            pixels = [(round(px - left), round(py - top)) for px, py in stroke]
            shadow.set_at(pixels[0], black)
            for a, b in zip(pixels, pixels[1:]):
                pygame.draw.line(shadow, black, a, b)
        width, height = shadow.get_size()
        for _ in range(3):
            filled = pygame.mask.from_surface(shadow)
            changed = False
            for y in range(height):
                for x in range(width):
                    if filled.get_at((x, y)):
                        continue
                    if ((0 < x < width - 1 and filled.get_at((x - 1, y)) and filled.get_at((x + 1, y)))
                            or (0 < y < height - 1 and filled.get_at((x, y - 1)) and filled.get_at((x, y + 1)))):
                        shadow.set_at((x, y), black)
                        changed = True
            if not changed:
                break
        result = (shadow, (left, top))
        self._cast_shadows[key] = result
        return result

    SHADOW_GROUND_HUG = 12

    def _shadow_window(self) -> tuple[GridPos, ...]:
        w, h = self.config.tile_width, self.config.tile_height
        height = self.config.world_sprite_padding
        key = (w, h, height, self.AFTERNOON_SHADOW_RUN, self.SHADOW_FALL)
        window = self._shadow_windows.get(key)
        if window is None:
            below = height // 10
            left = -height // 2 - below * self.AFTERNOON_SHADOW_RUN
            right = height // 2 + height * self.AFTERNOON_SHADOW_RUN
            top = -below * self.SHADOW_FALL - 1
            bottom = height * self.SHADOW_FALL + 1
            hw, hh = w / 2, h / 2
            screen_x = range(math.ceil((left - hw) / hw), math.floor((right + hw) / hw) + 1)
            screen_y = range(math.ceil((top - hh) / hh), math.floor((bottom + hh) / hh) + 1)
            window = tuple(GridPos((a + b) // 2, (b - a) // 2)
                           for a in screen_x for b in screen_y if (a + b) % 2 == 0)
            self._shadow_windows[key] = window
        return window

    def _prewarm_cast_shadows(self, world) -> None:
        steps = self._prewarm_steps(world)
        if self._defer_prewarm:
            self._prewarm_job = steps
            return
        for _ in steps:
            pass

    def _prewarm_steps(self, world):
        if self.config.cast_shadow_strength <= 0 or world.space_kind is not SpaceKind.OUTDOOR:
            return
        casters = [("object", o) for o in world.objects.values()]
        casters += [("portal", p) for p in world.portals.values()]
        for phase in (DayPhase.DAY, DayPhase.AFTERNOON):
            run = self.AFTERNOON_SHADOW_RUN if phase is DayPhase.AFTERNOON else self.SHADOW_RUN
            seen = set()
            for kind, payload in casters:
                key = self._caster_key(kind, payload)
                if key in seen:
                    continue
                seen.add(key)
                if (key, run) in self._cast_shadows:
                    continue
                current, self._phase = self._phase, phase
                try:
                    self._cast_shadow(kind, payload)
                finally:
                    self._phase = current
                yield

    def _shadow_receivers(self, world) -> dict[tuple[int, int], list[GridPos]]:
        window = self._shadow_window()
        cached = self._receivers.get(id(world))
        if cached is not None and cached[0] is world and cached[1] is window:
            return cached[2]
        index: dict[tuple[int, int], list[GridPos]] = {}
        offsets = [(d.x, d.y) for d in window]
        casters = [*world.objects, *world.portals]
        for caster in casters:
            cx, cy = caster.x, caster.y
            for dx, dy in offsets:
                index.setdefault((cx + dx, cy + dy), []).append(caster)
        self._receivers[id(world)] = (world, window, index)
        return index

    def _add_shadow_caster(self, world, position: GridPos) -> None:
        cached = self._receivers.get(id(world))
        if cached is None or cached[0] is not world:
            return
        for delta in cached[1]:
            casters = cached[2].setdefault((position.x + delta.x, position.y + delta.y), [])
            if position not in casters:
                casters.append(position)

    def _top_alpha(self) -> pygame.Surface:
        w, h = self.config.tile_width, self.config.tile_height
        surface = self._top_alphas.get((w, h))
        if surface is None:
            surface = pygame.Surface((w + 1, h + 1), pygame.SRCALPHA)
            surface.fill((255, 255, 255, 0))
            pygame.draw.polygon(surface, (255, 255, 255, 255), [(w // 2, 0), (w, h // 2), (w // 2, h), (0, h // 2)])
            self._top_alphas[(w, h)] = surface
        return surface

    def _build_tile_shadow(self, session: GameSession, position: GridPos, tile: Tile) -> pygame.Surface | None:
        strength = self.config.cast_shadow_strength
        if strength <= 0:
            return None
        world = session.world
        w, h = self.config.tile_width, self.config.tile_height
        union = None
        for caster_position in self._shadow_receivers(world).get((position.x, position.y), ()):
            caster = self._caster_at(world, caster_position)
            if caster is None or world.elevation_at(caster_position) != tile.elevation:
                continue
            shadow = self._cast_shadow(*caster)
            if shadow is None:
                continue
            delta = position - caster_position
            image, (left, top) = shadow
            foot_x = (delta.y - delta.x) * (w // 2) + w // 2
            foot_y = -(delta.x + delta.y) * (h // 2) + h // 2
            if union is None:
                union = pygame.Surface((w + 1, h + 1), pygame.SRCALPHA)
            union.blit(image, (foot_x + left, foot_y + top))
        if union is None:
            return None
        union.blit(self._top_alpha(), (0, 0), special_flags=pygame.BLEND_RGBA_MULT)
        mask = pygame.mask.from_surface(union)
        if not mask.count():
            return None
        shade = (round(255 * (1 - strength)), round(255 * (1 - strength)), round(255 * (1 - strength * .7)), 255)
        decal = pygame.Surface((w + 1, h + 1))
        decal.blit(mask.to_surface(setcolor=shade, unsetcolor=(255, 255, 255, 255)), (0, 0))
        return decal

    def _sync_shadow_casters(self, world) -> None:
        if self._shadow_signature and self._shadow_signature[0] == id(world):
            for p in world.chipped[self._seen_chips:]:
                self._invalidate_chunks_around(world, p, chip=True)
        self._seen_chips = len(world.chipped)
        signature = (id(world), len(world.objects), len(world.tile_map.changes), sum(o.available for o in world.objects.values()))
        if signature == self._shadow_signature:
            return
        if self._shadow_signature is None or self._shadow_signature[0] != id(world):
            self._prewarm_cast_shadows(world)
        snapshot = {p: self._caster_key("object", o) for p, o in world.objects.items()}
        if self._shadow_signature is not None and self._shadow_signature[0] == id(world):
            changed = {p for p in snapshot.keys() | self._shadow_snapshot.keys()
                       if snapshot.get(p) != self._shadow_snapshot.get(p)}
            for p in changed:
                own = self._prepared_tiles.get(p)
                if own is not None:
                    own.detail = SHADOW_UNSET
                if p in world.objects:
                    self._add_shadow_caster(world, p)
                self._invalidate_chunks_around(world, p)
                for delta in self._shadow_window():
                    prepared = self._prepared_tiles.get(p + delta)
                    if prepared is not None:
                        prepared.shadows.clear()
        self._shadow_signature = signature
        self._shadow_snapshot = snapshot

    def _terrain_texture(self, tile: Tile, position: GridPos) -> pygame.Surface | None:
        return None

    def _portal_sprite(self, portal: Portal, feet: tuple[int, int]) -> bool:
        return False

    def _draw_portal_body(self, portal: Portal, x: int, y: int) -> None:
        draw = WorldPrimitives((x, y), self.config.world_art_scale)
        if portal.target_kind is SpaceKind.INTERIOR:
            scale = self.config.world_art_scale
            sprite = cottage_art.cottage()
            if scale != 1:
                sprite = pygame.transform.scale_by(sprite, scale)
            px, py = cottage_art.PIVOT
            self.screen.blit(sprite, (x-round(px*scale), y-round(py*scale)))
            return
        draw.rect(self.screen, (62, 50, 43), (x - 16, y - 31, 32, 35))
        draw.rect(self.screen, (14, 17, 23), (x - 11, y - 25, 22, 29))
        draw.line(self.screen, (172, 120, 69), (x - 15, y - 28), (x + 15, y - 28), 5)
        for step in range(3):
            draw.line(self.screen, (142, 132, 114), (x - 9 + step * 2, y - step * 4),
                      (x + 9, y - step * 4), 2)
        if portal.target_kind is SpaceKind.OUTDOOR:
            draw.lines(self.screen, ACCENT, False, [(x - 5, y - 13), (x, y - 20), (x + 5, y - 13)], 2)

    def _draw_portal(self, session: GameSession, portal: Portal, origin: tuple[float, float]) -> None:
        self._draw_portal_static(session, portal, origin)
        self._draw_portal_label(session, portal, origin)

    def _draw_portal_static(self, session: GameSession, portal: Portal, origin: tuple[float, float]) -> None:
        if session.world.space_kind is SpaceKind.INTERIOR:
            return
        x, y = self._ground_center(session, portal.position, origin)
        if not self._portal_sprite(portal, (x, y)):
            self._draw_portal_body(portal, x, y)

    def _draw_portal_label(self, session: GameSession, portal: Portal, origin: tuple[float, float]) -> None:
        x, y = self._ground_center(session, portal.position, origin)
        player = session.player.position
        ready = (portal.position == player or exit_from(session.world, player, session.player.facing) is portal
                 or (portal.position == player + session.player.facing
                     and session.world.can_reach(player, portal.position, self.config.max_step_height)))
        near = max(abs(portal.position.x - player.x), abs(portal.position.y - player.y)) <= self.PORTAL_LABEL_RANGE
        if session.world.space_kind is SpaceKind.INTERIOR and not ready:
            return
        if not (ready or near):
            return
        text = ("[E] " if ready else "") + portal.label
        label = self.pixel_font.render(text, ACCENT if ready else TEXT, shadow=TEXT_SHADOW)
        label_y = y - round((78 if portal.target_kind is SpaceKind.INTERIOR else 47) * self.config.world_art_scale)
        if session.world.space_kind is SpaceKind.INTERIOR:
            label_y = y + round(20 * self.config.world_art_scale)
        self.screen.blit(label, (x - label.get_width() // 2, label_y))

    PORTAL_LABEL_RANGE = 3
    RUIN_NAMES = {ObjectKind.DOCK: "Cais em ruínas", ObjectKind.WINDMILL: "Moinho em ruínas"}
    RUIN_LABEL_HEIGHT = {ObjectKind.DOCK: 34, ObjectKind.WINDMILL: 92}

    def _draw_repair_labels(self, session: GameSession, origin: tuple[float, float]) -> None:
        player = session.player.position
        reach = self.PORTAL_LABEL_RANGE
        for dx in range(-reach, reach + 1):
            for dy in range(-reach, reach + 1):
                cell = player + GridPos(dx, dy)
                if session.repair_needs(cell) is None:
                    continue
                obj = session.world.objects[cell]
                ready = (cell == player + session.player.facing
                         and session.world.can_reach(player, cell, self.config.max_step_height))
                text = "[E] Consertar" if ready else self.RUIN_NAMES[obj.kind]
                label = self.pixel_font.render(text, ACCENT if ready else TEXT, shadow=TEXT_SHADOW)
                x, y = self._screen_center(obj.position3d, origin)
                top = y - round(self.RUIN_LABEL_HEIGHT[obj.kind] * self.config.world_art_scale)
                self.screen.blit(label, (x - label.get_width() // 2, top))

    def _draw_marker(self, session: GameSession, position: GridPos, kind: str,
                     origin: tuple[float, float]) -> None:
        x, y = self._ground_center(session, position, origin)
        draw = WorldPrimitives((x, y), self.config.world_art_scale)
        if kind == "torch":
            torchlight.draw_guide(self.screen, (x, y), self.config.world_art_scale,
                                  session.world.guides.toward_exit[position])
        elif kind == "goal":
            draw.circle(self.screen, ACCENT, (x, y - 20), 8, 2)
            draw.line(self.screen, ACCENT, (x, y - 12), (x, y + 5), 2)

    def _draw_grass_detail(
        self,
        center: tuple[int, int],
        variant: GrassVariant,
        target: pygame.Surface,
        biome: Biome,
    ) -> None:
        x, y = center
        draw = WorldPrimitives((x, y), self.config.world_art_scale)
        if variant is GrassVariant.TALL_GRASS:
            color = (125, 110, 67) if biome is Biome.DRY else (43, 96, 55)
            draw.line(target, color, (x - 8, y + 4), (x - 11, y - 4), 2)
            draw.line(target, color, (x - 6, y + 4), (x - 4, y - 6), 2)
            draw.line(target, color, (x + 7, y + 2), (x + 10, y - 5), 2)
        elif variant is GrassVariant.PEBBLES:
            draw.circle(target, (112, 124, 111), (x - 9, y + 1), 2)
            draw.circle(target, (91, 105, 94), (x + 4, y - 4), 2)
            draw.circle(target, (132, 137, 124), (x + 11, y + 3), 1)

    def _draw_chunk_boundary(self, session: GameSession, origin: tuple[float, float]) -> None:
        size = session.world.chunk_preview_size
        if size is None:
            return

        half_width = self.config.tile_width // 2
        half_height = self.config.tile_height // 2
        top = self._screen_center(GridPos(0, 0), origin)
        right = self._screen_center(GridPos(size - 1, 0), origin)
        bottom = self._screen_center(GridPos(size - 1, size - 1), origin)
        left = self._screen_center(GridPos(0, size - 1), origin)
        outline = [
            (top[0], top[1] - half_height),
            (right[0] + half_width, right[1]),
            (bottom[0], bottom[1] + half_height),
            (left[0] - half_width, left[1]),
        ]
        boundary_color = (73, 188, 224)
        pygame.draw.lines(self.screen, boundary_color, True, outline, 3)

        corners = (
            (GridPos(0, 0), "0,0"),
            (GridPos(size - 1, 0), f"{size - 1},0"),
            (GridPos(size - 1, size - 1), f"{size - 1},{size - 1}"),
            (GridPos(0, size - 1), f"0,{size - 1}"),
        )
        for position, label in corners:
            center = self._screen_center(position, origin)
            if not self._is_visible(center):
                continue
            pygame.draw.circle(self.screen, boundary_color, center, 5)
            self._draw_label(label, (center[0] + 7, center[1] - 9), boundary_color, self.font_small)

    def _draw_station_outputs(self, session, origin):
        for obj, box in station_outputs(session, origin, self.config):
            rect = pygame.Rect(box)
            pygame.draw.rect(self.screen, "#362c30", rect, border_radius=4)
            pygame.draw.rect(self.screen, "#beaa8b", rect, 1, border_radius=4)
            x, y = rect.midbottom
            pygame.draw.polygon(self.screen, "#beaa8b", ((x-3, y-1), (x+3, y-1), (x, y+2)))
            step = round(16 * self.config.world_art_scale)
            first = rect.left + rect.height // 2
            for i, (item, _) in enumerate(obj.production.outputs):
                sprite = icon(item, self.config.pixel_scale)
                show(self.screen, sprite, center=(first + i * step, rect.centery))

    def _draw_rest_hint(self, session, origin):
        bed = session.bed_beside()
        cell = bed or session.campfire_beside()
        if cell is None:
            return
        x, y = self._screen_center(session.world.surface_position(cell), origin)
        s = max(1, round(self.config.world_art_scale))
        box = pygame.Rect(0, 0, 11 * s, 11 * s)
        waiting = bed is None and any(obj.position == cell for obj, _ in station_outputs(session, origin, self.config))
        box.midbottom = (x, y - (28 if bed else 50 if waiting else 40) * s)
        show(self.screen, self._rest_bubble(s), topleft=(box.x - s, box.y - s))

    def _rest_bubble(self, s: int) -> pygame.Surface:
        bubbles = self.__dict__.setdefault("_rest_bubbles", {})
        if s not in bubbles:
            light, dark = (232, 226, 214), (44, 40, 46)
            bubble = pygame.Surface((13 * s, 16 * s + 1), pygame.SRCALPHA)
            box = pygame.Rect(s, s, 11 * s, 11 * s)
            pygame.draw.rect(bubble, light, box.inflate(2 * s, 2 * s), border_radius=3 * s)
            pygame.draw.rect(bubble, dark, box, border_radius=2 * s)
            pygame.draw.polygon(bubble, light, ((box.centerx - 3 * s, box.bottom + s),
                                                (box.centerx + 3 * s, box.bottom + s),
                                                (box.centerx, box.bottom + 4 * s)))
            label = self.pixel_font.render("R", light, s)
            bubble.blit(label, label.get_rect(center=box.center))
            bubbles[s] = bubble
        return bubbles[s]

    def _draw_placement(self, session, origin, target, item, valid, variant="default"):
        feet = self._ground_center(session, target, origin)
        key = item, valid, self.config.world_art_scale, variant
        if key not in self._placement_sprites:
            body, pivot = self._caster_image("object", WorldObject.create(target, ObjectKind(item), variant=variant))
            area = body.get_bounding_rect()
            sprite = body.subsurface(area)
            ghost = pygame.Surface((area.w+2, area.h+2), pygame.SRCALPHA)
            outline = pygame.mask.from_surface(sprite).to_surface(
                setcolor="#fff4cf" if valid else "#ef655d", unsetcolor=(0, 0, 0, 0))
            for dx, dy in ((1, 0), (1, 2), (0, 1), (2, 1)):
                ghost.blit(outline, (dx, dy))
            ghost.blit(sprite, (1, 1))
            ghost.set_alpha(207)
            self._placement_sprites[key] = ghost, (area.x-pivot[0]-1, area.y-pivot[1]-1)
        ghost, (dx, dy) = self._placement_sprites[key]
        self.screen.blit(ghost, (feet[0]+dx, feet[1]+dy))

    def _draw_bridge_preview(self, session: GameSession, origin: tuple[float, float]) -> None:
        if session.world.bridge.built:
            return
        for position in session.world.bridge.cells:
            points = self._diamond(self._screen_center(position, origin))
            pygame.draw.polygon(self.screen, (155, 127, 65), points, 2)

    def _draw_contact_shadow(
        self, center: tuple[int, int], width: int, scale: float | None = None, alpha: int = 95,
    ) -> None:
        x, y = center
        scale = self.config.world_art_scale if scale is None else scale
        width = round(width * scale)
        height = round(12 * scale)
        key = (width, height, alpha)
        shadow = self._shadow_surfaces.get(key)
        if shadow is None:
            shadow = pygame.Surface((width, height), pygame.SRCALPHA)
            pygame.draw.ellipse(shadow, (8, 12, 10, alpha), shadow.get_rect())
            self._shadow_surfaces[key] = shadow
        self.screen.blit(shadow, (x - width // 2, y - height // 2))

    def _draw_world_object(
        self,
        world_object: WorldObject,
        origin: tuple[float, float],
    ) -> None:
        x, y = self._screen_center(world_object.position3d, origin)
        if not self._is_visible((x, y)):
            return
        width = self.CONTACT_SHADOW_WIDTHS[world_object.kind]
        if self._live_impacts and world_object.position in self._live_impacts:
            self._draw_struck_object(world_object, x, y, self._live_impacts[world_object.position], width)
            return
        self._draw_contact_shadow((x, y), width, alpha=self._object_contact_alpha)
        self._draw_object_body(world_object, x, y)
        self._draw_ore_marks(world_object, x, y)

    def _draw_struck_object(self, world_object: WorldObject, x: int, y: int, effect, shadow_width: int) -> None:
        body, foot = self._caster_image("object", world_object)
        body = body.copy()
        previous, self.screen = self.screen, body
        try:
            self._draw_ore_marks(world_object, *foot)
        finally:
            self.screen = previous
        px = max(1, round(self.config.world_art_scale))
        image = wear_art.struck(body, foot, world_object.kind, effect.elapsed, effect.push, px)
        self._draw_contact_shadow((x, y), shadow_width, alpha=self._object_contact_alpha)
        self.screen.blit(image, (x - foot[0], y - foot[1]))

    def _wear_image(self, world_object: WorldObject, stage: int) -> tuple[pygame.Surface, tuple[int, int]]:
        p = world_object.position
        salt = (p.x * 92821 ^ p.y * 68917) & 0xF
        key = (self._caster_key("object", world_object), stage, salt)
        cached = self._wear_images.get(key)
        if cached is None:
            body, foot = self._caster_image("object", world_object)
            px = max(1, round(self.config.world_art_scale))
            cached = (wear_art.wear_overlay(body, foot, world_object.kind, stage, salt, px), foot)
            self._wear_images[key] = cached
        return cached

    def _draw_wall_wear(self, center: tuple[int, int], damage: int) -> None:
        total = OBJECT_SPECS[ObjectKind.ROCK].durability
        stage = max(1, min(4, math.ceil(4 * damage / total)))
        wear_art.wall_cracks(self.screen, center, stage, max(1, round(self.config.world_art_scale)))

    def _draw_voyage_veil(self, progress: float) -> None:
        alpha = round(255 * min(1., progress / VEIL_OPAQUE))
        if alpha <= 0:
            return
        veil = pygame.Surface(self.screen.get_size())
        veil.fill(VEIL)
        veil.set_alpha(alpha)
        self.screen.blit(veil, (0, 0))

    def _draw_voyage_caption(self, voyage) -> pygame.Rect:
        cx, cy = self.config.virtual_width // 2, self.config.virtual_height // 2
        label = self.pixel_font.render(f"Navegando para a {voyage.island.name}", (244, 238, 226), 2,
                                       shadow=(12, 8, 8))
        place = label.get_rect(center=(cx, cy - 22))
        self.screen.blit(label, place)
        left, right = cx - 90, cx + 90
        shift = round(voyage.elapsed * 17) % 12
        for x in range(left, right - 6, 12):
            pygame.draw.lines(self.screen, (70, 120, 150), False,
                              ((x + shift, cy + 14), (x + shift + 3, cy + 12), (x + shift + 6, cy + 14)))
        bx = round(left + 10 + (right - left - 40) * voyage.progress)
        by = cy + round(math.sin(voyage.elapsed * 10) * 1.5)
        hull = ((bx, by + 6), (bx + 26, by + 6), (bx + 21, by + 12), (bx + 5, by + 12))
        pygame.draw.polygon(self.screen, (158, 112, 70), hull)
        pygame.draw.polygon(self.screen, (44, 28, 24), hull, 1)
        pygame.draw.line(self.screen, (192, 148, 96), (bx + 8, by + 4), (bx + 2, by + 15), 2)
        pygame.draw.line(self.screen, (192, 148, 96), (bx + 18, by + 4), (bx + 24, by + 15), 2)
        return place.union(pygame.Rect(left - 2, cy, right - left + 34, 22))

    def _draw_revive_fade(self, remaining: float) -> None:
        alpha = round(255 * min(1., remaining / (REVIVE_SECONDS * .8)))
        if alpha <= 0:
            return
        veil = self.__dict__.get("_veil")
        if veil is None or veil.get_size() != self.screen.get_size():
            veil = self._veil = pygame.Surface(self.screen.get_size())
            veil.fill((10, 8, 14))
        show(self.screen, veil, alpha, topleft=(0, 0))

    def _draw_ore_marks(self, world_object: WorldObject, x: int, y: int) -> None:
        damage = world_object.damage_stage
        if damage > 0 and world_object.durability > 0:
            overlay, foot = self._wear_image(world_object, damage)
            self.screen.blit(overlay, (x - foot[0], y - foot[1]))

    CONTACT_SHADOW_WIDTHS = {ObjectKind.TREE: 34, ObjectKind.ROCK: 24, ObjectKind.CHEST: 29,
                             ObjectKind.TORCH: 6, ObjectKind.BED: 24,
                             ObjectKind.KILN: 23, ObjectKind.COMPOSTER: 22, ObjectKind.BENCH: 30,
                             ObjectKind.FALLEN_LOG: 46, ObjectKind.BERRY_BUSH: 25, ObjectKind.CACTUS: 22,
                             ObjectKind.MUSHROOM: 18, ObjectKind.CAMPFIRE: 30, ObjectKind.WINDMILL: 38,
                             ObjectKind.WAYSTONE: 23, ObjectKind.DOCK: 12, ObjectKind.MENHIR: 16}

    @property
    def _object_contact_alpha(self) -> int:
        return 55 if self.config.cast_shadow_strength > 0 else 95

    def _draw_object_body(self, world_object: WorldObject, x: int, y: int) -> None:
        if world_object.kind is ObjectKind.DOCK:
            sprite, (fx, fy) = dock_sprite(world_object.variant, world_object.elevation, self.config.world_art_scale)
            self.screen.blit(sprite, (x - fx, y - fy))
            return
        if world_object.kind is ObjectKind.MENHIR:
            sprite, (fx, fy) = guardian_art.menhir_sprite(world_object.variant, self.config.world_art_scale)
            self.screen.blit(sprite, (x - fx, y - fy))
            return
        if world_object.kind is ObjectKind.WAYSTONE:
            sprite, (fx, fy) = waystone_sprite(world_object.variant, world_object.available, self.config.world_art_scale)
            self.screen.blit(sprite, (x - fx, y - fy))
            return
        if world_object.kind is ObjectKind.WINDMILL:
            sprite, (fx, fy) = windmill_sprite(self.config.world_art_scale, world_object.variant == "restored")
            self.screen.blit(sprite, (x - fx, y - fy))
            return
        if world_object.kind in (ObjectKind.KILN, ObjectKind.BENCH):
            placed = placed_kiln if world_object.kind is ObjectKind.KILN else placed_workbench
            sprite, (fx, fy) = placed(world_object.variant == "right", self.config.world_art_scale)
            self.screen.blit(sprite, (x - fx, y - fy))
            return
        if world_object.kind is ObjectKind.CAMPFIRE:
            sprite, (fx, fy) = placed_campfire(self.config.world_art_scale)
            self.screen.blit(sprite, (x - fx, y - fy))
            return
        if world_object.production is not None or world_object.kind in (ObjectKind.BED, ObjectKind.TORCH):
            sprite = station_sprite(world_object.kind.value, self.config.world_art_scale)
            if world_object.variant == "right" and world_object.kind.value in MIRRORED:
                sprite = pygame.transform.flip(sprite, True, False)
            self.screen.blit(sprite, sprite.get_rect(midbottom=(x, y + round(3 * self.config.world_art_scale))))
            return
        draw = WorldPrimitives((x, y), self.config.world_art_scale)
        if world_object.kind is ObjectKind.CHEST:
            m = -1 if world_object.variant == "right" else 1
            for color, points in (
                ((111, 65, 42), ((-14,-15),(0,-9),(0,3),(-14,-3))),
                ((79, 48, 37), ((0,-9),(14,-16),(14,-4),(0,3))),
                ((195, 134, 74), ((-14,-15),(1,-22),(14,-16),(0,-9))),
            ):
                draw.polygon(self.screen, color, [(x+m*dx, y+dy) for dx, dy in points])
            draw.line(self.screen, (62,40,34), (x-m*14,y-10), (x,y-4))
            draw.line(self.screen, (62,40,34), (x,y-4), (x+m*14,y-11))
            for dx, dy in ((-11,-14),(-3,-11)):
                draw.line(self.screen, (213,169,92), (x+m*dx,y+dy), (x+m*dx,y+dy+10), 2)
                draw.line(self.screen, (232,190,109), (x+m*dx,y+dy), (x+m*(dx+14),y+dy-7), 2)
            draw.rect(self.screen, (252,210,110), (x-8,y-10,3,4) if m > 0 else (x+6,y-10,3,4))
        elif world_object.kind is ObjectKind.CACTUS:
            scale = self.config.world_art_scale
            self.screen.blit(cactus(world_object.variant, scale), (x-round(21*scale), y-round(45*scale)))
        elif world_object.kind is ObjectKind.TREE:
            self._draw_tree(world_object, x, y)
        elif world_object.kind is ObjectKind.ROCK:
            sprite, (fx, fy) = placed_rock(world_object.variant, rock_shape(world_object.position),
                                           self.config.world_art_scale)
            self.screen.blit(sprite, (x - fx, y - fy))
        elif world_object.kind is ObjectKind.MUSHROOM:
            sprite, (fx, fy) = placed_mushroom(world_object.variant, world_object.position,
                                               self.config.world_art_scale)
            self.screen.blit(sprite, (x - fx, y - fy))
        elif world_object.kind is ObjectKind.FALLEN_LOG:
            if world_object.variant == "northwest":
                start, end = (x - 20, y - 18), (x + 20, y + 1)
            else:
                start, end = (x + 20, y - 18), (x - 20, y + 1)
            draw.line(self.screen, (91, 52, 33), start, end, 12)
            draw.line(self.screen, (131, 77, 43), start, end, 7)
            draw.circle(self.screen, (174, 112, 66), end, 6)
            draw.circle(self.screen, (94, 53, 32), end, 3, 1)
        else:
            leaf_color = (46, 113, 59) if world_object.available else (55, 91, 58)
            draw.circle(self.screen, leaf_color, (x - 8, y - 11), 9)
            draw.circle(self.screen, leaf_color, (x + 7, y - 12), 10)
            draw.circle(self.screen, (57, 132, 67), (x, y - 17), 9)
            if world_object.available:
                berry_color = {
                    BerryColor.RED.value: (205, 58, 67),
                    BerryColor.PURPLE.value: (134, 74, 174),
                    BerryColor.PINK.value: (230, 112, 151),
                }.get(world_object.variant, (205, 58, 67))
                draw.circle(self.screen, berry_color, (x - 8, y - 14), 3)
                draw.circle(self.screen, berry_color, (x + 6, y - 17), 3)
                draw.circle(self.screen, berry_color, (x + 1, y - 8), 3)

    def _draw_tree(self, world_object: WorldObject, x: int, y: int) -> None:
        variant = world_object.variant
        if variant in PALMS:
            sprite, (fx, fy) = placed_palm(variant, self.config.world_art_scale)
            self.screen.blit(sprite, (x - fx, y - fy))
            return
        draw = WorldPrimitives((x, y), self.config.world_art_scale)
        trunk = (103, 61, 39)
        draw.rect(self.screen, trunk, (x - 4, y - 32, 8, 32))

        if variant == TreeVariant.PINE_DARK.value:
            upper, lower = (29, 68, 47), (40, 91, 53)
            draw.polygon(
                self.screen,
                upper,
                [(x, y - 72), (x - 19, y - 36), (x + 19, y - 36)],
            )
            draw.polygon(
                self.screen,
                lower,
                [(x, y - 59), (x - 22, y - 22), (x + 22, y - 22)],
            )
            return

        if variant == TreeVariant.PINE_LIGHT.value:
            upper, lower = (69, 139, 73), (52, 116, 61)
            draw.polygon(
                self.screen,
                upper,
                [(x, y - 69), (x - 18, y - 35), (x + 18, y - 35)],
            )
            draw.polygon(
                self.screen,
                lower,
                [(x, y - 56), (x - 21, y - 21), (x + 21, y - 21)],
            )
            return

        if variant == TreeVariant.AUTUMN_GOLD.value:
            dark, light = (183, 102, 38), (224, 148, 51)
        elif variant == TreeVariant.AUTUMN_RED.value:
            dark, light = (132, 57, 43), (184, 78, 48)
        else:
            dark, light = (39, 94, 51), (57, 128, 62)

        draw.circle(self.screen, dark, (x - 10, y - 43), 17)
        draw.circle(self.screen, dark, (x + 11, y - 42), 16)
        draw.circle(self.screen, light, (x, y - 55), 18)
        draw.circle(self.screen, light, (x - 4, y - 35), 15)

    HURT_SPARKS = ((-38, -30), (34, -40), (-20, -52), (46, -12), (-46, -6), (12, -58))

    def _draw_equipped_player(self, session, origin, visual_player):
        if session.drag_time > 0:
            return self._draw_sinking_player(session, origin, visual_player)
        hurt = session.hurt_time
        guarded = session.world is session.wildlife.world and session.wildlife.grace > 0
        if hurt <= 0 and not guarded:
            return self._draw_player_pose(session, origin, visual_player)
        feet = self._screen_center(visual_player, origin)
        px = max(1, round(self.config.world_art_scale))
        if hurt <= 0:
            if int(session.wildlife.grace * 10) % 2:
                return self._draw_player_pose(session, origin, visual_player)
            layer = self._player_layer(session, origin, visual_player, feet)
            layer.set_alpha(110)
            size = self.config.world_sprite_padding
            self.screen.blit(layer, (feet[0] - size, feet[1] - size))
            return
        progress = 1 - hurt / HURT_SECONDS
        layer = self._player_layer(session, origin, visual_player, feet)
        if progress < .2:
            flash = pygame.mask.from_surface(layer).to_surface(setcolor=(255, 252, 244, 255),
                                                               unsetcolor=(0, 0, 0, 0))
            layer.blit(flash, (0, 0))
        elif int(hurt * 18) % 2 == 0:
            layer.fill((255, 86, 85, 255), special_flags=pygame.BLEND_RGBA_MULT)
        dx, dy = session.hurt_from
        sx, sy = dx - dy, (dx + dy) / 2
        length = math.hypot(sx, sy) or 1.
        push = 3 * (1 - progress) ** 2
        offset = (round(sx / length * push) * px, round(sy / length * push * .5) * px)
        size = self.config.world_sprite_padding
        self.screen.blit(layer, (feet[0] - size + offset[0], feet[1] - size + offset[1]))
        if progress < .7:
            chest = (feet[0] + offset[0], feet[1] - 15 * px + offset[1])
            t = progress * HURT_SECONDS
            for i, (vx, vy) in enumerate(self.HURT_SPARKS):
                x = chest[0] + vx * t * px
                y = chest[1] + vy * t * px + 120 * t * t * px
                color = (255, 244, 230) if i % 3 == 0 else (236, 52, 64)
                self.screen.fill(color, (round(x / px) * px, round(y / px) * px, px * (1 + (i % 2)), px))

    def _player_layer(self, session, origin, visual_player, feet) -> pygame.Surface:
        size = self.config.world_sprite_padding
        layer = pygame.Surface((size*2, size*2), pygame.SRCALPHA)
        previous, self.screen = self.screen, layer
        try:
            self._draw_player_pose(session, (origin[0]-feet[0]+size, origin[1]-feet[1]+size), visual_player)
        finally:
            self.screen = previous
        return layer

    def _draw_player_pose(self, session, origin, visual_player):
        if self._player_pose.motion is MotionKind.SWIM:
            feet = self._screen_center(visual_player, origin)
            if self.player_sprites is None or not self.player_sprites.draw(self.screen, self._player_pose, feet, equipped=False):
                x, y = feet
                y -= self.config.water_lift
                pygame.draw.ellipse(self.screen, (164,207,209), (x-8,y-2,16,5), 1)
                pygame.draw.circle(self.screen, (106,71,52), (x,y-4), 4)
            return
        self._draw_player(session, origin, visual_player)
        strength = torchlight.carried_strength(session)
        if strength:
            feet = self._screen_center(visual_player, origin)
            torchlight.draw_hand_lamp(self.screen, feet, self.config.world_art_scale,
                                      strength, self._player_pose)

    def _draw_player(
        self,
        session: GameSession,
        origin: tuple[float, float],
        player_position: WorldPos,
    ) -> None:
        x, y = self._screen_center(player_position, origin)
        draw = WorldPrimitives((x, y), self.config.player_art_scale)
        self._draw_contact_shadow((x, y), 28, self.config.player_art_scale)
        if self.player_sprites is not None and self.player_sprites.draw(
                self.screen, self._player_pose, (x, y),
                equipped=session.player.equipped_tool):
            return
        draw.rect(self.screen, (53, 151, 171), (x - 9, y - 30, 18, 27))
        draw.circle(self.screen, (224, 181, 137), (x, y - 37), 8)

        direction_x, direction_y = grid_to_screen(
            session.player.facing,
            self.config.tile_width,
            self.config.tile_height,
        )
        direction = pygame.Vector2(direction_x, direction_y)
        if direction.length_squared() > 0:
            direction.scale_to_length(16)
            draw.line(
                self.screen,
                ACCENT,
                (x, y - 12),
                (round(x + direction.x), round(y - 12 + direction.y)),
                2,
            )

    def _draw_notice(self, session: GameSession) -> pygame.Rect | None:
        now = pygame.time.get_ticks()
        seen = (id(session), session.notice_count)
        if seen != self._notice_seen:
            same_game = self._notice_seen is not None and self._notice_seen[0] == seen[0]
            self._notice_seen = seen
            self._message_until = now + 3500 if same_game else -1
        if now > self._message_until:
            return
        message = session.notice
        if not message or session.voyage is not None:
            return
        label = self.pixel_font.render(message, TEXT, shadow=TEXT_SHADOW)
        panel = pygame.Rect(self.config.virtual_width - label.get_width() - 30, 20,
                            label.get_width() + 14, label.get_height() + 10)
        pygame.draw.rect(self.screen, SLOT, panel, border_radius=4)
        self.screen.blit(label, (panel.x + 7, panel.y + 5))
        return panel

    def _draw_help(self, session: GameSession) -> None:
        panel = pygame.Rect(16, 8, self.config.virtual_width - 32, 78)
        pygame.draw.rect(self.screen, PANEL, panel, border_radius=6)
        self._draw_label(f"{session.world.space_id} | Seed {session.world.seed}",
                         (26, 17), ACCENT, self.font_small)
        self._draw_label("Clique: mover / agir | Segurar: coletar, recolher móvel | 1-5 / roda: barra | I / Tab: mochila | M: mapa | Q: comer | E: usar | C: kit | R: descanso",
                         (26, 40), MUTED_TEXT, self.font_small)
        self._draw_label("Direito + foice: arar | U: melhorar picareta | Espaco: pular | F: tela cheia | F5 reiniciar | F6 nova seed | ESC pausa | F10 sair",
                         (26, 62), MUTED_TEXT, self.font_small)

    def _draw_debug(
        self,
        session: GameSession,
        origin: tuple[float, float],
        path: tuple[GridPos, ...],
        player_position: WorldPos,
    ) -> None:
        padding = session.world.tile_map.max_elevation * self.config.height_unit_pixels
        here = session.player.position
        for position in visible_grid_positions(origin, self.config, object_height=padding):
            if (position.x % 2 or position.y % 2 or abs(position.x - here.x) > DEBUG_LABEL_CELLS
                    or abs(position.y - here.y) > DEBUG_LABEL_CELLS):
                continue
            if session.world.tile_map.tile_at(position) is None:
                continue
            x, y = self._ground_center(session, position, origin)
            if not self._is_visible((x, y)):
                continue
            label = self.font_small.render(f"{position.x},{position.y},{session.world.elevation_at(position)}", True, (225, 230, 221))
            self.screen.blit(label, (x - label.get_width() // 2, y - 6))
        player = session.player
        self._draw_label(
            f"pos={player.position} z={player_position.z:.2f} "
            f"facing={player.facing} rota={len(path)} bridge={session.world.bridge.built}",
            (20, 104),
            TEXT,
            self.font_small,
        )

    def _draw_chunk_minimap(
        self,
        session: GameSession,
        player_position: WorldPos,
    ) -> None:
        size = session.world.chunk_preview_size
        if size is None:
            return

        panel = pygame.Rect(self.config.virtual_width - 214, 108, 198, 116)
        pygame.draw.rect(self.screen, (*PANEL, 235), panel, border_radius=8)
        pygame.draw.rect(self.screen, PANEL_EDGE, panel, 2, border_radius=8)
        self._draw_label(f"{session.world.space_kind.value.upper()} {size} x {size}", (panel.x + 10, panel.y + 7), TEXT, self.font_small)

        center_x = panel.centerx
        top_y = panel.y + 34
        half_width = 60
        half_height = 28

        def project(position: GridPoint) -> tuple[int, int]:
            scale_x = half_width / (size - 1)
            scale_y = half_height / (size - 1)
            if isinstance(position, (GridPos, WorldPos)):
                x, y = position.x, position.y
            else:
                x, y = position[:2]
            return (
                round(center_x + (x - y) * scale_x),
                round(top_y + (x + y) * scale_y),
            )

        guide_color = (56, 91, 105)
        for coordinate in range(8, size, 8):
            pygame.draw.line(
                self.screen,
                guide_color,
                project(GridPos(coordinate, 0)),
                project(GridPos(coordinate, size - 1)),
                1,
            )
            pygame.draw.line(
                self.screen,
                guide_color,
                project(GridPos(0, coordinate)),
                project(GridPos(size - 1, coordinate)),
                1,
            )

        boundary_color = (73, 188, 224)
        outline = [
            project(GridPos(0, 0)),
            project(GridPos(size - 1, 0)),
            project(GridPos(size - 1, size - 1)),
            project(GridPos(0, size - 1)),
        ]
        pygame.draw.lines(self.screen, boundary_color, True, outline, 2)
        pygame.draw.circle(self.screen, ACCENT, project(player_position), 4)
        self._draw_label(
            f"pos {session.player.position.x},{session.player.position.y}",
            (panel.x + 10, panel.bottom - 20),
            MUTED_TEXT,
            self.font_small,
        )

    def _is_visible(self, center: tuple[int, int]) -> bool:
        x, y = center
        width, height = self.screen.get_size()
        side = self.config.tile_width + self.config.world_sprite_padding // 2
        return (
            -side <= x <= width + side
            and -self.config.tile_height * 2
            <= y
            <= height + self.config.world_sprite_padding
        )

    def _draw_completion_banner(self, session: GameSession) -> None:
        del session
        banner = pygame.Rect(250, 190, 460, 105)
        pygame.draw.rect(self.screen, (23, 32, 30), banner, border_radius=10)
        pygame.draw.rect(self.screen, ACCENT, banner, 3, border_radius=10)
        self._center_pixel_text("SETOR RECONECTADO", ACCENT, 206, scale=3)
        self._center_pixel_text("A primeira fatia vertical foi concluida.", TEXT, 258, scale=2)

    def _draw_label(
        self,
        text: str,
        position: tuple[int, int],
        color: tuple[int, int, int],
        font: pygame.font.Font,
    ) -> None:
        self.screen.blit(font.render(text, True, color), position)

    def _pixel_text(self, text: str, position: tuple[int, int], color: tuple[int, int, int],
                    scale: int = 1) -> pygame.Rect:
        rendered = self.pixel_font.render(text, color, scale, shadow=TEXT_SHADOW)
        return self.screen.blit(rendered, position)

    def _center_pixel_text(self, text: str, color: tuple[int, int, int], y: int, scale: int = 1) -> None:
        rendered = self.pixel_font.render(text, color, scale, shadow=TEXT_SHADOW)
        self.screen.blit(rendered, ((self.config.virtual_width - rendered.get_width()) // 2, y))

    def _center_text(
        self,
        text: str,
        font: pygame.font.Font,
        color: tuple[int, int, int],
        y: int,
    ) -> None:
        rendered = font.render(text, True, color)
        self.screen.blit(rendered, ((self.config.virtual_width - rendered.get_width()) // 2, y))


_EYE_GLOWS: dict[tuple[int, int], pygame.Surface] = {}


def _eye_glow(px: int, level: int) -> pygame.Surface:
    key = (px, level)
    if key not in _EYE_GLOWS:
        size = 7 * px
        glow = pygame.Surface((size, size))
        glow.fill((0, 0, 0))
        strength = level / 4
        for ring, (r, g, b) in ((3, (60, 8, 6)), (2, (120, 20, 14)), (1, (210, 50, 36)), (0, (255, 120, 96))):
            side = (2 * ring + 1) * px
            rect = pygame.Rect(0, 0, side, side)
            rect.center = (size // 2, size // 2)
            glow.fill((round(r * strength), round(g * strength), round(b * strength)), rect)
        _EYE_GLOWS[key] = glow
    return _EYE_GLOWS[key]
