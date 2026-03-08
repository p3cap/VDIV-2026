"""

Main server meant to be run to connect the rover with the frontend.

Uses: Fastapi Websocket

"""

from datetime import datetime, timezone
import json
from typing import Any

import uvicorn
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

latest_data: dict[str, Any] = {}
setup_data: dict[str, Any] = {}

def _event(event_type: str, payload: Any) -> dict[str, Any]:
    return {"type": event_type, "timestamp": datetime.now(timezone.utc).isoformat(), "payload": payload}

class ConnectionManager:
    def __init__(self):
        self.connections: list[WebSocket] = []

    async def connect(self, ws: WebSocket) -> None:
        await ws.accept()
        self.connections.append(ws)

    def disconnect(self, ws: WebSocket) -> None:
        if ws in self.connections:
            self.connections.remove(ws)

    async def send(self, ws: WebSocket, data: dict[str, Any]) -> None:
        await ws.send_json(data)

    async def broadcast(
        self,
        data: dict[str, Any],
        exclude: WebSocket | None = None,
    ) -> None:
        disconnected: list[WebSocket] = []
        for ws in list(self.connections):
            if exclude is not None and ws is exclude:
                continue
            try:
                await ws.send_json(data)
            except Exception:
                disconnected.append(ws)

        for ws in disconnected:
            self.disconnect(ws)


manager = ConnectionManager()


# Runtime data
@app.get("/get_data")
async def get_data() -> dict[str, Any]:
    return latest_data


# Setup config
@app.get("/get_setup")
async def get_setup() -> dict[str, Any]:
    return setup_data


# Update runtime data from any external producer script.
# Example:
#   import requests
#   base_url = "http://127.0.0.1:8000"
#   requests.post(
#       f"{base_url}/send_data",
#       json={
#           "rover_position": {"x": 4, "y": 7},
#           "path_plan": [{"x": 1, "y": 0}, {"x": 0, "y": 1}],
#           "status": "MOVE",
#           "rover_battery": 86.5,
#       },
#       timeout=3,
#   )
@app.post("/send_data")
async def send_data(data: dict[str, Any]) -> dict[str, str]:
    global latest_data
    latest_data = data
    await manager.broadcast(_event("live", latest_data))
    return {"status": "ok"}


# Update setup config from any external producer script.
# Example:
#   import requests
#   base_url = "http://127.0.0.1:8000"
#   requests.post(
#       f"{base_url}/send_setup",
#       json={"map_matrix": [["S", "S"], ["S", "B"]]},
#       timeout=3,
#   )
@app.post("/send_setup")
async def send_setup(data: dict[str, Any]) -> dict[str, str]:
    global setup_data
    setup_data = data
    await manager.broadcast(_event("setup", setup_data))
    return {"status": "setup updated"}


@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket) -> None:
    # Producer-side websocket example:
    #   from websockets.sync.client import connect
    #   import json
    #   with connect("ws://127.0.0.1:8000/ws") as c:
    #       c.send(json.dumps({
    #           "type": "live",
    #           "payload": {"rover_position": {"x": 2, "y": 3}, "path_plan": []}
    #       }))
    global latest_data, setup_data
    await manager.connect(ws)
    try:
        await manager.send(
            ws,
            _event("snapshot", {"setup": setup_data, "live": latest_data}),
        )
        while True:
            # Keep the socket alive and allow optional client pings.
            msg = (await ws.receive_text()).strip()
            if msg.lower() == "ping":
                await manager.send(ws, _event("pong", {}))
                continue
            if msg.lower() == "snapshot":
                await manager.send(
                    ws,
                    _event("snapshot", {"setup": setup_data, "live": latest_data}),
                )
                continue

            try:
                packet = json.loads(msg)
            except json.JSONDecodeError:
                await manager.send(ws, _event("error", {"reason": "invalid_json"}))
                continue

            if not isinstance(packet, dict):
                await manager.send(ws, _event("error", {"reason": "invalid_packet"}))
                continue

            event_type = str(packet.get("type", "")).lower().strip()
            payload = packet.get("payload", {})
            if not isinstance(payload, dict):
                payload = {}

            if event_type in {"live", "publish_live"}:
                latest_data = payload
                await manager.broadcast(_event("live", latest_data), exclude=ws)
                continue

            if event_type in {"setup", "publish_setup"}:
                setup_data = payload
                await manager.broadcast(_event("setup", setup_data), exclude=ws)
                continue

            await manager.send(ws, _event("error", {"reason": "unsupported_type"}))
    except WebSocketDisconnect:
        manager.disconnect(ws)
    except Exception:
        manager.disconnect(ws)


if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
