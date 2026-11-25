from __future__ import annotations

from dataclasses import dataclass, replace
import math


@dataclass(frozen=True, slots=True)
class GameConfig:
    title: str = "SpawnBound - prototipo da espinha dorsal"
    virtual_width: int = 960
    virtual_height: int = 540
    camera_zoom: float = 1.0
    target_view_height: int = 540
    target_fps: int = 60
    max_fps: int = 144

    asset_tile_width: int = 32
    asset_tile_height: int = 16
    pixel_scale: int = 1
    terrain_grid_strength: float = 0.10
    cast_shadow_strength: float = 0.32
    ground_detail_density: float = 1.0
    scene_cache: bool = True

    max_energy: int = 100
    starting_hearts: int = 8
    rest_energy_ratio: float = 0.15
    movement_seconds_per_cell: float = 0.24
    max_frame_delta: float = 0.10
    height_unit_pixels: int = 10

    max_step_height: int = 1
    day_seconds: float = 30.0
    afternoon_seconds: float = 30.0
    night_seconds: float = 30.0

    @property
    def water_lift(self) -> int:
        return max(1, round(self.height_unit_pixels * .7))

    def __post_init__(self) -> None:
        if any(not math.isfinite(s) or s <= 0 for s in self.phase_durations):
            raise ValueError("day, afternoon and night durations must be positive and finite")
        if not math.isfinite(self.camera_zoom) or self.camera_zoom <= 0:
            raise ValueError("camera_zoom must be finite and positive")
        if self.target_view_height <= 0:
            raise ValueError("target_view_height must be positive")
        if not 0 <= self.terrain_grid_strength <= 1:
            raise ValueError("terrain_grid_strength must be between 0 and 1")
        if not 0 <= self.cast_shadow_strength <= 1:
            raise ValueError("cast_shadow_strength must be between 0 and 1")
        if not 0 <= self.ground_detail_density <= 3:
            raise ValueError("ground_detail_density must be between 0 and 3")

    @property
    def phase_durations(self) -> tuple[float, float, float]:
        return self.day_seconds, self.afternoon_seconds, self.night_seconds

    @property
    def world_view_config(self) -> GameConfig:
        if self.camera_zoom == 1:
            return self
        return replace(self, camera_zoom=1,
                       virtual_width=max(1, math.ceil(self.virtual_width / self.camera_zoom - 1e-9)),
                       virtual_height=max(1, math.ceil(self.virtual_height / self.camera_zoom - 1e-9)))

    def world_to_view(self, point: tuple[float, float]) -> tuple[float, float]:
        return point[0] * self.camera_zoom, point[1] * self.camera_zoom

    def view_to_world(self, point: tuple[float, float]) -> tuple[float, float]:
        return point[0] / self.camera_zoom, point[1] / self.camera_zoom

    def presentation_scale(self, window_size: tuple[int, int], *, interior: bool = False) -> tuple[int, float]:
        ratio = min(window_size[0] / self.virtual_width, window_size[1] / self.virtual_height)
        if ratio <= 0:
            return 1, self.camera_zoom
        view_height = 270 if interior else self.target_view_height
        scale = max(1, math.floor(ratio * self.virtual_height / view_height + .5))
        return scale, scale / ratio

    @property
    def tile_width(self) -> int:
        return self.asset_tile_width * self.pixel_scale

    @property
    def tile_height(self) -> int:
        return self.asset_tile_height * self.pixel_scale

    @property
    def world_art_scale(self) -> float:
        return self.tile_width / 32

    @property
    def player_art_scale(self) -> float:
        return self.tile_width / 64

    @property
    def world_sprite_padding(self) -> int:
        return round(80 * self.world_art_scale)


DEFAULT_CONFIG = GameConfig()
