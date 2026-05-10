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
  ocean:     "#1e6eb4",
  coast:     "#3088cc",
  grassland: "#44aa44",
  plains:    "#88c848",
  forest:    "#246624",
  hills:     "#8a6028",
  mountains: "#686868",
  desert:    "#d4b040",
  tundra:    "#7a98a8",
  arctic:    "#c8dce8",
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

// Unit sprites — discovered at runtime so dropping a new PNG is enough
fetch("/api/unit-sprites")
  .then(r => r.json())
  .then(({ sprites }) => {
    for (const key of sprites) {
      _loadSprite(key, `/resources/units/${key}.png`);
    }
  });

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
let showGrid = false;
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
function _unitDrawPos(unit) {
  const anim = _unitAnims[unit.id];
  if (!anim) return [unit.x * TILE + 2, unit.y * TILE + 2];
  const t    = Math.min(1, (performance.now() - anim.t0) / ANIM_DURATION);
  const ease = 1 - Math.pow(1 - t, 3);   // ease-out cubic
  return [
    anim.fx + (anim.tx - anim.fx) * ease,
    anim.fy + (anim.ty - anim.fy) * ease,
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
        fx: p.x * TILE + 2, fy: p.y * TILE + 2,
        tx: u.x * TILE + 2, ty: u.y * TILE + 2,
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
  };

  ws.onmessage = (e) => {
    const newState = JSON.parse(e.data);

    // ── Detect new game or server restart via game_id ──────────────
    if (newState.game_id !== _gameId) {
      _gameId = newState.game_id;
      _resetHistory();
      document.getElementById("event-log").innerHTML = "";
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
    tlSlider.value        = _maxTurn;
    tlTurnEl.textContent  = `Turn ${_maxTurn}`;
    updateSidebar();

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
  const totalW = state.map_width  * TILE;
  const totalH = state.map_height * TILE;
  if (mapCanvas.width !== totalW || mapCanvas.height !== totalH) {
    mapCanvas.width  = totalW;
    mapCanvas.height = totalH;
  }
  mapCanvas.style.transform = `translate(${-viewX * TILE}px, ${-viewY * TILE}px)`;
}

/**
 * Draw one frame.  Does NOT resize the canvas — call _ensureCanvasSize()
 * first if the canvas might be stale.  Safe to call from RAF.
 */
function _renderFrame() {
  if (!state) return;

  const vw = viewport.clientWidth;
  const vh = viewport.clientHeight;

  // Visible tile range (with a 2-tile buffer so animating units don't pop)
  const x0 = Math.max(0, viewX - 2);
  const y0 = Math.max(0, viewY - 2);
  const x1 = Math.min(state.map_width,  viewX + Math.ceil(vw / TILE) + 3);
  const y1 = Math.min(state.map_height, viewY + Math.ceil(vh / TILE) + 3);

  drawTerrain(x0, y0, x1, y1);
  drawResources(x0, y0, x1, y1);
  drawCityTerritories();
  if (showGrid) drawGrid(x0, y0, x1, y1);
  drawUnits();    // units first — cities and names render on top
  drawCities();
  drawMinimap();
}

function drawTerrain(x0, y0, x1, y1) {
  for (let y = y0; y < y1; y++) {
    for (let x = x0; x < x1; x++) {
      const terrain = state.terrain[y][x];
      const col = ((x + y) % 2 === 0) ? TERRAIN_COLOR[terrain] : TERRAIN_COLOR2[terrain];
      mapCtx.fillStyle = col || "#333";
      mapCtx.fillRect(x * TILE, y * TILE, TILE, TILE);

      // Road indicator
      if (state.roads[y][x]) {
        mapCtx.fillStyle = "#b8a060aa";
        mapCtx.fillRect(x * TILE + TILE/2 - 2, y * TILE, 4, TILE);
        mapCtx.fillRect(x * TILE, y * TILE + TILE/2 - 2, TILE, 4);
      }
    }
  }
}

function drawResources(x0, y0, x1, y1) {
  for (let y = y0; y < y1; y++) {
    for (let x = x0; x < x1; x++) {
      const res = state.resources[y][x];
      if (!res || res === "none") continue;
      const col = RESOURCE_COLOR[res] || "#ffffff";
      const cx = x * TILE + TILE / 2;
      const cy = y * TILE + TILE / 2;
      mapCtx.beginPath();
      mapCtx.arc(cx, cy, 4, 0, Math.PI * 2);
      mapCtx.fillStyle = col;
      mapCtx.fill();
      mapCtx.strokeStyle = "#00000066";
      mapCtx.lineWidth = 1;
      mapCtx.stroke();
    }
  }
}

function drawGrid(x0, y0, x1, y1) {
  mapCtx.strokeStyle = "#00000033";
  mapCtx.lineWidth = 0.5;
  for (let x = x0; x <= x1; x++) {
    mapCtx.beginPath();
    mapCtx.moveTo(x * TILE, y0 * TILE);
    mapCtx.lineTo(x * TILE, y1 * TILE);
    mapCtx.stroke();
  }
  for (let y = y0; y <= y1; y++) {
    mapCtx.beginPath();
    mapCtx.moveTo(x0 * TILE, y * TILE);
    mapCtx.lineTo(x1 * TILE, y * TILE);
    mapCtx.stroke();
  }
}

function drawCityTerritories() {
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
    mapCtx.fillRect(tx * TILE, ty * TILE, TILE, TILE);
  }
  mapCtx.restore();

  mapCtx.save();
  mapCtx.globalAlpha = 0.75;
  mapCtx.strokeStyle = color;
  mapCtx.lineWidth = 2;
  for (const [tx, ty] of city.worked_tiles) {
    mapCtx.strokeRect(tx * TILE + 1, ty * TILE + 1, TILE - 2, TILE - 2);
  }
  mapCtx.restore();
}

function drawCities() {
  const civMap   = buildCivMap();
  const citySprite = _sprites["city"];   // HTMLImageElement | "loading" | null

  for (const city of state.cities) {
    const civ   = civMap[city.civ_id];
    const color = civ ? civ.color : "#aaaaaa";
    const cx    = city.x * TILE;
    const cy    = city.y * TILE;

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
  const civMap = buildCivMap();

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

    // Use animated (interpolated) pixel position
    const [ux, uy] = _unitDrawPos(u);

    _drawUnitTile(mapCtx, u, color, ux, uy, sz);

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
  const mw = state.map_width * MINI;
  const mh = state.map_height * MINI;
  miniCanvas.width  = mw;
  miniCanvas.height = mh;

  const civMap = buildCivMap();

  // Terrain
  for (let y = 0; y < state.map_height; y++) {
    for (let x = 0; x < state.map_width; x++) {
      miniCtx.fillStyle = TERRAIN_COLOR[state.terrain[y][x]] || "#333";
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

  // Viewport rect
  const vw = viewport.clientWidth;
  const vh = viewport.clientHeight;
  const tilesX = Math.ceil(vw / TILE);
  const tilesY = Math.ceil(vh / TILE);

  miniCtx.strokeStyle = "#ffffff88";
  miniCtx.lineWidth = 1;
  miniCtx.strokeRect(
    viewX * MINI, viewY * MINI,
    tilesX * MINI, tilesY * MINI
  );
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

  // Events
  const log = document.getElementById("event-log");
  const evHtml = [...state.events].reverse().map(e =>
    `<div class="event-entry"><span class="ev-civ" style="color:${civColor(e.civ)}">${e.civ}:</span> ${e.message}</div>`
  ).join("");
  if (evHtml) log.innerHTML = evHtml + log.innerHTML;

  // Trim log
  while (log.children.length > 80) log.removeChild(log.lastChild);

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
  const maxX = state.map_width  - Math.ceil(vw / TILE);
  const maxY = state.map_height - Math.ceil(vh / TILE);

  switch (e.key) {
    case "ArrowLeft":  viewX = Math.max(0,    viewX - SCROLL_SPEED); break;
    case "ArrowRight": viewX = Math.min(maxX, viewX + SCROLL_SPEED); break;
    case "ArrowUp":    viewY = Math.max(0,    viewY - SCROLL_SPEED); break;
    case "ArrowDown":  viewY = Math.min(maxY, viewY + SCROLL_SPEED); break;
    default: return;
  }
  e.preventDefault();
  render();
});

// ── Mouse drag scrolling ──────────────────────────────────────────
let drag = null;

viewport.addEventListener("mousedown", (e) => {
  drag = { startX: e.clientX, startY: e.clientY, ox: viewX, oy: viewY };
});

document.addEventListener("mousemove", (e) => {
  if (!drag || !state) return;
  const dx = Math.round((drag.startX - e.clientX) / TILE);
  const dy = Math.round((drag.startY - e.clientY) / TILE);
  const vw = viewport.clientWidth;
  const vh = viewport.clientHeight;
  viewX = Math.max(0, Math.min(state.map_width  - Math.ceil(vw / TILE), drag.ox + dx));
  viewY = Math.max(0, Math.min(state.map_height - Math.ceil(vh / TILE), drag.oy + dy));
  render();
});

document.addEventListener("mouseup", () => { drag = null; });

// ── Tooltip on hover ──────────────────────────────────────────────
viewport.addEventListener("mousemove", (e) => {
  if (!state || drag) { tooltip.style.display = "none"; return; }
  const rect = viewport.getBoundingClientRect();
  const tx = Math.floor((e.clientX - rect.left) / TILE) + viewX;
  const ty = Math.floor((e.clientY - rect.top)  / TILE) + viewY;

  if (tx < 0 || ty < 0 || tx >= state.map_width || ty >= state.map_height) {
    tooltip.style.display = "none";
    return;
  }

  const terrain = state.terrain[ty][tx];
  const resource = state.resources[ty][tx];
  const city = state.cities.find(c => c.x === tx && c.y === ty);
  const units = state.units.filter(u => u.x === tx && u.y === ty);

  const newHoveredCityId = city ? city.id : null;
  if (newHoveredCityId !== hoveredCityId) {
    hoveredCityId = newHoveredCityId;
    render();
  }

  let html = `<b>${terrain}</b> (${tx},${ty})`;
  if (resource && resource !== "none") html += `<br>Resource: ${resource.replace(/_/g, " ")}`;
  if (city) {
    const civ = state.civs.find(c => c.id === city.civ_id);
    const civColor = civ ? civ.color : "#aaaaaa";
    html += `<br><span style="color:${civColor}">&#x1F3D9; <b>${city.name}</b></span> &mdash; ${civ ? civ.name : "?"}`;
    html += `<br>Pop: ${city.population}`;

    const fpt  = city.food_per_turn ?? "?";
    const fsto = city.food_stored   ?? 0;
    const fned = city.food_needed   ?? (20 + city.population * 10);
    html += `<br>&#x1F33E; Food: ${fsto}/${fned} (+${fpt}/turn)`;

    const ppt     = city.production_per_turn ?? "?";
    const psto    = city.production_stored   ?? 0;
    const upkeep  = city.unit_upkeep         ?? 0;
    const upkeepStr = upkeep > 0 ? ` <span style="color:#e07070">-${upkeep} upkeep</span>` : "";
    if (city.production_order) {
      const po  = city.production_order;
      const pct = po.cost > 0 ? Math.round(po.progress / po.cost * 100) : 100;
      const label = po.key.replace(/_/g, " ");
      html += `<br>&#x2699; Prod: ${psto}/${po.cost} (+${ppt}/turn${upkeep > 0 ? `, -${upkeep} upkeep` : ""})`;
      html += `<br>&#x1F528; ${po.type === "unit" ? "Unit" : "Building"}: ${label} (${pct}%)`;
    } else {
      html += `<br>&#x2699; Production: +${ppt}/turn${upkeep > 0 ? ` <span style="color:#e07070">(-${upkeep} upkeep)</span>` : ""} (idle)`;
    }

    if (city.buildings && city.buildings.length)
      html += `<br>&#x1F3DB; ${city.buildings.map(b => b.replace(/_/g, " ")).join(", ")}`;

    const maintained = state.units.filter(u => u.home_city_id === city.id);
    if (maintained.length)
      html += `<br>&#x2694; Units: ${maintained.map(u => u.name).join(", ")}`;
  }
  if (units.length) {
    html += `<br>Units: ${units.map(u => u.name).join(", ")}`;
  }

  tooltip.innerHTML = html;
  tooltip.style.display = "block";
  tooltip.style.left = (e.clientX - rect.left + 14) + "px";
  tooltip.style.top  = (e.clientY - rect.top  + 14) + "px";
});

viewport.addEventListener("mouseleave", () => {
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

document.getElementById("btn-toggle-grid").addEventListener("click", () => {
  showGrid = !showGrid;
  render();
});

document.getElementById("speed-slider").addEventListener("input", (e) => {
  // Communicate desired interval to server (for future use)
  // For now, we just note it; the server controls TURN_INTERVAL_SECONDS
});

// ── Resize ────────────────────────────────────────────────────────
window.addEventListener("resize", () => render());

// ── Boot ──────────────────────────────────────────────────────────
showOverlay("CONNECTING…");
connect();
