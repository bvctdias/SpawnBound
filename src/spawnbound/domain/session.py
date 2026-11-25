from __future__ import annotations

import threading
from dataclasses import dataclass, field
from enum import Enum

from spawnbound.config import GameConfig
from spawnbound.domain.coordinates import EAST, GridPos, NEIGHBOR_DIRECTIONS, WorldPos
from spawnbound.domain.daylight import Daylight, DayPhase
from spawnbound.domain.mobs import (ANGER_SECONDS, BLOW_HEARTS, CURL_SECONDS, DROPS, HERD_KINDS, SWORD_DAMAGE, Mob,
                                    MobKind, Wildlife, chebyshev)
from spawnbound.domain.generation import BRIDGE_RECIPE, WorldGenerator
from spawnbound.domain import boss
from spawnbound.domain.inventory import Inventory, Stack
from spawnbound.domain.archipelago import (DOCK_MIN_SIZE, IslandSpec, archipelago, build_island, dock_axis,
                                          dock_landing, dock_restored)
from spawnbound.domain.crafting import DOCK_REPAIR, FURNITURE, RECIPES, TURNABLE, WINDMILL_REPAIR, Recipe
from spawnbound.domain.model import OBJECT_SPECS, Biome, ObjectKind, SpaceKind, TileKind, ToolTier, World, WorldObject
from spawnbound.domain.farming import CROPS, SEEDS, WILD, Crop, garden_cells, ripe, stage
from spawnbound.domain.fish import COOKED, FISH, RAW_ENERGY, cooked_energy
from spawnbound.domain.tools import (AXE_STRENGTH, AXES, HAND_STRENGTH, KIND_NAMES, ORE_TIERS, PICKAXES, SICKLES,
                                     STRENGTH, SWORD_DAMAGES, SWORDS, TILL_STEPS, TOOLS, UPGRADES, CRAFTED_TOOLS, kind_of,
                                     tool_name)
from spawnbound.domain.movement import segment_allowed
from spawnbound.domain.spaces import WorldSpaces, exit_from
from spawnbound.domain.pathing import PlayerNavigation
from spawnbound.domain.schooling import SchoolVisit
from spawnbound.domain.exploration import IslandSurvey


BRIDGE_KIT_ID = "bridge_kit"


FOOD = {"cooked_venison": 45, "cooked_meat": 32, "cooked_snake_meat": 26, "morel": 20,
        "berry": 10, "brown_mushroom": 8, "white_mushroom": 6, "venison": 12, "meat": 8, "snake_meat": 6}
FOOD_HEARTS = {"cooked_venison": 1, "cooked_meat": 1, "cooked_snake_meat": 1, "morel": 1,
               "venison": -1, "meat": -1, "snake_meat": -1}
for _fish in FISH.values():
    FOOD[_fish.item], FOOD_HEARTS[_fish.item] = RAW_ENERGY, -1
    FOOD[COOKED[_fish.item]], FOOD_HEARTS[COOKED[_fish.item]] = cooked_energy(_fish), 1
FOOD.update({"pumpkin": 18, "carrot": 10, "turnip": 8})
FOOD = dict(sorted(FOOD.items(), key=lambda pair: (FOOD_HEARTS.get(pair[0], 0) < 0, -pair[1])))
LIGHT_FOOD = frozenset(item for item in FOOD if item not in FOOD_HEARTS)
RAW_MEAT = frozenset(item for item, hearts in FOOD_HEARTS.items() if hearts < 0)
ITEM_NAMES = {"sandworm_shell": "casco de sandworm", "meat": "carne", "venison": "carne de cervo", "hide": "couro", "snake_meat": "carne de cobra",
              "silk": "fio de teia", "venom_gland": "glandula de veneno", "berry": "frutas",
              "white_mushroom": "cogumelo branco", "brown_mushroom": "cogumelo pardo", "morel": "morchella",
              "cooked_meat": "carne assada", "cooked_venison": "carne de cervo assada",
              "cooked_snake_meat": "carne de cobra assada",
              "coal": "carvão", "copper": "cobre", "quartz": "quartzo"}
ITEM_NAMES.update({"carrot": "cenoura", "turnip": "nabo", "pumpkin": "abóbora",
                   "carrot_seed": "semente de cenoura", "turnip_seed": "semente de nabo",
                   "pumpkin_seed": "semente de abóbora"})
for _fish in FISH.values():
    ITEM_NAMES[_fish.item] = _fish.name.lower()
    ITEM_NAMES[COOKED[_fish.item]] = f"{_fish.name.lower()} assad{'a' if _fish.feminine else 'o'}"
QUIET = frozenset({"O alvo saiu de vista.", "Caminho bloqueado.", "Nada para atingir nessa celula.", "Tocha acesa."})
BLOW_MESSAGES = {"sandworm": "O sandworm te mordeu!", "arrow": "Uma flecha acertou voce!", "kick": "O cervo deu um coice!",
                 "antlers": "O cervo te acertou com os chifres!", "bite": "A cobra te picou!",
                 "fangs": "A aranha te mordeu!", "pounce": "A aranha saltou em voce!",
                 "shark": "O tubarão te mordeu! Saia da água.",
                 "maw": "O monstro da mina te mordeu!", "ram": "O monstro da mina te atropelou!",
                 "fist": "O punho do Guardião te acertou!", "stomp": "O Guardião caiu em cima de você!",
                 "boulder": "Uma pedra do Guardião caiu em você!",
                 "shockwave": "A onda de choque te derrubou! Pule com o espaço."}


class ActionCode(str, Enum):
    SOIL_TILLED = "soil_tilled"
    PLANTED = "planted"
    WAYSTONE_ACTIVATED = "waystone_activated"
    WAYSTONE_TRAVEL = "waystone_travel"
    WINDMILL_REPAIRED = "windmill_repaired"
    DOCK_REPAIRED = "dock_repaired"
    DOCK_OPENED = "dock_opened"
    VOYAGE_STARTED = "voyage_started"
    CHEST_OPENED = "chest_opened"
    STATION_OPENED = "station_opened"
    PLACED = "placed"
    MOB_HIT = "mob_hit"
    MOB_DEFEATED = "mob_defeated"
    ATE = "ate"
    MOVED = "moved"
    BLOCKED = "blocked"
    RESOURCE_HIT = "resource_hit"
    RESOURCE_GATHERED = "resource_gathered"
    NOT_ENOUGH_ENERGY = "not_enough_energy"
    CRAFTED = "crafted"
    MISSING_MATERIALS = "missing_materials"
    BRIDGE_BUILT = "bridge_built"
    BRIDGE_KIT_REQUIRED = "bridge_kit_required"
    RESTED = "rested"
    CAMPFIRE_OPENED = "campfire_opened"
    CAMP_REQUIRED = "camp_required"
    PRIMARY_ACTION_REQUIRED = "primary_action_required"
    TARGET_OUT_OF_RANGE = "target_out_of_range"
    TOOL_UPGRADE_REQUIRED = "tool_upgrade_required"
    TOOL_REQUIRED = "tool_required"
    INVENTORY_FULL = "inventory_full"
    OBJECT_DEPLETED = "object_depleted"
    NOTHING_HERE = "nothing_here"
    GOAL_REACHED = "goal_reached"
    SPACE_CHANGED = "space_changed"


@dataclass(frozen=True, slots=True)
class ActionResult:
    code: ActionCode
    success: bool
    message: str


