from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable

from spawnbound.domain.archipelago import dock_restored
from spawnbound.domain.crafting import RECIPES
from spawnbound.domain.daylight import DayPhase
from spawnbound.domain.farming import SEEDS
from spawnbound.domain.model import ObjectKind, SpaceKind, ToolTier
from spawnbound.domain.tools import TIERED, UPGRADES

if TYPE_CHECKING:
    from spawnbound.domain.session import GameSession

TIER_OF = {item: tier for table in TIERED.values() for item, tier in table.items()}
ROASTED = frozenset(recipe.product for recipe in RECIPES["campfire"])
TIP_SECONDS = 7.
TIP_GAP = 4.
FIRST_TIP_DELAY = 3.
ARENA_NOTICE = 12


@dataclass(frozen=True, slots=True)
class Objective:
    key: str
    text: str
    how: str
    done: Callable[["GameSession"], bool]
    lasting: bool = False


def _holds(session: GameSession, item: str, amount: int = 1) -> bool:
    return session.player.inventory.quantity(item) >= amount


def _stone_tool(session: GameSession) -> bool:
    return any(stack and TIER_OF.get(stack.item, ToolTier.NONE) >= ToolTier.STONE
               for stack in session.player.inventory.slots)


def _campfire_placed(session: GameSession) -> bool:
    return any(obj.kind is ObjectKind.CAMPFIRE for obj in session.world.objects.values())


def _roasted(session: GameSession) -> bool:
    return any(_holds(session, item) for item in ROASTED)


def _dock_fixed(session: GameSession) -> bool:
    world = session.home_world
    dock = world.objects.get(world.dock) if world.dock is not None else None
    return dock is not None and dock_restored(dock)


def _sailed(session: GameSession) -> bool:
    return any(space != session.home_world.space_id for space in session.visited)


def guardian_beaten(session: GameSession) -> bool:
    return any(getattr(world, "guardian_defeated", False) for world in session.spaces.worlds.values())


OBJECTIVES = (
    Objective("wood", "Colete 10 madeiras", "Clique numa árvore com o machado na barra.",
              lambda s: _holds(s, "wood", 10)),
    Objective("stone_tool", "Melhore uma ferramenta para pedra",
              "Com 2 madeiras e 3 pedras, selecione a ferramenta e aperte U.", _stone_tool),
    Objective("coal", "Junte 3 carvões na mina", "E na entrada da mina; quebre as rochas de carvão.",
              lambda s: _holds(s, "coal", 3)),
    Objective("campfire", "Monte uma fogueira",
              "I abre a mochila: a bancada faz a fogueira com 3 carvões e 5 pedras.", _campfire_placed),
    Objective("roast", "Asse uma carne na fogueira", "Cace um bicho; E ao lado da fogueira: cozinhar.", _roasted),
    Objective("dock", "Conserte o cais", "Leve 15 madeiras e 5 pedras e aperte E no cais quebrado.",
              _dock_fixed, lasting=True),
    Objective("sail", "Navegue até outra ilha", "E no cais abre a carta náutica.", _sailed, lasting=True),
    Objective("guardian", "Derrote o Guardião de Pedra", "Ele dorme num círculo de menires na ilha do barco.",
              guardian_beaten, lasting=True),
)


def current(session: GameSession) -> Objective | None:
    step = session.objective
    return OBJECTIVES[step] if step < len(OBJECTIVES) else None


def advance(session: GameSession) -> list[Objective]:
    start = session.objective
    step = max([start] + [index + 1 for index, objective in enumerate(OBJECTIVES)
                          if index >= start and objective.lasting and objective.done(session)])
    while step < len(OBJECTIVES) and OBJECTIVES[step].done(session):
        step += 1
    session.objective = step
    return list(OBJECTIVES[start:step])


def finished(session: GameSession) -> bool:
    return session.objective >= len(OBJECTIVES)


@dataclass(frozen=True, slots=True)
class Tip:
    key: str
    text: str
    when: Callable[["GameSession"], bool]


def _near_arena(session: GameSession) -> bool:
    arena = getattr(session.world, "arena", None)
    if arena is None or getattr(session.world, "guardian_defeated", False):
        return False
    here = session.player.position
    return max(abs(here.x - arena.x), abs(here.y - arena.y)) <= ARENA_NOTICE


def _can_upgrade(session: GameSession) -> bool:
    bag = session.player.inventory
    return any(stack and stack.item in UPGRADES and bag.has(UPGRADES[stack.item][1]) for stack in bag.slots)


TIPS = (
    Tip("pause", "Esc abre a pausa, onde estão todos os controles.", lambda s: True),
    Tip("arena", "O Guardião desvia a espada: golpeie quando o punho prender no chão. Espaço pula a onda.",
        _near_arena),
    Tip("hurt", "Aperte Q para comer. Carne assada cura; carne crua tira vida.",
        lambda s: s.player.hearts < s.max_hearts),
    Tip("night", "De noite surgem arqueiros. R ao lado de uma fogueira dorme até de manhã.",
        lambda s: s.world.space_kind is SpaceKind.OUTDOOR and s.daylight.phase is DayPhase.NIGHT),
    Tip("energy", "Energia baixa: coma frutas ou cogumelos, ou descanse numa cama.",
        lambda s: s.player.energy <= s.player.max_energy // 4),
    Tip("mine", "Na mina há carvão, cobre e quartzo. O cobre pede a picareta de pedra.",
        lambda s: s.world.space_kind is SpaceKind.CAVE),
    Tip("upgrade", "Você tem material para melhorar uma ferramenta: selecione-a e aperte U.", _can_upgrade),
    Tip("bag", "I ou Tab abre a mochila. O botão da bancada mostra o que dá para fabricar.",
        lambda s: _holds(s, "wood", 4)),
    Tip("seed", "Clique direito com a foice ara a terra; com a semente na barra, planta.",
        lambda s: any(_holds(s, item) for item in SEEDS)),
    Tip("rod", "Com a vara na barra, segure o clique na água e solte para lançar.",
        lambda s: _holds(s, "fishing_rod")),
    Tip("map", "M abre o mapa da ilha.", lambda s: s.played_seconds > 90 and s.survey is not None),
)


def next_tip(session: GameSession) -> Tip | None:
    for tip in TIPS:
        if tip.key not in session.tips_seen and tip.when(session):
            return tip
    return None


__all__ = ["OBJECTIVES", "TIPS", "Objective", "Tip", "advance", "current", "finished", "guardian_beaten",
           "next_tip"]
