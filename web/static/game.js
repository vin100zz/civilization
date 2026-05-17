"use strict";

// ── Constants ────────────────────────────────────────────────────
const TILE = 32;          // pixels per tile on main map
const MINI = 3;           // pixels per tile on minimap
const SCROLL_SPEED = 4;   // tiles per key press

// Terrain colors  (must match Python TerrainType values)
const TERRAIN_COLOR = {
  ocean:     "#1a5fa0",
  coast:     "#2a7bbf",
  grassland: "#3a9440",
  plains:    "#78b838",
  forest:    "#1e5c1e",
  hills:     "#7a5420",
  mountains: "#5a5a5a",
  desert:    "#c4a030",
  tundra:    "#6a8898",
  arctic:    "#b8ccd8",
};

// Slightly lighter shade for variety
const TERRAIN_COLOR2 = {
  ocean:     "#1c64a8",
  coast:     "#2d81c7",
  grassland: "#3f9c42",
  plains:    "#80be40",
  forest:    "#215f21",
  hills:     "#825a24",
  mountains: "#616161",
  desert:    "#caa838",
  tundra:    "#7290a0",
  arctic:    "#c0d4e0",
};

// ── Sprite cache ─────────────────────────────────────────────────
// Keyed by unit-type string or "city".  Values: HTMLImageElement | "loading" | null
const _sprites = {};

function _loadSprite(key, url) {
  const img = new Image();
  _sprites[key] = "loading";
  img.onload  = () => { _sprites[key] = img; if (state) render(); };
  img.onerror = () => { _sprites[key] = null; };
  img.src = url;
}

// City sprite
_loadSprite("city", "/resources/city/city.png");

// Terrain sprites
const _TERRAIN_TYPES = [
  "ocean", "coast", "grassland", "plains", "forest",
  "hills", "mountains", "desert", "tundra", "arctic",
];
for (const t of _TERRAIN_TYPES)
  _loadSprite("terrain_" + t, `/resources/terrain/${t}.png`);

// Resource sprites (game key → filename mapping for renamed entries)
const _RESOURCE_FILE = {
  wheat:       "wheat",
  cattle:      "cattle",
  fish:        "fish",
  coal:        "coal",
  iron:        "iron",
  horses:      "horses",
  gold_ore:    "gold",        // game uses "gold_ore", file is "gold.png"
  oil:         "oil",
  forest_game: "forest_game",
};
for (const [key, file] of Object.entries(_RESOURCE_FILE))
  _loadSprite("resource_" + key, `/resources/resource/${file}.png`);

// Unit sprites — all known types loaded at startup; missing files → null (fallback)
const _UNIT_TYPES = [
  // civilian
  "settler", "worker",
  // land – ancient
  "militia", "phalanx", "cavalry", "chariot", "legion", "catapult",
  // land – medieval / industrial
  "knight", "musketeer", "cannon", "rifleman", "armor", "mechinf", "artillery",
  // naval
  "trireme", "sail", "frigate", "ironclad", "cruiser", "transport",
  "submarine", "battleship", "carrier",
  // legacy keys kept for backward-compat with old save files
  "warrior", "horseman", "tank", "caravel", "infantry",
];
for (const key of _UNIT_TYPES)
  _loadSprite(key, `/resources/unit/${key}.png`);

const RESOURCE_COLOR = {
  wheat:       "#f0e040",
  cattle:      "#c07830",
  fish:        "#40b0f0",
  coal:        "#303030",
  iron:        "#8080a0",
  horses:      "#c09060",
  gold_ore:    "#f0d020",
  oil:         "#404040",
  forest_game: "#a06030",
};

// ── State ────────────────────────────────────────────────────────
let state      = null;   // currently displayed game state (may be historical)
let _liveState = null;   // latest state received from server
let viewX = 0;           // scroll offset in tiles
let viewY = 0;
let focusCivId = null;

// ── History ───────────────────────────────────────────────────────
const _history    = new Map();  // turn → state dict (client-side cache)
let   _maxTurn    = 0;          // highest turn number received
let   _replayTurn = null;       // null = live; number = viewing that turn
let   _gameId     = null;       // tracks the current game_id; resets on change

function _isLive() { return _replayTurn === null; }

/** Reset all history/timeline state (new game or server restart detected). */
function _resetHistory() {
  _history.clear();
  _liveState    = null;
  _maxTurn      = 0;
  _replayTurn   = null;
  tlSlider.min  = 0;
  tlSlider.max  = 0;
  tlSlider.value = 0;
  tlTurnEl.textContent  = "Turn 0";
  tlTotalEl.textContent = "/ 0";
  btnLive.textContent   = "● LIVE";
  btnLive.classList.remove("replay");
  _updateArrows();
}

// DOM refs
const mapCanvas  = document.getElementById("map-canvas");
const mapCtx     = mapCanvas.getContext("2d");
const miniCanvas = document.getElementById("minimap");
const miniCtx    = miniCanvas.getContext("2d");
const tooltip    = document.getElementById("tooltip");
const viewport   = document.getElementById("map-viewport");
const tlSlider   = document.getElementById("tl-slider");
const tlTurnEl   = document.getElementById("tl-turn");
const tlTotalEl  = document.getElementById("tl-total");
const btnLive    = document.getElementById("btn-live");
const btnPrev    = document.getElementById("btn-prev");
const btnNext    = document.getElementById("btn-next");

// ── Animation ─────────────────────────────────────────────────────
const ANIM_DURATION = 280;    // ms — snappy but visible

// unit.id → { fx, fy, tx, ty, t0 }   (from-pixel, to-pixel, start-time)
let _unitAnims = {};
let _rafId     = null;
let hoveredCityId = null;   // city id under the mouse, or null

/**
 * Return the current draw position (pixels) for a unit.
 * During animation this is an interpolated position; otherwise it's the
 * canonical tile-based position.
 */
// Returns [screenPixelX, screenPixelY] for a unit (accounts for wrap + animation).
function _unitDrawPos(unit) {
  const mw   = state.map_width;
  const anim = _unitAnims[unit.id];
  if (!anim) {
    return [_sx(unit.x) + 2, _sy(unit.y) + 2];
  }
  const t    = Math.min(1, (performance.now() - anim.t0) / ANIM_DURATION);
  const ease = 1 - Math.pow(1 - t, 3);   // ease-out cubic
  // Interpolate in screen-tile space (handles wrap correctly)
  const fromSx = _sx(anim.fromX) + 2;
  const toSx   = _sx(unit.x)     + 2;
  const fromSy = _sy(anim.fromY) + 2;
  const toSy   = _sy(unit.y)     + 2;
  return [
    fromSx + (toSx - fromSx) * ease,
    fromSy + (toSy - fromSy) * ease,
  ];
}

