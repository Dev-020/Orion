
import sys
import asyncio
import logging
from pathlib import Path
from typing import Optional, Dict, Any, List
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, BackgroundTasks
from fastapi.responses import StreamingResponse, JSONResponse
from pydantic import BaseModel
import uvicorn
import contextlib

# --- PATH SETUP ---
# Ensure we can import from backend modules
BACKEND_ROOT = Path(__file__).resolve().parent
sys.path.append(str(BACKEND_ROOT))

# Imports from our existing modules
from main_utils import config
try:
    from orion_core import OrionCore
except ImportError:
    # Fallback/Mock for initial testing if needed, but intended to work with real core
    print("WARNING: Could not import OrionCore. Server will likely fail.")
    pass

# --- LOGGING SETUP ---
# We want server logs to go to a file, not stdout (to keep TUI clean)
LOG_DIR = config.DATA_DIR / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = LOG_DIR / "server.log"

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler(LOG_FILE),
        # minimal console output for critical startup errors before redirection
    ]
)
logger = logging.getLogger("server")

# --- GLOBAL STATE ---
core_instance = None
core_lock = asyncio.Lock() # THE BRAIN LOCK

# --- Pydantic Models for Requests ---
class FileMetadata(BaseModel):
    name: Optional[str] = None
    uri: Optional[str] = None
    display_name: Optional[str] = None
    mime_type: Optional[str] = None
    size_bytes: Optional[int] = 0

class PromptRequest(BaseModel):
    prompt: str
    session_id: str
    user_id: str
    username: str
    files: List[FileMetadata] = [] # Replaces simple image_path
    stream: bool = True

class ModeRequest(BaseModel):
    session_id: str
    mode: str # 'cache' or 'functions'

class HistoryRequest(BaseModel):
    session_id: str
    limit: int = 10

# --- HELPER: Mock Object for Core ---
class StartableFile:
    def __init__(self, data: Dict):
        self.name = data.get("name")
        self.uri = data.get("uri")
        self.display_name = data.get("display_name")
        self.mime_type = data.get("mime_type")
        self.size_bytes = data.get("size_bytes")
        # Add any other attrs Core expects access to

# --- LIFECYCLE MANAGER ---
# ... (Lifespan remains same)

# --- FASTAPI APP ---
@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    global core_instance, core_lock
    logger.info("Server starting up...")
    try:
        # Initialize the Brain
        core_instance = OrionCore()
        logger.info("OrionCore Initialized Successfully.")
    except Exception as e:
        logger.critical(f"Failed to init OrionCore: {e}")
        # We might want to exit, but let's keep server alive to report health=bad
    
    yield
    
    # Shutdown
    logger.info("Server shutting down...")
    pass

app = FastAPI(lifespan=lifespan)
# app = FastAPI() # Fallback if no lifespan needed, but we need it for Core init

@app.get("/health")
async def health_check():
    """Simple health check for Launcher to assert server is up."""
    status = "healthy" if core_instance else "initializing"
    return {"status": status, "backend": config.BACKEND}

@app.post("/switch_mode")
async def switch_session_mode(request: ModeRequest):
    """Switch a session between caching and function calling modes."""
    async with core_lock:
        try:
            logger.info(f"Switching mode for {request.session_id} to {request.mode}")
            # core_instance.set_session_mode(request.session_id, request.mode)
            # Assuming set_session_mode exists or we log it for now.
            if hasattr(core_instance, 'set_session_mode'):
                 core_instance.set_session_mode(request.session_id, request.mode)
            return {"status": "success", "mode": request.mode}
        except Exception as e:
            logger.error(f"Error switching mode: {e}")
            raise HTTPException(status_code=500, detail=str(e))

