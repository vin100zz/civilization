from __future__ import annotations

from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set, TYPE_CHECKING
import uuid

from game.building import BUILDING_DEFS, BuildingDef
from game.unit import UNIT_DEFS

if TYPE_CHECKING:
    from game.tile import Tile


@dataclass
class ProductionOrder:
    item_type: str   # "unit" or "building"
    item_key: str


class City:
    def __init__(self, name: str, civ_id: str, x: int, y: int):
        self.id: str = str(uuid.uuid4())[:8]
        self.name = name
        self.civ_id = civ_id
        self.x = x
        self.y = y
        self.population: int = 1
        self.food_stored: int = 0
        self.production_stored: int = 0
        self.buildings: Set[str] = set()
        self.production_order: Optional[ProductionOrder] = None
        self.worked_tiles: List[tuple[int, int]] = []  # tiles this city works
        self.food_per_turn: int = 0        # cached after last turn (net)
        self.food_gross: int = 0           # gross food produced (before consumption)
        self.food_from_tiles: int = 0      # food from city center + worked tiles
        self.food_from_buildings: int = 0  # food from building bonuses
        self.food_consumed_citizens: int = 0
        self.food_consumed_workers: int = 0
        self.production_per_turn: int = 0  # cached after last turn (net)
        self.prod_gross: int = 0           # gross production (before upkeep)
        self.prod_from_tiles: int = 0      # production from city center + worked tiles
        self.prod_from_buildings: int = 0  # production from building bonuses
        self.unit_upkeep: int = 0          # production drained by maintained units

    # ------------------------------------------------------------------
    # Yield computation
    # ------------------------------------------------------------------

    def compute_yields(self, tiles: List[List["Tile"]]) -> tuple[int, int, int]:
        """Return total (food, production, trade) from worked tiles."""
        total_food = total_prod = total_trade = 0
        # City center: terrain yield + bonus +1 food +1 production
        map_h = len(tiles)
        map_w = len(tiles[0])
        cf, cp, ct = tiles[self.y % map_h][self.x % map_w].yields()
        total_food += cf + 1
        total_prod += cp + 1
        total_trade += ct

        for tx, ty in self.worked_tiles:
            f, p, t = tiles[ty][tx].yields()
            total_food += f
            total_prod += p
            total_trade += t

        # Building multipliers
        science_mult = 1.0
        gold_mult = 1.0
        for bk in self.buildings:
            bd = BUILDING_DEFS[bk]
            total_food += bd.food_bonus
            total_prod += bd.production_bonus
            science_mult *= bd.science_mult
            gold_mult *= bd.gold_mult

        # Trade split: half gold, half science (simplified)
        gold = int(total_trade * gold_mult / 2)
        science = int(total_trade * science_mult / 2)

        return int(total_food), int(total_prod), gold, science

    def food_needed_to_grow(self) -> int:
        return 20 + self.population * 10

    def max_size_without_aqueduct(self) -> int:
        return 8

    def max_population(self) -> int:
        base = self.max_size_without_aqueduct()
        for bk in self.buildings:
            base += BUILDING_DEFS[bk].max_pop_increase
        return base

    # ------------------------------------------------------------------
    # Production
    # ------------------------------------------------------------------

    def production_cost(self) -> int:
        if self.production_order is None:
            return 0
        if self.production_order.item_type == "unit":
            return UNIT_DEFS[self.production_order.item_key].cost
        else:
            return BUILDING_DEFS[self.production_order.item_key].cost

    def upkeep_per_turn(self) -> int:
        return sum(BUILDING_DEFS[bk].upkeep for bk in self.buildings)

    def defense_value(self) -> int:
        base = self.population
        for bk in self.buildings:
            base += BUILDING_DEFS[bk].defense_bonus
        return base

    def has_barracks(self) -> bool:
        return "barracks" in self.buildings

    # ------------------------------------------------------------------
    # Tile working
    # ------------------------------------------------------------------

    def is_coastal(self, tiles: List[List["Tile"]]) -> bool:
        """True if any tile adjacent (8-connected) to the city is water."""
        from game.terrain import TERRAIN_DEFS
        map_h = len(tiles)
        map_w = len(tiles[0])
        for dy in range(-1, 2):
            for dx in range(-1, 2):
                if dx == 0 and dy == 0:
                    continue
                tx = (self.x + dx) % map_w
                ty = self.y + dy
                if not (0 <= ty < map_h):
                    continue
                if TERRAIN_DEFS[tiles[ty][tx].terrain].is_water:
                    return True
        return False

    def select_worked_tiles(self, tiles: List[List["Tile"]]) -> None:
        """Pick the best tiles around the city to work (up to population count)."""
        from game.terrain import TERRAIN_DEFS, TerrainType
        from game.tile import Tile as TileClass

        map_h = len(tiles)
        map_w = len(tiles[0])
        candidates = []

        for dy in range(-2, 3):
            for dx in range(-2, 3):
                if dx == 0 and dy == 0:
                    continue
                tx = (self.x + dx) % map_w
                ty = self.y + dy
                if not (0 <= ty < map_h):
                    continue
                tile = tiles[ty][tx]
                td = TERRAIN_DEFS[tile.terrain]
                if not td.is_passable and not td.is_water:
                    continue
                f, p, t = tile.yields()
                score = f * 2 + p + t
                candidates.append((score, tx, ty))

        candidates.sort(reverse=True)
        self.worked_tiles = [(tx, ty) for _, tx, ty in candidates[: self.population]]

    # ------------------------------------------------------------------
    # Serialization
    # ------------------------------------------------------------------

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "civ_id": self.civ_id,
            "x": self.x,
            "y": self.y,
            "population": self.population,
            "food_stored": self.food_stored,
            "food_needed": self.food_needed_to_grow(),
            "food_per_turn": self.food_per_turn,
            "food_gross": self.food_gross,
            "food_from_tiles": self.food_from_tiles,
            "food_from_buildings": self.food_from_buildings,
            "food_consumed_citizens": self.food_consumed_citizens,
            "food_consumed_workers": self.food_consumed_workers,
            "production_stored": self.production_stored,
            "production_per_turn": self.production_per_turn,
            "prod_gross": self.prod_gross,
            "prod_from_tiles": self.prod_from_tiles,
            "prod_from_buildings": self.prod_from_buildings,
            "unit_upkeep": self.unit_upkeep,
            "buildings": list(self.buildings),
            "worked_tiles": self.worked_tiles,
            "production_order": (
                {
                    "type": self.production_order.item_type,
                    "key": self.production_order.item_key,
                    "cost": self.production_cost(),
                    "progress": self.production_stored,
                }
                if self.production_order
                else None
            ),
        }
