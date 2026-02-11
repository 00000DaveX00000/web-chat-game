"""FastAPI server with WebSocket support for AI Raid Battle."""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path
from typing import Any

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

logger = logging.getLogger(__name__)

app = FastAPI(title="AI副本战")

# Paths relative to project root
_BASE_DIR = Path(__file__).resolve().parent.parent
_STATIC_DIR = _BASE_DIR / "web" / "static"


class ConnectionManager:
    """Manages active WebSocket connections and broadcasts game state."""

    def __init__(self) -> None:
        self.active_connections: list[WebSocket] = []

    async def connect(self, websocket: WebSocket) -> None:
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket) -> None:
        if websocket in self.active_connections:
            self.active_connections.remove(websocket)

    async def broadcast(self, message: dict[str, Any]) -> None:
        for connection in list(self.active_connections):
            try:
                await connection.send_json(message)
            except Exception:
                if connection in self.active_connections:
                    self.active_connections.remove(connection)


manager = ConnectionManager()
engine = None  # Injected by main.py at startup


# Static files
app.mount("/static", StaticFiles(directory=str(_STATIC_DIR)), name="static")


@app.get("/")
async def root():
    return FileResponse(str(_STATIC_DIR / "index.html"))


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await manager.connect(websocket)
    try:
        # Send current game state on connect
        if engine:
            state = engine.get_full_state()
            await websocket.send_json({"type": "state_update", "data": state})

        while True:
            data = await websocket.receive_json()
            msg_type = data.get("type")
            if msg_type == "god_command" and engine:
                content = data.get("content", "")
                engine.submit_god_command(content)
                # Broadcast the command to all clients as a log entry
                await manager.broadcast({
                    "type": "combat_log",
                    "data": {"message": f"[上帝指令] {content}", "type": "phase"},
                })
            elif msg_type == "start" and engine:
                asyncio.create_task(engine.start_game())
    except WebSocketDisconnect:
        manager.disconnect(websocket)
    except Exception:
        manager.disconnect(websocket)


@app.post("/api/start")
async def start_game():
    if engine:
        if engine.is_running:
            return {"status": "already_running"}
        asyncio.create_task(engine.start_game())
        await manager.broadcast({"type": "game_control", "data": {"action": "started"}})
        return {"status": "started"}
    return {"status": "error", "message": "engine not initialized"}


@app.post("/api/stop")
async def stop_game():
    if engine:
        engine.stop_game()
        await manager.broadcast({"type": "game_control", "data": {"action": "stopped"}})
        return {"status": "stopped"}
    return {"status": "error", "message": "engine not initialized"}


@app.post("/api/restart")
async def restart_game():
    if engine:
        engine.stop_game()
        engine.reset_game()
        asyncio.create_task(engine.start_game())
        await manager.broadcast({"type": "game_control", "data": {"action": "restarted"}})
        return {"status": "restarted"}
    return {"status": "error", "message": "engine not initialized"}


@app.get("/api/status")
async def game_status():
    if engine:
        return {
            "running": engine.is_running,
            "result": engine.result,
            "tick": engine.tick_count,
        }
    return {"running": False}


@app.post("/api/god_command")
async def god_command(content: str = ""):
    if engine:
        engine.submit_god_command(content)
        return {"status": "ok"}
    return {"status": "error", "message": "engine not initialized"}
