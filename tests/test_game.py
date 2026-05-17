"""Unit tests for core game logic — no server, no browser, no AI."""
import pytest

from game.terrain import TerrainType, TERRAIN_DEFS
from game.tech import TECH_DEFS, get_available_techs, tech_era_order
from game.building import BUILDING_DEFS, get_buildable_buildings
from game.unit import UNIT_DEFS, Unit, UnitAbility, get_buildable_units
from game.map_generator import generate_map, find_valid_start_positions
from game.city import City, ProductionOrder
from game.civilization import Civilization
from game.game_state import GameState
from game.constants import MAP_WIDTH, MAP_HEIGHT, NUM_CIVS

import random


# ── Terrain ──────────────────────────────────────────────────────

def test_terrain_defs_complete():
    for t in TerrainType:
        assert t in TERRAIN_DEFS, f"Missing def for {t}"

def test_ocean_not_passable():
    assert not TERRAIN_DEFS[TerrainType.OCEAN].is_passable

def test_mountains_not_passable():
    assert not TERRAIN_DEFS[TerrainType.MOUNTAINS].is_passable

def test_grassland_passable():
    assert TERRAIN_DEFS[TerrainType.GRASSLAND].is_passable


# ── Tech tree ────────────────────────────────────────────────────

def test_no_circular_prerequisites():
    """Every tech's prerequisites exist in the registry."""
    for key, td in TECH_DEFS.items():
        for prereq in td.prerequisites:
            assert prereq in TECH_DEFS, f"{key} requires unknown tech {prereq}"

def test_available_techs_empty_research():
    available = get_available_techs(set())
    # Techs with no prerequisites should be available from the start
    no_prereqs = [k for k, td in TECH_DEFS.items() if not td.prerequisites]
    for k in no_prereqs:
        assert k in available

def test_available_techs_after_prereq():
    available = get_available_techs({"alphabet"})
    assert "writing" in available

def test_era_order_covers_all_techs():
    ordered = tech_era_order()
    assert set(ordered) == set(TECH_DEFS.keys())

def test_modern_tech_chain_availability():
    # electronics needs engineering + electricity
    assert "electronics" not in get_available_techs({"electricity"})
    assert "electronics" in get_available_techs({"electricity", "engineering"})


# ── Buildings ────────────────────────────────────────────────────

def test_buildable_buildings_no_research():
    buildable = get_buildable_buildings(set(), set())
    # barracks requires no tech
    assert "barracks" in buildable

def test_library_requires_writing():
    assert "library" not in get_buildable_buildings(set(), set())
    assert "library" in get_buildable_buildings({"writing"}, set())

def test_existing_buildings_excluded():
    buildable = get_buildable_buildings(set(), {"barracks"})
    assert "barracks" not in buildable


# ── Units ────────────────────────────────────────────────────────

def test_militia_always_buildable():
    assert "militia" in get_buildable_units(set())

def test_phalanx_requires_bronze_working():
    assert "phalanx" not in get_buildable_units(set())
    assert "phalanx" in get_buildable_units({"bronze_working"})

def test_armor_requires_automobile():
    assert "armor" not in get_buildable_units({"electricity"})
    assert "armor" in get_buildable_units({"automobile"})

def test_unit_instance():
    u = Unit("militia", "civ1", 5, 5)
    assert u.unit_def.attack == 1
    assert u.unit_def.defense == 1
    assert u.moves_left == 1

def test_settler_has_found_city_ability():
    u = Unit("settler", "civ1", 0, 0)
    assert u.has_ability(UnitAbility.FOUND_CITY)


# ── Map generation ───────────────────────────────────────────────

def test_map_dimensions():
    tiles = generate_map(seed=1)
    assert len(tiles) == MAP_HEIGHT
    assert len(tiles[0]) == MAP_WIDTH

def test_map_has_land_and_ocean():
    tiles = generate_map(seed=1)
    terrain_types = {tiles[y][x].terrain for y in range(MAP_HEIGHT) for x in range(MAP_WIDTH)}
    assert TerrainType.OCEAN in terrain_types
    land_types = {
        TerrainType.GRASSLAND, TerrainType.PLAINS, TerrainType.FOREST,
        TerrainType.HILLS, TerrainType.DESERT, TerrainType.TUNDRA,
    }
    assert terrain_types & land_types, "Map must contain at least one land terrain type"

def test_start_positions():
    tiles = generate_map(seed=1)
    rng = random.Random(1)
    positions = find_valid_start_positions(tiles, NUM_CIVS, rng)
    assert len(positions) == NUM_CIVS
    # Check uniqueness
    assert len(set(positions)) == NUM_CIVS


# ── City ─────────────────────────────────────────────────────────

def test_city_growth_food():
    city = City("TestCity", "civ1", 10, 10)
    assert city.food_needed_to_grow() == 30  # 20 + 1*10
    city.population = 3
    assert city.food_needed_to_grow() == 50  # 20 + 3*10

def test_city_max_population_increases_with_aqueduct():
    city = City("TestCity", "civ1", 10, 10)
    base = city.max_population()
    city.buildings.add("aqueduct")
    assert city.max_population() > base

def test_city_production_cost_unit():
    city = City("TestCity", "civ1", 10, 10)
    city.production_order = ProductionOrder("unit", "militia")
    assert city.production_cost() == UNIT_DEFS["militia"].cost

def test_city_upkeep_increases_with_buildings():
    city = City("TestCity", "civ1", 10, 10)
    upkeep0 = city.upkeep_per_turn()
    city.buildings.add("barracks")
    assert city.upkeep_per_turn() > upkeep0


# ── Civilization ─────────────────────────────────────────────────

def test_civilization_gold_upkeep():
    civ = Civilization("Test", "#fff", ["CityA"])
    # No units above free threshold → no unit upkeep
    assert civ.total_upkeep() == 0

def test_civilization_has_tech():
    civ = Civilization("Test", "#fff", ["CityA"])
    assert not civ.has_tech("writing")
    civ.researched_techs.add("writing")
    assert civ.has_tech("writing")


# ── Full game state ───────────────────────────────────────────────

def test_game_state_initializes():
    gs = GameState(seed=7)
    assert gs.turn == 0
    assert len(gs.civs) == NUM_CIVS
    for civ in gs.civs.values():
        assert len(civ.cities) >= 1
        assert len(civ.units) >= 1

def test_advance_turn_increments():
    gs = GameState(seed=7)
    gs.advance_turn()
    assert gs.turn == 1

def test_advance_ten_turns_no_crash():
    gs = GameState(seed=42)
    # advance_turn() plays one civ at a time; NUM_CIVS calls = 1 full turn
    for _ in range(10 * NUM_CIVS):
        gs.advance_turn()
    assert gs.turn == 10

def test_serialization_keys():
    gs = GameState(seed=7)
    d = gs.to_dict()
    for key in ("turn", "year", "terrain", "cities", "units", "civs", "events"):
        assert key in d, f"Missing key: {key}"

def test_terrain_grid_shape():
    gs = GameState(seed=7)
    d = gs.to_dict()
    assert len(d["terrain"]) == MAP_HEIGHT
    assert len(d["terrain"][0]) == MAP_WIDTH
