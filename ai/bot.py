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

        # Assign garrison defenders AFTER production so new units are included
        self._garrison_map: dict = self._compute_garrison_assignments()

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

        coastal = city.is_coastal(self.state.tiles)
        buildable_units = get_buildable_units(self.civ.researched_techs, coastal=coastal)
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

        num_cities   = len(self.civ.cities)
        num_units    = len(self.civ.units)
        num_settlers = sum(1 for u in self.civ.units.values() if u.unit_def_key == "settler")
        num_workers  = sum(1 for u in self.civ.units.values() if u.unit_def_key == "worker")

        # Count military units by role
        num_defenders = sum(
            1 for u in self.civ.units.values()
            if not u.has_ability(UnitAbility.FOUND_CITY)
            and not u.has_ability(UnitAbility.IMPROVE_TERRAIN)
            and self._is_defender_unit(u)
        )
        num_attackers = sum(
            1 for u in self.civ.units.values()
            if not u.has_ability(UnitAbility.FOUND_CITY)
            and not u.has_ability(UnitAbility.IMPROVE_TERRAIN)
            and not self._is_defender_unit(u)
        )

        coastal = city.is_coastal(self.state.tiles)
        best_defender = self._best_defender_unit(buildable_units, naval=coastal)
        best_attacker = self._best_military_unit(buildable_units, naval=coastal)

        # Aim for at least 2 defender-typed units per city; fill attackers after that.
        # Cap attackers at 4 per city to prevent runaway accumulation when terrain
        # blocks their path to enemy cities.
        need_defender = num_defenders < num_cities * 2
        attacker_cap_reached = num_attackers >= num_cities * 4
        best_military = (best_defender if (need_defender and best_defender)
                         else (best_attacker or best_defender))

        # Priority 0: city has no garrison — always build a defender first
        city_defended = any(
            u.x == city.x and u.y == city.y
            and not u.has_ability(UnitAbility.FOUND_CITY)
            and not u.has_ability(UnitAbility.IMPROVE_TERRAIN)
            for u in self.civ.units.values()
        )
        if not city_defended:
            unit_to_build = best_defender or best_attacker
            if unit_to_build:
                return ProductionOrder("unit", unit_to_build)

        # Priority 1: granary
        if "granary" in buildable_buildings and "granary" not in city.buildings:
            return ProductionOrder("building", "granary")

        # Priority 2: barracks
        if "barracks" in buildable_buildings and "barracks" not in city.buildings:
            if num_units > 3:
                return ProductionOrder("building", "barracks")

        # Priority 3: expand — send a settler as long as we have basic defence
        if num_settlers == 0 and num_units > num_cities:
            if "settler" in buildable_units:
                return ProductionOrder("unit", "settler")

        # Priority 4: workers
        if num_workers < num_cities and "worker" in buildable_units:
            return ProductionOrder("unit", "worker")

        # Priority 5: military — mix defenders and attackers based on army composition
        # Don't build more attackers if we're already over the cap (they would
        # just pile up if terrain blocks their path).
        if best_military and not attacker_cap_reached and (num_units < num_cities * 3 or rng.random() < 0.6):
            return ProductionOrder("unit", best_military)

        # Priority 6: buildings
        for bk in ["library", "marketplace", "temple", "aqueduct",
                   "colosseum", "university", "factory"]:
            if bk in buildable_buildings:
                return ProductionOrder("building", bk)

        return ProductionOrder("unit", "militia")

    def _best_military_unit(self, buildable: List[str], naval: bool = False) -> Optional[str]:
        """Choose the strongest attacker-typed military unit (highest attack+defense).
        If *naval* is True, prefer naval units; otherwise prefer land units."""
        candidates = [
            k for k in buildable
            if not UNIT_DEFS[k].abilities  # no special abilities = combat unit
            and UNIT_DEFS[k].is_naval == naval
        ]
        if not candidates:
            # Fall back to the other category
            candidates = [
                k for k in buildable
                if not UNIT_DEFS[k].abilities
            ]
        if not candidates:
            return None
        return max(candidates, key=lambda k: UNIT_DEFS[k].attack + UNIT_DEFS[k].defense)

    def _best_defender_unit(self, buildable: List[str], naval: bool = False) -> Optional[str]:
        """Choose the best defender-typed unit (defense ≥ attack, ranked by defense).
        Falls back to any military unit if no pure defenders are buildable."""
        candidates = [
            k for k in buildable
            if not UNIT_DEFS[k].abilities
            and UNIT_DEFS[k].is_naval == naval
            and UNIT_DEFS[k].defense >= UNIT_DEFS[k].attack
        ]
        if not candidates:
            # Fall back: any land/naval military unit ranked by defense
            candidates = [
                k for k in buildable
                if not UNIT_DEFS[k].abilities
                and UNIT_DEFS[k].is_naval == naval
            ]
        if not candidates:
            candidates = [k for k in buildable if not UNIT_DEFS[k].abilities]
        if not candidates:
            return None
        return max(candidates, key=lambda k: UNIT_DEFS[k].defense)

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
        # Land unit currently at sea: keep moving, don't fight
        if not unit.unit_def.is_naval:
            from game.terrain import TERRAIN_DEFS
            if TERRAIN_DEFS[self.state.tiles[unit.y][unit.x].terrain].is_water:
                return "transit"
        if unit.id in self._garrison_map:
            return "garrison"
        return "attack"

    def _execute_unit_action(self, unit: Unit, action: str) -> bool:
        """Execute action. Returns True if the unit moved/acted."""
        if action == "settle":
            return self._act_settler(unit)
        elif action == "improve":
            return self._act_worker(unit)
        elif action == "garrison":
            return self._act_garrison(unit)
        elif action == "transit":
            return self._act_transit(unit)
        elif action == "attack":
            return self._act_attacker(unit)
        else:
            return self._act_explorer(unit)

    def _act_garrison(self, unit: Unit) -> bool:
        """Hold position in/near assigned city; counter-attack adjacent enemies."""
        city = self._garrison_map.get(unit.id)
        if city is None:
            unit.moves_left = 0
            return False

        # Counter-attack any adjacent enemy before doing anything else
        from game.terrain import TERRAIN_DEFS
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
                    if self.state.tile_is_passable_for(nx, ny, unit):
                        unit.x = nx
                        unit.y = ny
                    self.state.check_city_capture(unit)
                return True

        # Hold if already at or adjacent to the assigned city
        dist = abs(unit.x - city.x) + abs(unit.y - city.y)
        if dist <= 1:
            unit.moves_left = 0
            return False

        # Otherwise move toward the city
        return self._step_toward(unit, city.x, city.y)

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
        from game.terrain import TerrainType
        NO_ROAD   = (TerrainType.OCEAN, TerrainType.COAST, TerrainType.MOUNTAINS)
        IRRIGABLE = (TerrainType.GRASSLAND, TerrainType.PLAINS)
        MINEABLE  = (TerrainType.HILLS, TerrainType.MOUNTAINS)
        TURNS     = {"road": 3, "irrigation": 4, "mine": 4}

        if self._is_in_civ_territory(unit.x, unit.y):
            tile = self.state.tiles[unit.y][unit.x]

            # Decide what to build on this tile (road first, then terrain improvement)
            task: Optional[str] = None
            if tile.terrain not in NO_ROAD and not tile.has_road:
                task = "road"
            elif tile.terrain in IRRIGABLE and not tile.has_irrigation:
                task = "irrigation"
            elif tile.terrain in MINEABLE and not tile.has_mine:
                task = "mine"

            if task:
                # Continue progress if still on the same tile with the same task
                if (unit.improve_x == unit.x and unit.improve_y == unit.y
                        and unit.improve_type == task):
                    unit.improve_progress += 1
                else:
                    unit.improve_progress = 1
                    unit.improve_x = unit.x
                    unit.improve_y = unit.y
                    unit.improve_type = task

                if unit.improve_progress >= TURNS[task]:
                    if task == "road":
                        tile.has_road = True
                    elif task == "irrigation":
                        tile.has_irrigation = True
                    elif task == "mine":
                        tile.has_mine = True
                    unit.improve_progress = 0
                    unit.improve_x = None
                    unit.improve_y = None
                    unit.improve_type = None

                unit.moves_left = 0
                return True

        # Move toward the nearest tile that still needs work
        target = self._find_worker_task(unit)
        if target:
            # Reset progress when leaving the current tile
            if (unit.improve_x, unit.improve_y) != (unit.x, unit.y):
                unit.improve_progress = 0
                unit.improve_x = None
                unit.improve_y = None
                unit.improve_type = None
            return self._step_toward(unit, target[0], target[1])

        # Nothing left to do: stay put
        unit.moves_left = 0
        return False

    def _find_worker_task(self, unit: Unit) -> Optional[Tuple[int, int]]:
        """Nearest tile inside civ territory that still needs a road, irrigation, or mine."""
        from game.terrain import TerrainType
        NO_ROAD   = (TerrainType.OCEAN, TerrainType.COAST, TerrainType.MOUNTAINS)
        IRRIGABLE = (TerrainType.GRASSLAND, TerrainType.PLAINS)
        MINEABLE  = (TerrainType.HILLS, TerrainType.MOUNTAINS)

        best_pos: Optional[Tuple[int, int]] = None
        best_dist = float("inf")

        for city in self.civ.cities.values():
            for dy in range(-2, 3):
                for dx in range(-2, 3):
                    tx = (city.x + dx) % MAP_WIDTH
                    ty = city.y + dy
                    if not (0 <= ty < MAP_HEIGHT):
                        continue
                    tile = self.state.tiles[ty][tx]
                    needs_work = (
                        (tile.terrain not in NO_ROAD and not tile.has_road)
                        or (tile.terrain in IRRIGABLE and not tile.has_irrigation)
                        or (tile.terrain in MINEABLE  and not tile.has_mine)
                    )
                    if not needs_work:
                        continue
                    d = abs(tx - unit.x) + abs(ty - unit.y)
                    if d < best_dist:
                        best_dist = d
                        best_pos = (tx, ty)

        return best_pos

    def _act_transit(self, unit: Unit) -> bool:
        """Land unit crossing water: head toward nearest passable land tile."""
        best_pos = None
        best_dist = float("inf")
        from game.terrain import TERRAIN_DEFS
        # Find nearest land tile that isn't water
        for dy in range(-8, 9):
            for dx in range(-8, 9):
                tx = (unit.x + dx) % MAP_WIDTH
                ty = unit.y + dy
                if not (0 <= ty < MAP_HEIGHT):
                    continue
                td = TERRAIN_DEFS[self.state.tiles[ty][tx].terrain]
                if td.is_passable and not td.is_water:
                    d = abs(dx) + abs(dy)
                    if d < best_dist:
                        best_dist = d
                        best_pos = (tx, ty)
        if best_pos:
            return self._step_toward(unit, best_pos[0], best_pos[1])
        return self._random_step(unit)

    def _act_attacker(self, unit: Unit) -> bool:
        from game.terrain import TERRAIN_DEFS

        # 1. Attack any adjacent enemy unit immediately (if attack is legal)
        for dx, dy in [(0, 1), (0, -1), (1, 0), (-1, 0)]:
            nx = (unit.x + dx) % MAP_WIDTH
            ny = unit.y + dy
            if not (0 <= ny < MAP_HEIGHT):
                continue
            occupant = self.state._unit_at(nx, ny)
            if occupant and occupant.civ_id != unit.civ_id:
                # Land units cannot attack naval units
                if not unit.unit_def.is_naval and occupant.unit_def.is_naval:
                    continue
                # Naval units: only attack land units on water/coast tiles
                if unit.unit_def.is_naval and not occupant.unit_def.is_naval:
                    def_td = TERRAIN_DEFS[self.state.tiles[ny][nx].terrain]
                    if not def_td.is_water:
                        continue  # naval units cannot attack units on inland tiles
                won = self.state.attack(unit, nx, ny)
                unit.moves_left = 0
                if won and unit.id in self.civ.units:
                    # Only move onto the tile if passable (naval units must stay on water)
                    if self.state.tile_is_passable_for(nx, ny, unit):
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

        # 3. Naval units: prioritise hunting land units crossing water
        if unit.unit_def.is_naval:
            for u in self.state._unit_index.values():
                if u.civ_id == unit.civ_id:
                    continue
                if not u.unit_def.is_naval:
                    def_td = TERRAIN_DEFS[self.state.tiles[u.y][u.x].terrain]
                    if def_td.is_water:
                        return self._step_toward(unit, u.x, u.y)

        # 4. March toward the nearest *reachable* target.
        # Try all targets by ascending Manhattan distance so that an impassable
        # nearest city (blocked by mountains / ocean) does not freeze the unit.
        tried = 0
        for target in self._find_all_attack_targets(unit):
            tried += 1
            if self._step_toward(unit, target[0], target[1]):
                return True

        # No target reachable: hold position rather than wandering
        if tried > 0:
            print(
                f"[AI DEBUG] {self.civ.name} {unit.unit_def.name} at "
                f"({unit.x},{unit.y}) has no reachable target after trying "
                f"{tried} candidate(s) — unit stays idle."
            )
        unit.moves_left = 0
        return False

    def _find_attack_target(self, unit: Unit) -> Optional[Tuple[int, int]]:
        """Nearest enemy city (preferred) or nearest enemy unit.
        Returns the single closest target (Manhattan distance). Kept for
        backward-compat; prefer _find_all_attack_targets for movement."""
        targets = self._find_all_attack_targets(unit)
        return targets[0] if targets else None

    def _find_all_attack_targets(self, unit: Unit) -> List[Tuple[int, int]]:
        """All enemy cities, then enemy units, sorted by ascending Manhattan
        distance.  Cities are listed before units of equal distance so that
        city-capture is preferred over chasing lone units."""
        city_targets: List[Tuple[int, Tuple[int, int]]] = []
        unit_targets: List[Tuple[int, Tuple[int, int]]] = []

        for civ in self.state.civs.values():
            if civ.id == self.civ.id:
                continue
            for city in civ.cities.values():
                d = abs(city.x - unit.x) + abs(city.y - unit.y)
                city_targets.append((d, (city.x, city.y)))

        for u in self.state._unit_index.values():
            if u.civ_id == self.civ.id:
                continue
            d = abs(u.x - unit.x) + abs(u.y - unit.y)
            unit_targets.append((d, (u.x, u.y)))

        city_targets.sort(key=lambda x: x[0])
        unit_targets.sort(key=lambda x: x[0])

        # Interleave: cities first within the same distance bucket
        merged: List[Tuple[int, int]] = []
        ci, ui = 0, 0
        while ci < len(city_targets) and ui < len(unit_targets):
            if city_targets[ci][0] <= unit_targets[ui][0]:
                merged.append(city_targets[ci][1])
                ci += 1
            else:
                merged.append(unit_targets[ui][1])
                ui += 1
        for d, pos in city_targets[ci:]:
            merged.append(pos)
        for d, pos in unit_targets[ui:]:
            merged.append(pos)

        return merged

    def _act_explorer(self, unit: Unit) -> bool:
        # Move toward least recently explored areas or just wander
        if unit._goal is None or (unit.x, unit.y) == unit._goal:
            unit._goal = (
                self.state.rng.randint(0, MAP_WIDTH - 1),
                self.state.rng.randint(0, MAP_HEIGHT - 1),
            )
        return self._step_toward(unit, unit._goal[0], unit._goal[1])

    # ------------------------------------------------------------------
    # Role helpers
    # ------------------------------------------------------------------

    def _is_defender_unit(self, unit: Unit) -> bool:
        """Units whose defense stat ≥ attack stat play a defensive role."""
        return unit.unit_def.defense >= unit.unit_def.attack

    def _is_in_civ_territory(self, x: int, y: int) -> bool:
        """True if (x, y) is within Chebyshev radius 2 of any of this civ's cities."""
        for city in self.civ.cities.values():
            if max(abs(x - city.x), abs(y - city.y)) <= 2:
                return True
        return False

    # ------------------------------------------------------------------
    # Garrison assignment
    # ------------------------------------------------------------------

    def _compute_garrison_assignments(self) -> dict:
        """
        Assign up to SLOTS_PER_CITY defender-typed units per city.
        Returns unit_id → City.

        Defender-typed = defense ≥ attack.  Attacker-typed units are never
        garrisoned so they stay free to march on enemy cities.

        Pass 1 — defender units already at/adjacent (dist ≤ 1) to a city
                  claim that city's slot first.
        Pass 2 — each undefended city (0 slots) gets the closest free
                  defender; if none exist, fall back to any military unit.
        Pass 3 — fill second garrison slot with the highest-defense free
                  defender available.
        """
        SLOTS_PER_CITY = 2
        unit_to_city: dict = {}
        city_fill: dict = {city.id: 0 for city in self.civ.cities.values()}

        def is_military(u: Unit) -> bool:
            return (
                not u.has_ability(UnitAbility.FOUND_CITY)
                and not u.has_ability(UnitAbility.IMPROVE_TERRAIN)
            )

        defenders = [u for u in self.civ.units.values()
                     if is_military(u) and self._is_defender_unit(u)]
        all_military = [u for u in self.civ.units.values() if is_military(u)]

        # Pass 1: units already at or adjacent to a city claim its garrison
        for city in self.civ.cities.values():
            for u in sorted(defenders, key=lambda u: u.unit_def.defense, reverse=True):
                if u.id in unit_to_city:
                    continue
                if city_fill[city.id] >= SLOTS_PER_CITY:
                    break
                if abs(u.x - city.x) + abs(u.y - city.y) <= 1:
                    unit_to_city[u.id] = city
                    city_fill[city.id] += 1

        # Pass 2: every city must have at least 1 garrison unit (defenders only)
        # Attackers are intentionally left free to march on enemy cities.
        for city in self.civ.cities.values():
            if city_fill[city.id] > 0:
                continue
            pool = [u for u in defenders if u.id not in unit_to_city]
            if not pool:
                continue  # no defender available; leave city ungarrisoned
            best = min(pool, key=lambda u: abs(u.x - city.x) + abs(u.y - city.y))
            unit_to_city[best.id] = city
            city_fill[city.id] += 1

        # Pass 3: fill second slot with the highest-defense available defender
        for city in self.civ.cities.values():
            if city_fill[city.id] >= SLOTS_PER_CITY:
                continue
            free = [u for u in defenders if u.id not in unit_to_city]
            if not free:
                break
            best = max(free, key=lambda u: u.unit_def.defense)
            unit_to_city[best.id] = city
            city_fill[city.id] += 1

        return unit_to_city

    # ------------------------------------------------------------------
    # Movement helpers
    # ------------------------------------------------------------------

    def _step_toward(self, unit: Unit, tx: int, ty: int) -> bool:
        """BFS to find next step toward (tx, ty). Returns True if moved.
        Returns False (without wandering) if no path exists."""
        path = self._bfs(unit.x, unit.y, tx, ty, unit)
        if path and len(path) > 1:
            nx, ny = path[1]
            return self._try_move(unit, nx, ny)
        return False

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
        # Chebyshev distance ≥ 5 so territory radii (2 tiles) don't overlap
        for civ in self.state.civs.values():
            for city in civ.cities.values():
                dx = min(abs(city.x - x), MAP_WIDTH - abs(city.x - x))
                dy = abs(city.y - y)
                if max(dx, dy) < 5:
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
        """Score a candidate site by the yields of tiles it would exclusively own."""
        from game.terrain import TerrainType
        all_cities = [
            city for civ in self.state.civs.values() for city in civ.cities.values()
        ]
        score = 0
        for dy in range(-2, 3):
            for dx in range(-2, 3):
                if dx == 0 and dy == 0:
                    continue
                tx = (x + dx) % MAP_WIDTH
                ty = y + dy
                if not (0 <= ty < MAP_HEIGHT):
                    continue
                my_ch = max(abs(dx), abs(dy))
                # Tile is ours only if no existing city is as close or closer
                contested = False
                for city in all_cities:
                    cdx = min(abs(city.x - tx), MAP_WIDTH - abs(city.x - tx))
                    cdy = abs(city.y - ty)
                    if max(cdx, cdy) <= my_ch:
                        contested = True
                        break
                if contested:
                    continue
                tile = self.state.tiles[ty][tx]
                f, p, t = tile.yields()
                score += f * 2 + p + t
                if tile.terrain == TerrainType.COAST:
                    score += 2
        return score

    # ------------------------------------------------------------------
    # Utility
    # ------------------------------------------------------------------

    def _remove_unit_from_civ(self, unit: Unit) -> None:
        self.civ.units.pop(unit.id, None)
        self.state._unit_index.pop(unit.id, None)
