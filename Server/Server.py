
# TODO make it ip/rover/...

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

latest_data = {}
setup_data = {}

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
	latest_data = data
	return {"status": "ok"}

# Update setup config
@app.post("/send_setup")
async def send_setup(data: dict):
	global setup_data
	setup_data = data
	return {"status": "setup updated"}


if __name__ == "__main__":
	uvicorn.run(app, host="0.0.0.0", port=8000) # TODO make universal laterrr