from __future__ import annotations
import json
from pathlib import Path
import pygame
from spawnbound.pplay_media import load_image
from spawnbound.renderer import PlaceholderRenderer
from spawnbound.sprites import PlayerSprites
from spawnbound.domain.model import Biome, GrassVariant, ObjectKind, SpaceKind, TileKind


MIRRORED_ART = ('chest',)


class NativeArtPack:
    def __init__(self, manifest: Path):
        spec = json.loads(manifest.read_text(encoding='utf-8'))
        self.entries = spec['sprites']
        self.player_atlas = manifest.parent / spec['player_atlas'] if 'player_atlas' in spec else None
        self.images, self.masks = {}, {}
        for name, item in self.entries.items():
            image = load_image(manifest.parent / item['file'])
            if list(image.get_size()) != item['canvas']:
                raise ValueError(f'Canvas incorreto no sprite {name}')
            self.images[name] = image
            self.masks[name] = pygame.mask.from_surface(image)
        for name in MIRRORED_ART:
            if name in self.images:
                image = pygame.transform.flip(self.images[name], True, False)
                px, py = self.entries[name]['pivot']
                self.entries[name + '_right'] = {**self.entries[name], 'pivot': [image.get_width() - px, py]}
                self.images[name + '_right'] = image
                self.masks[name + '_right'] = pygame.mask.from_surface(image)

    def draw(self, target, name, feet):
        if name not in self.images:
            return False
        pivot = self.entries[name]['pivot']
        target.blit(self.images[name], (feet[0]-pivot[0], feet[1]-pivot[1]))
        return True

    def contains(self, name, dx, dy):
        if name not in self.images:
            return None
        px, py = self.entries[name]['pivot']
        x, y = round(dx+px), round(dy+py)
        w, h = self.images[name].get_size()
        return bool(0 <= x < w and 0 <= y < h and self.masks[name].get_at((x, y)))


class PrototypeArtRenderer(PlaceholderRenderer):
    def __init__(self, screen, config, manifest: Path):
        super().__init__(screen, config)
        if config.pixel_scale != 1:
            raise ValueError('O lote nativo atual usa pixel_scale=1; afastamento pertence a camera.')
        self.art = NativeArtPack(manifest)
        if self.art.player_atlas is not None:
            self.player_sprites = PlayerSprites.from_atlas(self.art.player_atlas)
        self._texture_cache = {}
        self._space_kind = SpaceKind.OUTDOOR

    def draw_gameplay(self, session, **kwargs):
        self._space_kind = session.world.space_kind
        super().draw_gameplay(session, **kwargs)

    def object_name(self, obj):
        if obj.kind in (ObjectKind.WINDMILL, ObjectKind.WAYSTONE, ObjectKind.DOCK, ObjectKind.MENHIR):
            return obj.kind.value
        if obj.production is not None or obj.kind in (ObjectKind.BED, ObjectKind.TORCH, ObjectKind.BENCH,
                                                      ObjectKind.ROCK, ObjectKind.MUSHROOM, ObjectKind.CAMPFIRE):
            return obj.kind.value
        if obj.kind is ObjectKind.CACTUS:
            return "cactus_" + obj.variant
        if obj.kind is ObjectKind.CHEST:
            return 'chest_right' if obj.variant == 'right' else 'chest'
        if obj.kind is ObjectKind.TREE:
            return 'tree_' + obj.variant
        if obj.kind is ObjectKind.BERRY_BUSH:
            return 'bush_' + obj.variant if obj.available else 'bush_empty'
        if obj.kind is ObjectKind.FALLEN_LOG:
            return 'log_northwest' if obj.variant == 'northwest' else 'log_northeast'
        return 'rock_surface'

    def portal_name(self, portal):
        if portal.target_kind is SpaceKind.INTERIOR:
            return 'shelter'
        if portal.target_kind is SpaceKind.OUTDOOR and 'cave_exit' in self.art.images:
            return 'cave_exit'
        return 'cave_entry'

    def _caster_name(self, kind, payload):
        if kind == 'object':
            return self.object_name(payload)
        return self.portal_name(payload)

    def _caster_key(self, kind, payload):
        name = self._caster_name(kind, payload)
        if name in self.art.images:
            return ('art', name)
        return super()._caster_key(kind, payload)

    def _caster_image(self, kind, payload):
        name = self._caster_name(kind, payload)
        if name in self.art.images:
            return self.art.images[name], tuple(self.art.entries[name]['pivot'])
        return super()._caster_image(kind, payload)

    def hit_test(self, kind, payload, dx, dy):
        name = self.object_name(payload) if kind == 'object' else self.portal_name(payload)
        return self.art.contains(name, dx, dy)

    def _draw_world_object(self, obj, origin):
        name = self.object_name(obj)
        if name not in self.art.images:
            return super()._draw_world_object(obj, origin)
        feet = self._screen_center(obj.position3d, origin)
        if self._live_impacts and obj.position in self._live_impacts:
            self._draw_struck_object(obj, *feet, self._live_impacts[obj.position], 28)
            return
        self._draw_contact_shadow(feet, 28, alpha=self._object_contact_alpha)
        self.art.draw(self.screen, name, feet)
        self._draw_ore_marks(obj, *feet)

    def _portal_sprite(self, portal, feet):
        return self.art.draw(self.screen, self.portal_name(portal), feet)

    def _draw_player(self, session, origin, player_position):
        feet = self._screen_center(player_position, origin)
        if 'player_idle' not in self.art.images:
            return super()._draw_player(session, origin, player_position)
        self._draw_contact_shadow(feet, 28, self.config.player_art_scale)
        if self.player_sprites is not None and self.player_sprites.draw(
                self.screen, self._player_pose, feet,
                equipped=session.player.equipped_tool):
            return
        self.art.draw(self.screen, 'player_idle', feet)

    def _terrain_texture(self, tile, position):
        if tile.kind is TileKind.GRASS:
            if tile.biome is Biome.DRY:
                name = 'ground_dry'
            elif tile.biome is Biome.MEADOW:
                name = 'grass_meadow'
            else:
                name = {GrassVariant.NORMAL:'grass_forest', GrassVariant.TALL_GRASS:'grass_tall',
                        GrassVariant.PEBBLES:'grass_pebbles'}[tile.variant]
        else:
            name = {TileKind.CAVE_FLOOR:'ground_cave', TileKind.WOOD_FLOOR:'floor_wood',
                    TileKind.BRIDGE:'bridge_wood'}.get(tile.kind)
        if name not in self.art.images:
            return None
        tone = min(tile.elevation, 6) * 4
        key = name, tone
        if key not in self._texture_cache:
            image = self.art.images[name].copy()
            image.fill((tone, tone, tone, 0), special_flags=pygame.BLEND_RGB_ADD)
            self._texture_cache[key] = image
        return self._texture_cache[key]