/**
 * Compare new unit positions against *prevPos* (id → {x,y}).
 * Populate _unitAnims for every unit that moved, then kick off a RAF loop.
 * Returns true if at least one animation was started.
 */
function _scheduleAnimations(prevPos) {
  _unitAnims = {};
  if (!state) return false;
  const now = performance.now();
  for (const u of state.units) {
    const p = prevPos[u.id];
    if (p && (p.x !== u.x || p.y !== u.y)) {
      _unitAnims[u.id] = {
        fromX: p.x, fromY: p.y,   // tile coords (screen pos computed at draw time)
        t0: now,
      };
    }
  }
  if (Object.keys(_unitAnims).length > 0) {
    if (_rafId === null) _rafId = requestAnimationFrame(_animTick);
    return true;
  }
  return false;
}

function _animTick() {
  _rafId = null;
  _renderFrame();

  const now = performance.now();
  const anyRunning = Object.values(_unitAnims).some(a => now - a.t0 < ANIM_DURATION);
  if (anyRunning) {
    _rafId = requestAnimationFrame(_animTick);
  } else {
    _unitAnims = {};
    _renderFrame();   // final frame at exact tile positions
  }
}

// ── Timeline controls ─────────────────────────────────────────────

/** Switch back to live mode, displaying the latest received state. */
function _setLiveMode() {
  _replayTurn = null;
  btnLive.classList.remove("replay");
  btnLive.textContent = "● LIVE";
  tlSlider.value       = _maxTurn;
  tlTurnEl.textContent = `Turn ${_maxTurn}`;
  if (_liveState) {
    state = _liveState;
    render();
    updateSidebar();
  }
}

/** Enter replay mode showing *turn*. */
function _enterReplay(turn) {
  _replayTurn = turn;
  btnLive.classList.add("replay");
  btnLive.textContent  = "▶ LIVE";
  tlTurnEl.textContent = `Turn ${turn}`;
}

/** Display the state for *turn*, fetching from server if not cached. */
async function _showTurn(turn) {
  // Local cache hit
  if (_history.has(turn)) {
    state = _history.get(turn);
    render();
    updateSidebar();
    return;
  }
  // Fetch from server
  try {
    const resp = await fetch(`/snapshot/${turn}`);
    if (!resp.ok) return;   // turn not available — leave display unchanged
    const snap = await resp.json();
    _history.set(snap.turn, snap);
    // Only apply if the user is still looking at this turn
    if (_replayTurn === turn) {
      state = snap;
      render();
      updateSidebar();
      _renderStats();
    }
  } catch (err) {
    console.warn("Failed to fetch snapshot for turn", turn, err);
  }
}

/** Navigate to a specific turn (clamped to available range). */
function _goToTurn(turn) {
  const t = Math.max(0, Math.min(_maxTurn, turn));
  tlSlider.value = t;
  if (t >= _maxTurn) {
    _setLiveMode();
  } else {
    _enterReplay(t);
    _showTurn(t);
  }
}

/** Update the disabled state of the arrow buttons. */
function _updateArrows() {
  const cur = _replayTurn !== null ? _replayTurn : _maxTurn;
  btnPrev.disabled = cur <= 0;
  btnNext.disabled = _isLive();   // already at latest
}

btnLive.addEventListener("click", () => { _setLiveMode(); _updateArrows(); });

btnPrev.addEventListener("click", () => {
  const cur = _replayTurn !== null ? _replayTurn : _maxTurn;
  _goToTurn(cur - 1);
  _updateArrows();
});

btnNext.addEventListener("click", () => {
  const cur = _replayTurn !== null ? _replayTurn : _maxTurn;
  _goToTurn(cur + 1);
  _updateArrows();
});

tlSlider.addEventListener("input", () => {
  const turn = parseInt(tlSlider.value, 10);
  if (turn >= _maxTurn) {
    _setLiveMode();
  } else {
    _enterReplay(turn);
    _showTurn(turn);
  }
  _updateArrows();
});

// ── WebSocket ────────────────────────────────────────────────────
let ws = null;

function connect() {
  const proto = location.protocol === "https:" ? "wss" : "ws";
  ws = new WebSocket(`${proto}://${location.host}/ws`);

  ws.onopen = () => {
    removeOverlay();
    // Sync speed with the server immediately on connect
    const speed = parseFloat(document.getElementById("speed-slider").value);
    ws.send(JSON.stringify({ action: "set_speed", speed }));
    // Sync pause state (resume on reconnect; reset button if needed)
    ws.send(JSON.stringify({ action: "set_paused", paused: _gamePaused }));
  };

  ws.onmessage = (e) => {
    const newState = JSON.parse(e.data);

    // ── Detect new game or server restart via game_id ──────────────
    if (newState.game_id !== _gameId) {
      _gameId = newState.game_id;
      _resetHistory();
      focusCivId = null;
    }

    // ── Store in client cache ──────────────────────────────────────
    _history.set(newState.turn, newState);
    if (_history.size > 500) _history.delete(_history.keys().next().value);
    _liveState = newState;
    _maxTurn   = Math.max(_maxTurn, newState.turn);

    // Update slider range / arrows
    tlSlider.max          = _maxTurn;
    tlTotalEl.textContent = `/ ${_maxTurn}`;
    _updateArrows();

    // ── In replay mode: don't change the display ──────────────────
    if (!_isLive()) return;

    // ── Live mode: animate + render ───────────────────────────────
    const prevPos = {};
    if (state) {
      for (const u of state.units) prevPos[u.id] = { x: u.x, y: u.y };
    }

    state = newState;
    tlSlider.value = _maxTurn;
    if (newState.active_civ) {
      const civData = newState.civs.find(c => c.name === newState.active_civ);
      const color   = civData ? civData.color : '#aaa';
      tlTurnEl.innerHTML =
        `Turn ${_maxTurn}&nbsp;<span style="display:inline-block;width:9px;height:9px;background:${color};border:1px solid #ffffff55;vertical-align:middle;border-radius:1px"></span>`;
    } else {
      tlTurnEl.textContent = `Turn ${_maxTurn}`;
    }
    updateSidebar();
    _refreshTooltip();
    _renderStats();

    if (!_scheduleAnimations(prevPos)) render();
  };

  ws.onclose = () => {
    showOverlay("RECONNECTING…");
    setTimeout(connect, 2000);
  };

  ws.onerror = () => ws.close();
}

