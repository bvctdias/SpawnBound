from __future__ import annotations

import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from spawnbound.config import DEFAULT_CONFIG
from spawnbound.domain.coordinates import GridPos, NEIGHBOR_DIRECTIONS, WorldPos
from spawnbound.domain.model import ObjectKind, SpaceKind, TileKind, TileMap, Portal
from spawnbound.domain.inventory import CHEST_SIZE, SLOT_COUNT
from spawnbound.domain.mine_guides import MineGuides
from spawnbound.domain.navigation import find_path
from spawnbound.domain.spaces import generate_space, _connect_cave
from spawnbound.domain.session import ActionCode, GameSession
from spawnbound.domain.terrain import reachable_surface
from spawnbound.input import InputFrame
from spawnbound.states import ClickIntent, GameplayState
from spawnbound.view import camera_origin, screen_center, slot_rect


def enter(session, portal):
    session.player.position = portal.approach
    session.player.facing = portal.position - portal.approach
    result = session.interact()
    if result.code is not ActionCode.SPACE_CHANGED:
        raise AssertionError(result)


def leave(session):
    portal = next(iter(session.world.portals.values()))
    enter(session, portal)


class SpacesTests(unittest.TestCase):
    def test_chest_click_deposit_withdraw_and_return(self):
        session = GameSession.create(1234, DEFAULT_CONFIG, chunk_preview_size=32)
        shelter = next(p for p in session.world.portals.values() if p.target_kind is SpaceKind.INTERIOR)
        enter(session, shelter)
        state = GameplayState(session, DEFAULT_CONFIG)
        self.assertFalse(session.world.objects)
        from spawnbound.domain.crafting import RECIPES
        recipe = next(r for r in RECIPES["bench"] if r.product == "chest")
        bag = session.player.inventory
        for item, qty in recipe.costs.items():
            bag.add(item, qty)
        self.assertTrue(session.craft_at_bench(recipe).success)
        bag.selected = next(i for i, stack in enumerate(bag.slots) if stack and stack.item == "chest")
        position = session.player.position + GridPos(1, 0)
        self.assertTrue(session.place_furniture(position, "chest").success)
        bag.selected = 0
        chest = session.world.objects[position]
        self.assertFalse(session.world.is_walkable(chest.position))
        self.assertEqual(32, len(chest.storage.slots))
        x,y = screen_center(chest.position3d, camera_origin(session, DEFAULT_CONFIG), DEFAULT_CONFIG)
        state.step(InputFrame(destination_click=(x, y-12)), 0)
        for _ in range(180):
            state.step(InputFrame(), 1/60)
            if not state._path and state._animation_to is None:
                break
        state.step(InputFrame(interact_pressed=True), 0)
        self.assertTrue(state.inventory_open)
        bag = session.player.inventory
        self.assertEqual(20, len(bag.slots))
        bag.add("wood", 5)

        def point(index):
            x,y,w,h = slot_rect(DEFAULT_CONFIG, index, True, True)
            return x+w//2, y+h//2

        last_slot = point(SLOT_COUNT + CHEST_SIZE - 1)
        wood_slot = next(i for i, stack in enumerate(bag.slots) if stack and stack.item == "wood")
        state.step(InputFrame(destination_click=point(wood_slot), left_release=last_slot), 0)
        self.assertEqual((0,5), (bag.quantity("wood"), chest.storage.quantity("wood")))
        state.step(InputFrame(destination_click=last_slot, right_click=point(wood_slot)), 0)
        self.assertEqual((1,4), (bag.quantity("wood"), chest.storage.quantity("wood")))
        state.step(InputFrame(hotbar_index=0, pointer=last_slot), 0)
        self.assertEqual("wood", bag.equipped)
        self.assertEqual(1, chest.storage.quantity("pickaxe"))
        state.step(InputFrame(pause_pressed=True), 0)
        self.assertFalse(state.inventory_open)
        leave(session)
        enter(session, shelter)
        self.assertIs(chest.storage, session.world.objects[chest.position].storage)
        self.assertEqual(1, chest.storage.quantity("pickaxe"))

    def test_lazy_cave_entry_preserves_player_and_return_state(self):
        session = GameSession.create(1234, DEFAULT_CONFIG, chunk_preview_size=32)
        outside = session.world
        mine = next(p for p in outside.portals.values() if p.target_kind is SpaceKind.CAVE)
        self.assertEqual(1, len(session.spaces.worlds))
        player = session.player
        player.inventory.add("wood", 7)
        player.xp, player.energy = 34, 55
        enter(session, mine)
        cave = session.world
        self.assertIs(player, session.player)
        self.assertEqual(mine.target_space_id, player.space_id)
        self.assertEqual(7, player.inventory.quantity("wood"))
        self.assertEqual((34, 55), (player.xp, player.energy))
        self.assertEqual(2, len(session.spaces.worlds))
        leave(session)
        self.assertIs(outside, session.world)
        self.assertEqual(mine.approach, player.position)
        enter(session, mine)
        self.assertIs(cave, session.world)

    def test_partial_rock_damage_and_collection_persist_across_returns(self):
        session = GameSession.create(1234, DEFAULT_CONFIG, chunk_preview_size=32)
        mine = next(p for p in session.world.portals.values() if p.target_kind is SpaceKind.CAVE)
        enter(session, mine)
        cave = session.world
        wall, neighbor = next((p, p + d) for p in cave.objects
                              for d in NEIGHBOR_DIRECTIONS if cave.is_walkable(p + d)
                              and cave.can_reach(p + d, p))
        session.player.position = neighbor
        self.assertEqual(ActionCode.RESOURCE_HIT, session.primary_action(wall).code)
        leave(session)
        enter(session, mine)
        self.assertEqual(22, session.world.object_at(wall).durability)
        session.player.position = neighbor
        for _ in range(8):
            result = session.primary_action(wall)
        self.assertEqual(ActionCode.RESOURCE_GATHERED, result.code)
        self.assertTrue(session.world.is_walkable(wall))
        self.assertEqual(1, session.player.inventory.quantity("stone"))
        leave(session)
        enter(session, mine)
        self.assertEqual(TileKind.CAVE_FLOOR, session.world.tile_map.kind_at(wall))
        self.assertIsNone(session.world.object_at(wall))

    def test_space_generation_is_independent_of_discovery_order(self):
        signatures = []
        for order in ((SpaceKind.CAVE, SpaceKind.INTERIOR), (SpaceKind.INTERIOR, SpaceKind.CAVE)):
            session = GameSession.create(5432, DEFAULT_CONFIG, chunk_preview_size=32)
            outside = session.world
            result = {}
            for kind in order:
                portal = next(p for p in outside.portals.values() if p.target_kind is kind)
                enter(session, portal)
                result[kind] = session.world.signature()
                self.assertTrue(session.world.is_walkable(session.player.position))
                leave(session)
            signatures.append(result)
        self.assertEqual(*signatures)
        self.assertNotEqual(signatures[0][SpaceKind.CAVE][0], signatures[0][SpaceKind.INTERIOR][0])

    def test_cave_has_connected_relief_and_void_outside_terrain(self):
        for seed in range(8):
            with self.subTest(seed=seed):
                session = GameSession.create(seed, DEFAULT_CONFIG, chunk_preview_size=32)
                mine = next(p for p in session.world.portals.values() if p.target_kind is SpaceKind.CAVE)
                enter(session, mine)
                world = session.world
                floors = {p for p in world.tile_map.tiles if world.is_walkable(p)}
                self.assertEqual(floors, reachable_surface(world))
                guides = world.guides
                self.assertIn(world.spawn, guides.toward_exit)
                self.assertFalse(set(guides.toward_exit) & (world.objects.keys() | world.portals.keys()))
                for p in floors:
                    self.assertGreater(max(guides.nearby(world.surface_position(p)).values()), 0.5)
                for p, direction in guides.toward_exit.items():
                    self.assertTrue(world.can_step(p, p + direction))
                size = world.chunk_preview_size
                self.assertEqual(16, size)
                self.assertTrue(all(world.tile_map.tile_at(GridPos(x, y)) is None
                                    for x in range(size) for y in range(size)
                                    if x in (0, size - 1) or y in (0, size - 1)))
                self.assertTrue(all(t.kind is TileKind.CAVE_FLOOR for t in world.tile_map.tiles.values()))
                self.assertGreater(len({t.elevation for t in world.tile_map.tiles.values()}), 1)
                for obj in world.objects.values():
                    self.assertEqual(world.elevation_at(obj.position), obj.elevation)

    def test_entrance_torch_fades_by_passage_distance_and_relit_on_return(self):
        from collections import deque
        portal = Portal("mine", GridPos(7, 7), GridPos(6, 7), "mine", SpaceKind.CAVE, "MINA")
        world = generate_space(1234, portal, "overworld", cave_size=32)
        root = world.spawn
        route = {root: ()}
        frontier = deque([root])
        while frontier:
            p = frontier.popleft()
            if len(route[p]) == 10:
                break
            for d in NEIGHBOR_DIRECTIONS:
                q = p + d
                if q not in route and world.can_step(p, q):
                    route[q] = route[p] + (q,)
                    frontier.append(q)
        steps = (root, *route[p])
        self.assertEqual(11, len(steps))
        def level(pos):
            return world.guides.nearby(pos).get(root, 0)
        levels = [level(world.surface_position(q)) for q in steps]
        self.assertEqual((1, 0), (levels[0], levels[-1]))
        self.assertEqual(sorted(levels, reverse=True), levels)
        a, b = next((p, q) for q, route_to_q in route.items() if len(route_to_q) == 6
                    for p in (route_to_q[-2],) if p.x == q.x or p.y == q.y)
        midpoint = WorldPos((a.x+b.x)/2, (a.y+b.y)/2, world.elevation_at(a))
        self.assertAlmostEqual((level(world.surface_position(a))+level(world.surface_position(b)))/2,
                               level(midpoint))
        self.assertEqual(levels[::-1], [level(world.surface_position(q)) for q in reversed(steps)])

    def test_nearby_platforms_do_not_require_the_known_forty_step_detour(self):
        portal = Portal("mine", GridPos(7, 7), GridPos(6, 7), "test-cave", SpaceKind.CAVE, "MINA")
        world = generate_space(4382193466650729510, portal, "overworld", cave_size=64)
        start, end = GridPos(26, 61), GridPos(30, 61)
        route = find_path(start, end, world.is_walkable, world.can_step)
        self.assertTrue(route)
        self.assertLessEqual(len(route), 8)

    def test_nearby_platform_across_a_long_chasm_does_not_light_the_entrance_torch(self):
        world = GameSession.create(1234, DEFAULT_CONFIG, chunk_preview_size=8).world
        world.objects.clear()
        world.spawn = GridPos(0, 0)
        world.tile_map = TileMap()
        for y in range(12):
            for x in (0, 2):
                world.tile_map.add(GridPos(x, y), TileKind.CAVE_FLOOR)
        world.tile_map.add(GridPos(1, 11), TileKind.CAVE_FLOOR)
        exit_cell = GridPos(0, 1)
        world.portals = {exit_cell: Portal("return", exit_cell, world.spawn, "out", SpaceKind.OUTDOOR, "SAIDA")}
        world.strict_diagonals = True
        guides = MineGuides.place(world)
        opposite = world.surface_position(GridPos(2, 0))
        self.assertNotIn(world.spawn, guides.nearby(opposite))
        self.assertGreater(max(guides.nearby(opposite).values()), 0.5)
        self.assertTrue(any(world.tile_map.tile_at(GridPos(x, y)) is None
                            for x in range(10, 54) for y in range(10, 54)))

    def test_repair_corridor_has_width_and_stays_inside_cave_border(self):
        start, end = GridPos(3, 3), GridPos(10, 3)
        floors = {start, end}
        _connect_cave(floors, start, size=16)
        self.assertTrue(all(GridPos(x, y) in floors for x in range(3, 11) for y in (2, 3, 4)))
        self.assertTrue(all(2 <= p.x < 14 and 2 <= p.y < 14 for p in floors))

    def test_larger_caves_are_connected_with_final_heights_and_ore(self):
        portal = Portal("mine", GridPos(7, 7), GridPos(6, 7), "test-cave", SpaceKind.CAVE, "MINA")
        for seed in (0, 1, 2, 1234):
            with self.subTest(seed=seed):
                world = generate_space(seed, portal, "overworld", cave_size=64)
                self.assertEqual({p for p in world.tile_map.tiles if world.is_walkable(p)}, reachable_surface(world))

    def test_cave_size_scales_with_parent_and_void_cannot_be_entered(self):
        for side in (128, 256):
            session = GameSession.create(1234, DEFAULT_CONFIG, chunk_preview_size=side)
            mine = next(p for p in session.world.portals.values() if p.target_kind is SpaceKind.CAVE)
            enter(session, mine)
            self.assertEqual(side // 2, session.world.chunk_preview_size)
            self.assertEqual({p for p in session.world.tile_map.tiles if session.world.is_walkable(p)},
                             reachable_surface(session.world))
            boundary, outside = next((p, p + d) for p in reachable_surface(session.world)
                                     for d in NEIGHBOR_DIRECTIONS
                                     if session.world.tile_map.tile_at(p + d) is None)
            session.player.position = boundary
            self.assertFalse(session.move(outside - boundary).success)
            self.assertIsNone(session.world.tile_map.tile_at(outside))

    def test_portal_click_approaches_and_e_resets_route_and_visual_pose(self):
        session = GameSession.create(1234, DEFAULT_CONFIG, chunk_preview_size=32)
        state = GameplayState(session, DEFAULT_CONFIG)
        portal = next(p for p in session.world.portals.values() if p.target_kind is SpaceKind.CAVE)
        state._plan_target(portal.position, ClickIntent.CONTEXT_INTERACTION)
        for _ in range(30):
            state.step(InputFrame(), .1)
        self.assertEqual("Pressione E para interagir.", session.last_message)
        state.step(InputFrame(interact_pressed=True), 0)
        self.assertEqual(SpaceKind.CAVE, session.world.space_kind)
        self.assertEqual((), state._path)
        self.assertIsNone(state._animation_to)
        p = session.player.position3d
        self.assertEqual((p.x, p.y, p.z), state.visual_position3d)