@dataclass(slots=True)
class Player:
    position: GridPos
    object_id: str = "player"
    facing: GridPos = EAST
    max_energy: int = 100
    energy: int = 100
    hearts: int = 3
    bonus_hearts: int = 0
    xp: int = 0
    level: int = 1
    inventory: Inventory = field(default_factory=Inventory.starter)
    elevation: int = 0
    space_id: str = "overworld"
    offset_x: float = 0.0
    offset_y: float = 0.0

    @property
    def tool_tier(self) -> ToolTier:
        return PICKAXES.get(self.inventory.equipped, ToolTier.NONE)

    @property
    def equipped_tool(self) -> str | None:
        item = self.inventory.equipped
        return item if item in TOOLS else None

    @property
    def position3d(self) -> WorldPos:
        return WorldPos(self.position.x + self.offset_x, self.position.y + self.offset_y, self.elevation)

    def place(self, position: WorldPos) -> None:
        self.position = position.grid
        self.offset_x = position.x - self.position.x
        self.offset_y = position.y - self.position.y
        self.elevation = position.z

    @property
    def xp_to_next_level(self) -> int:
        return 100 + (self.level - 1) * 50

    def gain_xp(self, amount: int) -> None:
        self.xp += amount
        while self.xp >= self.xp_to_next_level:
            threshold = self.xp_to_next_level
            self.xp -= threshold
            self.level += 1


@dataclass(slots=True)
class Afterimage:
    location: WorldPos
    space_id: str
    subject: WorldObject | Mob | None
    loot: str | None
    elapsed: float = 0.0
    destroyed: bool = False
    impact: bool = False
    push: int = 1

    @property
    def lifetime(self) -> float:
        return IMPACT_SECONDS if self.impact else AFTERIMAGE_SECONDS


AFTERIMAGE_SECONDS = .85
IMPACT_SECONDS = .55
HURT_SECONDS = .38
REVIVE_SECONDS = 1.2
DRAG_SECONDS = 1.6
REST_HEARTS = 2
VOYAGE_SECONDS = 1.4


@dataclass(slots=True)
class Voyage:
    island: IslandSpec
    remaining: float = VOYAGE_SECONDS
    elapsed: float = 0.
    arrival: GridPos | None = None
    facing: GridPos | None = None
    world: World | None = None
    life: Wildlife | None = None
    builder: threading.Thread | None = field(default=None, repr=False)
    behind: tuple[World, ...] = ()
    landing_ready: bool = True

    def build(self, spaces: WorldSpaces | None = None) -> None:
        world = self.world
        if world is None:
            world = build_island(self.island)
            self.life = Wildlife(world)
        if spaces is not None:
            self.behind = tuple(spaces.build_behind(world))
        self.world = world

    @property
    def built(self) -> bool:
        return self.remaining <= 0 and (self.builder is None or not self.builder.is_alive())

    @property
    def ready(self) -> bool:
        return self.built and self.landing_ready

    @property
    def landing(self) -> GridPos | None:
        world = self.world
        if world is None:
            return None
        return self.arrival or dock_landing(world) or world.spawn

    @property
    def progress(self) -> float:
        return 1. - max(0., self.remaining) / VOYAGE_SECONDS


