from __future__ import annotations

import random
import uuid
from typing import Dict, List, Optional, Tuple

from game.city import City, ProductionOrder
from game.civilization import Civilization
from game.constants import (
    CIV_DATA,
    MAP_HEIGHT,
    MAP_WIDTH,
    NUM_CIVS,
    START_YEAR,
    YEAR_INCREMENTS,
)
from game.map_generator import generate_map, find_valid_start_positions
from game.tech import TECH_DEFS
from game.terrain import TerrainType
from game.tile import Tile
from game.unit import Unit, UnitAbility, UNIT_DEFS


class GameEvent:
    def __init__(self, turn: int, civ_name: str, message: str):
        self.turn = turn
        self.civ_name = civ_name
        self.message = message

    def to_dict(self) -> dict:
        return {"turn": self.turn, "civ": self.civ_name, "message": self.message}


class GameState:
    def __init__(self, seed: int = 42):
        self.game_id: str = uuid.uuid4().hex[:10]   # unique ID per game instance
        self.seed = seed
        self.rng = random.Random(seed)
        self.turn: int = 0
        self.year: int = START_YEAR
        self.tiles: List[List[Tile]] = generate_map(seed)
        self.civs: Dict[str, Civilization] = {}
        self._unit_index: Dict[str, Unit] = {}   # id -> Unit (cross-civ lookup)
        self._city_index: Dict[str, City] = {}   # id -> City
        self.events: List[GameEvent] = []        # events from last turn
        self.is_over: bool = False

        self._init_civs()

    # ------------------------------------------------------------------
    # Initialization
    # ------------------------------------------------------------------

    def _init_civs(self) -> None:
        civ_data = self.rng.sample(CIV_DATA, NUM_CIVS)
        start_positions = find_valid_start_positions(
            self.tiles, NUM_CIVS, self.rng
        )

        for i, (data, (sx, sy)) in enumerate(zip(civ_data, start_positions)):
            civ = Civilization(data["name"], data["color"], data["city_names"])
            self.civs[civ.id] = civ

            # Found starting city
            city = self._found_city(civ, sx, sy)

            # Starting units: 1 settler + 1 warrior
            warrior = Unit("warrior", civ.id, sx, sy)
            civ.units[warrior.id] = warrior
            self._unit_index[warrior.id] = warrior

            settler = Unit("settler", civ.id,
                           (sx + 1) % MAP_WIDTH, sy)
            civ.units[settler.id] = settler
            self._unit_index[settler.id] = settler

    # ------------------------------------------------------------------
    # City founding
    # ------------------------------------------------------------------

    def _found_city(self, civ: Civilization, x: int, y: int) -> City:
        city = City(civ.next_city_name(), civ.id, x, y)
        civ.cities[city.id] = city
        self._city_index[city.id] = city
        self.tiles[y][x].city_id = city.id
        self._allocate_worked_tiles()   # re-allocate all cities after founding
        city.production_order = ProductionOrder("unit", "warrior")
        return city

    # ------------------------------------------------------------------
    # Turn advancement
    # ------------------------------------------------------------------

    def advance_turn(self) -> List[GameEvent]:
        from ai.bot import BotAI

        self.events = []
        self.turn += 1
        self.year = self._compute_year()

        # Allocate tiles exclusively before any city processing
        self._allocate_worked_tiles()

        for civ in list(self.civs.values()):
            if not civ.is_alive:
                continue
            bot = BotAI(civ, self)
            new_units = bot.play_turn()
            for u in new_units:
                self._unit_index[u.id] = u

        self._check_game_over()
        return self.events

    # ------------------------------------------------------------------
    # Tile allocation
    # ------------------------------------------------------------------

    def _allocate_worked_tiles(self) -> None:
        """Assign each workable tile to at most one city — the closest one within
        Chebyshev radius 2. Ties broken by city id for determinism.
        Each city then works its best tiles up to its population count."""
        from game.terrain import TERRAIN_DEFS

        all_cities = [
            city for civ in self.civs.values() for city in civ.cities.values()
        ]

        for city in all_cities:
            city.worked_tiles = []

        if not all_cities:
            return

        # City-centre tiles are handled directly in compute_yields — exclude them
        city_centers = {(city.x, city.y) for city in all_cities}

        # Accumulate candidate tiles per city
        city_candidates: Dict[str, list] = {city.id: [] for city in all_cities}

        for y in range(MAP_HEIGHT):
            for x in range(MAP_WIDTH):
                if (x, y) in city_centers:
                    continue
                tile = self.tiles[y][x]
                td = TERRAIN_DEFS[tile.terrain]
                if not td.is_passable and not td.is_water:
                    continue   # mountains etc. can't be worked

                best_city = None
                best_ch = 3  # sentinel > radius 2

                for city in all_cities:
                    dx = min(abs(city.x - x), MAP_WIDTH - abs(city.x - x))
                    dy = abs(city.y - y)
                    ch = max(dx, dy)
                    if ch > 2:
                        continue
                    # Prefer smaller distance; break ties by id (deterministic)
                    if ch < best_ch or (
                        ch == best_ch
                        and best_city is not None
                        and city.id < best_city.id
                    ):
                        best_ch = ch
                        best_city = city

                if best_city is not None:
                    f, p, t = tile.yields()
                    score = f * 2 + p + t
                    city_candidates[best_city.id].append((score, x, y))

        city_map = {city.id: city for city in all_cities}
        for cid, candidates in city_candidates.items():
            city = city_map[cid]
            candidates.sort(reverse=True)
            city.worked_tiles = [
                (x, y) for _, x, y in candidates[: city.population]
            ]

    # ------------------------------------------------------------------
    # Economy helpers called by bot
    # ------------------------------------------------------------------

    def process_city_turn(self, city: City, civ: Civilization) -> Optional[Unit]:
        """Advance city economy. Returns a new Unit if production completed."""
        food, prod, gold, science = city.compute_yields(self.tiles)

        # Unit upkeep: 1 production per unit homed to this city
        unit_upkeep = sum(
            1 for u in self._unit_index.values() if u.home_city_id == city.id
        )
        city.unit_upkeep = unit_upkeep
        city.food_per_turn = food - city.population * 2  # net: gross minus 2 per pop
        city.production_per_turn = max(0, prod - unit_upkeep)

        # Food
        city.food_stored += food - city.population * 2  # 2 food consumed per pop
        if city.food_stored >= city.food_needed_to_grow():
            city.population += 1
            city.food_stored = 0
            self._add_event(civ.name, f"{city.name} grew to size {city.population}!")

        # Gold and science
        civ.gold += gold - city.upkeep_per_turn()
        if civ.current_research:
            civ.science_stored += science
            if civ.science_stored >= TECH_DEFS[civ.current_research].cost:
                self._complete_research(civ)

        # Production (net of unit upkeep)
        produced_unit: Optional[Unit] = None
        if city.production_order:
            city.production_stored += city.production_per_turn
            cost = city.production_cost()
            if city.production_stored >= cost:
                city.production_stored -= cost
                produced_unit = self._complete_production(city, civ)

        return produced_unit

    def _complete_research(self, civ: Civilization) -> None:
        tech_key = civ.current_research
        civ.researched_techs.add(tech_key)
        civ.science_stored = 0
        civ.current_research = None
        self._add_event(
            civ.name,
            f"{civ.name} discovered {TECH_DEFS[tech_key].name}!"
        )

    def _complete_production(
        self, city: City, civ: Civilization
    ) -> Optional[Unit]:
        order = city.production_order
        if order.item_type == "building":
            city.buildings.add(order.item_key)
            bname = order.item_key.replace("_", " ").title()
            self._add_event(civ.name, f"{city.name} built a {bname}")
            city.production_order = None
            return None
        else:
            veteran = city.has_barracks()
            unit = Unit(order.item_key, civ.id, city.x, city.y, veteran)
            unit.home_city_id = city.id
            civ.units[unit.id] = unit
            uname = unit.unit_def.name
            self._add_event(civ.name, f"{city.name} produced a {uname}")
            city.production_order = None
            return unit

    # ------------------------------------------------------------------
    # Combat
    # ------------------------------------------------------------------

    def attack(self, attacker: Unit, target_x: int, target_y: int) -> bool:
        """Resolve combat. Returns True if attacker wins."""
        defender = self._unit_at(target_x, target_y)
        if defender is None:
            return True

        att_civ = self.civs[attacker.civ_id]
        def_civ = self.civs[defender.civ_id]

        att_str = attacker.unit_def.attack * (1.5 if attacker.veteran else 1.0)
        def_str = defender.unit_def.defense

        # Terrain defense bonus
        tile = self.tiles[target_y][target_x]
        from game.terrain import TERRAIN_DEFS
        def_str *= TERRAIN_DEFS[tile.terrain].defense_bonus

        total = att_str + def_str
        if total == 0:
            return False
        win_prob = att_str / total

        if self.rng.random() < win_prob:
            self._remove_unit(defender)
            self._add_event(att_civ.name,
                f"{att_civ.name}'s {attacker.unit_def.name} defeated "
                f"{def_civ.name}'s {defender.unit_def.name}!")
            return True
        else:
            self._remove_unit(attacker)
            self._add_event(def_civ.name,
                f"{def_civ.name}'s {defender.unit_def.name} repelled "
                f"{att_civ.name}'s {attacker.unit_def.name}!")
            return False

    def _remove_unit(self, unit: Unit) -> None:
        civ = self.civs.get(unit.civ_id)
        if civ:
            civ.units.pop(unit.id, None)
        self._unit_index.pop(unit.id, None)

    # ------------------------------------------------------------------
    # City capture
    # ------------------------------------------------------------------

    def capture_city(self, attacker: Unit, city: City) -> None:
        """Transfer *city* to the attacker's civilisation."""
        old_civ = self.civs.get(city.civ_id)
        new_civ = self.civs.get(attacker.civ_id)

        if old_civ:
            old_civ.cities.pop(city.id, None)
            if not old_civ.cities:
                old_civ.is_alive = False
                self._add_event(old_civ.name,
                                f"{old_civ.name} has been eliminated!")

        if new_civ:
            city.civ_id = new_civ.id
            new_civ.cities[city.id] = city
            self._add_event(new_civ.name,
                            f"{new_civ.name} captured {city.name}!")

    def check_city_capture(self, unit: Unit) -> None:
        """If *unit* is standing on an enemy city tile, capture it."""
        city = self._city_at(unit.x, unit.y)
        if city and city.civ_id != unit.civ_id:
            self.capture_city(unit, city)

    # ------------------------------------------------------------------
    # Queries
    # ------------------------------------------------------------------

    def _unit_at(self, x: int, y: int) -> Optional[Unit]:
        for u in self._unit_index.values():
            if u.x == x and u.y == y:
                return u
        return None

    def _city_at(self, x: int, y: int) -> Optional[City]:
        tid = self.tiles[y][x].city_id
        return self._city_index.get(tid)

    def tile_is_passable_for(self, x: int, y: int, unit: Unit) -> bool:
        from game.terrain import TERRAIN_DEFS
        tile = self.tiles[y % MAP_HEIGHT][x % MAP_WIDTH]
        td = TERRAIN_DEFS[tile.terrain]
        if unit.unit_def.is_naval:
            return td.is_water
        return td.is_passable

    def neighboring_enemy_unit(self, unit: Unit, radius: int = 3) -> Optional[Unit]:
        for u in self._unit_index.values():
            if u.civ_id == unit.civ_id:
                continue
            if abs(u.x - unit.x) + abs(u.y - unit.y) <= radius:
                return u
        return None

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _compute_year(self) -> int:
        year = START_YEAR
        for turn_num in range(self.turn):
            increment = 50
            for threshold, inc in YEAR_INCREMENTS:
                if year >= threshold:
                    increment = inc
            year += increment
        return year

    def year_string(self) -> str:
        y = self.year
        if y < 0:
            return f"{-y} BC"
        return f"{y} AD"

    def total_population(self) -> int:
        return sum(
            sum(c.population for c in civ.cities.values())
            for civ in self.civs.values()
        )

    def _add_event(self, civ_name: str, message: str) -> None:
        self.events.append(GameEvent(self.turn, civ_name, message))

    def _check_game_over(self) -> None:
        alive = [c for c in self.civs.values() if c.is_alive and c.cities]
        if len(alive) <= 1:
            self.is_over = True
            if alive:
                self._add_event(alive[0].name, f"{alive[0].name} has won the game!")

    # ------------------------------------------------------------------
    # Serialization
    # ------------------------------------------------------------------

    def to_dict(self) -> dict:
        # Flatten tiles
        terrain_grid = [
            [self.tiles[y][x].terrain.value for x in range(MAP_WIDTH)]
            for y in range(MAP_HEIGHT)
        ]
        resource_grid = [
            [self.tiles[y][x].resource.value for x in range(MAP_WIDTH)]
            for y in range(MAP_HEIGHT)
        ]
        has_road_grid = [
            [self.tiles[y][x].has_road for x in range(MAP_WIDTH)]
            for y in range(MAP_HEIGHT)
        ]
        irrigation_grid = [
            [self.tiles[y][x].has_irrigation for x in range(MAP_WIDTH)]
            for y in range(MAP_HEIGHT)
        ]
        mine_grid = [
            [self.tiles[y][x].has_mine for x in range(MAP_WIDTH)]
            for y in range(MAP_HEIGHT)
        ]
        tile_yields_grid = [
            [list(self.tiles[y][x].yields()) for x in range(MAP_WIDTH)]
            for y in range(MAP_HEIGHT)
        ]

        cities = [
            city.to_dict()
            for civ in self.civs.values()
            for city in civ.cities.values()
        ]
        units = [
            unit.to_dict()
            for civ in self.civs.values()
            for unit in civ.units.values()
        ]

        return {
            "game_id": self.game_id,
            "turn": self.turn,
            "year": self.year_string(),
            "map_width": MAP_WIDTH,
            "map_height": MAP_HEIGHT,
            "terrain": terrain_grid,
            "resources": resource_grid,
            "roads": has_road_grid,
            "irrigation": irrigation_grid,
            "mines": mine_grid,
            "tile_yields": tile_yields_grid,
            "cities": cities,
            "units": units,
            "civs": [c.to_dict() for c in self.civs.values()],
            "events": [e.to_dict() for e in self.events[-20:]],
            "is_over": self.is_over,
        }
