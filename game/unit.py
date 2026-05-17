from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional
import uuid


class UnitAbility(Enum):
    FOUND_CITY = "found_city"
    IMPROVE_TERRAIN = "improve_terrain"
    EXPLORE = "explore"


@dataclass(frozen=True)
class UnitDef:
    key: str
    name: str
    cost: int              # production shields
    attack: int
    defense: int
    movement: int
    prerequisites: List[str]  # tech keys
    abilities: List[UnitAbility] = field(default_factory=list)
    is_naval: bool = False
    description: str = ""


# fmt: off
_UNIT_LIST = [
    # ── Civilian ──────────────────────────────────────────────────────────
    UnitDef("settler",    "Settler",          40,  0,  1, 1, [],                            [UnitAbility.FOUND_CITY]),
    UnitDef("worker",     "Worker",           40,  0,  1, 1, [],                            [UnitAbility.IMPROVE_TERRAIN]),

    # ── Land – ancient ────────────────────────────────────────────────────
    UnitDef("militia",    "Militia",          10,  1,  1, 1, []),
    UnitDef("phalanx",    "Phalanx",          20,  1,  2, 1, ["bronze_working"]),
    UnitDef("cavalry",    "Cavalry",          20,  2,  1, 2, ["horseback_riding"]),
    UnitDef("chariot",    "Chariot",          40,  4,  1, 2, ["wheel"]),
    UnitDef("legion",     "Legion",           20,  3,  1, 1, ["iron_working"]),
    UnitDef("catapult",   "Catapult",         40,  6,  1, 1, ["mathematics"]),

    # ── Land – medieval ───────────────────────────────────────────────────
    UnitDef("knight",     "Knight",           40,  4,  2, 2, ["chivalry"]),
    UnitDef("musketeer",  "Musketeer",        30,  2,  3, 1, ["gunpowder"]),
    UnitDef("cannon",     "Cannon",           40,  8,  1, 1, ["metallurgy"]),

    # ── Land – industrial / modern ────────────────────────────────────────
    UnitDef("rifleman",   "Rifleman",         30,  3,  5, 1, ["conscription"]),
    UnitDef("armor",      "Armor",            80,  10, 5, 3, ["automobile"]),
    UnitDef("mechinf",    "Mech. Infantry",   50,  6,  6, 3, ["labor_union"]),
    UnitDef("artillery",  "Artillery",        60,  12, 2, 2, ["robotics"]),

    # ── Naval – ancient / classical ───────────────────────────────────────
    UnitDef("trireme",    "Trireme",          40,  1,  0, 3, ["map_making"],                is_naval=True),
    UnitDef("sail",       "Sail",             40,  1,  1, 3, ["navigation"],               is_naval=True),

    # ── Naval – medieval / renaissance ───────────────────────────────────
    UnitDef("frigate",    "Frigate",          40,  2,  2, 3, ["magnetism"],                is_naval=True),
    UnitDef("ironclad",   "Ironclad",         60,  4,  4, 4, ["steam_engine"],             is_naval=True),

    # ── Naval – industrial / modern ───────────────────────────────────────
    UnitDef("cruiser",    "Cruiser",          80,  6,  6, 6, ["combustion"],               is_naval=True),
    UnitDef("transport",  "Transport",        50,  0,  3, 4, ["industrialization"],        is_naval=True),
    UnitDef("submarine",  "Submarine",        50,  8,  2, 3, ["mass_production"],          is_naval=True),
    UnitDef("battleship", "Battleship",       160, 18, 12,4, ["steel"],                    is_naval=True),
    UnitDef("carrier",    "Carrier",          160, 1,  12, 5, ["advanced_flight"],         is_naval=True),

    # ── Air – not yet supported ───────────────────────────────────────────
    # UnitDef("fighter",  "Fighter",           60,  4,  2, 10, ["flight"],           is_air=True),
    # UnitDef("bomber",   "Bomber",           120, 12,  1,  8, ["advanced_flight"],  is_air=True),
    # UnitDef("nuclear",  "Nuclear",          160, 99,  0, 16, ["rocketry"],         is_air=True),
]
# fmt: on

UNIT_DEFS: Dict[str, UnitDef] = {u.key: u for u in _UNIT_LIST}


def get_buildable_units(researched: set, coastal: bool = False) -> List[str]:
    return [
        key
        for key, ud in UNIT_DEFS.items()
        if all(p in researched for p in ud.prerequisites)
        and (not ud.is_naval or coastal)
    ]


class Unit:
    """Runtime instance of a unit on the map."""

    def __init__(
        self,
        unit_def_key: str,
        civ_id: str,
        x: int,
        y: int,
        veteran: bool = False,
    ):
        self.id: str = str(uuid.uuid4())[:8]
        self.unit_def_key = unit_def_key
        self.civ_id = civ_id
        self.x = x
        self.y = y
        self.veteran = veteran
        self.moves_left: int = self.unit_def.movement
        self.hp: int = 3
        self.fortified: bool = False
        self._goal: Optional[tuple] = None  # target (x, y) for pathfinding
        self.home_city_id: Optional[str] = None  # city that produced this unit

        # Worker improvement progress (resets if the unit moves or switches task)
        self.improve_progress: int = 0           # turns spent on current task
        self.improve_x: Optional[int] = None     # tile being improved
        self.improve_y: Optional[int] = None
        self.improve_type: Optional[str] = None  # "road" | "irrigation" | "mine"

    @property
    def unit_def(self) -> UnitDef:
        return UNIT_DEFS[self.unit_def_key]

    def reset_moves(self):
        self.moves_left = self.unit_def.movement

    def has_ability(self, ability: UnitAbility) -> bool:
        return ability in self.unit_def.abilities

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "type": self.unit_def_key,
            "name": self.unit_def.name,
            "civ_id": self.civ_id,
            "x": self.x,
            "y": self.y,
            "hp": self.hp,
            "attack": self.unit_def.attack,
            "defense": self.unit_def.defense,
            "moves_left": self.moves_left,
            "veteran": self.veteran,
            "fortified": self.fortified,
            "home_city_id": self.home_city_id,
            "improve_type": self.improve_type,   # "road" | "irrigation" | "mine" | None
        }
