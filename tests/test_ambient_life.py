import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT / "src"), str(ROOT / "dependencias")]
os.environ.setdefault("SDL_VIDEODRIVER", "dummy")

import pygame

from spawnbound.ambient_life import (BEHIND_COVER, CARDINAL, FROG_SCARE, LIMITS, RADIUS, AmbientLife,
                                     _clear_in_front, find_anchors)
from spawnbound.config import GameConfig
from spawnbound.domain.coordinates import GridPos
from spawnbound.domain.model import Biome, ObjectKind, SpaceKind, TileKind
from spawnbound.domain.session import GameSession
from spawnbound.view import camera_origin

SEEDS = (1234, 7)


def settle(life, world, cell):
    while life._cell != cell:
        life.anchors(world, cell)
    return life.anchors(world, cell)


class AmbientLifeTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        pygame.font.init()
        cls.config = GameConfig().world_view_config
        cls.sessions = {seed: GameSession.create(seed, GameConfig(), chunk_preview_size=128) for seed in SEEDS}

    def spots(self, world):
        tiles = world.tile_map.tiles
        shore = min((p for p, t in tiles.items() if t.kind is TileKind.GRASS and any(
            (w := world.tile_map.tile_at(p + d)) is not None and w.kind is TileKind.WATER
            and p + d not in world.sea_cells for d in CARDINAL)),
            key=lambda p: (p.x - world.spawn.x) ** 2 + (p.y - world.spawn.y) ** 2)
        forest = min((p for p, t in tiles.items() if t.biome is Biome.FOREST and t.kind is TileKind.GRASS),
                     key=lambda p: (p.x - world.spawn.x) ** 2 + (p.y - world.spawn.y) ** 2)
        return world.spawn, shore, forest

    def test_each_kind_lives_where_it_belongs_within_its_limit(self):
        for seed in SEEDS:
            world = self.sessions[seed].world
            seen = set()
            for centre in self.spots(world):
                with self.subTest(seed=seed, centre=centre):
                    anchors = find_anchors(world, centre)
                    for kind, found in anchors.items():
                        self.assertLessEqual(len(found), LIMITS[kind])
                        if found:
                            seen.add(kind)
                        for cell, *_ in found:
                            self.assertLessEqual(max(abs(cell.x - centre.x), abs(cell.y - centre.y)), RADIUS)
                            self.assertIs(TileKind.GRASS, world.tile_map.tile_at(cell).kind)
                            if kind not in BEHIND_COVER:
                                self.assertTrue(_clear_in_front(world, cell, world.elevation_at(cell)))
                    for cell, _ in anchors["bee"]:
                        self.assertIs(ObjectKind.BERRY_BUSH, world.objects[cell].kind)
                    for cell, _ in anchors["butterfly"]:
                        self.assertIsNot(Biome.FOREST, world.tile_map.tile_at(cell).biome)
                        self.assertNotIn(cell, world.objects)
                    for cell, _, water in anchors["frog"]:
                        lake = world.tile_map.tile_at(cell + water)
                        self.assertIs(TileKind.WATER, lake.kind)
                        self.assertNotIn(cell + water, world.sea_cells)
            self.assertEqual(set(LIMITS), seen, seed)

    def draw(self, session, clock):
        session.cycle_seconds = clock
        screen = pygame.Surface((self.config.virtual_width, self.config.virtual_height))
        origin = camera_origin(session, self.config, session.player.position3d)
        life = AmbientLife()
        if session.world.space_kind is SpaceKind.OUTDOOR:
            settle(life, session.world, session.player.position)
        return life.draw_ground(screen, session, origin, self.config), life.draw_glow(screen, session, origin, self.config)

    def test_butterflies_by_day_fireflies_by_night_and_nothing_underground(self):
        session = self.sessions[1234]
        world = session.world
        day, afternoon, night = self.config.phase_durations
        base, shore, forest = self.spots(world)
        try:
            session.player.position = base
            ground, glow = self.draw(session, day * .3)
            self.assertGreater(ground, 0)
            self.assertEqual(0, glow)
            session.player.position = forest
            lights = [self.draw(session, day + afternoon + night * .3 + k * .37)[1] for k in range(12)]
            self.assertGreater(max(lights), 0)
            flyers = find_anchors(world, forest)
            frogs_only = self.draw(session, day + afternoon + night * .3)[0]
            self.assertLessEqual(frogs_only, len(flyers["frog"]))
            cave = next(p for p in world.portals.values() if p.target_kind is SpaceKind.CAVE)
            session.world, session.player.position = session.spaces.resolve(world, cave)
            self.assertEqual((0, 0), self.draw(session, day * .3))
            self.assertEqual((0, 0), self.draw(session, day + afternoon + night * .3))
        finally:
            session.world, session.player.position = world, world.spawn
            session.cycle_seconds = 0.0

    def test_frogs_dive_when_the_player_comes_close(self):
        session = self.sessions[1234]
        world = session.world
        _, shore, _ = self.spots(world)
        frog = find_anchors(world, shore)["frog"][0][0]
        watch = next(p for p in sorted(world.tile_map.tiles)
                     if 9 <= (p.x - frog.x) ** 2 + (p.y - frog.y) ** 2 <= 16
                     and frog in [c for c, *_ in find_anchors(world, p)["frog"]])
        night = sum(self.config.phase_durations[:2]) + 5
        try:
            for stand in (watch, frog):
                session.player.position = stand
                frogs = [c for c, *_ in find_anchors(world, stand)["frog"]]
                visible = [c for c in frogs if (c.x - stand.x) ** 2 + (c.y - stand.y) ** 2 >= FROG_SCARE ** 2]
                self.assertEqual(len(visible), self.draw(session, night)[0], stand)
                self.assertEqual(stand == watch, frog in visible)
        finally:
            session.player.position = world.spawn
            session.cycle_seconds = 0.0

    def test_another_island_starts_from_scratch(self):
        life = AmbientLife()
        centre = GridPos(64, 64)
        for seed in SEEDS + SEEDS[:1]:
            world = self.sessions[seed].world
            self.assertEqual(find_anchors(world, centre), life.anchors(world, centre), seed)

    def test_candidates_are_found_once_per_block_and_refreshed_after_changes(self):
        world = self.sessions[7].world
        life = AmbientLife()
        centre = world.spawn
        before = settle(life, world, centre)
        self.assertIs(before, life.anchors(world, centre))
        blocks = dict(life._blocks)
        life.anchors(world, centre + GridPos(1, 0))
        self.assertTrue(all(life._blocks[k] is v for k, v in blocks.items()))
        bush = next((cell for cell, _ in before["bee"]), None)
        if bush is None:
            self.skipTest("no bees near this base")
        removed = world.remove_object(bush)
        try:
            self.assertNotIn(bush, [cell for cell, _ in life.anchors(world, centre)["bee"]])
            self.assertEqual(find_anchors(world, centre), settle(life, world, centre))
        finally:
            world.objects[bush] = removed
            world.tile_map.changes.append(bush)


if __name__ == "__main__":
    unittest.main()
