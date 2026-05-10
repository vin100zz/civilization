"""FastAPI server — hosts static files and drives the game loop over WebSocket.

Each connected client gets its own asyncio.Queue.  The game loop puts state
dicts into every queue; a dedicated per-client sender-task drains the queue
and writes to the socket.  This avoids concurrent send/receive on the same
WebSocket object, which is forbidden in Starlette 0.41+.
"""
from __future__ import annotations

import asyncio
import json
import logging
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Dict, Set

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles

from game.constants import TURN_INTERVAL_SECONDS
from game.game_state import GameState

log = logging.getLogger("civ")
STATIC_DIR = Path(__file__).parent / "static"
RESOURCES_DIR = Path(__file__).parent.parent / "resources"

MAX_SNAPSHOTS = 500   # how many past turns to keep in memory

# ---------------------------------------------------------------------------
# Shared game state
# ---------------------------------------------------------------------------
_game: GameState = GameState(seed=42)

# Turn number → serialised state dict  (sliding window of last MAX_SNAPSHOTS turns)
_snapshots: Dict[int, dict] = {0: _game.to_dict()}

# Per-client queues: only the sender-task for each client writes to the socket.
_queues: Dict[int, asyncio.Queue] = {}   # id(ws) -> Queue


def _store_snapshot(snap: dict) -> None:
    """Add *snap* to the history, evicting the oldest entry when full."""
    _snapshots[snap["turn"]] = snap
    if len(_snapshots) > MAX_SNAPSHOTS:
        del _snapshots[min(_snapshots)]


# ---------------------------------------------------------------------------
# Game loop
# ---------------------------------------------------------------------------

async def _game_loop() -> None:
    log.info("Game loop started (interval=%.1fs)", TURN_INTERVAL_SECONDS)
    while True:
        await asyncio.sleep(TURN_INTERVAL_SECONDS)

        # Advance the simulation — catch errors without losing snapshot storage
        try:
            if not _game.is_over:
                _game.advance_turn()
                log.debug("Turn %d (%s)", _game.turn, _game.year_string())
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("Unhandled error in advance_turn — storing current state anyway")

        # Always snapshot + broadcast, even after a partial failure
        try:
            snapshot = _game.to_dict()
            _store_snapshot(snapshot)
            if _queues:
                _enqueue_all(snapshot)
        except asyncio.CancelledError:
            raise
        except Exception:
            log.exception("Unhandled error storing/sending snapshot")


def _enqueue_all(data: dict) -> None:
    """Put data into every connected client's queue (non-blocking; skip if full)."""
    for q in list(_queues.values()):
        try:
            q.put_nowait(data)
        except asyncio.QueueFull:
            pass   # slow client — skip this frame rather than blocking


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------

@asynccontextmanager
async def lifespan(app: FastAPI):
    task = asyncio.create_task(_game_loop())
    log.info("Game task created")
    try:
        yield
    finally:
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass
        log.info("Game task stopped")


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(title="Civilization", lifespan=lifespan)
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
app.mount("/resources", StaticFiles(directory=RESOURCES_DIR), name="resources")


# ---------------------------------------------------------------------------
# HTTP routes
# ---------------------------------------------------------------------------

@app.get("/")
async def index():
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/new-game")
async def new_game(seed: int = 42):
    global _game
    _game = GameState(seed=seed)
    _snapshots.clear()
    snap = _game.to_dict()
    _store_snapshot(snap)
    _enqueue_all(snap)
    return {"status": "ok", "seed": seed}


@app.get("/api/techs")
async def get_techs():
    """Return the full ordered tech list (key, name, era, description, cost)."""
    from game.tech import _TECH_LIST
    era_order = ["ancient", "classical", "medieval", "renaissance", "industrial", "modern"]
    techs_by_era = {e: [] for e in era_order}
    for t in _TECH_LIST:
        techs_by_era.get(t.era, []).append({
            "key": t.key,
            "name": t.name,
            "era": t.era,
            "description": t.description,
            "cost": t.cost,
        })
    ordered = []
    for era in era_order:
        ordered.extend(techs_by_era[era])
    return {"techs": ordered}


@app.get("/api/unit-sprites")
async def unit_sprites():
    """Return the list of unit-type keys that have a sprite in resources/units/."""
    units_dir = RESOURCES_DIR / "units"
    keys = [p.stem for p in sorted(units_dir.glob("*.png"))]
    return {"sprites": keys}


@app.get("/snapshot/{turn}")
async def get_snapshot(turn: int):
    if turn in _snapshots:
        return _snapshots[turn]
    return JSONResponse({"error": "not found"}, status_code=404)


# ---------------------------------------------------------------------------
# WebSocket
# ---------------------------------------------------------------------------

@app.websocket("/ws")
async def websocket_endpoint(ws: WebSocket):
    await ws.accept()

    # Each client owns a small queue; the sender-task is the sole writer to ws.
    q: asyncio.Queue = asyncio.Queue(maxsize=4)
    qid = id(ws)
    _queues[qid] = q
    log.info("Client connected (%d total)", len(_queues))

    # Push current state immediately so the page loads without waiting
    await q.put(_game.to_dict())

    # Sender task: drains queue → sends to this WebSocket
    async def _sender() -> None:
        try:
            while True:
                data = await q.get()
                await ws.send_text(json.dumps(data))
        except Exception:
            pass   # connection closed; exit quietly

    sender_task = asyncio.create_task(_sender())

    # Receiver loop: handle commands sent by the client
    try:
        while True:
            raw = await ws.receive_text()
            try:
                await _handle_command(ws, q, json.loads(raw))
            except Exception:
                log.exception("Error handling client command")
    except WebSocketDisconnect:
        pass
    except Exception:
        pass
    finally:
        sender_task.cancel()
        _queues.pop(qid, None)
        log.info("Client disconnected (%d total)", len(_queues))


async def _handle_command(ws: WebSocket, q: asyncio.Queue, cmd: dict) -> None:
    global _game
    action = cmd.get("action")
    if action == "new_game":
        seed = int(cmd.get("seed", 42))
        _game = GameState(seed=seed)
        _snapshots.clear()
        snap = _game.to_dict()
        _store_snapshot(snap)
        _enqueue_all(snap)
    elif action == "get_state":
        try:
            q.put_nowait(_game.to_dict())
        except asyncio.QueueFull:
            pass
