"""Map generation using smoothed random grids (no external deps)."""
import random
from typing import List

from game.constants import MAP_WIDTH, MAP_HEIGHT
from game.terrain import TerrainType
from game.tile import Tile, ResourceType


def _smooth_grid(grid: List[List[float]], iterations: int, radius: int = 2) -> List[List[float]]:
    h, w = len(grid), len(grid[0])
    for _ in range(iterations):
        out = [[0.0] * w for _ in range(h)]
        for y in range(h):
            for x in range(w):
                total, count = 0.0, 0
                for dy in range(-radius, radius + 1):
                    for dx in range(-radius, radius + 1):
                        ny = y + dy
                        nx = (x + dx) % w  # wrap east-west
                        if 0 <= ny < h:
                            total += grid[ny][nx]
                            count += 1
                out[y][x] = total / count
        grid = out
    return grid


def _make_grid(rng: random.Random, w: int, h: int) -> List[List[float]]:
    return [[rng.random() for _ in range(w)] for _ in range(h)]


def _normalise(grid: List[List[float]]) -> List[List[float]]:
    """Stretch values to fill [0, 1]."""
    flat = [v for row in grid for v in row]
    lo, hi = min(flat), max(flat)
    span = hi - lo or 1e-9
    return [[(v - lo) / span for v in row] for row in grid]


def generate_map(seed: int = 42) -> List[List[Tile]]:
    rng = random.Random(seed)

    # Two continent seeds blended → height map
    h1 = _smooth_grid(_make_grid(rng, MAP_WIDTH, MAP_HEIGHT), iterations=5, radius=3)
    h2 = _smooth_grid(_make_grid(rng, MAP_WIDTH, MAP_HEIGHT), iterations=5, radius=3)
    height = _normalise([
        [max(h1[y][x], h2[y][x] * 0.85) for x in range(MAP_WIDTH)]
        for y in range(MAP_HEIGHT)
    ])

    # Moisture map
    moisture = _normalise(_smooth_grid(_make_grid(rng, MAP_WIDTH, MAP_HEIGHT), iterations=4, radius=2))

    tiles: List[List[Tile]] = [
        [Tile(x, y, TerrainType.OCEAN) for x in range(MAP_WIDTH)]
        for y in range(MAP_HEIGHT)
    ]

    for y in range(MAP_HEIGHT):
        lat = abs(y - MAP_HEIGHT / 2) / (MAP_HEIGHT / 2)  # 0 = equator, 1 = poles
        for x in range(MAP_WIDTH):
            # Depress height toward poles → less land
            h = height[y][x] - lat * 0.30
            m = moisture[y][x]
            tiles[y][x].terrain = _classify(h, m, lat)

    _add_coast(tiles)
    _add_resources(tiles, rng)
    return tiles


def _classify(h: float, m: float, lat: float) -> TerrainType:
    if h < 0.42:
        return TerrainType.OCEAN

    if lat > 0.85:
        return TerrainType.ARCTIC
    if lat > 0.70:
        return TerrainType.TUNDRA

    if h > 0.80:
        return TerrainType.MOUNTAINS
    if h > 0.68:
        return TerrainType.HILLS

    if m < 0.25:
        return TerrainType.DESERT

    if m > 0.65:
        return TerrainType.FOREST
    if m > 0.45:
        return TerrainType.PLAINS

    return TerrainType.GRASSLAND


def _add_coast(tiles: List[List[Tile]]) -> None:
    for y in range(MAP_HEIGHT):
        for x in range(MAP_WIDTH):
            if tiles[y][x].terrain != TerrainType.OCEAN:
                continue
            for dy in (-1, 0, 1):
                for dx in (-1, 0, 1):
                    nx_ = (x + dx) % MAP_WIDTH
                    ny_ = y + dy
                    if 0 <= ny_ < MAP_HEIGHT:
                        nb = tiles[ny_][nx_].terrain
                        if nb not in (TerrainType.OCEAN, TerrainType.COAST):
                            tiles[y][x].terrain = TerrainType.COAST
                            break


def _add_resources(tiles: List[List[Tile]], rng: random.Random) -> None:
    terrain_resources = {
        TerrainType.GRASSLAND: [ResourceType.WHEAT, ResourceType.CATTLE],
        TerrainType.PLAINS:    [ResourceType.WHEAT, ResourceType.HORSES],
        TerrainType.FOREST:    [ResourceType.FOREST_GAME, ResourceType.IRON],
        TerrainType.HILLS:     [ResourceType.COAL, ResourceType.IRON, ResourceType.GOLD_ORE],
        TerrainType.DESERT:    [ResourceType.GOLD_ORE, ResourceType.OIL],
        TerrainType.COAST:     [ResourceType.FISH],
        TerrainType.TUNDRA:    [ResourceType.IRON],
        TerrainType.MOUNTAINS: [ResourceType.COAL, ResourceType.GOLD_ORE],
    }
    for y in range(MAP_HEIGHT):
        for x in range(MAP_WIDTH):
            tile = tiles[y][x]
            options = terrain_resources.get(tile.terrain)
            if options and rng.random() < 0.12:
                tile.resource = rng.choice(options)


# Candidate terrain types that civs can start on (ordered by preference)
_SETTLE_TERRAIN = (
    TerrainType.GRASSLAND, TerrainType.PLAINS, TerrainType.FOREST,
    TerrainType.HILLS, TerrainType.DESERT, TerrainType.TUNDRA,
)


def find_valid_start_positions(
    tiles: List[List[Tile]], num_civs: int, rng: random.Random
) -> List[tuple]:
    candidates = [
        (x, y)
        for y in range(5, MAP_HEIGHT - 5)
        for x in range(MAP_WIDTH)
        if tiles[y][x].terrain in _SETTLE_TERRAIN
    ]
    rng.shuffle(candidates)

    positions: List[tuple] = []
    min_dist = MAP_WIDTH // (num_civs + 1)

    for cx, cy in candidates:
        too_close = any(
            abs(cx - px) + abs(cy - py) < min_dist
            for px, py in positions
        )
        if not too_close:
            positions.append((cx, cy))
        if len(positions) == num_civs:
            break

    # Relax distance constraint if we couldn't place everyone
    if len(positions) < num_civs:
        rng.shuffle(candidates)
        for cx, cy in candidates:
            if len(positions) == num_civs:
                break
            if (cx, cy) not in positions:
                positions.append((cx, cy))

    return positions
