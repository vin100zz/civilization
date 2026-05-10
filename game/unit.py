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


_UNIT_LIST = [
    UnitDef("settler",   "Settler",   40, 0, 1, 1, [], [UnitAbility.FOUND_CITY]),
    UnitDef("worker",    "Worker",    20, 0, 1, 1, [], [UnitAbility.IMPROVE_TERRAIN]),
    UnitDef("warrior",   "Warrior",   10, 1, 1, 1, []),
    UnitDef("archer",    "Archer",    20, 2, 1, 1, ["bronze_working"]),
    UnitDef("chariot",   "Chariot",   30, 3, 1, 2, ["wheel", "horseback_riding"]),
    UnitDef("horseman",  "Horseman",  30, 2, 1, 2, ["horseback_riding"]),
    UnitDef("legion",    "Legion",    40, 3, 3, 1, ["iron_working"]),
    UnitDef("swordsman", "Swordsman", 30, 3, 2, 1, ["iron_working"]),
    UnitDef("catapult",  "Catapult",  40, 6, 1, 1, ["mathematics"]),
    UnitDef("knight",    "Knight",    60, 5, 2, 2, ["feudalism", "horseback_riding"]),
    UnitDef("crusader",  "Crusader",  50, 5, 2, 1, ["monotheism"]),
    UnitDef("musketeer", "Musketeer", 60, 5, 4, 1, ["gunpowder"]),
    UnitDef("cannon",    "Cannon",    80, 8, 1, 1, ["gunpowder"]),
    UnitDef("trireme",   "Trireme",   40, 1, 1, 3, ["map_making"], is_naval=True),
    UnitDef("caravel",   "Caravel",   60, 2, 1, 3, ["navigation"], is_naval=True),
]

UNIT_DEFS: Dict[str, UnitDef] = {u.key: u for u in _UNIT_LIST}


def get_buildable_units(researched: set) -> List[str]:
    return [
        key
        for key, ud in UNIT_DEFS.items()
        if all(p in researched for p in ud.prerequisites)
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
        }
