# Server Documentation

## Concept
The server is a small FastAPI backend that sits between the rover side and the dashboard. It stores the latest setup data and latest live rover data, exposes them over HTTP, and also pushes updates over WebSocket.

## Files By Category

### Backend file
- `Server/Server.py`
 - FastAPI app, HTTP routes, WebSocket route, and in-memory live/setup storage.

### Rover-side related file
- `MarsRover/RoverLogger.py`
 - Client-side sender used by the rover processes to publish data to the backend.

## Main Components

### FastAPI app
Main backend application object.

- role:
 - Handles HTTP and WebSocket communication.
 - Stores the latest rover state in memory.
 - Broadcasts new setup/live packets to connected clients.

- stored data:
 - `latest_data`: latest live rover payload `[dict[str, Any]]`
 - `setup_data`: latest setup/config payload `[dict[str, Any]]`

### class ConnectionManager
Simple connection list manager for active WebSocket clients.

- important variables:
 - `connections`: connected websocket clients `[list[WebSocket]]`

- functions:
 - `connect(self, ws: WebSocket)`
  - Accepts a websocket connection and stores it.
 - `disconnect(self, ws: WebSocket)`
  - Removes a websocket from the active list.
 - `send(self, ws: WebSocket, data: dict[str, Any])`
  - Sends one JSON packet to one websocket.
 - `broadcast(self, data: dict[str, Any], exclude: WebSocket | None = None)`
  - Sends one JSON packet to all connected clients, optionally skipping one source socket.

## HTTP Endpoints

- `GET /get_data`
 - Returns the latest live rover payload.

- `GET /get_setup`
 - Returns the latest setup payload.

- `POST /send_data`
 - Replaces the current live rover payload and broadcasts it as a `live` event.

- `POST /send_setup`
 - Replaces the current setup payload and broadcasts it as a `setup` event.

## WebSocket Endpoint

- `WS /ws`
 - Accepts dashboard or producer websocket connections.
 - Sends a `snapshot` packet immediately after connect.
 - Accepts `ping` and returns `pong`.
 - Accepts `snapshot` and returns the current setup + live state.
 - Accepts JSON packets with `type` + `payload`.
 - Supported packet types:
  - `live` / `publish_live`
   - Updates live rover data and broadcasts it to the other clients.
  - `setup` / `publish_setup`
   - Updates setup data and broadcasts it to the other clients.

## Main Functions

- `get_data()`
 - FastAPI route handler for the latest live data.

- `get_setup()`
 - FastAPI route handler for the latest setup data.

- `send_data(data)`
 - FastAPI route handler that stores and broadcasts live rover data.

- `send_setup(data)`
 - FastAPI route handler that stores and broadcasts setup data.

- `ws_endpoint(ws)`
 - Main websocket route handler for snapshots, pings, and pushed updates.

## Usage

- Start the backend by running `Server/Server.py`.
- Rover-side scripts can send setup/live data through `RoverLogger`.
- Dashboard clients can:
 - poll `GET /get_setup` and `GET /get_data`
 - or connect to `WS /ws` for live pushed updates