@dataclass(slots=True)
class GameSession:
    world: World
    player: Player
    config: GameConfig
    last_message: str = "Explore a ilha inicial e reconecte o setor."
    notice: str = ""
    notice_count: int = 0
    completed: bool = False
    cycle_seconds: float = 0.0
    production_seconds: float = 0.0
    hurt_time: float = 0.0
    hurt_from: tuple[float, float] = (0.0, 0.0)
    revive_time: float = 0.0
    drag_time: float = 0.0
    drag_shark: int | None = None
    played_seconds: float = 0.0
    airborne: bool = False
    objective: int = 0
    tips_seen: set[str] = field(default_factory=set)
    ending_seen: bool = False
    afterimages: list[Afterimage] = field(default_factory=list, init=False)
    spaces: WorldSpaces = field(init=False)
    wildlife: Wildlife = field(init=False)
    island_life: Wildlife = field(init=False)
    islands: tuple[IslandSpec, ...] = field(default=(), init=False)
    home_world: World = field(init=False)
    island_lives: dict[str, Wildlife] = field(default_factory=dict, init=False)
    surveys: dict[str, IslandSurvey | None] = field(default_factory=dict, init=False)
    visited: set[str] = field(default_factory=set, init=False)
    voyage: Voyage | None = field(default=None, init=False)
    mine_life: dict[str, Wildlife] = field(default_factory=dict, init=False)
    school: SchoolVisit = field(default_factory=SchoolVisit, init=False)
    survey: IslandSurvey | None = field(default=None, init=False)
    _navigation: dict[str, PlayerNavigation] = field(default_factory=dict, init=False, repr=False)

    @property
    def max_hearts(self) -> int:
        return self.config.starting_hearts + self.player.bonus_hearts

    @property
    def navigation(self) -> PlayerNavigation:
        navigation = self._navigation.get(self.world.space_id)
        if navigation is None or navigation.world is not self.world:
            navigation = PlayerNavigation(self.world, self.config.max_step_height)
            self._navigation[self.world.space_id] = navigation
        return navigation

    def __post_init__(self) -> None:
        self.spaces = WorldSpaces(self.world.seed, {self.world.space_id: self.world})
        self.home_world = self.world
        self.wildlife = self.island_life = self.island_lives[self.world.space_id] = Wildlife(self.world)
        self.survey = self.surveys[self.world.space_id] = IslandSurvey.of(self.world)
        size = self.world.chunk_preview_size
        if size and size >= DOCK_MIN_SIZE and self.world.dock is not None:
            self.islands = archipelago(self.world.seed, size)
            self.visited.add(self.world.space_id)
        self.player.space_id = self.world.space_id
        self.player.elevation = self.world.elevation_at(self.player.position)

    def can_step(self, source: GridPos, destination: GridPos) -> bool:
        return self.world.can_step(source, destination, self.config.max_step_height, swim=True)

    def advance_time(self, seconds: float) -> None:
        dt = max(0., seconds)
        self.production_seconds += dt
        self.hurt_time = max(0., self.hurt_time - dt)
        self.revive_time = max(0., self.revive_time - dt)
        if self.afterimages:
            for effect in self.afterimages:
                effect.elapsed += dt
            self.afterimages[:] = [e for e in self.afterimages
                                   if e.elapsed < e.lifetime and e.space_id == self.world.space_id]
        self.school.advance(self.world, self.player.position3d, max(0.0, seconds))
        total = self.cycle_seconds + max(0.0, seconds)
        duration = sum(self.config.phase_durations)
        self.cycle_seconds = total % duration
        outdoors = self.world is self.island_life.world
        if outdoors and self.survey is not None:
            self.survey.follow(self.player.position)
        if total >= duration:
            for life in self.island_lives.values():
                life.dawn()
        if outdoors and self.daylight.phase is DayPhase.NIGHT and not self.island_life.night_spawned:
            self.island_life.start_night(self.player.position3d)

    def update_mobs(self, seconds: float) -> bool:
        if self.voyage is not None:
            self.voyage.remaining -= max(0., seconds)
            self.voyage.elapsed += max(0., seconds)
            if self.voyage.ready:
                self._finish_voyage()
                return True
            return False
        if self.drag_time > 0:
            self.drag_time -= max(0., seconds)
            if self.drag_time > 0:
                return False
            self.drag_time, self.drag_shark = 0., None
            self._revive("O tubarão te levou para o fundo do mar. Você voltou ao acampamento.")
            return True
        if self.world is not self.wildlife.world:
            return False
        self.wildlife.airborne = self.airborne
        damaged = self.wildlife.tick(seconds, self.player.position3d)
        woke, self.wildlife.woke = self.wildlife.woke, None
        if woke is not None and not damaged:
            self.warn(f"O {boss.NAME} despertou!" if woke.kind is MobKind.GUARDIAN else "O monstro da mina acordou!")
        shark, self.wildlife.dragging = self.wildlife.dragging, None
        if shark is not None:
            self.drag_time, self.drag_shark = DRAG_SECONDS, shark.id
            self.warn("O tubarão te arrastou para o fundo!")
            return False
        if not damaged:
            return False
        self.player.hearts = max(0, self.player.hearts - BLOW_HEARTS.get(self.wildlife.last_blow, 1))
        self.hurt_time = HURT_SECONDS
        self.hurt_from = self.wildlife.last_hit
        self.warn(BLOW_MESSAGES[self.wildlife.last_blow])
        if self.player.hearts > 0:
            return False
        self._revive("Voce voltou ao acampamento.")
        return True

    def _fauna_of(self, world: World) -> Wildlife:
        if world.space_kind is SpaceKind.OUTDOOR:
            life = self.island_lives.get(world.space_id)
            if life is None or life.world is not world:
                life = self.island_lives[world.space_id] = Wildlife(world)
                life.in_view = self.island_life.in_view
            return life
        if world.space_kind is not SpaceKind.CAVE:
            return self.island_life
        life = self.mine_life.get(world.space_id)
        if life is None or life.world is not world:
            life = self.mine_life[world.space_id] = Wildlife(world)
            life.in_view = self.island_life.in_view
        life.settle()
        return life

    def _revive(self, message: str) -> None:
        if self.world is not self.home_world:
            self.wildlife.arrows.clear()
            self._enter(self.home_world)
        self.voyage = None
        self.revive_time = REVIVE_SECONDS
        self.player.place(self.world.surface_position(self.world.spawn))
        self.player.hearts = self.max_hearts
        self.player.energy = self.player.max_energy
        self.wildlife.grace = 5.
        self.wildlife.arrows.clear()
        self.afterimages.clear()
        self.warn(message)

    def attack_mob(self, uid: int) -> ActionResult:
        mob = self.wildlife.mobs.get(uid)
        if mob is None or self.world is not self.wildlife.world:
            return self._record(ActionCode.NOTHING_HERE, False, "O alvo saiu de vista.")
        if mob.kind is MobKind.SHARK:
            return self._record(ActionCode.BLOCKED, False, "Não dá para ferir o tubarão. Saia da água!")
        pos = mob.location.grid
        if self.player.position != pos and not self.world.can_step(self.player.position, pos):
            return self._record(ActionCode.TARGET_OUT_OF_RANGE, False, "Aproxime-se do alvo.")
        if self.player.energy < 5:
            return self._record(ActionCode.NOT_ENOUGH_ENERGY, False, "Energia insuficiente.")
        if self.player.inventory.equipped in SWORDS:
            damage = SWORD_DAMAGES[SWORDS[self.player.inventory.equipped]]
        elif mob.kind is MobKind.SANDWORM:
            damage = max(1, int(self.player.tool_tier))
        else:
            damage = 1
        if mob.curled > 0:
            self.player.energy -= 5
            if pos != self.player.position:
                self.player.facing = pos - self.player.position
            mob.lunge = .2
            return self._record(ActionCode.MOB_HIT, True, "O tatu está enrolado: o golpe não entra.", warn=True)
        if mob.kind is MobKind.GUARDIAN and not boss.opening(mob):
            if pos != self.player.position:
                self.player.facing = pos - self.player.position
            self.player.energy -= 2
            if mob.asleep:
                mob.asleep, mob.boss.rest = False, boss.WAKE_PAUSE
                self.wildlife.woke = mob
            return self._record(ActionCode.MOB_HIT, True,
                                "A pedra desvia a lâmina. Golpeie com o punho preso no chão ou depois do salto.",
                                warn=True)
        drops = mob.loot or DROPS[mob.kind]
        if mob.hp <= damage and drops and not self.player.inventory.exchange({}, drops):
            return self._inventory_full()
        self.player.energy -= 5
        if pos != self.player.position:
            self.player.facing = pos - self.player.position
        mob.hp = max(0, mob.hp - damage)
        mob.flash = .22
        if mob.kind in HERD_KINDS:
            for animal in self.wildlife.mobs.values():
                if animal.kind is mob.kind and chebyshev(animal.location, mob.location) <= 3:
                    animal.flee_time = 2.0
                    animal.wait = 0
        elif mob.kind is MobKind.DEER:
            mob.anger = ANGER_SECONDS
            if not mob.windup and mob.charge is None:
                mob.wait = 0
        elif mob.kind is MobKind.SNAKE and not mob.windup:
            mob.flee_time = mob.dazed + .6
            mob.wait = 0
        elif mob.kind is MobKind.SPIDER and self.wildlife.night_spawned:
            mob.anger = max(mob.anger, 2.0)
            if not mob.windup and mob.charge is None:
                mob.wait = 0
        elif mob.kind is MobKind.MINE_MONSTER:
            self.wildlife.wake(mob)
            if not mob.windup and mob.charge is None:
                mob.wait = 0
        elif mob.kind is MobKind.ARMADILLO and mob.hp > 0:
            mob.curled, mob.flee_time = CURL_SECONDS, 0.
            return self._record(ActionCode.MOB_HIT, True, "O tatu se enrolou na casca!")
        if mob.hp > 0:
            return self._record(ActionCode.MOB_HIT, True, "Golpe acertou!")
        self.afterimages.append(Afterimage(mob.location, self.world.space_id, mob, drops[0][0] if drops else None))
        del self.wildlife.mobs[uid]
        self.player.gain_xp(40 if mob.kind is MobKind.GUARDIAN
                            else 8 if mob.kind in (MobKind.DEER, MobKind.SPIDER, MobKind.MINE_MONSTER) else 5)
        if not drops:
            return self._record(ActionCode.MOB_DEFEATED, True, "Esqueleto derrotado.")
        gains = ", ".join(f"+{amount} {ITEM_NAMES[item]}" for item, amount in drops)
        if mob.kind is MobKind.GUARDIAN:
            self.world.guardian_defeated = True
            self.player.bonus_hearts += 1
            self.player.hearts = self.max_hearts
            return self._record(ActionCode.MOB_DEFEATED, True,
                                f"O {boss.NAME} caiu! Você ganhou um coração a mais. {gains}.", warn=True)
        hint = (" Asse na fogueira antes de comer." if any(item in RAW_MEAT for item, _ in drops)
                else " Q para comer." if any(item in FOOD for item, _ in drops) else "")
        return self._record(ActionCode.MOB_DEFEATED, True, f"{gains}.{hint}")

    def eat(self) -> ActionResult:
        player = self.player
        if player.energy == player.max_energy and player.hearts == self.max_hearts:
            return self._record(ActionCode.NOTHING_HERE, False, "Vida e energia cheias.")
        inventory = player.inventory
        food = inventory.equipped if inventory.equipped in FOOD else next(
            (item for item in FOOD if inventory.quantity(item) and not self._food_refusal(item)),
            next((item for item in FOOD if inventory.quantity(item)), None))
        if food is None:
            return self._record(ActionCode.MISSING_MATERIALS, False, "Sem comida no inventario.")
        refusal = self._food_refusal(food)
        if refusal:
            return self._record(ActionCode.NOTHING_HERE, False, refusal)
        if not inventory.remove({food: 1}, selected_first=True):
            return self._record(ActionCode.MISSING_MATERIALS, False, "Sem comida no inventario.")
        gained = min(player.max_energy, player.energy + FOOD[food]) - player.energy
        player.energy += gained
        hearts = FOOD_HEARTS.get(food, 0)
        player.hearts = min(self.max_hearts, player.hearts + hearts)
        if hearts < 0:
            return self._record(ActionCode.ATE, True,
                                f"+{gained} de energia, mas carne crua custou 1 coração. Asse na fogueira.", warn=True)
        if hearts == 0:
            return self._record(ActionCode.ATE, True, "Voce comeu e recuperou energia.")
        return self._record(ActionCode.ATE, True, "Voce comeu e recuperou forcas.")

    def _food_refusal(self, food: str) -> str:
        hearts = FOOD_HEARTS.get(food, 0)
        if hearts < 0 and self.player.hearts <= 1:
            return "Carne crua custaria seu último coração. Asse na fogueira."
        if hearts <= 0 and self.player.energy == self.player.max_energy:
            return ("Energia cheia. Carne crua só tiraria vida." if hearts < 0
                    else "Energia cheia. Frutas e cogumelos so recuperam energia.")
        return ""

    @property
    def daylight(self) -> Daylight:
        return Daylight.at(self.cycle_seconds, self.config.phase_durations)

    @classmethod
    def create(
        cls,
        seed: int,
        config: GameConfig,
        *,
        chunk_preview_size: int | None = None,
    ) -> "GameSession":
        generator = WorldGenerator()
        if chunk_preview_size is None:
            world = generator.generate(seed)
        else:
            world = generator.generate_chunk_preview(seed, chunk_preview_size)
        player = Player(
            position=world.spawn,
            max_energy=config.max_energy,
            energy=config.max_energy,
            hearts=config.starting_hearts,
        )
        session = cls(world=world, player=player, config=config)
        session._sow_wild_garden()
        if chunk_preview_size is not None:
            session.last_message = (
                f"Ilha de referencia {chunk_preview_size}x{chunk_preview_size}: clique para explorar."
            )
        return session

    WILD_GARDEN = ("carrot", "carrot", "turnip", "pumpkin")

    def _sow_wild_garden(self) -> None:
        world = self.world
        if not world.home_island or world.camp is None or world.space_kind is not SpaceKind.OUTDOOR:
            return
        kinds = list(self.WILD_GARDEN)
        for cell in garden_cells(world.camp):
            if not kinds:
                break
            if not self.soil_obstacle(cell) and self.can_place(cell) and world.is_walkable(cell):
                world.crops[cell] = Crop(kinds.pop(0), WILD)

    @property
    def day_seconds(self) -> float:
        return sum(self.config.phase_durations)

    def crop_stage(self, cell: GridPos) -> int | None:
        crop = self.world.crops.get(cell)
        return None if crop is None else stage(crop, self.production_seconds, self.day_seconds)

    def crop_ripe(self, cell: GridPos) -> bool:
        crop = self.world.crops.get(cell)
        return crop is not None and ripe(crop, self.production_seconds, self.day_seconds)

    def plant(self, target: GridPos) -> ActionResult:
        bag, world = self.player.inventory, self.world
        kind = SEEDS.get(bag.equipped)
        if kind is None:
            return self._record(ActionCode.TOOL_REQUIRED, False, "Selecione uma semente na barra.")
        if not world.can_reach(self.player.position, target, self.config.max_step_height):
            return self._record(ActionCode.TARGET_OUT_OF_RANGE, False, "Aproxime-se do bloco.")
        if target in world.crops:
            return self._record(ActionCode.BLOCKED, False, "Já há uma planta aqui.")
        if world.tilled_soil.get(target) != 2:
            return self._record(ActionCode.BLOCKED, False, "Prepare a terra com a foice antes de plantar.")
        if not bag.remove({CROPS[kind].seed: 1}, selected_first=True):
            return self._record(ActionCode.MISSING_MATERIALS, False, "Sem sementes.")
        world.crops[target] = Crop(kind, self.production_seconds)
        self.player.facing = target - self.player.position
        name = ITEM_NAMES[CROPS[kind].seed]
        return self._record(ActionCode.PLANTED, True, f"{name[0].upper()}{name[1:]} plantada.")

    def harvest(self, target: GridPos) -> ActionResult:
        world = self.world
        crop = world.crops.get(target)
        if crop is None:
            return self._record(ActionCode.NOTHING_HERE, False, "Nada para colher aqui.")
        if not world.can_reach(self.player.position, target, self.config.max_step_height):
            return self._record(ActionCode.TARGET_OUT_OF_RANGE, False, "Aproxime-se da planta.")
        if not self.crop_ripe(target):
            return self._record(ActionCode.BLOCKED, False, "Ainda não está madura.")
        amount = CROPS[crop.kind].harvest
        if not self.player.inventory.exchange({}, ((crop.kind, amount),)):
            return self._inventory_full()
        del world.crops[target]
        self.player.facing = target - self.player.position
        self.afterimages.append(Afterimage(world.surface_position(target), world.space_id, None, crop.kind,
                                           destroyed=True, push=self._push(target)))
        self.player.gain_xp(2)
        return self._record(ActionCode.RESOURCE_GATHERED, True, f"+{amount} {ITEM_NAMES[crop.kind]}. Q para comer.")

    def move(self, direction: GridPos) -> ActionResult:
        self.player.facing = direction
        target = self.player.position + direction
        if not self.can_step(self.player.position, target):
            return self._record(ActionCode.BLOCKED, False, "Caminho bloqueado.")

        self.player.position = target
        self.player.offset_x = self.player.offset_y = 0.0
        self.player.elevation = self.world.elevation_at(target)
        if self.world.chunk_preview_size is None and target == self.world.goal and not self.completed:
            self.completed = True
            return self._record(ActionCode.GOAL_REACHED, True, "Setor reconectado!")
        return ActionResult(ActionCode.MOVED, True, "")

    def move_continuous(self, x: float, y: float) -> ActionResult:
        target = WorldPos(x, y, 0)
        if not segment_allowed(self.world, self.player.position3d, target, self.config.max_step_height, swim=True):
            return self._record(ActionCode.BLOCKED, False, "Caminho bloqueado.")
        self.player.place(WorldPos(x, y, self.world.elevation_at(target.grid)))
        if self.world.chunk_preview_size is None and target.grid == self.world.goal and not self.completed:
            self.completed = True
            return self._record(ActionCode.GOAL_REACHED, True, "Setor reconectado!")
        return ActionResult(ActionCode.MOVED, True, "")

    def interact(self) -> ActionResult:
        target = self.player.position + self.player.facing
        portal = (self.world.portals.get(target) or self.world.portals.get(self.player.position)
                  or exit_from(self.world, self.player.position, self.player.facing))
        if portal is not None:
            if target == portal.position and not self.world.can_reach(self.player.position, target, self.config.max_step_height):
                return self._record(ActionCode.TARGET_OUT_OF_RANGE, False, "A entrada esta em outro nivel.")
            try:
                destination, arrival = self.spaces.resolve(self.world, portal)
            except ValueError as error:
                return self._record(ActionCode.BLOCKED, False, f"Entrada indisponivel: {error}.")
            self.wildlife.arrows.clear()
            self._enter(destination)
            self.player.place(destination.surface_position(arrival))
            self.player.elevation = destination.elevation_at(arrival)
            self.player.facing = GridPos(0, -1 if destination.space_kind is SpaceKind.INTERIOR else 1)
            message = {SpaceKind.OUTDOOR: "Voce voltou para a ilha.",
                       SpaceKind.CAVE: "Siga as setas das tochas para voltar. Use E na saida.",
                       SpaceKind.INTERIOR: "Voce entrou no abrigo. Use E na saida para voltar."}[destination.space_kind]
            return self._record(ActionCode.SPACE_CHANGED, True, message)
        world_object = self.world.object_at(target)
        if world_object is not None and world_object.kind is ObjectKind.WAYSTONE:
            return self._use_waystone(world_object)
        if world_object is not None and world_object.kind is ObjectKind.DOCK:
            return self._use_dock(world_object)
        if world_object is not None and world_object.kind is ObjectKind.WINDMILL:
            if not self.world.can_reach(self.player.position, target, self.config.max_step_height):
                return self._record(ActionCode.TARGET_OUT_OF_RANGE, False, "Aproxime-se do moinho.")
            if world_object.variant == "restored":
                return self._record(ActionCode.NOTHING_HERE, False, "O moinho ja esta consertado.")
            if not self.player.inventory.remove(WINDMILL_REPAIR):
                return self._record(ActionCode.MISSING_MATERIALS, False, self.windmill_repair_hint())
            world_object.variant = "restored"
            self.world.tile_map.changes.append(target)
            return self._record(ActionCode.WINDMILL_REPAIRED, True, "Moinho consertado!")
        if world_object is not None and world_object.kind is ObjectKind.CAMPFIRE:
            if not self.world.can_reach(self.player.position, target, self.config.max_step_height):
                return self._record(ActionCode.TARGET_OUT_OF_RANGE, False, "Aproxime-se da fogueira.")
            return self._record(ActionCode.CAMPFIRE_OPENED, True, "")
        station = world_object is not None and (world_object.production is not None
                                                 or world_object.kind is ObjectKind.BENCH)
        if world_object and (world_object.storage is not None or station):
            if not self.world.can_reach(self.player.position, target, self.config.max_step_height):
                return self._record(ActionCode.TARGET_OUT_OF_RANGE, False, "Aproxime-se para abrir.")
            code = ActionCode.STATION_OPENED if station else ActionCode.CHEST_OPENED
            return self._record(code, True, "")
        if world_object is not None:
            return self._record(
                ActionCode.PRIMARY_ACTION_REQUIRED,
                False,
                "Use o clique no objeto para executar a acao primaria.",
            )

        if self.world.bridge.contains(target) and not self.world.bridge.built:
            if self.player.inventory.quantity(BRIDGE_KIT_ID) < 1:
                return self._record(
                    ActionCode.BRIDGE_KIT_REQUIRED,
                    False,
                    "Fabrique um kit de ponte com C.",
                )
            self.player.inventory.remove({BRIDGE_KIT_ID: 1})
            self.world.build_bridge()
            return self._record(ActionCode.BRIDGE_BUILT, True, "Ponte construida. Atravesse!")

        return self._record(ActionCode.NOTHING_HERE, False, "Nada para interagir nessa direcao.")

    def dock_repair_hint(self) -> str:
        bag = self.player.inventory
        return (f"E: consertar o cais e o barco. Madeira {bag.quantity('wood')}/{DOCK_REPAIR['wood']} "
                f"  Pedra {bag.quantity('stone')}/{DOCK_REPAIR['stone']}")

    def _use_dock(self, dock: WorldObject) -> ActionResult:
        if not self.world.can_reach(self.player.position, dock.position, self.config.max_step_height):
            return self._record(ActionCode.TARGET_OUT_OF_RANGE, False, "Aproxime-se do cais.")
        if dock_restored(dock):
            return self._record(ActionCode.DOCK_OPENED, True, "")
        if not self.player.inventory.remove(DOCK_REPAIR):
            return self._record(ActionCode.MISSING_MATERIALS, False, self.dock_repair_hint())
        dock.variant = dock.variant.replace("ruined", "restored")
        self.world.tile_map.changes.append(dock.position)
        return self._record(ActionCode.DOCK_REPAIRED, True, "Cais consertado! Use E no cais para navegar.", warn=True)

    @property
    def island(self) -> IslandSpec | None:
        here = self.island_life.world.space_id
        return next((spec for spec in self.islands if spec.space_id == here), None)

    def at_dock(self) -> bool:
        dock = self.world.objects.get(self.world.dock) if self.world.dock is not None else None
        return (dock is not None and dock_restored(dock)
                and self.world.can_reach(self.player.position, dock.position, self.config.max_step_height))

    def sail_to(self, space_id: str) -> ActionResult:
        spec = next((s for s in self.islands if s.space_id == space_id), None)
        if spec is None or self.voyage is not None:
            return self._record(ActionCode.BLOCKED, False, "Não há como navegar para lá.")
        if not self.at_dock():
            return self._record(ActionCode.TARGET_OUT_OF_RANGE, False, "Vá até o cais para navegar.")
        if spec is self.island:
            return self._record(ActionCode.NOTHING_HERE, False, f"Você já está na {spec.name}.")
        self._set_sail(Voyage(spec))
        return self._record(ActionCode.VOYAGE_STARTED, True, f"Navegando para a {spec.name}...")

    def island_world(self, spec: IslandSpec) -> World:
        world = self.spaces.worlds.get(spec.space_id)
        if world is None:
            world = self.spaces.worlds[spec.space_id] = build_island(spec)
        return world

    def _set_sail(self, voyage: Voyage) -> None:
        voyage.world = self.spaces.worlds.get(voyage.island.space_id)
        missing = voyage.world is None or any(
            portal.target_kind is not SpaceKind.OUTDOOR and portal.target_space_id not in self.spaces.worlds
            for portal in voyage.world.portals.values())
        if missing:
            voyage.builder = threading.Thread(target=voyage.build, args=(self.spaces,),
                                              name=voyage.island.space_id, daemon=True)
            voyage.builder.start()
        self.voyage = voyage

    def _finish_voyage(self) -> None:
        voyage, self.voyage = self.voyage, None
        if voyage.builder is not None:
            voyage.builder.join()
        if voyage.world is not None:
            self.spaces.worlds.setdefault(voyage.island.space_id, voyage.world)
        for space in voyage.behind:
            self.spaces.worlds.setdefault(space.space_id, space)
        world = self.island_world(voyage.island)
        if voyage.life is not None and voyage.life.world is world and world.space_id not in self.island_lives:
            voyage.life.in_view = self.island_life.in_view
            self.island_lives[world.space_id] = voyage.life
        arrival = voyage.arrival or dock_landing(world) or world.spawn
        first = voyage.island.space_id not in self.visited
        self.wildlife.arrows.clear()
        self._enter(world)
        self.player.place(world.surface_position(arrival))
        self.player.elevation = world.elevation_at(arrival)
        if voyage.facing is not None:
            self.player.facing = voyage.facing
        elif voyage.arrival is None and world.dock is not None:
            self.player.facing = GridPos(-dock_axis(world.objects[world.dock]).x,
                                         -dock_axis(world.objects[world.dock]).y)
        self.visited.add(voyage.island.space_id)
        self.revive_time = REVIVE_SECONDS
        self.wildlife.grace = 3.
        hint = " A pedra de viagem fica no centro da ilha." if first and not voyage.island.home else ""
        self.warn(f"Você chegou à {voyage.island.name}.{hint}")

    def _enter(self, world: World) -> None:
        self.world = world
        self.wildlife = self._fauna_of(world)
        if world.space_kind is SpaceKind.OUTDOOR:
            self.island_life = self.wildlife
            if world.space_id not in self.surveys:
                self.surveys[world.space_id] = IslandSurvey.of(world)
            self.survey = self.surveys[world.space_id]
        self.player.space_id = world.space_id

    def windmill_repair_hint(self) -> str:
        bag = self.player.inventory
        return (f"E: consertar moinho. Madeira {bag.quantity('wood')}/{WINDMILL_REPAIR['wood']} "
                f"  Pedra {bag.quantity('stone')}/{WINDMILL_REPAIR['stone']}")

    def _use_waystone(self, stone: WorldObject) -> ActionResult:
        world = self.world
        if not world.can_reach(self.player.position, stone.position, self.config.max_step_height):
            return self._record(ActionCode.TARGET_OUT_OF_RANGE, False, "Aproxime-se da pedra.")
        if not stone.available:
            stone.available = True
            return self._record(ActionCode.WAYSTONE_ACTIVATED, True, "Pedra ativada! Use E para viajar.", warn=True)
        stops = [(spec, self.spaces.worlds[spec.space_id], position) for spec in self.islands
                 if spec.space_id in self.spaces.worlds
                 for position in self.spaces.worlds[spec.space_id].waystones
                 if self._stone_active(self.spaces.worlds[spec.space_id], position)]
        if not any(w is world and p == stone.position for _, w, p in stops):
            stops = [(None, world, item.position) for item in world.active_waystones()]
        if len(stops) < 2:
            return self._record(ActionCode.NOTHING_HERE, False, "Pedra ativa. Descubra e ative outra pedra para viajar.")
        here = next(i for i, (_, w, p) in enumerate(stops) if w is world and p == stone.position)
        spec, target, destination = stops[(here + 1) % len(stops)]
        for direction in NEIGHBOR_DIRECTIONS:
            arrival = destination - direction
            if (target.is_walkable(arrival) and arrival not in target.portals
                    and target.can_reach(arrival, destination, self.config.max_step_height)):
                if target is not world:
                    self._set_sail(Voyage(spec, arrival=arrival, facing=direction))
                    return self._record(ActionCode.WAYSTONE_TRAVEL, True, f"Viajando para a {spec.name}...")
                self.player.place(world.surface_position(arrival))
                self.player.facing = direction
                return self._record(ActionCode.WAYSTONE_TRAVEL, True, "Viagem concluida.")
        return self._record(ActionCode.BLOCKED, False, "Sem espaco para chegar a outra pedra.")

    @staticmethod
    def _stone_active(world: World, position: GridPos) -> bool:
        stone = world.objects.get(position)
        return stone is not None and stone.kind is ObjectKind.WAYSTONE and stone.available

    def _end_impacts(self, same) -> None:
        self.afterimages[:] = [e for e in self.afterimages if not (e.impact and same(e))]

    def _push(self, target: GridPos) -> int:
        across = (target.x - target.y) - (self.player.position.x - self.player.position.y)
        return -1 if across < 0 else 1

    def soil_obstacle(self, target: GridPos) -> str | None:
        world = self.world
        tile = world.tile_map.tile_at(target)
        if (world.space_kind is not SpaceKind.OUTDOOR or tile is None or tile.kind is not TileKind.GRASS
                or tile.biome is Biome.DRY or target in world.objects or target in world.portals
                or target == world.camp):
            return "Escolha um bloco de grama livre."
        if target in world.crops:
            return "Já há uma planta aqui."
        if world.tilled_soil.get(target) == 2:
            return "Este solo ja esta pronto para plantar."
        return None

    def till_soil(self, target: GridPos) -> ActionResult:
        sickle = SICKLES.get(self.player.inventory.equipped)
        if sickle is None:
            return self._record(ActionCode.TOOL_REQUIRED, False, "Equipe a foice para arar.")
        if not self.world.can_reach(self.player.position, target, self.config.max_step_height):
            return self._record(ActionCode.TARGET_OUT_OF_RANGE, False, "Aproxime-se do bloco.")
        obstacle = self.soil_obstacle(target)
        if obstacle:
            return self._record(ActionCode.BLOCKED, False, obstacle)
        stage = min(2, self.world.tilled_soil.get(target, 0) + TILL_STEPS[sickle])
        self.world.tilled_soil[target] = stage
        self.world.chipped.append(target)
        self.player.facing = target - self.player.position
        notice = "Terra revolvida. Use a foice mais uma vez." if stage == 1 else "Solo pronto para plantar."
        return self._record(ActionCode.SOIL_TILLED, True, notice)

    def primary_action(self, target: GridPos) -> ActionResult:
        direction = target - self.player.position
        if not self.world.can_reach(self.player.position, target, self.config.max_step_height):
            return self._record(
                ActionCode.TARGET_OUT_OF_RANGE,
                False,
                "Aproxime-se do alvo para usar a ferramenta.",
            )

        self.player.facing = direction
        tile = self.world.tile_map.tile_at(target)
        if tile is not None and tile.kind is TileKind.CAVE_WALL:
            if self.player.tool_tier is ToolTier.NONE:
                return self._need_pickaxe()
            if not (0 < target.x < self.world.chunk_preview_size - 1
                    and 0 < target.y < self.world.chunk_preview_size - 1):
                return self._record(ActionCode.BLOCKED, False, "A borda da mina nao pode ser escavada.")
            spec = OBJECT_SPECS[ObjectKind.ROCK]
            damage = self.world.wall_damage.get(target, 0)
            remaining, cost = self._strike_cost(spec, spec.durability - damage)
            if self.player.energy <= 0 or self.player.energy < cost:
                return self._record(ActionCode.NOT_ENOUGH_ENERGY, False, "Energia insuficiente.")
            if remaining == 0 and not self.player.inventory.add("stone"):
                return self._inventory_full()
            self.player.energy -= cost
            if remaining:
                self.world.wall_damage[target] = spec.durability - remaining
                self.world.chipped.append(target)
                self.afterimages.append(Afterimage(self.world.surface_position(target), self.world.space_id,
                                                   None, None, impact=True, push=self._push(target)))
                return self._record(ActionCode.RESOURCE_HIT, True, "A parede da mina foi atingida.")
            self.world.wall_damage.pop(target, None)
            self.world.tile_map.add(target, TileKind.CAVE_FLOOR, biome=tile.biome)
            location = self.world.surface_position(target)
            self._end_impacts(lambda e: e.subject is None and e.location.grid == target)
            self.afterimages.append(Afterimage(location, self.world.space_id,
                                               None, "stone", destroyed=True, push=self._push(target)))
            self.player.gain_xp(4)
            return self._record(ActionCode.RESOURCE_GATHERED, True, "Coletado: stone. Passagem aberta.")
        world_object = self.world.object_at(target)
        if world_object is None:
            return self._record(ActionCode.NOTHING_HERE, False, "Nada para atingir nessa celula.")
        if world_object.kind is ObjectKind.WAYSTONE:
            message = "Use E para viajar." if world_object.available else "Use E para ativar a pedra."
            return self._record(ActionCode.NOTHING_HERE, False, message)
        if world_object.kind is ObjectKind.WINDMILL:
            message = "O moinho ja esta consertado." if world_object.variant == "restored" else self.windmill_repair_hint()
            return self._record(ActionCode.NOTHING_HERE, False, message)
        if world_object.kind is ObjectKind.DOCK:
            message = "E no cais: carta náutica." if dock_restored(world_object) else self.dock_repair_hint()
            return self._record(ActionCode.NOTHING_HERE, False, message)
        if world_object.kind is ObjectKind.CAMPFIRE:
            return self._record(ActionCode.NOTHING_HERE, False, "Clique na fogueira para cozinhar ou descansar.")
        if world_object.kind in (ObjectKind.BED, ObjectKind.TORCH):
            return self._record(ActionCode.NOTHING_HERE, False, "Use R na cama." if world_object.kind is ObjectKind.BED else "Tocha acesa.")
        if world_object.kind is ObjectKind.CHEST:
            return self._record(ActionCode.NOTHING_HERE, False, "Pressione E para abrir o bau.")
        if world_object.production is not None:
            return self._record(ActionCode.NOTHING_HERE, False, "Clique para abrir as receitas.")

        if not world_object.available:
            message = (
                "O arbusto ainda esta sem frutos."
                if world_object.kind is ObjectKind.BERRY_BUSH
                else "O objeto nao esta disponivel."
            )
            return self._record(ActionCode.OBJECT_DEPLETED, False, message)

        spec = world_object.spec
        if spec.required_tool_tier != ToolTier.NONE and self.player.tool_tier is ToolTier.NONE:
            return self._need_pickaxe()
        tier, refusal = ORE_TIERS.get(world_object.variant, (ToolTier.NONE, "")) if world_object.kind is ObjectKind.ROCK else (ToolTier.NONE, "")
        if self.player.tool_tier < tier:
            return self._record(ActionCode.TOOL_UPGRADE_REQUIRED, False, refusal)
        remaining, cost = self._strike_cost(spec, world_object.durability, world_object.kind)
        if self.player.energy < cost or (spec.total_energy and self.player.energy <= 0):
            return self._record(ActionCode.NOT_ENOUGH_ENERGY, False, "Energia insuficiente.")

        if remaining == 0 and not self.player.inventory.exchange({}, world_object.drops):
            return self._inventory_full()
        self.player.energy -= cost
        alarm = (" O monstro da mina acordou!" if world_object.kind is ObjectKind.ROCK
                 and self.wildlife.world is self.world and self.wildlife.wake_guards(target) else "")
        if alarm:
            self.wildlife.woke = None
        previous_stage = world_object.damage_stage
        world_object.durability = remaining
        if world_object.durability > 0:
            if world_object.damage_stage != previous_stage:
                self.world.chipped.append(target)
            self.afterimages.append(Afterimage(world_object.position3d, self.world.space_id, world_object,
                                               None, impact=True, push=self._push(target)))
            return self._record(ActionCode.RESOURCE_HIT, True, "O objeto foi atingido." + alarm, warn=bool(alarm))

        self.player.gain_xp(world_object.xp_reward)
        if world_object.kind is ObjectKind.MUSHROOM:
            (item, amount), = world_object.drops
            self.world.remove_object(target)
            self.afterimages.append(Afterimage(world_object.position3d, self.world.space_id, None, item))
            return self._record(ActionCode.RESOURCE_GATHERED, True, f"+{amount} {ITEM_NAMES[item]}. Q para comer.")
        if spec.removed_when_depleted:
            self._end_impacts(lambda e: e.subject is world_object)
            self.afterimages.append(Afterimage(world_object.position3d, self.world.space_id,
                                               world_object, world_object.drops[0][0], destroyed=True,
                                               push=self._push(target)))
            self.world.remove_object(target)
        else:
            world_object.available = False
            self.afterimages.append(Afterimage(world_object.position3d, self.world.space_id, None, world_object.drops[0][0]))
        if world_object.kind is ObjectKind.BERRY_BUSH:
            (item, amount), = world_object.drops
            return self._record(ActionCode.RESOURCE_GATHERED, True, f"+{amount} {ITEM_NAMES[item]}. Q para comer.")

        drops = ", ".join(
            f"{amount} {item_id}" if amount > 1 else item_id
            for item_id, amount in world_object.drops
        )
        return self._record(
            ActionCode.RESOURCE_GATHERED,
            True,
            f"Coletado: {drops}." + alarm,
            warn=bool(alarm),
        )

    def _strike_cost(self, spec, durability, kind: ObjectKind = ObjectKind.ROCK):
        if kind in (ObjectKind.TREE, ObjectKind.FALLEN_LOG):
            axe = AXES.get(self.player.inventory.equipped)
            strength = STRENGTH[axe] if axe else HAND_STRENGTH
        elif kind is ObjectKind.ROCK:
            strength = STRENGTH.get(self.player.tool_tier, HAND_STRENGTH)
        else:
            strength = AXE_STRENGTH
        remaining = max(0, durability - strength)
        # Cobrar a diferença acumulada mantém o custo total mesmo se o jogador trocar de ferramenta.
        def energy_left(work):
            if work == spec.durability or work == 0 or spec.total_energy == 0:
                return spec.total_energy if work else 0
            return max(1, min(spec.total_energy - 1, round(work * spec.total_energy / spec.durability)))
        return remaining, energy_left(durability) - energy_left(remaining)

    def upgrade_pickaxe(self) -> ActionResult:
        bag = self.player.inventory
        if kind_of(bag.equipped) is None:
            return self._record(ActionCode.TOOL_REQUIRED, False, "Selecione uma ferramenta na barra.")
        if bag.equipped not in UPGRADES:
            return self._record(ActionCode.BLOCKED, False, "Quartzo ja e a melhoria final.")
        return self._upgrade_slot(bag.selected)

    upgrade_tool = upgrade_pickaxe

    def _upgrade_slot(self, index: int) -> ActionResult:
        bag = self.player.inventory
        item, costs, _name, ingredients = UPGRADES[bag.slots[index].item]
        if not bag.remove(costs):
            return self._record(ActionCode.MISSING_MATERIALS, False, f"{tool_name(item)} exige {ingredients}.")
        bag.slots[index] = Stack(item, 1)
        ending = KIND_NAMES[kind_of(item)][1]
        status = f"equipad{ending}" if index == bag.selected else f"pront{ending}"
        return self._record(ActionCode.CRAFTED, True, f"{tool_name(item)} {status}.")

    def craft_at_bench(self, recipe: Recipe) -> ActionResult:
        if recipe not in RECIPES["bench"]:
            return self._record(ActionCode.BLOCKED, False, "Receita de outro equipamento.")
        if recipe.product == BRIDGE_KIT_ID:
            return self.craft_bridge_kit()
        bag = self.player.inventory
        if not bag.has(recipe.costs):
            return self._record(ActionCode.MISSING_MATERIALS, False, "Faltam ingredientes.")
        if recipe.product in FURNITURE:
            if not bag.exchange(recipe.costs, ((recipe.product, 1),)):
                return self._inventory_full()
            return self._record(ActionCode.CRAFTED, True, "Fabricado. Selecione na barra para colocar.")
        if recipe.product in CRAFTED_TOOLS:
            if not bag.exchange(recipe.costs, ((recipe.product, 1),)):
                return self._inventory_full()
            return self._record(ActionCode.CRAFTED, True,
                                "Vara de pesca fabricada. Selecione na barra e segure o clique na água.")
        index = next(i for i in (bag.selected, *range(len(bag.slots))) if bag.slots[i]
                     and bag.slots[i].item in UPGRADES and bag.slots[i].item in recipe.costs)
        return self._upgrade_slot(index)

    def catch_fish(self, item: str) -> ActionResult:
        fish = FISH[item]
        article = "a" if fish.feminine else "o"
        if not self.player.inventory.add(item):
            return self._record(ActionCode.INVENTORY_FULL, False,
                                f"Sem espaço na mochila: {article} {fish.name.lower()} voltou para a água.")
        return self._record(ActionCode.RESOURCE_GATHERED, True,
                            f"Você pescou um{'a' if fish.feminine else ''} {fish.name.lower()}!")

    def craft_bridge_kit(self) -> ActionResult:
        if not self.player.inventory.has(BRIDGE_RECIPE):
            return self._record(
                ActionCode.MISSING_MATERIALS,
                False,
                "Kit exige 3 madeiras e 2 pedras.",
            )
        if not self.player.inventory.exchange(BRIDGE_RECIPE, ((BRIDGE_KIT_ID, 1),)):
            return self._inventory_full()
        return self._record(ActionCode.CRAFTED, True, "Kit de ponte fabricado.")

    def _inventory_full(self) -> ActionResult:
        return self._record(ActionCode.INVENTORY_FULL, False, "Sem espaco no inventario.")

    def _need_pickaxe(self) -> ActionResult:
        return self._record(ActionCode.TOOL_REQUIRED, False, "Selecione a picareta na barra.")

    def can_place(self, target: GridPos) -> bool:
        world = self.world
        tile = world.tile_map.tile_at(target)
        return (tile is not None and tile.kind in (TileKind.GRASS, TileKind.WOOD_FLOOR, TileKind.CAVE_FLOOR)
                and target not in (self.player.position, world.spawn, world.camp, world.goal)
                and target not in world.objects and target not in world.portals
                and target not in world.guides.toward_exit and target not in world.crops
                and all(target != portal.approach for portal in world.portals.values()))

    def place_furniture(self, target: GridPos, item: str, variant: str = "default") -> ActionResult:
        bag = self.player.inventory
        if item not in FURNITURE or bag.equipped != item or not self.can_place(target):
            return self._record(ActionCode.BLOCKED, False, "Escolha um espaço livre.")
        if not self.world.can_reach(self.player.position, target, self.config.max_step_height):
            return self._record(ActionCode.TARGET_OUT_OF_RANGE, False, "Aproxime-se para colocar.")
        variant = variant if variant in TURNABLE.get(item, ()) else "default"
        obj = WorldObject.create(target, ObjectKind(item), variant=variant, elevation=self.world.elevation_at(target))
        bag.remove({item: 1}, selected_first=True)
        self.world.objects[target] = obj
        self.world.tile_map.changes.append(target)
        if obj.kind is ObjectKind.TORCH:
            self.world.placed_torches.add(target)
        if obj.production is not None:
            self.world.placed_stations.add(target)
        if obj.kind is ObjectKind.CAMPFIRE:
            self.world.placed_fires.add(target)
        return self._record(ActionCode.PLACED, True, "Colocado.")

    def rest(self) -> ActionResult:
        bed = self.bed_beside() is not None
        if not bed and self.campfire_beside() is not None:
            return self._record(ActionCode.CAMPFIRE_OPENED, True, "")
        if not bed:
            return self._record(ActionCode.CAMP_REQUIRED, False, "Descanse numa cama ou ao lado de uma fogueira.")
        if self.daylight.phase is not DayPhase.DAY:
            return self.rest_until_morning()

        recovered = max(1, round(self.player.max_energy * self.config.rest_energy_ratio))
        previous = self.player.energy
        self.player.energy = min(self.player.max_energy, self.player.energy + recovered)
        gained = self.player.energy - previous
        return self._record(ActionCode.RESTED, True, f"Descanso recuperou {gained} de energia.")

    def campfire_beside(self) -> GridPos | None:
        here = self.player.position
        for direction in (self.player.facing, *NEIGHBOR_DIRECTIONS):
            cell = here + direction
            obj = self.world.object_at(cell)
            if (obj is not None and obj.kind is ObjectKind.CAMPFIRE
                    and self.world.can_reach(here, cell, self.config.max_step_height)):
                return cell
        return None

    def bed_beside(self) -> GridPos | None:
        here = self.player.position
        if (obj := self.world.object_at(here)) is not None and obj.kind is ObjectKind.BED:
            return here
        for direction in (self.player.facing, *NEIGHBOR_DIRECTIONS):
            cell = here + direction
            obj = self.world.object_at(cell)
            if (obj is not None and obj.kind is ObjectKind.BED
                    and self.world.can_reach(here, cell, self.config.max_step_height)):
                return cell
        return None

    def rest_until_morning(self) -> ActionResult:
        if self.campfire_beside() is None and self.bed_beside() is None:
            return self._record(ActionCode.CAMP_REQUIRED, False, "Fique ao lado da fogueira ou da cama para descansar.")
        if self.daylight.phase is DayPhase.DAY:
            return self._record(ActionCode.BLOCKED, False, "Ainda é dia. A fogueira serve para passar a noite.")
        self.production_seconds += sum(self.config.phase_durations) - self.cycle_seconds
        self.cycle_seconds = 0.
        for life in self.island_lives.values():
            life.dawn()
        previous, hearts = self.player.energy, self.player.hearts
        self.player.energy = min(self.player.max_energy, previous + self.player.max_energy // 2)
        self.player.hearts = min(self.max_hearts, hearts + REST_HEARTS)
        self.revive_time = REVIVE_SECONDS
        healed = self.player.hearts - hearts
        cure = f" e {healed} {'coração' if healed == 1 else 'corações'}" if healed else ""
        return self._record(ActionCode.RESTED, True,
                            f"Você dormiu até de manhã e recuperou {self.player.energy - previous} de energia{cure}.")

    def take_furniture(self) -> ActionResult:
        target = self.player.position + self.player.facing
        obj = self.world.object_at(target)
        if not obj or obj.kind.value not in FURNITURE or not self.world.can_reach(self.player.position, target):
            return self._record(ActionCode.NOTHING_HERE, False, "Aproxime-se e olhe para o móvel.")
        # Recolher um móvel devolve também o conteúdo e os ingredientes das receitas que faltam.
        items = [(obj.kind.value, 1)]
        if obj.storage:
            items += [(stack.item, stack.count) for stack in obj.storage.slots if stack]
        if obj.production:
            obj.production.refresh(self.production_seconds)
            items += [*obj.production.outputs, *obj.production.refund()]
        if not self.player.inventory.exchange({}, tuple(items)):
            message = "Sem espaço na mochila para o móvel" + (" e o que ele guarda." if len(items) > 1 else ".")
            return self._record(ActionCode.INVENTORY_FULL, False, message)
        self.world.remove_object(target)
        self.world.tile_map.changes.append(target)
        return self._record(ActionCode.CRAFTED, True, "Recolhido para a mochila.")

    def shake(self, target: GridPos) -> None:
        obj = self.world.object_at(target)
        if obj is not None:
            self.afterimages.append(Afterimage(obj.position3d, self.world.space_id, obj, None,
                                               impact=True, push=self._push(target)))

    def repair_needs(self, target: GridPos) -> dict[str, int] | None:
        obj = self.world.object_at(target)
        if obj is not None and obj.kind is ObjectKind.DOCK and not dock_restored(obj):
            return DOCK_REPAIR
        if obj is not None and obj.kind is ObjectKind.WINDMILL and obj.variant != "restored":
            return WINDMILL_REPAIR
        return None

    def _record(self, code: ActionCode, success: bool, message: str, *, warn: bool | None = None) -> ActionResult:
        self.last_message = message
        if message and (not success if warn is None else warn) and message not in QUIET:
            self.notice = message
            self.notice_count += 1
        return ActionResult(code=code, success=success, message=message)

    def warn(self, message: str) -> None:
        self.last_message = self.notice = message
        self.notice_count += 1
