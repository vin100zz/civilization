from dataclasses import dataclass, field
from typing import Dict, List, Optional


@dataclass(frozen=True)
class TechDef:
    key: str
    name: str
    cost: int                        # science points required
    prerequisites: List[str]         # keys of required techs
    description: str = ""
    era: str = "ancient"


# fmt: off
_TECH_LIST: List[TechDef] = [
    # Ancient
    TechDef("pottery",           "Pottery",           10, [],                              "Enables Granary",                      "ancient"),
    TechDef("bronze_working",    "Bronze Working",    15, [],                              "Enables Archer, Bronze units",         "ancient"),
    TechDef("alphabet",          "Alphabet",          15, [],                              "Enables Writing, Diplomacy",           "ancient"),
    TechDef("masonry",           "Masonry",           15, [],                              "Enables Walls",                        "ancient"),
    TechDef("wheel",             "Wheel",             15, [],                              "Enables Chariot",                      "ancient"),
    TechDef("horseback_riding",  "Horseback Riding",  20, ["wheel"],                       "Enables Horseman",                     "ancient"),
    TechDef("iron_working",      "Iron Working",      25, ["bronze_working"],              "Enables Legion, Swordsman",            "ancient"),
    TechDef("writing",           "Writing",           20, ["alphabet"],                    "Enables Library, Diplomat",            "classical"),
    TechDef("mathematics",       "Mathematics",       25, ["alphabet"],                    "Enables Catapult",                     "classical"),
    TechDef("map_making",        "Map Making",        25, ["alphabet"],                    "Enables Trireme, Exploration",         "classical"),
    TechDef("construction",      "Construction",      30, ["masonry", "iron_working"],     "Enables Aqueduct, Colosseum",          "classical"),
    TechDef("philosophy",        "Philosophy",        30, ["writing"],                     "Enables Temple",                       "classical"),
    TechDef("currency",          "Currency",          30, ["bronze_working"],              "Enables Marketplace, Caravan",         "classical"),
    TechDef("code_of_laws",      "Code of Laws",      30, ["alphabet"],                    "Enables Courthouse",                   "classical"),
    TechDef("trade",             "Trade",             35, ["currency", "map_making"],      "Enables Caravel",                      "medieval"),
    TechDef("feudalism",         "Feudalism",         40, ["masonry", "iron_working"],     "Enables Knight",                       "medieval"),
    TechDef("monotheism",        "Monotheism",        40, ["philosophy"],                  "Enables Crusader",                     "medieval"),
    TechDef("gunpowder",         "Gunpowder",         50, ["feudalism"],                   "Enables Musketeer, Cannon",            "medieval"),
    TechDef("navigation",        "Navigation",        50, ["map_making", "trade"],         "Enables Galleon",                      "medieval"),
    TechDef("printing_press",    "Printing Press",    60, ["writing", "feudalism"],        "Enables University",                   "renaissance"),
    TechDef("banking",           "Banking",           60, ["currency", "trade"],           "Enables Bank",                         "renaissance"),
    TechDef("steam_engine",      "Steam Engine",      80, ["mathematics", "construction"], "Enables Railroad",                     "industrial"),
    TechDef("industrialization", "Industrialization", 90, ["steam_engine"],                "Enables Factory",                      "industrial"),
    TechDef("democracy",         "Democracy",         70, ["printing_press"],              "Government type",                      "industrial"),
    TechDef("electricity",       "Electricity",       100,["industrialization"],           "Enables Power Plant",                  "modern"),
]
# fmt: on

TECH_DEFS: Dict[str, TechDef] = {t.key: t for t in _TECH_LIST}


def get_available_techs(researched: set) -> List[str]:
    """Return tech keys whose prerequisites are all satisfied."""
    return [
        key
        for key, td in TECH_DEFS.items()
        if key not in researched
        and all(p in researched for p in td.prerequisites)
    ]


def tech_era_order() -> List[str]:
    """Return all techs in a sensible research order (simple BFS by era)."""
    era_order = ["ancient", "classical", "medieval", "renaissance", "industrial", "modern"]
    result = []
    for era in era_order:
        result.extend(
            key for key, td in TECH_DEFS.items() if td.era == era
        )
    return result