// ── Overlay helpers ───────────────────────────────────────────────
function showOverlay(msg) {
  let el = document.getElementById("overlay");
  if (!el) {
    el = document.createElement("div");
    el.id = "overlay";
    document.body.appendChild(el);
  }
  el.textContent = msg;
  el.style.display = "flex";
}
function removeOverlay() {
  const el = document.getElementById("overlay");
  if (el) el.style.display = "none";
}

// ── Rendering ────────────────────────────────────────────────────

/**
 * Full render: cancel any running animation, resize canvas if needed,
 * then draw everything.  Called for scroll, grid toggle, resize, etc.
 */
function render() {
  if (!state) return;
  // Cancel animation — user action takes priority
  if (_rafId !== null) { cancelAnimationFrame(_rafId); _rafId = null; }
  _unitAnims = {};
  _ensureCanvasSize();
  _renderFrame();
}

/**
 * Resize (and clear) the canvas only when the world dimensions change.
 * Also updates the CSS scroll transform.
 */
function _ensureCanvasSize() {
  if (!state) return;
  const vw = viewport.clientWidth;
  const vh = viewport.clientHeight;
  if (mapCanvas.width !== vw || mapCanvas.height !== vh) {
    mapCanvas.width  = vw;
    mapCanvas.height = vh;
  }
  mapCanvas.style.transform = "";   // no CSS scroll — handled in draw code
}

/**
 * Draw one frame.  Does NOT resize the canvas — call _ensureCanvasSize()
 * first if the canvas might be stale.  Safe to call from RAF.
 */
// Number of tile columns/rows visible on screen (+ 1 to fill partial edge tile)
function _visibleTiles() {
  return {
    visW: Math.ceil(viewport.clientWidth  / TILE) + 1,
    visH: Math.ceil(viewport.clientHeight / TILE) + 1,
  };
}

// Convert a world tile-x to a screen pixel-x (wrapping, result may be negative or > vw)
function _sx(tx) {
  const mw = state.map_width;
  return ((tx - viewX % mw + mw) % mw) * TILE;
}
// Convert a world tile-y to a screen pixel-y (no wrapping)
function _sy(ty) { return (ty - viewY) * TILE; }

function _renderFrame() {
  if (!state) return;
  const { visW, visH } = _visibleTiles();
  drawTerrain(visW, visH);
  drawResources(visW, visH);
  drawCityTerritories(visW, visH);
  drawUnits();    // units first — cities and names render on top
  drawCities();
  drawMinimap();
}

function drawTerrain(visW, visH) {
  for (let sy = 0; sy < visH; sy++) {
    const ty = viewY + sy;
    if (ty < 0 || ty >= state.map_height) continue;
    for (let sx = 0; sx < visW; sx++) {
      const tx      = (viewX + sx) % state.map_width;
      const terrain = state.terrain[ty][tx];
      const px      = sx * TILE, py = sy * TILE;
      const sprite  = _sprites["terrain_" + terrain];

      if (sprite instanceof HTMLImageElement) {
        mapCtx.drawImage(sprite, px, py, TILE, TILE);
        // Subtle light overlay so units/cities stand out against the terrain
        mapCtx.fillStyle = "rgba(255,255,255,0.22)";
        mapCtx.fillRect(px, py, TILE, TILE);
      } else {
        // Fallback: flat colour (checkerboard for variety while sprites load)
        const col = ((tx + ty) % 2 === 0) ? TERRAIN_COLOR[terrain]
                                           : TERRAIN_COLOR2[terrain];
        mapCtx.fillStyle = col || "#333";
        mapCtx.fillRect(px, py, TILE, TILE);
      }

      if (state.roads[ty][tx]) {
        mapCtx.fillStyle = "#b8a060aa";
        mapCtx.fillRect(sx * TILE + TILE/2 - 2, sy * TILE, 4, TILE);
        mapCtx.fillRect(sx * TILE, sy * TILE + TILE/2 - 2, TILE, 4);
      }

      // Irrigation: diagonal blue hatch lines (clipped to tile)
      if (state.irrigation && state.irrigation[ty][tx]) {
        mapCtx.save();
        mapCtx.beginPath();
        mapCtx.rect(sx * TILE, sy * TILE, TILE, TILE);
        mapCtx.clip();
        mapCtx.strokeStyle = "#1166cccc";
        mapCtx.lineWidth = 2;
        mapCtx.beginPath();
        const x0 = sx * TILE, y0 = sy * TILE;
        for (let d = 0; d < TILE * 2; d += 9) {
          mapCtx.moveTo(x0 + d,        y0);
          mapCtx.lineTo(x0,            y0 + d);
          mapCtx.moveTo(x0 + TILE,     y0 + d - TILE);
          mapCtx.lineTo(x0 + d - TILE, y0 + TILE);
        }
        mapCtx.stroke();
        mapCtx.restore();
      }

      // Mine: small charcoal circle in the bottom-right corner
      if (state.mines && state.mines[ty][tx]) {
        const cx = sx * TILE + TILE - 7;
        const cy = sy * TILE + TILE - 7;
        const r  = 5;
        mapCtx.beginPath();
        mapCtx.arc(cx, cy, r, 0, Math.PI * 2);
        mapCtx.fillStyle = "#2a2a2a";
        mapCtx.fill();
        mapCtx.strokeStyle = "#777777";
        mapCtx.lineWidth = 1;
        mapCtx.stroke();
        // small highlight dot
        mapCtx.beginPath();
        mapCtx.arc(cx - 1, cy - 1, 1.5, 0, Math.PI * 2);
        mapCtx.fillStyle = "#aaaaaa";
        mapCtx.fill();
      }
    }
  }
}

function drawResources(visW, visH) {
  for (let sy = 0; sy < visH; sy++) {
    const ty = viewY + sy;
    if (ty < 0 || ty >= state.map_height) continue;
    for (let sx = 0; sx < visW; sx++) {
      const tx  = (viewX + sx) % state.map_width;
      const res = state.resources[ty][tx];
      if (!res || res === "none") continue;

      const sprite = _sprites["resource_" + res];
      if (sprite instanceof HTMLImageElement) {
        // Draw centred, slightly smaller than the tile so terrain shows around it
        const pad = 6;
        mapCtx.drawImage(sprite, sx * TILE + pad, sy * TILE + pad,
                         TILE - pad * 2, TILE - pad * 2);
      } else {
        // Fallback: coloured dot
        const col = RESOURCE_COLOR[res] || "#ffffff";
        mapCtx.beginPath();
        mapCtx.arc(sx * TILE + TILE / 2, sy * TILE + TILE / 2, 4, 0, Math.PI * 2);
        mapCtx.fillStyle = col;
        mapCtx.fill();
        mapCtx.strokeStyle = "#00000066";
        mapCtx.lineWidth = 1;
        mapCtx.stroke();
      }
    }
  }
}

