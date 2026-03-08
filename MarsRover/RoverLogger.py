import json
from urllib.parse import urlparse

import requests
from websockets.sync.client import connect



class RoverLogger:
    def __init__(self, base_url: str, ws_path: str = "/ws", timeout: float = 3.0):
        self.base_url = base_url.rstrip("/")
        self.timeout = timeout
        self.ws_url = self._to_ws_url(self.base_url, ws_path)
        self.ws = None

    def _to_ws_url(self, base_url: str, ws_path: str) -> str:
        parsed = urlparse(base_url)
        scheme = "wss" if parsed.scheme == "https" else "ws"
        host = parsed.netloc or parsed.path
        path = ws_path if ws_path.startswith("/") else f"/{ws_path}"
        return f"{scheme}://{host}{path}"

    def _connect_ws(self) -> bool:
        if self.ws is not None:
            return True
        try:
            self.ws = connect(
                self.ws_url,
                open_timeout=self.timeout,
                close_timeout=self.timeout,
                ping_interval=20,
                ping_timeout=20,
            )
            return True
        except Exception as err:
            print(f"WebSocket connect failed ({self.ws_url}): {err}")
            self.ws = None
            return False

    def _close_ws(self):
        if self.ws is None:
            return
        try:
            self.ws.close()
        except Exception:
            pass
        self.ws = None

    def _send_ws(self, event_type: str, payload: dict) -> bool:
        print(payload)
        if not self._connect_ws():
            return False

        packet = {"type": event_type, "payload": payload}
        raw = json.dumps(packet)

        try:
            self.ws.send(raw)
            return True
        except Exception:
            self._close_ws()

        if not self._connect_ws():
            return False

        try:
            self.ws.send(raw)
            return True
        except Exception as err:
            print(f"WebSocket send failed ({event_type}): {err}")
            self._close_ws()
            return False

    def _send_http(self, endpoint: str, data: dict) -> bool:
        try:
            response = requests.post(
                f"{self.base_url}/{endpoint}",
                json=data,
                timeout=self.timeout,
            )
            response.raise_for_status()
            return True
        except requests.exceptions.RequestException as err:
            print(f"HTTP send failed ({endpoint}): {err}")
            return False

    # Update setup payload.
    # If websocket is available, sends:
    #   {"type":"setup","payload":{...}}
    # Otherwise falls back to POST /send_setup.
    def send_setup(self, data: dict) -> bool:
        if self._send_ws("setup", data):
            return True
        return self._send_http("send_setup", data)

    # Update live payload.
    # If websocket is available, sends:
    #   {"type":"live","payload":{...}}
    # Otherwise falls back to POST /send_data.
    def send_live(self, data: dict) -> bool:
        if self._send_ws("live", data):
            return True
        return self._send_http("send_data", data)

    def close(self):
        self._close_ws()
