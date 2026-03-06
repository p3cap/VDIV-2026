from pathlib import Path
import json

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
import uvicorn

app = FastAPI()

app.add_middleware(
	CORSMiddleware,
	allow_origins=["*"],
	allow_credentials=True,
	allow_methods=["*"],
	allow_headers=["*"],
)

def _load_json(path: Path) -> dict:
	try:
		with path.open("r", encoding="utf-8") as f:
			data = json.load(f)
			return data if isinstance(data, dict) else {}
	except (OSError, json.JSONDecodeError):
		return {}


ROOT = Path(__file__).resolve().parent.parent
latest_data = _load_json(ROOT / "MarsRover" / "data" / "livedata.json")
setup_data = _load_json(ROOT / "MarsRover" / "data" / "setupdata.json")

# Runtime data
@app.get("/get_data")
async def get_data():
	return latest_data

# Setup config
@app.get("/get_setup")
async def get_setup():
	return setup_data

# Update runtime data
@app.post("/send_data")
async def send_data(data: dict):
	global latest_data
	if not data:
		return {"status": "ignored empty live payload"}
	latest_data = data
	return {"status": "ok"}

# Update setup config
@app.post("/send_setup")
async def send_setup(data: dict):
	global setup_data
	if not data:
		return {"status": "ignored empty setup payload"}
	setup_data = data
	return {"status": "setup updated"}


if __name__ == "__main__":
	uvicorn.run(app, host="0.0.0.0", port=8000) # TODO make universal laterrr
