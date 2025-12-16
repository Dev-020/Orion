import sys
import os
import uvicorn
from pathlib import Path
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel

# --- PATH HACK ---
# Enable importing from backends (for logger/config)
sys.path.append(str(Path(__file__).resolve().parent.parent / 'backends'))
from main_utils import config
from main_utils.orion_logger import setup_logging

# --- LOGGING SETUP ---
LOG_FILE = config.DATA_DIR / "logs" / "web.log"
logger = setup_logging("WebFrontend", LOG_FILE)

app = FastAPI()

# Enable CORS to allow the frontend to talk to the Backend API (Port 8000)
# even though they are now on different ports (8001 vs 8000).
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- CLIENT LOGGING ---
class LogRequest(BaseModel):
    level: str
    message: str

@app.post("/log")
async def receive_log(request: LogRequest):
    """endpoint for the browser to send logs to the server console/file"""
    msg = f"[Client] {request.message}"
    if request.level == "error":
        logger.error(msg)
    elif request.level == "warning":
        logger.warning(msg)
    else:
        logger.info(msg)
    return {"status": "ok"}

# --- STATIC FILES ---
# Serve the Vite build output
FRONTEND_BUILD_DIR = Path(__file__).parent / "web" / "dist"

if FRONTEND_BUILD_DIR.exists():
    app.mount("/", StaticFiles(directory=str(FRONTEND_BUILD_DIR), html=True), name="static")
    logger.info(f"Serving Web Frontend from: {FRONTEND_BUILD_DIR}")
else:
    logger.error(f"Build not found at {FRONTEND_BUILD_DIR}. Please run 'npm run build' in frontends/web")

# --- SPA ROUTING ---
# Ensure that any 404 route returns index.html so React Router can handle it.
@app.exception_handler(404)
async def spa_404_handler(request, exc):
    # Only serve index.html for GET requests that are not API calls
    # (API calls usually start with /api or /log, which generic 404 is fine)
    # But since this server ONLY serves frontend, practically everything is frontend.
    return FileResponse(FRONTEND_BUILD_DIR / "index.html")

if __name__ == "__main__":
    logger.info("Starting Web Frontend Server on Port 8001...")
    
    # Configure Uvicorn to log to our file
    # We need to explicitly tell Uvicorn to use our log file for 'uvicorn.access'
    log_config = uvicorn.config.LOGGING_CONFIG.copy()
    log_config["handlers"]["file"] = {
        "class": "logging.FileHandler",
        "filename": str(LOG_FILE),
        "mode": "a",
        "formatter": "default",
        "encoding": "utf-8"
    }
    log_config["formatters"]["default"] = {
        "format": "%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    }
    log_config["loggers"]["uvicorn.access"]["handlers"] = ["file"]
    log_config["loggers"]["uvicorn.error"]["handlers"] = ["file"]

    uvicorn.run(app, host="127.0.0.1", port=8001, log_config=log_config)