function drawCityTerritories(visW, visH) {
  if (!hoveredCityId) return;
  const city = state.cities.find(c => c.id === hoveredCityId);
  if (!city || !city.worked_tiles || !city.worked_tiles.length) return;

  const civMap = buildCivMap();
  const civ    = civMap[city.civ_id];
  const color  = civ ? civ.color : "#aaaaaa";

  mapCtx.save();
  mapCtx.globalAlpha = 0.45;
  mapCtx.fillStyle = color;
  for (const [tx, ty] of city.worked_tiles) {
    const sx = _sx(tx), sy = _sy(ty);
    if (sx < 0 || sx >= visW * TILE || sy < 0 || sy >= visH * TILE) continue;
    mapCtx.fillRect(sx, sy, TILE, TILE);
  }
  mapCtx.restore();

  mapCtx.save();
  mapCtx.globalAlpha = 0.75;
  mapCtx.strokeStyle = color;
  mapCtx.lineWidth = 2;
  for (const [tx, ty] of city.worked_tiles) {
    const sx = _sx(tx), sy = _sy(ty);
    if (sx < 0 || sx >= visW * TILE || sy < 0 || sy >= visH * TILE) continue;
    mapCtx.strokeRect(sx + 1, sy + 1, TILE - 2, TILE - 2);
  }
  mapCtx.restore();
}

function drawCities() {
  const civMap     = buildCivMap();
  const citySprite = _sprites["city"];
  const { visW, visH } = _visibleTiles();

  for (const city of state.cities) {
    const civ   = civMap[city.civ_id];
    const color = civ ? civ.color : "#aaaaaa";
    const cx    = _sx(city.x);
    const cy    = _sy(city.y);
    if (cx < 0 || cx >= visW * TILE || cy < 0 || cy >= visH * TILE) continue;

    // Leave a 2-px margin so the city sits slightly inside the tile
    const ox = cx + 2, oy = cy + 2, sz = TILE - 4;

    if (citySprite instanceof HTMLImageElement) {
      // ── Sprite mode ──────────────────────────────────────────
      // 1. Civ-color fill replaces transparent background
      mapCtx.fillStyle = color;
      mapCtx.fillRect(ox, oy, sz, sz);

      // 2. Sprite on top
      mapCtx.drawImage(citySprite, ox, oy, sz, sz);

      // 3. Thin border
      mapCtx.strokeStyle = "#ffffffaa";
      mapCtx.lineWidth = 1;
      mapCtx.strokeRect(ox + 0.5, oy + 0.5, sz - 1, sz - 1);
    } else {
      // ── Fallback: colored square ─────────────────────────────
      mapCtx.fillStyle = color;
      mapCtx.fillRect(ox, oy, sz, sz);
      mapCtx.strokeStyle = "#ffffffaa";
      mapCtx.lineWidth = 1.5;
      mapCtx.strokeRect(ox + 0.5, oy + 0.5, sz - 1, sz - 1);
    }

    // Population — large number centered on the tile
    mapCtx.font = `bold 14px "Courier New"`;
    mapCtx.textAlign = "center";
    mapCtx.textBaseline = "middle";
    mapCtx.fillStyle = "#000000bb";
    mapCtx.fillText(city.population, cx + TILE / 2 + 1, cy + TILE / 2 + 1);
    mapCtx.fillStyle = "#ffffff";
    mapCtx.fillText(city.population, cx + TILE / 2, cy + TILE / 2);

    // City name below the tile, with drop-shadow for readability
    mapCtx.font = `10px "Courier New"`;
    mapCtx.textAlign = "center";
    mapCtx.textBaseline = "top";
    mapCtx.fillStyle = "#000000bb";
    mapCtx.fillText(city.name, cx + TILE / 2 + 1, cy + TILE + 1);
    mapCtx.fillStyle = "#ffffff";
    mapCtx.fillText(city.name, cx + TILE / 2, cy + TILE);
  }
}

function drawUnits() {
  const civMap          = buildCivMap();
  const { visW, visH }  = _visibleTiles();

  // Group units by final tile so stacks show a count badge
  const byTile = {};
  for (const u of state.units) {
    const key = `${u.x},${u.y}`;
    if (!byTile[key]) byTile[key] = [];
    byTile[key].push(u);
  }

  for (const [, units] of Object.entries(byTile)) {
    const u     = units[0];
    const civ   = civMap[u.civ_id];
    const color = civ ? civ.color : "#888888";
    const sz    = TILE - 4;

    // Screen position (accounts for wrap + animation)
    const [ux, uy] = _unitDrawPos(u);
    if (ux < -TILE || ux >= visW * TILE || uy < -TILE || uy >= visH * TILE) continue;

    _drawUnitTile(mapCtx, u, color, ux, uy, sz);

    // Worker task badge  (R = road, I = irrigation, M = mine)
    if (u.type === "worker" && u.improve_type) {
      const TASK_LABEL = { road: "R", irrigation: "I", mine: "M" };
      const TASK_COLOR = { road: "#c8901a", irrigation: "#1a66cc", mine: "#555555" };
      const label = TASK_LABEL[u.improve_type];
      const bg    = TASK_COLOR[u.improve_type];
      if (label) {
        const bx = ux + sz / 2;
        const by = uy + sz - 4;
        mapCtx.fillStyle = bg;
        mapCtx.fillRect(bx - 6, by - 8, 12, 10);
        mapCtx.strokeStyle = "#000000bb";
        mapCtx.lineWidth = 1;
        mapCtx.strokeRect(bx - 6, by - 8, 12, 10);
        mapCtx.fillStyle = "#ffffff";
        mapCtx.font = `bold 8px "Courier New"`;
        mapCtx.textAlign = "center";
        mapCtx.textBaseline = "middle";
        mapCtx.fillText(label, bx, by - 3);
      }
    }

    // Stack badge
    if (units.length > 1) {
      mapCtx.fillStyle = "#ffff00";
      mapCtx.strokeStyle = "#000";
      mapCtx.lineWidth = 1;
      mapCtx.font = `bold 8px "Courier New"`;
      mapCtx.textAlign = "right";
      mapCtx.textBaseline = "top";
      mapCtx.strokeText(units.length, ux + sz - 1, uy + 1);
      mapCtx.fillText(units.length, ux + sz - 1, uy + 1);
    }

    // Veteran star
    if (u.veteran) {
      mapCtx.fillStyle = "#f0cc44";
      mapCtx.font = `7px sans-serif`;
      mapCtx.textAlign = "left";
      mapCtx.textBaseline = "top";
      mapCtx.fillText("★", ux + 1, uy + 1);
    }
  }
}

