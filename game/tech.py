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

    # ── Ancient ───────────────────────────────────────────────────────────
    TechDef("alphabet",          "Alphabet",           20, [],                                        "Enables Writing, Code of Laws",        "ancient"),
    TechDef("bronze_working",    "Bronze Working",     20, [],                                        "Enables Phalanx",                      "ancient"),
    TechDef("ceremonial_burial", "Ceremonial Burial",  20, [],                                        "Enables Temple",                       "ancient"),
    TechDef("horseback_riding",  "Horseback Riding",   20, [],                                        "Enables Cavalry",                      "ancient"),
    TechDef("irrigation",        "Irrigation",         20, [],                                        "Workers can irrigate",                 "ancient"),
    TechDef("masonry",           "Masonry",            20, [],                                        "Enables City Walls",                   "ancient"),
    TechDef("mathematics",       "Mathematics",        25, ["alphabet", "masonry"],                   "Enables Catapult",                     "ancient"),
    TechDef("mining",            "Mining",             20, [],                                        "Workers can mine",                     "ancient"),
    TechDef("mysticism",         "Mysticism",          20, ["ceremonial_burial"],                     "Enables Oracle",                       "ancient"),
    TechDef("pottery",           "Pottery",            20, [],                                        "Enables Granary",                      "ancient"),
    TechDef("roads",             "Roads",              20, [],                                        "Workers can build roads",              "ancient"),
    TechDef("wheel",             "Wheel",              20, [],                                        "Enables Chariot",                      "ancient"),

    # ── Classical ─────────────────────────────────────────────────────────
    TechDef("astronomy",         "Astronomy",          35, ["mysticism", "mathematics"],              "Enables Navigation",                   "classical"),
    TechDef("code_of_laws",      "Code of Laws",       30, ["alphabet"],                              "Enables Courthouse, Monarchy",         "classical"),
    TechDef("construction",      "Construction",       40, ["currency", "masonry"],                   "Enables Aqueduct, Colosseum",          "classical"),
    TechDef("currency",          "Currency",           30, ["bronze_working"],                        "Enables Marketplace",                  "classical"),
    TechDef("iron_working",      "Iron Working",       30, ["bronze_working"],                        "Enables Legion",                       "classical"),
    TechDef("literacy",          "Literacy",           40, ["code_of_laws", "writing"],               "Enables Library",                      "classical"),
    TechDef("map_making",        "Map Making",         30, ["alphabet"],                              "Enables Trireme",                      "classical"),
    TechDef("monarchy",          "Monarchy",           35, ["code_of_laws", "ceremonial_burial"],     "Government: Monarchy",                 "classical"),
    TechDef("navigation",        "Navigation",         50, ["astronomy", "map_making"],               "Enables Sail",                         "classical"),
    TechDef("trade",             "Trade",              40, ["code_of_laws", "currency"],              "Enables Caravan",                      "classical"),
    TechDef("writing",           "Writing",            30, ["alphabet"],                              "Enables Library, Diplomat",            "classical"),

    # ── Medieval ──────────────────────────────────────────────────────────
    TechDef("banking",           "Banking",            80, ["republic", "trade"],                     "Enables Bank",                         "medieval"),
    TechDef("bridge_building",   "Bridge Building",    60, ["iron_working", "construction"],          "Roads over rivers",                    "medieval"),
    TechDef("chivalry",          "Chivalry",           70, ["horseback_riding", "feudalism"],         "Enables Knights",                      "medieval"),
    TechDef("democracy",         "Democracy",          80, ["philosophy", "literacy"],                "Government: Democracy",                "medieval"),
    TechDef("engineering",       "Engineering",        60, ["wheel", "construction"],                 "Enables advanced construction",        "medieval"),
    TechDef("feudalism",         "Feudalism",          60, ["monarchy", "masonry"],                   "Enables Chivalry",                     "medieval"),
    TechDef("gunpowder",         "Gunpowder",          80, ["iron_working", "invention"],             "Enables Musketeer",                    "medieval"),
    TechDef("invention",         "Invention",          70, ["engineering", "literacy"],               "Enables Steam Engine",                 "medieval"),
    TechDef("magnetism",         "Magnetism",          90, ["navigation", "physics"],                 "Enables Frigate",                      "medieval"),
    TechDef("medicine",          "Medicine",           80, ["philosophy", "trade"],                   "Enables Shakespeare's Theatre",        "medieval"),
    TechDef("metallurgy",        "Metallurgy",         90, ["gunpowder", "university"],               "Enables Cannon",                       "medieval"),
    TechDef("philosophy",        "Philosophy",         60, ["mysticism", "literacy"],                 "Enables Democracy, Religion",          "medieval"),
    TechDef("physics",           "Physics",            80, ["navigation", "mathematics"],             "Enables Steam Engine",                 "medieval"),
    TechDef("religion",          "Religion",           70, ["philosophy", "writing"],                 "Enables Cathedral",                    "medieval"),
    TechDef("republic",          "Republic",           60, ["code_of_laws", "literacy"],              "Government: Republic",                 "medieval"),
    TechDef("steam_engine",      "Steam Engine",      110, ["invention", "physics"],                  "Enables Ironclad, Railroad",           "medieval"),
    TechDef("theory_of_gravity", "Theory of Gravity", 100, ["astronomy", "university"],               "Enables Isaac Newton's College",       "medieval"),
    TechDef("university",        "University",         80, ["philosophy", "mathematics"],             "Enables University building",          "medieval"),

    # ── Renaissance ───────────────────────────────────────────────────────
    TechDef("chemistry",         "Chemistry",         100, ["medicine", "university"],                "Enables Explosives",                   "renaissance"),
    TechDef("communism",         "Communism",         140, ["philosophy", "industrialization"],       "Government: Communism",                "renaissance"),
    TechDef("conscription",      "Conscription",      140, ["republic", "explosives"],               "Enables Rifleman",                     "renaissance"),
    TechDef("corporation",       "Corporation",       160, ["banking", "industrialization"],          "Enables Refining",                     "renaissance"),
    TechDef("electricity",       "Electricity",       150, ["metallurgy", "magnetism"],              "Enables Electronics",                  "renaissance"),
    TechDef("electronics",       "Electronics",       160, ["engineering", "electricity"],            "Enables Hoover Dam, Computers",        "renaissance"),
    TechDef("explosives",        "Explosives",        120, ["gunpowder", "chemistry"],               "Enables Conscription",                 "renaissance"),
    TechDef("industrialization", "Industrialization", 140, ["banking", "railroad"],                   "Enables Factory, Transport",           "renaissance"),
    TechDef("railroad",          "Railroad",          130, ["bridge_building", "steam_engine"],       "Enables Railroad tiles",               "renaissance"),
    TechDef("steel",             "Steel",             160, ["metallurgy", "industrialization"],       "Enables Battleship",                   "renaissance"),

    # ── Industrial ────────────────────────────────────────────────────────
    TechDef("advanced_flight",   "Advanced Flight",   220, ["flight", "electricity"],                "Enables Bomber, Carrier",              "industrial"),
    TechDef("atomic_theory",     "Atomic Theory",     200, ["theory_of_gravity", "physics"],         "Enables Nuclear Fission",              "industrial"),
    TechDef("automobile",        "Automobile",        180, ["combustion", "steel"],                  "Enables Armor",                        "industrial"),
    TechDef("combustion",        "Combustion",        170, ["refining", "explosives"],               "Enables Cruiser, Flight",              "industrial"),
    TechDef("computers",         "Computers",         220, ["electronics", "mathematics"],           "Enables SETI Program, Robotics",       "industrial"),
    TechDef("flight",            "Flight",            190, ["combustion", "physics"],                "Enables Fighter",                      "industrial"),
    TechDef("genetic_engineering","Genetic Engineering",230, ["corporation", "medicine"],            "Enables Cure for Cancer",              "industrial"),
    TechDef("mass_production",   "Mass Production",   220, ["corporation", "automobile"],            "Enables Submarine",                    "industrial"),
    TechDef("nuclear_fission",   "Nuclear Fission",   250, ["mass_production", "atomic_theory"],     "Enables Manhattan Project",            "industrial"),
    TechDef("recycling",         "Recycling",         230, ["mass_production", "democracy"],         "Enables Recycling Center",             "industrial"),
    TechDef("refining",          "Refining",          170, ["corporation", "chemistry"],             "Enables Power Plant",                  "industrial"),
    TechDef("rocketry",          "Rocketry",          240, ["electronics", "advanced_flight"],       "Enables Nuclear",                      "industrial"),

    # ── Modern ────────────────────────────────────────────────────────────
    TechDef("fusion_power",      "Fusion Power",      300, ["nuclear_power", "superconductor"],      "",                                     "modern"),
    TechDef("future_tech",       "Future Tech",       400, ["fusion_power"],                         "",                                     "modern"),
    TechDef("labor_union",       "Labor Union",       240, ["mass_production", "communism"],         "Enables Mech. Infantry",               "modern"),
    TechDef("nuclear_power",     "Nuclear Power",     280, ["electronics", "nuclear_fission"],       "Enables Nuclear Plant",                "modern"),
    TechDef("plastics",          "Plastics",          280, ["refining", "space_flight"],             "Enables SS Component",                 "modern"),
    TechDef("robotics",          "Robotics",          280, ["computers", "plastics"],               "Enables Artillery",                    "modern"),
    TechDef("space_flight",      "Space Flight",      270, ["computers", "rocketry"],               "Enables Apollo Program",               "modern"),
    TechDef("superconductor",    "Superconductor",    300, ["mass_production", "plastics"],          "Enables SDI Defense",                  "modern"),
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
    """Return all techs in a sensible research order (BFS by era)."""
    era_order = ["ancient", "classical", "medieval", "renaissance", "industrial", "modern"]
    result = []
    for era in era_order:
        result.extend(key for key, td in TECH_DEFS.items() if td.era == era)
    return result
