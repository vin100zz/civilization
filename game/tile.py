from dataclasses import dataclass, field
from enum import Enum
from typing import Optional

from game.terrain import TerrainType


class ResourceType(Enum):
    NONE = "none"
    WHEAT = "wheat"
    CATTLE = "cattle"
    FISH = "fish"
    COAL = "coal"
    IRON = "iron"
    HORSES = "horses"
    GOLD_ORE = "gold_ore"
    OIL = "oil"
    FOREST_GAME = "forest_game"


@dataclass
class Tile:
    x: int
    y: int
    terrain: TerrainType
    resource: ResourceType = ResourceType.NONE
    has_road: bool = False
    has_irrigation: bool = False
    has_mine: bool = False
    has_river: bool = False
    city_id: Optional[str] = None   # id of city on this tile

    def yields(self) -> tuple[int, int, int]:
        """Return (food, production, trade) base yields."""
        from game.terrain import TERRAIN_DEFS
        td = TERRAIN_DEFS[self.terrain]
        food = td.food
        production = td.production
        trade = td.trade

        resource_bonuses = {
            ResourceType.WHEAT:       (2, 0, 1),
            ResourceType.CATTLE:      (2, 1, 0),
            ResourceType.FISH:        (2, 0, 1),
            ResourceType.COAL:        (0, 3, 0),
            ResourceType.IRON:        (0, 3, 0),
            ResourceType.HORSES:      (1, 1, 1),
            ResourceType.GOLD_ORE:    (0, 0, 4),
            ResourceType.OIL:         (0, 2, 2),
            ResourceType.FOREST_GAME: (2, 0, 0),
        }
        if self.resource in resource_bonuses:
            f, p, t = resource_bonuses[self.resource]
            food += f
            production += p
            trade += t

        if self.has_irrigation:
            food += 1
        if self.has_mine:
            production += 1
        if self.has_road:
            trade += 1

        return food, production, trade

    def to_dict(self) -> dict:
        return {
            "x": self.x,
            "y": self.y,
            "terrain": self.terrain.value,
            "resource": self.resource.value,
            "has_road": self.has_road,
            "has_irrigation": self.has_irrigation,
            "has_mine": self.has_mine,
            "has_river": self.has_river,
            "city_id": self.city_id,
        }