/**
 * Draw one unit tile at (ux, uy) with the given size.
 *
 * If a loaded sprite exists for this unit type:
 *   1. Fill background with civ color (replaces transparency)
 *   2. Draw the sprite scaled to fill the tile
 *
 * Otherwise fall back to a colored box with the unit's initial letter.
 */
function _drawUnitTile(ctx, unit, civColor, ux, uy, sz) {
  const sprite = _sprites[unit.type];

  if (sprite instanceof HTMLImageElement) {
    // 1. Civ-color background (fills transparent areas of the sprite)
    ctx.fillStyle = civColor;
    ctx.fillRect(ux, uy, sz, sz);

    // 2. Border
    ctx.strokeStyle = "#00000066";
    ctx.lineWidth = 1;
    ctx.strokeRect(ux + 0.5, uy + 0.5, sz - 1, sz - 1);

    // 3. Sprite on top
    ctx.drawImage(sprite, ux, uy, sz, sz);

  } else {
    // Fallback: colored box with the unit's initial letter
    ctx.fillStyle = civColor;
    ctx.fillRect(ux, uy, sz, sz);

    ctx.fillStyle = "#00000055";
    ctx.fillRect(ux + 3, uy + 3, sz - 6, sz - 6);

    ctx.strokeStyle = "#ffffff55";
    ctx.lineWidth = 1;
    ctx.strokeRect(ux + 0.5, uy + 0.5, sz - 1, sz - 1);

    ctx.fillStyle = "#ffffff";
    ctx.font = `bold ${TILE > 24 ? 10 : 8}px "Courier New"`;
    ctx.textAlign = "center";
    ctx.textBaseline = "middle";
    ctx.fillText(unit.name.charAt(0), ux + sz / 2, uy + sz / 2);
  }
}

function drawMinimap() {
  if (!state) return;
  miniCanvas.width  = state.map_width  * MINI;
  miniCanvas.height = state.map_height * MINI;

  const civMap = buildCivMap();

  // Terrain — sea vs land only
  for (let y = 0; y < state.map_height; y++) {
    for (let x = 0; x < state.map_width; x++) {
      const t = state.terrain[y][x];
      miniCtx.fillStyle = (t === "ocean" || t === "coast") ? "#2a6ea6" : "#a08060";
      miniCtx.fillRect(x * MINI, y * MINI, MINI, MINI);
    }
  }

  // Territory tiles in civ color
  miniCtx.globalAlpha = 0.55;
  for (const city of state.cities) {
    if (!city.worked_tiles) continue;
    const civ = civMap[city.civ_id];
    miniCtx.fillStyle = civ ? civ.color : "#aaa";
    for (const [tx, ty] of city.worked_tiles) {
      miniCtx.fillRect(tx * MINI, ty * MINI, MINI, MINI);
    }
  }
  miniCtx.globalAlpha = 1;

  // Cities as black squares
  for (const city of state.cities) {
    miniCtx.fillStyle = "#000000";
    miniCtx.fillRect(city.x * MINI, city.y * MINI, MINI + 1, MINI + 1);
  }

  // Viewport rect — split into two pieces if it wraps around the right edge
  const vw     = viewport.clientWidth;
  const vh     = viewport.clientHeight;
  const tilesX = Math.ceil(vw / TILE);
  const tilesY = Math.ceil(vh / TILE);
  const mw     = state.map_width;
  const startX = viewX % mw;

  miniCtx.strokeStyle = "#ffffff88";
  miniCtx.lineWidth = 1;
  if (startX + tilesX <= mw) {
    miniCtx.strokeRect(startX * MINI, viewY * MINI, tilesX * MINI, tilesY * MINI);
  } else {
    const w1 = mw - startX;
    const w2 = tilesX - w1;
    miniCtx.strokeRect(startX * MINI, viewY * MINI, w1 * MINI, tilesY * MINI);
    miniCtx.strokeRect(0,             viewY * MINI, w2 * MINI, tilesY * MINI);
  }
}

// ── Sidebar ───────────────────────────────────────────────────────
function updateSidebar() {
  if (!state) return;

  // Choose displayed civ: focused or first alive
  const civ = focusCiv() || state.civs[0];
  if (!civ) return;

  document.getElementById("active-civ-name").textContent = civ.name;
  document.getElementById("active-civ-name").style.color = civ.color;

  // Aggregate population
  const totalPop = state.cities
    .filter(c => c.civ_id === civ.id)
    .reduce((s, c) => s + c.population, 0);

  document.getElementById("st-pop").textContent = (totalPop * 10000).toLocaleString();
  document.getElementById("st-year").textContent = state.year;
  document.getElementById("st-gold").textContent = `${civ.gold}⚙`;
  document.getElementById("st-rates").textContent = `${civ.tax_rate} / ${civ.science_rate}`;

  const research = civ.current_research
    ? civ.current_research.replace(/_/g, " ").toUpperCase()
    : "NONE";
  const sciPct = civ.science_needed > 0
    ? Math.round(civ.science_stored / civ.science_needed * 100)
    : 0;
  document.getElementById("st-research").textContent =
    civ.current_research ? `${research} (${sciPct}%)` : "—";

  document.getElementById("st-turn").textContent = state.turn;

  // Civ list
  const civList = document.getElementById("civ-list");
  civList.innerHTML = "";
  for (const c of state.civs) {
    if (!c.is_alive) continue;
    const row = document.createElement("div");
    row.className = "civ-row";
    if (c.id === (focusCivId || (state.civs[0] && state.civs[0].id))) {
      row.style.background = "#2a3a50";
    }
    row.innerHTML = `
      <div class="civ-dot" style="background:${c.color}"></div>
      <div class="civ-row-name">${c.name}</div>
      <div class="civ-row-cities">${c.num_cities}🏙 ${c.num_units}⚔</div>
    `;
    row.addEventListener("click", () => {
      focusCivId = c.id;
      focusOnCiv(c.id);
      updateSidebar();
    });
    civList.appendChild(row);
  }


  // Game over
  if (state.is_over) {
    document.getElementById("sidebar-footer").textContent = "GAME OVER";
    document.getElementById("sidebar-footer").style.color = "#f0cc44";
  }
}

