from __future__ import annotations

from typing import Dict, List, Optional, Set
import uuid

from game.city import City
from game.tech import TECH_DEFS, get_available_techs
from game.unit import Unit


class Civilization:
    def __init__(self, name: str, color: str, city_names: List[str]):
        self.id: str = str(uuid.uuid4())[:8]
        self.name = name
        self.color = color
        self._city_name_pool: List[str] = list(city_names)
        self._city_name_index: int = 0

        self.cities: Dict[str, City] = {}
        self.units: Dict[str, Unit] = {}

        self.gold: int = 50
        self.science_stored: int = 0
        self.researched_techs: Set[str] = set()
        self.current_research: Optional[str] = None

        # Rates (0-10, must sum to 10)
        self.tax_rate: int = 5
        self.science_rate: int = 5
        self.luxury_rate: int = 0

        self.is_alive: bool = True

    # ------------------------------------------------------------------
    # Naming
    # ------------------------------------------------------------------

    def next_city_name(self) -> str:
        name = self._city_name_pool[self._city_name_index % len(self._city_name_pool)]
        self._city_name_index += 1
        return name

    # ------------------------------------------------------------------
    # Economy
    # ------------------------------------------------------------------

    def total_upkeep(self) -> int:
        unit_upkeep = max(0, len(self.units) - len(self.cities))  # free unit per city
        building_upkeep = sum(c.upkeep_per_turn() for c in self.cities.values())
        return unit_upkeep + building_upkeep

    def net_gold_per_turn(self, gold_income: int) -> int:
        return gold_income - self.total_upkeep()

    # ------------------------------------------------------------------
    # Science
    # ------------------------------------------------------------------

    def has_tech(self, key: str) -> bool:
        return key in self.researched_techs

    def available_techs(self) -> List[str]:
        return get_available_techs(self.researched_techs)

    def science_cost_of_current(self) -> int:
        if self.current_research is None:
            return 0
        return TECH_DEFS[self.current_research].cost

    # ------------------------------------------------------------------
    # Military
    # ------------------------------------------------------------------

    def military_power(self) -> int:
        return sum(u.unit_def.attack + u.unit_def.defense for u in self.units.values())

    # ------------------------------------------------------------------
    # Serialization
    # ------------------------------------------------------------------

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "name": self.name,
            "color": self.color,
            "gold": self.gold,
            "science_stored": self.science_stored,
            "researched_techs": list(self.researched_techs),
            "current_research": self.current_research,
            "science_needed": self.science_cost_of_current(),
            "tax_rate": self.tax_rate,
            "science_rate": self.science_rate,
            "luxury_rate": self.luxury_rate,
            "num_cities": len(self.cities),
            "num_units": len(self.units),
            "is_alive": self.is_alive,
        }
