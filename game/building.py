from dataclasses import dataclass
from typing import Dict, List


@dataclass(frozen=True)
class BuildingDef:
    key: str
    name: str
    cost: int               # production shields required
    prerequisites: List[str]  # tech keys required
    upkeep: int             # gold per turn
    description: str
    # Modifiers
    food_bonus: float = 0.0        # additive food per turn
    production_bonus: float = 0.0  # additive production per turn
    science_mult: float = 1.0      # multiplier on city science output
    gold_mult: float = 1.0         # multiplier on city gold output
    happy_bonus: int = 0           # extra happy citizens
    defense_bonus: int = 0         # added to city defense value
    max_pop_increase: int = 0      # allows city to grow beyond base cap


_BUILDING_LIST = [
    BuildingDef("barracks",    "Barracks",     40,  [],                  1, "Units produced here start as veterans"),
    BuildingDef("granary",     "Granary",      60,  ["pottery"],         1, "+50 % food stored on growth", food_bonus=2.0),
    BuildingDef("walls",       "Walls",        40,  ["masonry"],         1, "+3 city defense", defense_bonus=3),
    BuildingDef("library",     "Library",      80,  ["writing"],         1, "+50 % science", science_mult=1.5),
    BuildingDef("marketplace", "Marketplace",  80,  ["currency"],        1, "+50 % gold", gold_mult=1.5),
    BuildingDef("temple",      "Temple",       40,  ["philosophy"],      1, "+1 happy citizen", happy_bonus=1),
    BuildingDef("aqueduct",    "Aqueduct",     80,  ["construction"],    2, "City can grow past size 8", max_pop_increase=4),
    BuildingDef("colosseum",   "Colosseum",   100,  ["construction"],    4, "+3 happy citizens", happy_bonus=3),
    BuildingDef("courthouse",  "Courthouse",   80,  ["code_of_laws"],    1, "Reduces corruption"),
    BuildingDef("bank",        "Bank",        120,  ["banking"],         2, "+50 % gold", gold_mult=1.5),
    BuildingDef("university",  "University",  160,  ["printing_press"],  3, "+100 % science", science_mult=2.0),
    BuildingDef("factory",     "Factory",     200,  ["industrialization"],4,"+ 50 % production", production_bonus=3.0),
    BuildingDef("power_plant", "Power Plant", 240,  ["electricity"],     4, "+50 % production", production_bonus=3.0),
]

BUILDING_DEFS: Dict[str, BuildingDef] = {b.key: b for b in _BUILDING_LIST}


def get_buildable_buildings(researched: set, existing: set) -> List[str]:
    """Return building keys that can be built given current research and existing buildings."""
    return [
        key
        for key, bd in BUILDING_DEFS.items()
        if key not in existing
        and all(p in researched for p in bd.prerequisites)
    ]
