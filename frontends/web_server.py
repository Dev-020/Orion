import sys
import os
import uvicorn
from pathlib import Path
try:
    import setproctitle
    setproctitle.setproctitle("Orion Web Frontend")
except ImportError:
    pass
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel
import subprocess

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
# even though they are now on different ports (8001 vs 8000).#
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.ALLOWED_ORIGINS,
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

# --- BUILD SYSTEM ---
def build_frontend_if_needed():
    """
    Checks if the frontend needs rebuilding by comparing source file timestamps
    to the build output timestamp.
    """
    web_dir = Path(__file__).parent / "web"
    dist_dir = web_dir / "dist"
    index_html = dist_dir / "index.html"
    
    # 1. Source files to check for changes
    # We want to check everything in src/, plus package.json and vite config
    source_patterns = [
        "src/**/*",
        "package.json",
        "vite.config.*",
        "index.html" # The public index.html (source)
    ]
    
    latest_src_mtime = 0.0
    
    for pattern in source_patterns:
        for f in web_dir.glob(pattern):
            if f.is_file():
                try:
                    mtime = f.stat().st_mtime
                    if mtime > latest_src_mtime:
                        latest_src_mtime = mtime
                except OSError:
                    pass

    # 2. Check existing build
    last_build_mtime = 0.0
    if index_html.exists():
        last_build_mtime = index_html.stat().st_mtime

    # 3. Decision
    # Epsilon for safety, though direct comparison usually fine locally
    # 3. Decision
    # Epsilon for safety, though direct comparison usually fine locally
    if latest_src_mtime > last_build_mtime or not index_html.exists():
        logger.info("Frontend changes detected or build missing. Running build process...")
        
        # Check for node_modules
        node_modules = web_dir / "node_modules"
        if not node_modules.exists():
            logger.info("node_modules missing. Running 'npm install'...")
            try:
                # Install dependencies first
                subprocess.run(["npm", "install"], cwd=str(web_dir), shell=True, check=True)
                logger.info("Dependencies installed successfully.")
            except subprocess.CalledProcessError as e:
                logger.error(f"npm install failed: {e}")
                return # Cannot build without dependencies

        logger.info("Running 'npm run build'...")
        try:
            # Pass environment variables to the build
            env = os.environ.copy()
            # Ensure VITE_API_URL is set for the build, default to 8000 if not present
            if "VITE_API_URL" not in env:
                env["VITE_API_URL"] = "http://localhost:8000"
                
            # shell=True is often required on Windows to find 'npm' (which is a batch file)
            # We capture output to help debug if needed, or let it flow to stdout/stderr
            subprocess.run(["npm", "run", "build"], cwd=str(web_dir), shell=True, check=True, env=env)
            logger.info("Frontend build completed successfully.")
        except subprocess.CalledProcessError as e:
            logger.error(f"Frontend build failed: {e}")
            # We don't raise here because maybe an old build exists and is usable? 
            # Or we just let the 404 handler deal with it.
            pass
    else:
        logger.info("Frontend is up to date. Skipping build.")


# Run smart build before mounting
build_frontend_if_needed()

# --- STATIC FILES ---
# Serve the Vite build output
FRONTEND_BUILD_DIR = Path(__file__).parent / "web" / "dist"

if FRONTEND_BUILD_DIR.exists():
    # Mount at /Orion to match vite.config.js base
    app.mount("/Orion", StaticFiles(directory=str(FRONTEND_BUILD_DIR), html=True), name="static_orion")
    # Also mount at / for direct access? No, that causes confusion if assets are /Orion/...
    # But files inside dist don't have Orion prefix. 
    # If app requests /Orion/assets/foo.js, StaticFiles at /Orion will look for dist/assets/foo.js. Correct.
    logger.info(f"Serving Web Frontend from: {FRONTEND_BUILD_DIR} at /Orion")
else:
    logger.error(f"Build not found at {FRONTEND_BUILD_DIR}. Please run 'npm run build' in frontends/web")

# --- SPA ROUTING ---
# Ensure that any 404 route returns index.html so React Router can handle it.
from fastapi.responses import RedirectResponse

@app.get("/")
async def root():
    return RedirectResponse(url="/Orion/")

# --- SPA ROUTING ---
# Ensure that any 404 route returns index.html so React Router can handle it.
@app.exception_handler(404)
async def spa_404_handler(request, exc):
    # If request starts with /Orion but not found, serve index.html (client-side routing)
    if request.url.path.startswith("/Orion"):
         return FileResponse(FRONTEND_BUILD_DIR / "index.html")
    return JSONResponse(status_code=404, content={"message": "Not Found"})

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
