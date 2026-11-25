from enum import IntEnum


class ToolTier(IntEnum):
    NONE = 0
    WOOD = 1
    STONE = 2
    COPPER = 3
    QUARTZ = 4
    BASIC = WOOD
    REINFORCED = STONE


PICKAXES = {"pickaxe": ToolTier.WOOD, "stone_pickaxe": ToolTier.STONE,
            "copper_pickaxe": ToolTier.COPPER, "quartz_pickaxe": ToolTier.QUARTZ}
# As ferramentas de madeira mantêm os identificadores usados nos saves antigos.
AXES = {"axe": ToolTier.WOOD, "stone_axe": ToolTier.STONE,
        "copper_axe": ToolTier.COPPER, "quartz_axe": ToolTier.QUARTZ}
SWORDS = {"sword": ToolTier.WOOD, "stone_sword": ToolTier.STONE,
          "copper_sword": ToolTier.COPPER, "quartz_sword": ToolTier.QUARTZ}
SICKLES = {"sickle": ToolTier.WOOD, "stone_sickle": ToolTier.STONE,
           "copper_sickle": ToolTier.COPPER, "quartz_sickle": ToolTier.QUARTZ}
TIERED = {"pickaxe": PICKAXES, "axe": AXES, "sword": SWORDS, "sickle": SICKLES}
KIND_NAMES = {"pickaxe": ("Picareta", "a"), "axe": ("Machado", "o"), "sword": ("Espada", "a"),
              "sickle": ("Foice", "a")}
MATERIALS = {ToolTier.WOOD: "madeira", ToolTier.STONE: "pedra", ToolTier.COPPER: "cobre",
             ToolTier.QUARTZ: "quartzo"}
STARTER_TOOLS = ("pickaxe", "axe", "sickle", "sword")
CRAFTED_TOOLS = {"fishing_rod": {"wood": 1, "silk": 3}}
TOOLS = frozenset().union(*TIERED.values(), CRAFTED_TOOLS)
SWORD_DAMAGES = {ToolTier.WOOD: 2, ToolTier.STONE: 3, ToolTier.COPPER: 4, ToolTier.QUARTZ: 5}
TILL_STEPS = {ToolTier.WOOD: 1, ToolTier.STONE: 2, ToolTier.COPPER: 2, ToolTier.QUARTZ: 2}
STRENGTH = {ToolTier.WOOD: 3, ToolTier.STONE: 4, ToolTier.COPPER: 6, ToolTier.QUARTZ: 8}
AXE_STRENGTH = 3
HAND_STRENGTH = 1
ORE_TIERS = {"copper_ore": (ToolTier.STONE, "O cobre pede a picareta de pedra."),
             "quartz_ore": (ToolTier.COPPER, "O quartzo pede a picareta de cobre.")}
STEPS = (({"wood": 2, "stone": 3}, "2 madeiras e 3 pedras"),
         ({"stone": 2, "copper": 1}, "2 pedras e 1 cobre"),
         ({"quartz": 1, "wood": 2}, "1 quartzo e 2 madeiras"))
UPGRADES = {}
for _table in TIERED.values():
    _chain = sorted(_table, key=_table.get)
    for _step, (_costs, _ingredients) in enumerate(STEPS):
        _next = _chain[_step + 1]
        UPGRADES[_chain[_step]] = (_next, _costs, MATERIALS[_table[_next]], _ingredients)


def kind_of(item: str | None) -> str | None:
    return next((kind for kind, table in TIERED.items() if item in table), None)


def tool_name(item: str) -> str:
    kind = kind_of(item)
    return f"{KIND_NAMES[kind][0]} de {MATERIALS[TIERED[kind][item]]}"