@app.post("/upload_file")
async def upload_file_endpoint(
    file: UploadFile = File(...),
    display_name: str = Form(...),
    mime_type: str = Form(...)
):
    """
    Handle file uploads.
    Accepts bytes, passes to Core.upload_file, returns result metadata.
    """
    async with core_lock:
        try:
            logger.info(f"Received file upload: {display_name} ({mime_type})")
            
            # Read bytes to memory (assuming manageable size) or stream to temp
            content = await file.read()
            
            # Call Core.upload_file(bytes, display_name, mime_type)
            # This returns a Gemini File Object (or similar)
            uploaded_obj = core_instance.upload_file(content, display_name, mime_type)
            
            if not uploaded_obj:
                raise HTTPException(status_code=500, detail="Core refused upload")

            # Serialize the object to JSON compatible dict
            # We assume the object has attributes like .name, .uri, etc.
            result_data = {
                "name": getattr(uploaded_obj, 'name', None),
                "uri": getattr(uploaded_obj, 'uri', None),
                "display_name": display_name, # Fallback
                "mime_type": mime_type,
                "size_bytes": getattr(uploaded_obj, 'size_bytes', len(content))
            }
            # Add specific 'text_content' if it's an analyzed file
            if hasattr(uploaded_obj, 'text_content'):
                result_data['text_content'] = uploaded_obj.text_content
            
            logger.info(f"Upload processed: {result_data.get('uri')}")
            
            return result_data
            
        except Exception as e:
            logger.error(f"Upload failed: {e}")
            raise HTTPException(status_code=500, detail=str(e))

@app.post("/process_prompt")
async def process_prompt(request: PromptRequest):
    """
    The main chat endpoint.
    Uses StreamingResponse to yield tokens exactly like the local generator.
    """
    logger.info(f"Request from {request.username} ({request.session_id})")
    
    # Reconstruct file objects for Core
    reconstructed_files = [StartableFile(f.dict()) for f in request.files]

    async def response_generator():
        async with core_lock:
            try:
                iterator = core_instance.process_prompt(
                    session_id=request.session_id,
                    user_prompt=request.prompt,
                    file_check=reconstructed_files,
                    user_id=request.user_id,
                    user_name=request.username,
                    stream=True # We always force stream for HTTP endpoint, client can buffer if needed
                )
                
                for chunk in iterator:
                    # Chunk is a dict (see OrionCore.process_prompt yield)
                    # We serialize it to JSON line
                    import json
                    yield json.dumps(chunk) + "\n"
                    
            except Exception as e:
                logger.error(f"Error during processing: {e}")
                err = {"type": "token", "content": f"[SERVER ERROR] {str(e)}"}
                yield json.dumps(err) + "\n"

    return StreamingResponse(response_generator(), media_type="application/x-ndjson")

@app.get("/list_sessions")
async def list_sessions_endpoint():
    async with core_lock:
        sessions = core_instance.list_sessions()
        return {"sessions": sessions}

@app.get("/get_mode")
async def get_mode_endpoint(session_id: str):
    async with core_lock:
        mode = core_instance.get_session_mode(session_id)
        return {"mode": mode}

@app.post("/truncate_history")
async def truncate_history_endpoint(request: dict):
    # Expects {session_id, count, index}
    async with core_lock:
        core_instance.manage_session_history(
            request.get("session_id"), 
            count=request.get("count", 1), 
            index=request.get("index", 0)
        )
        return {"status": "success"}

@app.post("/refresh_instructions")
async def refresh_instructions_endpoint(request: dict):
    # Expects {restart: bool}
    async with core_lock:
        status = core_instance.trigger_instruction_refresh(full_restart=request.get("restart", False))
        return {"status": status}

@app.get("/history")
async def get_history(session_id: str, limit: int = 10):
    async with core_lock:
        # Fetch history from core's in-memory session store
        hist = core_instance.sessions.get(session_id, [])
        # We might need to serialize complex objects if hist contains them
        # For now assuming dicts or serializable
        return {"history": hist[-limit:]}

if __name__ == "__main__":
    # HOST on localhost, Port 8000
    uvicorn.run(app, host="127.0.0.1", port=8000, log_config=None)
