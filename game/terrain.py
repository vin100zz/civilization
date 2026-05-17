from dataclasses import dataclass
from enum import Enum
from typing import Dict


class TerrainType(Enum):
    OCEAN = "ocean"
    COAST = "coast"
    GRASSLAND = "grassland"
    PLAINS = "plains"
    FOREST = "forest"
    HILLS = "hills"
    MOUNTAINS = "mountains"
    DESERT = "desert"
    TUNDRA = "tundra"
    ARCTIC = "arctic"


@dataclass(frozen=True)
class TerrainDef:
    name: str
    movement_cost: int   # moves consumed per tile
    defense_bonus: float  # multiplier applied to defender
    food: int
    production: int
    trade: int
    color: str           # CSS hex color for rendering
    is_passable: bool    # land units can enter
    is_water: bool


TERRAIN_DEFS: Dict[TerrainType, TerrainDef] = {
    TerrainType.OCEAN: TerrainDef(
        name="Ocean", movement_cost=1, defense_bonus=1.0,
        food=1, production=0, trade=2, color="#1a6bb5",
        is_passable=False, is_water=True,
    ),
    TerrainType.COAST: TerrainDef(
        name="Coast", movement_cost=1, defense_bonus=1.0,
        food=1, production=0, trade=2, color="#3388cc",
        is_passable=True, is_water=True,
    ),
    TerrainType.GRASSLAND: TerrainDef(
        name="Grassland", movement_cost=1, defense_bonus=1.0,
        food=2, production=0, trade=1, color="#44aa44",
        is_passable=True, is_water=False,
    ),
    TerrainType.PLAINS: TerrainDef(
        name="Plains", movement_cost=1, defense_bonus=1.0,
        food=1, production=1, trade=1, color="#88cc44",
        is_passable=True, is_water=False,
    ),
    TerrainType.FOREST: TerrainDef(
        name="Forest", movement_cost=2, defense_bonus=1.5,
        food=1, production=1, trade=1, color="#226622",
        is_passable=True, is_water=False,
    ),
    TerrainType.HILLS: TerrainDef(
        name="Hills", movement_cost=2, defense_bonus=2.0,
        food=1, production=1, trade=0, color="#8b6914",
        is_passable=True, is_water=False,
    ),
    TerrainType.MOUNTAINS: TerrainDef(
        name="Mountains", movement_cost=3, defense_bonus=3.0,
        food=0, production=1, trade=0, color="#6b6b6b",
        is_passable=False, is_water=False,
    ),
    TerrainType.DESERT: TerrainDef(
        name="Desert", movement_cost=1, defense_bonus=1.0,
        food=0, production=1, trade=0, color="#ccaa44",
        is_passable=True, is_water=False,
    ),
    TerrainType.TUNDRA: TerrainDef(
        name="Tundra", movement_cost=1, defense_bonus=1.0,
        food=1, production=0, trade=0, color="#7a9aaa",
        is_passable=True, is_water=False,
    ),
    TerrainType.ARCTIC: TerrainDef(
        name="Arctic", movement_cost=2, defense_bonus=1.0,
        food=0, production=0, trade=0, color="#ccdded",
        is_passable=True, is_water=False,
    ),
}