function focusCiv() {
  if (!state) return null;
  if (focusCivId) return state.civs.find(c => c.id === focusCivId) || null;
  return state.civs.find(c => c.is_alive) || null;
}

function civColor(civName) {
  if (!state) return "#aaa";
  const c = state.civs.find(c => c.name === civName);
  return c ? c.color : "#aaa";
}

function buildCivMap() {
  const m = {};
  if (state) for (const c of state.civs) m[c.id] = c;
  return m;
}

function focusOnCiv(civId) {
  // Scroll to first city of this civ
  const city = state && state.cities.find(c => c.civ_id === civId);
  if (!city) return;
  const vw = viewport.clientWidth;
  const vh = viewport.clientHeight;
  viewX = Math.max(0, Math.min(state.map_width  - Math.ceil(vw / TILE), city.x - Math.ceil(vw / TILE / 2)));
  viewY = Math.max(0, Math.min(state.map_height - Math.ceil(vh / TILE), city.y - Math.ceil(vh / TILE / 2)));
  render();
}

// ── Minimap click → scroll ────────────────────────────────────────
miniCanvas.addEventListener("click", (e) => {
  if (!state) return;
  const rect = miniCanvas.getBoundingClientRect();
  const mx = (e.clientX - rect.left) / MINI;
  const my = (e.clientY - rect.top)  / MINI;
  const vw = viewport.clientWidth;
  const vh = viewport.clientHeight;
  viewX = Math.max(0, Math.min(state.map_width  - Math.ceil(vw / TILE), Math.floor(mx) - Math.ceil(vw / TILE / 2)));
  viewY = Math.max(0, Math.min(state.map_height - Math.ceil(vh / TILE), Math.floor(my) - Math.ceil(vh / TILE / 2)));
  render();
});

// ── Keyboard scrolling ────────────────────────────────────────────
document.addEventListener("keydown", (e) => {
  if (!state) return;
  const vw = viewport.clientWidth;
  const vh = viewport.clientHeight;
  const maxY = state.map_height - Math.ceil(vh / TILE);
  const mw   = state.map_width;

  switch (e.key) {
    case "ArrowLeft":  viewX = ((viewX - SCROLL_SPEED) % mw + mw) % mw; break;
    case "ArrowRight": viewX = (viewX + SCROLL_SPEED) % mw; break;
    case "ArrowUp":    viewY = Math.max(0,    viewY - SCROLL_SPEED); break;
    case "ArrowDown":  viewY = Math.min(maxY, viewY + SCROLL_SPEED); break;
    default: return;
  }
  e.preventDefault();
  render();
});

// ── Mouse drag scrolling ──────────────────────────────────────────
let drag = null;

// Prevent timeline clicks/drags from bubbling up and starting a map drag
document.getElementById("timeline").addEventListener("mousedown", (e) => {
  e.stopPropagation();
});

viewport.addEventListener("mousedown", (e) => {
  drag = { startX: e.clientX, startY: e.clientY, ox: viewX, oy: viewY };
});

document.addEventListener("mousemove", (e) => {
  if (!drag || !state) return;
  const dx = Math.round((drag.startX - e.clientX) / TILE);
  const dy = Math.round((drag.startY - e.clientY) / TILE);
  const vw = viewport.clientWidth;
  const vh = viewport.clientHeight;
  const mw = state.map_width;
  viewX = ((drag.ox + dx) % mw + mw) % mw;
  viewY = Math.max(0, Math.min(state.map_height - Math.ceil(vh / TILE), drag.oy + dy));
  render();
});

document.addEventListener("mouseup", () => { drag = null; });

// ── Tooltip ───────────────────────────────────────────────────────
let _lastMouseEvent = null;   // last MouseEvent over the viewport

// ── Stats ─────────────────────────────────────────────────────────
let _techList  = [];   // loaded once from /api/techs
let _statsOpen = false;

async function _loadTechs() {
  try {
    const r = await fetch("/api/techs");
    const d = await r.json();
    _techList = d.techs || [];
  } catch (e) { console.warn("Could not load tech list", e); }
}

function _toggleStats() {
  _statsOpen = !_statsOpen;
  document.getElementById("stats-panel").style.display = _statsOpen ? "flex" : "none";
  if (_statsOpen) _renderStats();
}

function _renderStats() {
  if (!_statsOpen || !state) return;

  // Update turn label in header
  document.getElementById("stats-turn-label").textContent =
    `Turn ${state.turn}  —  ${state.year}`;

  const content = document.getElementById("stats-content");

  // Group units by civ
  const unitsByCiv = {};
  for (const u of state.units) {
    if (!unitsByCiv[u.civ_id]) unitsByCiv[u.civ_id] = [];
    unitsByCiv[u.civ_id].push(u);
  }
  // Population by civ (sum city populations)
  const popByCiv = {};
  for (const c of state.cities) {
    popByCiv[c.civ_id] = (popByCiv[c.civ_id] || 0) + c.population;
  }

  let html = "";

  for (const civ of state.civs) {
    const units    = unitsByCiv[civ.id] || [];
    const pop      = popByCiv[civ.id]   || 0;
    const deadCls  = civ.is_alive ? "" : " civ-card-dead";

    // ── Card ──────────────────────────────────────────────────────
    html += `<div class="civ-card${deadCls}" style="border-top:3px solid ${civ.color}">`;

    // Name
    html += `<div class="civ-card-name" style="color:${civ.color}">`
          + `${civ.name}${civ.is_alive ? "" : " ☠"}</div>`;

    // Summary
    html += `<div class="stat-block">`;
    html += `<div class="stat-row"><span class="stat-lbl">Population</span><span class="stat-val">${pop}</span></div>`;
    html += `<div class="stat-row"><span class="stat-lbl">Cities</span><span class="stat-val">${civ.num_cities}</span></div>`;
    html += `<div class="stat-row"><span class="stat-lbl">Units</span><span class="stat-val">${civ.num_units}</span></div>`;
    html += `<div class="stat-row"><span class="stat-lbl">Gold</span><span class="stat-val">${civ.gold}</span></div>`;
    html += `</div>`;

    // Unit breakdown
    const typeCount = {};
    for (const u of units) typeCount[u.name] = (typeCount[u.name] || 0) + 1;
    const types = Object.entries(typeCount).sort((a, b) => a[0].localeCompare(b[0]));
    if (types.length) {
      html += `<div class="unit-block">`;
      html += `<div class="unit-block-title">Units</div>`;
      for (const [name, cnt] of types)
        html += `<div class="unit-row"><span>${name}</span><span class="unit-count">×${cnt}</span></div>`;
      html += `</div>`;
    }

    // Tech list
    if (_techList.length) {
      const researched = new Set(civ.researched_techs || []);
      let currentEra = null;
      html += `<div class="tech-block">`;
      for (const tech of _techList) {
        if (tech.era !== currentEra) {
          currentEra = tech.era;
          html += `<div class="tech-era">${tech.era}</div>`;
        }
        const known = researched.has(tech.key);
        if (known) {
          html += `<div class="tech-chip tech-known" `
                + `style="background:${civ.color}22;border-color:${civ.color}66;color:${civ.color}" `
                + `title="${tech.description}">● ${tech.name}</div>`;
        } else {
          html += `<div class="tech-chip tech-unknown" title="${tech.description}">○ ${tech.name}</div>`;
        }
      }
      html += `</div>`;
    }

    html += `</div>`;  // .civ-card
  }

  content.innerHTML = html;
}

