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
        "Ocean", 1, 1.0, 1, 0, 2, "#1a6bb5", False, True
    ),
    TerrainType.COAST: TerrainDef(
        "Coast", 1, 1.0, 1, 0, 2, "#3388cc", True, True
    ),
    TerrainType.GRASSLAND: TerrainDef(
        "Grassland", 1, 1.0, 2, 1, 0, "#44aa44", True, False
    ),
    TerrainType.PLAINS: TerrainDef(
        "Plains", 1, 1.0, 1, 1, 1, "#88cc44", True, False
    ),
    TerrainType.FOREST: TerrainDef(
        "Forest", 2, 1.5, 1, 2, 0, "#226622", True, False
    ),
    TerrainType.HILLS: TerrainDef(
        "Hills", 2, 2.0, 1, 2, 0, "#8b6914", True, False
    ),
    TerrainType.MOUNTAINS: TerrainDef(
        "Mountains", 3, 3.0, 0, 1, 0, "#6b6b6b", False, False
    ),
    TerrainType.DESERT: TerrainDef(
        "Desert", 1, 1.0, 0, 1, 0, "#ccaa44", True, False
    ),
    TerrainType.TUNDRA: TerrainDef(
        "Tundra", 1, 1.0, 1, 0, 0, "#7a9aaa", True, False
    ),
    TerrainType.ARCTIC: TerrainDef(
        "Arctic", 2, 1.0, 0, 0, 0, "#ccdded", True, False
    ),
}
