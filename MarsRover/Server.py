from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
import uvicorn

app = FastAPI()

# Enable CORS so Vue can fetch
app.add_middleware(
	CORSMiddleware,
	allow_origins=["*"],
	allow_credentials=True,
	allow_methods=["*"],
	allow_headers=["*"],
)

# Shared variable for latest JSON
latest_data = {}

# Endpoint for JS/Vue to GET the latest JSON
@app.get("/get_data")
async def get_data():
	return JSONResponse(content=latest_data)

# Endpoint for other Python scripts to POST JSON
@app.post("/send_data")
async def send_data(data: dict):
	global latest_data
	latest_data = data
	return {"status": "ok", "received": latest_data}


if __name__ == "__main__":
  uvicorn.run(app, host="127.0.0.1", port=8000)