// ── Tooltip helpers ───────────────────────────────────────────────

/** Group units by type, return HTML with sprite icons and counts.
 *  Units are tinted with their civ colour. */
function _ttUnitGroup(units) {
  const groups = {};
  for (const u of units) {
    if (!groups[u.type]) groups[u.type] = { name: u.name, count: 0, civ_id: u.civ_id };
    groups[u.type].count++;
  }
  const entries = Object.entries(groups);
  if (!entries.length) return "";
  let html = `<div class="tt-units">`;
  for (const [type, g] of entries) {
    const civ   = state.civs.find(c => c.id === g.civ_id);
    const color = civ ? civ.color : "#aaaaaa";
    const icon  = `<img class="tt-unit-icon" src="/resources/unit/${type}.png" `
                + `alt="${g.name}" style="background:${color}" `
                + `onerror="this.style.display='none'">`;
    html += `<div class="tt-unit-entry">${icon} ${g.name}`;
    if (g.count > 1) html += ` <b>×${g.count}</b>`;
    html += `</div>`;
  }
  html += `</div>`;
  return html;
}

/** Net value coloring: green +, red -, grey 0. */
function _ttNetColor(n) {
  return n > 0 ? "#66cc66" : n < 0 ? "#cc4444" : "#778";
}
function _ttSign(n) { return n >= 0 ? `+${n}` : `${n}`; }

/** Build the full city tooltip HTML. */
function _buildCityTooltip(city) {
  const civ      = state.civs.find(c => c.id === city.civ_id);
  const civColor = civ ? civ.color : "#aaaaaa";

  let html = "";

  // ── Header ────────────────────────────────────────────────────────
  html += `<div class="tt-city-name" style="color:${civColor}">🏙 ${city.name}</div>`;
  html += `<div class="tt-city-sub">${civ ? civ.name : "?"} &nbsp;·&nbsp; Population ${city.population}</div>`;

  // ── Food ──────────────────────────────────────────────────────────
  const fg   = city.food_gross             ?? (city.food_per_turn + city.population * 2);
  // Use server-provided breakdown when available (food_from_tiles > 0 means it was computed)
  const fgT  = (city.food_from_tiles  > 0) ? city.food_from_tiles  : fg;
  const fgB  = (city.food_from_tiles  > 0) ? city.food_from_buildings : 0;
  const fc   = city.food_consumed_citizens ?? city.population * 2;
  const fw   = city.food_consumed_workers  ?? 0;
  const fn   = city.food_per_turn          ?? 0;
  const fSt  = city.food_stored            ?? 0;
  const fNd  = city.food_needed            ?? (20 + city.population * 10);
  const fPc  = fNd > 0 ? Math.min(100, Math.round(fSt / fNd * 100)) : 0;

  html += `<div class="tt-section">`;
  html += `<div class="tt-section-title">🌾 Food <span style="float:right;color:${_ttNetColor(fn)}">${_ttSign(fn)}</span></div>`;
  html += `<div class="tt-row tt-sub"><span>Tiles</span><span style="color:#66cc66">+${fgT}</span></div>`;
  if (fgB > 0)
    html += `<div class="tt-row tt-sub"><span>Buildings</span><span style="color:#66cc66">+${fgB}</span></div>`;
  html += `<div class="tt-row"><span>Citizens (${city.population})</span><span style="color:#cc7755">−${fc}</span></div>`;
  if (fw > 0)
    html += `<div class="tt-row"><span>Workers (${fw})</span><span style="color:#cc7755">−${fw}</span></div>`;
  html += `<div class="tt-bar-label">Growth: ${fSt} / ${fNd} &nbsp;(${fPc}%)</div>`;
  html += `<div class="tt-bar tt-bar-food"><div class="tt-bar-fill" style="width:${fPc}%"></div></div>`;
  html += `</div>`;

  // ── Production ────────────────────────────────────────────────────
  const pg   = city.prod_gross          ?? (city.production_per_turn + (city.unit_upkeep ?? 0));
  const pgT  = (city.prod_from_tiles  > 0) ? city.prod_from_tiles  : pg;
  const pgB  = (city.prod_from_tiles  > 0) ? city.prod_from_buildings : 0;
  const pu   = city.unit_upkeep         ?? 0;
  const pn   = city.production_per_turn ?? 0;
  const pSt  = city.production_stored   ?? 0;

  html += `<div class="tt-section">`;
  html += `<div class="tt-section-title">⚙ Production <span style="float:right;color:${_ttNetColor(pn)}">${_ttSign(pn)}</span></div>`;
  html += `<div class="tt-row tt-sub"><span>Tiles</span><span style="color:#ffaa44">+${pgT}</span></div>`;
  if (pgB > 0)
    html += `<div class="tt-row tt-sub"><span>Buildings</span><span style="color:#ffaa44">+${pgB}</span></div>`;
  if (pu > 0)
    html += `<div class="tt-row"><span>Unit upkeep (${pu})</span><span style="color:#cc7755">−${pu}</span></div>`;
  if (city.production_order) {
    const po   = city.production_order;
    const pPc  = po.cost > 0 ? Math.min(100, Math.round(pSt / po.cost * 100)) : 100;
    const name = po.key.replace(/_/g, " ");
    const lbl  = po.type === "unit" ? "Unit" : "Building";
    html += `<div class="tt-bar-label">${lbl}: <b>${name}</b> &nbsp;${pSt} / ${po.cost} &nbsp;(${pPc}%)</div>`;
    html += `<div class="tt-bar tt-bar-prod"><div class="tt-bar-fill" style="width:${pPc}%"></div></div>`;
  } else {
    html += `<div class="tt-idle">No production order</div>`;
  }
  html += `</div>`;

  // ── Units in city ─────────────────────────────────────────────────
  const inCity = state.units.filter(u => u.x === city.x && u.y === city.y);
  if (inCity.length) {
    html += `<div class="tt-section">`;
    html += `<div class="tt-section-title">Units in city (${inCity.length})</div>`;
    html += _ttUnitGroup(inCity);
    html += `</div>`;
  }

  // ── Maintained units ──────────────────────────────────────────────
  const maintained = state.units.filter(u => u.home_city_id === city.id);
  if (maintained.length) {
    html += `<div class="tt-section">`;
    html += `<div class="tt-section-title">Maintained units (${maintained.length}) &nbsp;·&nbsp; upkeep ${pu}</div>`;
    html += _ttUnitGroup(maintained);
    html += `</div>`;
  }

  // ── Buildings ─────────────────────────────────────────────────────
  if (city.buildings && city.buildings.length) {
    const sorted = [...city.buildings].sort();
    html += `<div class="tt-section">`;
    html += `<div class="tt-section-title">🏛 Buildings (${sorted.length})</div>`;
    html += `<div class="tt-building-list">`;
    for (const b of sorted)
      html += `<div class="tt-building-entry">${b.replace(/_/g, " ")}</div>`;
    html += `</div>`;
    html += `</div>`;
  }

  return html;
}

