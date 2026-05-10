"""Rule-based AI for each civilization."""
from __future__ import annotations

import random
from collections import deque
from typing import TYPE_CHECKING, List, Optional, Tuple

from game.building import BUILDING_DEFS, get_buildable_buildings
from game.city import City, ProductionOrder
from game.tech import TECH_DEFS, tech_era_order
from game.unit import Unit, UnitAbility, UNIT_DEFS, get_buildable_units
from game.constants import MAP_WIDTH, MAP_HEIGHT

if TYPE_CHECKING:
    from game.civilization import Civilization
    from game.game_state import GameState


class BotAI:
    def __init__(self, civ: "Civilization", state: "GameState"):
        self.civ = civ
        self.state = state

    # ------------------------------------------------------------------
    # Main entry point
    # ------------------------------------------------------------------

    def play_turn(self) -> List[Unit]:
        """Execute one turn for this civ. Returns any new units created."""
        new_units: List[Unit] = []

        self._manage_research()

        for city in list(self.civ.cities.values()):
            self._manage_city_production(city)
            produced = self.state.process_city_turn(city, self.civ)
            if produced:
                new_units.append(produced)

        # Reset moves
        for unit in self.civ.units.values():
            unit.reset_moves()

        for unit in list(self.civ.units.values()):
            self._move_unit(unit)

        # Prevent bankruptcy
        if self.civ.gold < -20:
            self.civ.tax_rate = min(10, self.civ.tax_rate + 1)
            self.civ.science_rate = max(0, self.civ.science_rate - 1)

        return new_units

    # ------------------------------------------------------------------
    # Research
    # ------------------------------------------------------------------

    def _manage_research(self) -> None:
        if self.civ.current_research:
            return
        available = self.civ.available_techs()
        if not available:
            return
        # Follow the era order for a sensible research path
        ordered = [k for k in tech_era_order() if k in available]
        if ordered:
            self.civ.current_research = ordered[0]
        else:
            self.civ.current_research = available[0]

    # ------------------------------------------------------------------
    # City production
    # ------------------------------------------------------------------

    def _manage_city_production(self, city: City) -> None:
        if city.production_order is not None:
            return

        buildable_units = get_buildable_units(self.civ.researched_techs)
        buildable_buildings = get_buildable_buildings(
            self.civ.researched_techs, city.buildings
        )

        # Decide what to build
        order = self._choose_production(city, buildable_units, buildable_buildings)
        city.production_order = order

    def _choose_production(
        self,
        city: City,
        buildable_units: List[str],
        buildable_buildings: List[str],
    ) -> ProductionOrder:
        rng = self.state.rng

        num_cities = len(self.civ.cities)
        num_units = len(self.civ.units)
        num_settlers = sum(
            1 for u in self.civ.units.values() if u.unit_def_key == "settler"
        )
        num_workers = sum(
            1 for u in self.civ.units.values() if u.unit_def_key == "worker"
        )

        # Priority 1: granary if no food building and population small
        if "granary" in buildable_buildings and "granary" not in city.buildings:
            return ProductionOrder("building", "granary")

        # Priority 2: barracks if none
        if "barracks" in buildable_buildings and "barracks" not in city.buildings:
            if num_units > 3:
                return ProductionOrder("building", "barracks")

        # Priority 3: more settlers if we have few cities and enough military
        if num_settlers == 0 and num_cities < 5 and num_units >= num_cities * 2:
            if "settler" in buildable_units:
                return ProductionOrder("unit", "settler")

        # Priority 4: workers
        if num_workers < num_cities and "worker" in buildable_units:
            return ProductionOrder("unit", "worker")

        # Priority 5: military units
        best_military = self._best_military_unit(buildable_units)
        if best_military and (num_units < num_cities * 3 or rng.random() < 0.6):
            return ProductionOrder("unit", best_military)

        # Priority 6: buildings
        priority_buildings = ["library", "marketplace", "temple", "aqueduct",
                              "colosseum", "university", "factory"]
        for bk in priority_buildings:
            if bk in buildable_buildings:
                return ProductionOrder("building", bk)

        # Default: warrior
        return ProductionOrder("unit", "warrior")

    def _best_military_unit(self, buildable: List[str]) -> Optional[str]:
        """Choose the strongest affordable military unit."""
        military = [
            k for k in buildable
            if not UNIT_DEFS[k].abilities  # no special abilities = combat unit
            and not UNIT_DEFS[k].is_naval
        ]
        if not military:
            return None
        return max(military, key=lambda k: UNIT_DEFS[k].attack + UNIT_DEFS[k].defense)

    # ------------------------------------------------------------------
    # Unit actions
    # ------------------------------------------------------------------

    def _move_unit(self, unit: Unit) -> None:
        while unit.moves_left > 0:
            action = self._decide_unit_action(unit)
            if action == "idle":
                break
            moved = self._execute_unit_action(unit, action)
            if not moved:
                break

    def _decide_unit_action(self, unit: Unit) -> str:
        if unit.has_ability(UnitAbility.FOUND_CITY):
            return "settle"
        if unit.has_ability(UnitAbility.IMPROVE_TERRAIN):
            return "improve"
        # All military units always attack — no peace
        return "attack"

    def _execute_unit_action(self, unit: Unit, action: str) -> bool:
        """Execute action. Returns True if the unit moved/acted."""
        rng = self.state.rng

        if action == "settle":
            return self._act_settler(unit)
        elif action == "improve":
            return self._act_worker(unit)
        elif action == "attack":
            return self._act_attacker(unit)
        else:
            return self._act_explorer(unit)

    def _act_settler(self, unit: Unit) -> bool:
        # Found city if location is good; else move to better spot
        tile = self.state.tiles[unit.y][unit.x]
        if self._is_good_city_site(unit.x, unit.y):
            city = self.state._found_city(self.civ, unit.x, unit.y)
            self._remove_unit_from_civ(unit)
            return False  # unit consumed

        # Move toward a good site
        target = self._find_city_site_near(unit.x, unit.y)
        if target:
            return self._step_toward(unit, target[0], target[1])
        return self._random_step(unit)

    def _act_worker(self, unit: Unit) -> bool:
        tile = self.state.tiles[unit.y][unit.x]
        from game.terrain import TerrainType
        # Build road if none
        if not tile.has_road and tile.terrain not in (
            TerrainType.OCEAN, TerrainType.COAST, TerrainType.MOUNTAINS
        ):
            tile.has_road = True
            unit.moves_left = 0
            return True
        return self._random_step(unit)

    def _act_attacker(self, unit: Unit) -> bool:
        # 1. Attack any adjacent enemy unit immediately
        for dx, dy in [(0, 1), (0, -1), (1, 0), (-1, 0)]:
            nx = (unit.x + dx) % MAP_WIDTH
            ny = unit.y + dy
            if not (0 <= ny < MAP_HEIGHT):
                continue
            occupant = self.state._unit_at(nx, ny)
            if occupant and occupant.civ_id != unit.civ_id:
                won = self.state.attack(unit, nx, ny)
                unit.moves_left = 0
                if won and unit.id in self.civ.units:
                    unit.x = nx
                    unit.y = ny
                    self.state.check_city_capture(unit)
                return True

        # 2. Walk into any adjacent undefended enemy city
        for dx, dy in [(0, 0), (0, 1), (0, -1), (1, 0), (-1, 0)]:
            nx = (unit.x + dx) % MAP_WIDTH
            ny = unit.y + dy
            if not (0 <= ny < MAP_HEIGHT):
                continue
            city = self.state._city_at(nx, ny)
            if city and city.civ_id != unit.civ_id:
                if self.state._unit_at(nx, ny) is None:
                    return self._try_move(unit, nx, ny)

        # 3. March toward nearest target (enemy city first, then any unit)
        target = self._find_attack_target(unit)
        if target:
            return self._step_toward(unit, target[0], target[1])

        return self._random_step(unit)

    def _find_attack_target(self, unit: Unit) -> Optional[Tuple[int, int]]:
        """Nearest enemy city (preferred) or nearest enemy unit."""
        best_pos: Optional[Tuple[int, int]] = None
        best_dist = float("inf")

        # Enemy cities are the primary target
        for civ in self.state.civs.values():
            if civ.id == self.civ.id:
                continue
            for city in civ.cities.values():
                d = abs(city.x - unit.x) + abs(city.y - unit.y)
                if d < best_dist:
                    best_dist = d
                    best_pos = (city.x, city.y)

        # Enemy units — only preferred if closer than the nearest city
        for u in self.state._unit_index.values():
            if u.civ_id == self.civ.id:
                continue
            d = abs(u.x - unit.x) + abs(u.y - unit.y)
            if d < best_dist:
                best_dist = d
                best_pos = (u.x, u.y)

        return best_pos

    def _act_explorer(self, unit: Unit) -> bool:
        # Move toward least recently explored areas or just wander
        if unit._goal is None or (unit.x, unit.y) == unit._goal:
            unit._goal = (
                self.state.rng.randint(0, MAP_WIDTH - 1),
                self.state.rng.randint(0, MAP_HEIGHT - 1),
            )
        return self._step_toward(unit, unit._goal[0], unit._goal[1])

    # ------------------------------------------------------------------
    # Movement helpers
    # ------------------------------------------------------------------

    def _step_toward(self, unit: Unit, tx: int, ty: int) -> bool:
        """BFS to find next step toward (tx, ty). Returns True if moved."""
        path = self._bfs(unit.x, unit.y, tx, ty, unit)
        if path and len(path) > 1:
            nx, ny = path[1]
            return self._try_move(unit, nx, ny)
        return self._random_step(unit)

    def _random_step(self, unit: Unit) -> bool:
        directions = [(0, 1), (0, -1), (1, 0), (-1, 0)]
        self.state.rng.shuffle(directions)
        for dx, dy in directions:
            nx = (unit.x + dx) % MAP_WIDTH
            ny = unit.y + dy
            if 0 <= ny < MAP_HEIGHT and self.state.tile_is_passable_for(nx, ny, unit):
                return self._try_move(unit, nx, ny)
        unit.moves_left = 0
        return False

    def _try_move(self, unit: Unit, nx: int, ny: int) -> bool:
        from game.terrain import TERRAIN_DEFS
        if not self.state.tile_is_passable_for(nx, ny, unit):
            return False

        tile = self.state.tiles[ny][nx]
        # If enemy unit is there, attack instead of move
        occupant = self.state._unit_at(nx, ny)
        if occupant and occupant.civ_id != unit.civ_id:
            if unit.unit_def.attack > 0:
                self.state.attack(unit, nx, ny)
                unit.moves_left = 0
                return True
            return False

        td = TERRAIN_DEFS[tile.terrain]
        cost = 1 if tile.has_road else td.movement_cost
        if unit.moves_left > 0:
            unit.x = nx
            unit.y = ny
            unit.moves_left = max(0, unit.moves_left - cost)
            self.state.check_city_capture(unit)
            return True

        return False

    def _bfs(
        self, sx: int, sy: int, tx: int, ty: int, unit: Unit
    ) -> Optional[List[Tuple[int, int]]]:
        """BFS shortest path. Returns list of (x,y) from start to target, or None."""
        if sx == tx and sy == ty:
            return [(sx, sy)]

        visited = {(sx, sy): None}
        queue = deque([(sx, sy)])
        found = False

        while queue and not found:
            cx, cy = queue.popleft()
            for dx, dy in [(0, 1), (0, -1), (1, 0), (-1, 0)]:
                nx = (cx + dx) % MAP_WIDTH
                ny = cy + dy
                if not (0 <= ny < MAP_HEIGHT):
                    continue
                if (nx, ny) in visited:
                    continue
                if not self.state.tile_is_passable_for(nx, ny, unit):
                    continue
                visited[(nx, ny)] = (cx, cy)
                if nx == tx and ny == ty:
                    found = True
                    break
                queue.append((nx, ny))

        if not found:
            return None

        # Reconstruct path
        path = []
        cur = (tx, ty)
        while cur is not None:
            path.append(cur)
            cur = visited[cur]
        path.reverse()
        return path

    # ------------------------------------------------------------------
    # City site evaluation
    # ------------------------------------------------------------------

    def _is_good_city_site(self, x: int, y: int) -> bool:
        from game.terrain import TerrainType
        tile = self.state.tiles[y][x]
        if tile.terrain in (
            TerrainType.OCEAN, TerrainType.COAST, TerrainType.MOUNTAINS, TerrainType.ARCTIC
        ):
            return False
        if tile.city_id:
            return False
        # Must be far from other cities
        for civ in self.state.civs.values():
            for city in civ.cities.values():
                if abs(city.x - x) + abs(city.y - y) < 4:
                    return False
        return True

    def _find_city_site_near(
        self, ox: int, oy: int, radius: int = 8
    ) -> Optional[Tuple[int, int]]:
        best_score = -1
        best_pos = None
        for dy in range(-radius, radius + 1):
            for dx in range(-radius, radius + 1):
                tx = (ox + dx) % MAP_WIDTH
                ty = oy + dy
                if not (0 <= ty < MAP_HEIGHT):
                    continue
                if not self._is_good_city_site(tx, ty):
                    continue
                score = self._city_site_score(tx, ty)
                if score > best_score:
                    best_score = score
                    best_pos = (tx, ty)
        return best_pos

    def _city_site_score(self, x: int, y: int) -> int:
        from game.terrain import TerrainType
        score = 0
        for dy in range(-2, 3):
            for dx in range(-2, 3):
                tx = (x + dx) % MAP_WIDTH
                ty = y + dy
                if not (0 <= ty < MAP_HEIGHT):
                    continue
                tile = self.state.tiles[ty][tx]
                f, p, t = tile.yields()
                score += f * 2 + p + t
                if tile.terrain == TerrainType.COAST:
                    score += 2  # bonus for coastal trade
        return score

    # ------------------------------------------------------------------
    # Utility
    # ------------------------------------------------------------------

    def _remove_unit_from_civ(self, unit: Unit) -> None:
        self.civ.units.pop(unit.id, None)
        self.state._unit_index.pop(unit.id, None)