function _refreshTooltip() {
  const e = _lastMouseEvent;
  if (!e || !state || drag) { tooltip.style.display = "none"; return; }

  const rect = viewport.getBoundingClientRect();
  const mw   = state.map_width;
  const tx   = ((Math.floor((e.clientX - rect.left) / TILE) + viewX) % mw + mw) % mw;
  const ty   = Math.floor((e.clientY - rect.top)  / TILE) + viewY;

  if (ty < 0 || ty >= state.map_height) { tooltip.style.display = "none"; return; }

  const terrain  = state.terrain[ty][tx];
  const resource = state.resources[ty][tx];
  const city     = state.cities.find(c => c.x === tx && c.y === ty);
  const units    = state.units.filter(u => u.x === tx && u.y === ty);

  // Sync hovered city (triggers re-render if changed)
  const newHoveredCityId = city ? city.id : null;
  if (newHoveredCityId !== hoveredCityId) {
    hoveredCityId = newHoveredCityId;
    render();
  }

  // ── City tile → rich panel ─────────────────────────────────────────
  if (city) {
    tooltip.className     = "tt-city-mode";
    tooltip.innerHTML     = _buildCityTooltip(city);
    tooltip.style.display = "block";
    // Position: keep tooltip on-screen
    const ttW = 300, ttH = 400;
    const vW  = rect.width, vH = rect.height;
    const mx  = e.clientX - rect.left, my = e.clientY - rect.top;
    const left = mx + ttW + 18 > vW ? mx - ttW - 4 : mx + 14;
    const top  = my + ttH     > vH ? Math.max(0, my - ttH) : my + 14;
    tooltip.style.left = left + "px";
    tooltip.style.top  = top  + "px";
    return;
  }

  // ── Regular tile ──────────────────────────────────────────────────
  tooltip.className = "";
  let html = `<b>${terrain}</b> (${tx},${ty})`;
  if (resource && resource !== "none") html += `<br>Resource: ${resource.replace(/_/g, " ")}`;

  if (state.tile_yields) {
    const [tyFood, tyProd, tyTrade] = state.tile_yields[ty][tx];
    html += `<br>&#x1F33E;${tyFood} &nbsp;&#x2699;${tyProd} &nbsp;&#x1F4B0;${tyTrade}`;
  }
  const improvements = [];
  if (state.irrigation && state.irrigation[ty][tx]) improvements.push("Irrigation");
  if (state.mines     && state.mines[ty][tx])      improvements.push("Mine");
  if (state.roads     && state.roads[ty][tx])      improvements.push("Road");
  if (improvements.length) html += `<br><i>${improvements.join(", ")}</i>`;

  if (units.length)
    html += `<br>Units: ${units.map(u => u.name).join(", ")}`;

  tooltip.innerHTML      = html;
  tooltip.style.display  = "block";
  tooltip.style.left     = (e.clientX - rect.left + 14) + "px";
  tooltip.style.top      = (e.clientY - rect.top  + 14) + "px";
}

viewport.addEventListener("mousemove", (e) => {
  _lastMouseEvent = e;
  _refreshTooltip();
});

viewport.addEventListener("mouseleave", () => {
  _lastMouseEvent = null;
  tooltip.style.display = "none";
  if (hoveredCityId !== null) { hoveredCityId = null; render(); }
});

// ── Buttons ───────────────────────────────────────────────────────
document.getElementById("btn-new-game").addEventListener("click", () => {
  const seed = Math.floor(Math.random() * 100000);
  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify({ action: "new_game", seed }));
  }
  // _resetHistory() + log/focus reset will fire automatically when the server
  // sends back the new state with a different game_id.
});

document.getElementById("btn-stats").addEventListener("click", _toggleStats);
document.getElementById("btn-close-stats").addEventListener("click", _toggleStats);

document.getElementById("btn-copy-state").addEventListener("click", () => {
  if (!state) return;
  const btn = document.getElementById("btn-copy-state");
  navigator.clipboard.writeText(JSON.stringify(state, null, 2))
    .then(() => {
      btn.textContent = "✔ Copied!";
      setTimeout(() => { btn.textContent = "📋 Copy state"; }, 1500);
    })
    .catch(() => {
      btn.textContent = "✖ Failed";
      setTimeout(() => { btn.textContent = "📋 Copy state"; }, 1500);
    });
});

document.getElementById("speed-slider").addEventListener("input", (e) => {
  const speed = parseFloat(e.target.value);   // 0.5 … 5  (higher = faster)
  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify({ action: "set_speed", speed }));
  }
});

// ── Pause / Resume ────────────────────────────────────────────────
let _gamePaused = false;
document.getElementById("btn-pause").addEventListener("click", () => {
  _gamePaused = !_gamePaused;
  const btn = document.getElementById("btn-pause");
  btn.textContent = _gamePaused ? "▶ Resume" : "⏸ Pause";
  btn.classList.toggle("paused", _gamePaused);
  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify({ action: "set_paused", paused: _gamePaused }));
  }
});

// Send initial speed to server once the socket opens (handled inside connect())


// ── Resize ────────────────────────────────────────────────────────
window.addEventListener("resize", () => render());

// ── Boot ──────────────────────────────────────────────────────────
showOverlay("CONNECTING…");
_loadTechs();
connect();
