
import sys
import asyncio
import logging
from pathlib import Path
from typing import Optional, Dict, Any, List
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, BackgroundTasks, WebSocket, WebSocketDisconnect, Depends, Header
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse, FileResponse
from pydantic import BaseModel
import json
import uvicorn
import contextlib
import signal
import shutil
import os

# --- LOG FILTERING ---
class EndpointFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        return record.getMessage().find("/health") == -1

# Filter out health checks from uvicorn access log
logging.getLogger("uvicorn.access").addFilter(EndpointFilter())

# --- PATH SETUP ---
# Ensure we can import from backend modules
BACKEND_ROOT = Path(__file__).resolve().parent
sys.path.append(str(BACKEND_ROOT))

# Imports from our existing modules
from main_utils import config
from main_utils.orion_logger import setup_logging
# Import Backup System
try:
    from system_utils import backup_db
except ImportError:
    backup_db = None

try:
    from orion_core import OrionCore
except ImportError:
    pass

try:
    from orion_core_lite import OrionLiteCore 
except ImportError:
    pass

# --- LOGGING SETUP ---
# Server logs go to file primarily, with console output for debugging/TUI.
# Standard log location: logs/server.log
LOG_DIR = config.DATA_DIR / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)
LOG_FILE = LOG_DIR / "server.log"

logger = setup_logging("Server", LOG_FILE, level=logging.INFO)

# --- GLOBAL STATE ---
core_instance = None
core_lock = asyncio.Lock() # THE BRAIN LOCK
auth_manager = None # Initialized in lifespan

# Import AuthManager
try:
    from main_utils.auth_manager import AuthManager
except ImportError as e:
    logger.error(f"Could not import AuthManager: {e}. Authentication will be disabled.")
    AuthManager = None

# --- Pydantic Models for Requests ---
class FileMetadata(BaseModel):
    name: str
    path: str
class UnifiedFile(BaseModel):
    """
    Standardized payload for file objects across Frontend -> Server -> Core.
    Unifies 'File API' style objects and local/base64 objects.
    """
    name: Optional[str] = None # Internal/API Name (Uri)
    uri: Optional[str] = None  # URI (file://, https://, or internal id)
    display_name: Optional[str] = None # Human readable filename
    mime_type: Optional[str] = None
    size_bytes: Optional[int] = 0
    text_content: Optional[str] = None # For injected text/code/analysis
    base64_data: Optional[str] = None  # For small images/local usage
    local_path: Optional[str] = None   # For local file references
    is_analysis: Optional[bool] = False # Flag if this is a text analysis of a file

class UserRegister(BaseModel):
    username: str
    password: str

class UserLogin(BaseModel):
    username: str
    password: str

class PromptRequest(BaseModel):
    prompt: str
    session_id: str
    user_id: str
    username: str
    files: List[UnifiedFile] = [] 
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
        # Maps UnifiedFile fields to Core's expected attributes
        self.name = data.get("name")
        self.uri = data.get("uri")
        self.display_name = data.get("display_name")
        self.mime_type = data.get("mime_type")
        self.size_bytes = data.get("size_bytes")
        self.text_content = data.get("text_content")
        self.base64_data = data.get("base64_data") # Support Local/Ollama images
        self.local_path = data.get("local_path")   # Support Local Docs

# --- WEBSOCKET MANAGER ---
class ConnectionManager:
    def __init__(self):
        self.active_connections: List[WebSocket] = []

    async def connect(self, websocket: WebSocket):
        await websocket.accept()
        self.active_connections.append(websocket)

    def disconnect(self, websocket: WebSocket):
        self.active_connections.remove(websocket)

    async def send_personal_message(self, message: str, websocket: WebSocket):
        await websocket.send_text(message)

    async def broadcast(self, message: str):
        for connection in self.active_connections:
            await connection.send_text(message)

manager = ConnectionManager()

# --- LIFECYCLE MANAGER ---
# ... (Lifespan remains same)

# --- FASTAPI APP ---
@contextlib.asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    global core_instance, core_lock, auth_manager
    logger.info("Server starting up...")
    
    # Initialize Auth Manager
    if AuthManager:
        # User requested root databases directory
        # We are in backends/, so root is backends/../databases -> ../databases
        db_path = str(BACKEND_ROOT.parent / "databases" / "users.db")
        
        auth_manager = AuthManager(db_path=db_path)
        logger.info(f"AuthManager initialized. DB: {db_path}")
    
    # --- AUTO BACKUP SCHEDULER ---
    async def auto_backup_scheduler():
        """Runs auto-backup check every 15 minutes."""
        if not backup_db: return
        logger.info("Auto-Backup Scheduler Started (Interval: 15m)")
        while True:
            try:
                # Run in executor to avoid blocking async loop
                # backup_db.run_backup handles the 12h gate and hash check logic internally
                await asyncio.to_thread(backup_db.run_backup, 'auto')
            except Exception as e:
                logger.error(f"Auto-Backup Scheduler Error: {e}")
            
            await asyncio.sleep(15 * 60) # 15 minutes
            
    try:
        # Initialize the Brain
        if config.BACKEND == "ollama":
             logger.info("Initializing OrionLiteCore (Ollama Backend)...")
             core_instance = OrionLiteCore()
             logger.info("OrionLiteCore Initialized Successfully.")
        else:
             logger.info("Initializing OrionCore (API Backend)...")
             core_instance = OrionCore()
             logger.info("OrionCore Initialized Successfully.")

        # Launch Backup Scheduler
        if backup_db:
            # Run one check immediately on startup (non-blocking)
            asyncio.create_task(asyncio.to_thread(backup_db.run_backup, 'auto'))
            # Start loop
            asyncio.create_task(auto_backup_scheduler())

    except Exception as e:
        logger.critical(f"Failed to init OrionCore: {e}")
        # We might want to exit, but let's keep server alive to report health=bad
    
    yield
    
    # Shutdown
    logger.info("Server shutting down...")
    if core_instance:
        logger.info("Shutting down OrionCore...")
        core_instance.shutdown()
        
    # Final Backup Check
    if backup_db:
        logger.info("Performing final auto-backup check...")
        try:
            # We use a synchronous call here since we are shutting down
            # but wrapping in to_thread might be safer if event loop still running?
            # Actually, just run it. If it takes time, so be it, safety first.
            backup_db.run_backup('auto')
        except Exception as e:
            logger.error(f"Final Backup Failed: {e}")

app = FastAPI(lifespan=lifespan)

# --- CORS SETUP ---
# Allow requests from the React dev server (e.g., localhost:5173) and others
app.add_middleware(
    CORSMiddleware,
    allow_origins=config.ALLOWED_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# --- STATIC FILES FOR AVATARS ---
AVATAR_DIR = config.DATA_DIR / "avatars"
AVATAR_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/avatars", StaticFiles(directory=str(AVATAR_DIR)), name="avatars")

# --- AUTH HELPERS ---
async def verify_auth_header(authorization: Optional[str] = Header(None)):
    if not auth_manager:
        return None 
    
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing Authorization Header")
    
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer":
        raise HTTPException(status_code=401, detail="Invalid Authentication Scheme")
    
    user_payload = auth_manager.verify_token(token)
    if not user_payload:
        raise HTTPException(status_code=401, detail="Invalid or Expired Token")
        
    return user_payload

# --- PROFILE ENDPOINTS ---

@app.get("/api/profile")
async def get_profile(user: Dict = Depends(verify_auth_header)):
    """Get current user profile"""
    if not auth_manager:
        raise HTTPException(503, "Auth disabled")
    profile = auth_manager.get_user_profile(user['user_id'])
    
    # If auth_manager returns empty dict, it means DB error or user not found
    if not profile:
         raise HTTPException(status_code=404, detail="Profile not found or DB error")
         
    return profile

@app.post("/api/profile")
async def update_profile(updates: Dict[str, Any], user: Dict = Depends(verify_auth_header)):
    """Update arbitrary profile fields"""
    if not auth_manager:
        raise HTTPException(503, "Auth disabled")
        
    success = auth_manager.update_user_profile(user['user_id'], updates)
    if success:
        return {"status": "success", "profile": auth_manager.get_user_profile(user['user_id'])}
    raise HTTPException(status_code=500, detail="Failed to update profile")

@app.post("/api/profile/avatar")
async def upload_avatar(
    file: UploadFile = File(...), 
    user: Dict = Depends(verify_auth_header)
):
    """Upload avatar image. Auto-converts GIFs to WebM."""
    try:
        if not auth_manager:
            raise HTTPException(503, "Auth disabled")

        if not file.content_type.startswith("image/"):
            raise HTTPException(400, "File must be an image")

        import time
        import subprocess
        
        # Determine extension
        original_ext = file.filename.split('.')[-1] if '.' in file.filename else "png"
        timestamp = int(time.time())
        user_id = user['user_id']
        
        # Paths
        raw_filename = f"raw_{user_id}_{timestamp}.{original_ext}"
        raw_path = AVATAR_DIR / raw_filename
        
        # --- CLEANUP OLD AVATARS ---
        # Find and remove any existing avatar file for this user to save space
        for existing_file in AVATAR_DIR.glob(f"*_{user_id}_*"):
            try:
                os.remove(existing_file)
                logger.info(f"Deleted old avatar: {existing_file.name}")
            except Exception as e:
                logger.warning(f"Failed to delete old avatar {existing_file.name}: {e}")
                
        # Write Raw File
        with open(raw_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)
            
        final_filename = raw_filename
        
        # GIF -> WebM Conversion
        if file.content_type == "image/gif":
            webm_filename = f"avatar_{user_id}_{timestamp}.webm"
            webm_path = AVATAR_DIR / webm_filename
            
            # FFmpeg Command:
            # -i input
            # -c:v libvpx-vp9 (Modern WebM codec)
            # -b:v 0 -crf 40 (Constant Quality, efficient)
            # -vf scale=256:256:force_original_aspect_ratio=decrease (Resize to max 256x256)
            # -an (Remove Audio)
            cmd = [
                "ffmpeg", "-y",
                "-i", str(raw_path),
                "-c:v", "libvpx-vp9",
                "-b:v", "0", "-crf", "40",
                "-vf", "scale=256:256:force_original_aspect_ratio=decrease",
                "-an",
                str(webm_path)
            ]
            
            logger.info(f"Converting GIF to WebM: {' '.join(cmd)}")
            
            # Run conversion in thread to avoid blocking event loop
            try:
                result = await asyncio.to_thread(subprocess.run, cmd, capture_output=True, text=True)
                
                if result.returncode == 0:
                    logger.info("Conversion successful")
                    final_filename = webm_filename
                    # Delete raw gif to save space
                    try:
                        os.remove(raw_path)
                    except Exception as e:
                        logger.warning(f"Failed to delete temp raw file: {e}") 
                else:
                    logger.error(f"FFmpeg failed: {result.stderr}")
                    # Fallback to raw GIF if conversion fails
                    final_filename = raw_filename
            except Exception as e:
                logger.error(f"Conversion Exception: {e}")
                final_filename = raw_filename
        else:
            # For non-GIFs, just rename/keep the raw file as the official avatar
            # Maybe enforce resize for PNGs too? For now, we trust the Cropper.
            pass

        # Update Profile with URL
        # Use relative path so frontend can prepend API_BASE (works for Ngrok/Localhost/IP)
        avatar_url = f"/avatars/{final_filename}" 
        
        success = auth_manager.update_user_profile(user['user_id'], {"avatar_url": avatar_url})
        
        if success:
            return {"status": "success", "avatar_url": avatar_url}
        else:
            raise HTTPException(500, "Failed to save avatar reference")
            
    except Exception as e:
        logger.error(f"Avatar Upload Error: {e}")
        raise HTTPException(500, str(e))


# app = FastAPI() # Fallback if no lifespan needed, but we need it for Core init

@app.get("/health")
async def health_check():
    """Simple health check for Launcher to assert server is up."""
    status = "healthy" if core_instance else "initializing"
    auth_status = "enabled" if auth_manager else "disabled"
    return {"status": status, "backend": config.BACKEND, "auth": auth_status}

# --- AUTH ENDPOINTS ---

@app.post("/api/auth/register")
async def register(user: UserRegister):
    if not auth_manager:
        raise HTTPException(status_code=503, detail="Authentication disabled.")
    
    result = auth_manager.register_user(user.username, user.password)
    if not result['success']:
        raise HTTPException(status_code=400, detail=result['error'])
    
    return result

@app.post("/api/auth/login")
async def login(user: UserLogin):
    if not auth_manager:
        raise HTTPException(status_code=503, detail="Authentication disabled.")
        
    result = auth_manager.login_user(user.username, user.password)
    if not result['success']:
        raise HTTPException(status_code=401, detail=result['error'])
        
    return result



@app.get("/api/auth/me")
async def get_me(user: dict = Depends(verify_auth_header)):
    """Returns current user details from token."""
    return {"user": user}

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
            
            # Read bytes
            content = await file.read()
            
            # Call Core.upload_file (Delegates to FileManager)
            # Returns: SimpleNamespace(uri, display_name, mime_type, size_bytes, [text_content], [base64_data])
            # OR types.File payload
            uploaded_obj = core_instance.upload_file(content, display_name, mime_type)
            
            if not uploaded_obj:
                raise HTTPException(status_code=500, detail="Core refused upload")

            # Serialize the object to JSON compatible dict
            result_data = {
                "name": getattr(uploaded_obj, 'name', None),
                "uri": getattr(uploaded_obj, 'uri', None),
                "display_name": getattr(uploaded_obj, 'display_name', display_name),
                "mime_type": getattr(uploaded_obj, 'mime_type', mime_type),
                "size_bytes": getattr(uploaded_obj, 'size_bytes', len(content)),
                "text_content": getattr(uploaded_obj, 'text_content', None),
                "base64_data": getattr(uploaded_obj, 'base64_data', None),
                "local_path": getattr(uploaded_obj, 'local_path', None)
            }
            
            logger.info(f"Upload processed: {result_data.get('display_name')}")
            
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
    reconstructed_files = [StartableFile(f.model_dump()) for f in request.files]

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
                    # Force yield to event loop to ensure StreamingResponse flushes to socket
                    await asyncio.sleep(0)
                    
            except Exception as e:
                logger.error(f"Error during processing: {e}")
                err = {"type": "token", "content": f"[SERVER ERROR] {str(e)}"}
                yield json.dumps(err) + "\n"

    return StreamingResponse(response_generator(), media_type="application/x-ndjson")

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket, token: Optional[str] = None):
    await manager.connect(websocket)
    
    # Authenticate
    user = None
    if auth_manager and token:
        user = auth_manager.verify_token(token)
    
    if not user and auth_manager:
        # If auth is enabled but failed
        await websocket.close(code=1008) # Policy Violation
        return

    # If auth disabled, create anonymous user
    if not user:
        user = {'user_id': 'anonymous', 'username': 'Anonymous'}

    user_id = user['user_id']
    username = user['username']
    
    # Use User ID as the base Session ID for now to ensure 1:1 privacy
    # Or allow client to request a specific session, but we default to user_id
    session_id = user_id 

    try:
        while True:
            data = await websocket.receive_text()
            try:
                message_data = json.loads(data)
                
                if message_data.get("type") == "prompt":
                     # Check if client requested specific sub-session, otherwise use user_id
                     # requested_session = message_data.get("session_id")
                     # For now, enforce session_id = user_id to prevent snooping
                     
                     user_prompt = message_data.get("prompt", "")
                     files_data = message_data.get("files", []) # Extract files list
                     
                     async with core_lock:
                        if not core_instance:
                             await websocket.send_text(json.dumps({"type": "error", "content": "Core not initialized"}))
                             continue

                        # Convert dicts to StartableFile objects
                        file_objects = [StartableFile(f) for f in files_data]

                        # Process Prompt
                        iterator = core_instance.process_prompt(
                            session_id=session_id, # Enforce User's specific session
                            user_prompt=user_prompt,
                            file_check=file_objects, # Pass files here
                            user_id=user_id,
                            user_name=username,
                            stream=True
                        )
                        
                        for chunk in iterator:
                            await websocket.send_text(json.dumps(chunk))
                            await asyncio.sleep(0)
                            
                else:
                     await manager.send_personal_message(json.dumps({"type": "info", "content": f"Echo: {data}"}), websocket)
            
            except json.JSONDecodeError:
                await manager.send_personal_message(json.dumps({"type": "error", "content": "Invalid JSON"}), websocket)
                
    except WebSocketDisconnect:
        manager.disconnect(websocket)
        logger.info(f"User {username} ({user_id}) disconnected")

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

@app.get("/get_history")
async def get_history_endpoint(authorization: Optional[str] = Header(None)):
    """
    Retrieves the chat history for the authenticated user (session_id = user_id).
    """
    user = await verify_auth_header(authorization)
    session_id = user['user_id']
    
    async with core_lock:
        # Use centralized sanitization if available (Standard/Lite)
        if hasattr(core_instance, 'chat') and hasattr(core_instance.chat, 'sanitize_history_for_client'):
             return {"history": core_instance.chat.sanitize_history_for_client(session_id)}
        
        # Fallback for legacy cores (unlikely but safe)
        history = []
        if hasattr(core_instance, 'chat'):
             history = core_instance.chat.get_session(session_id)
        elif hasattr(core_instance, 'get_session_history'):
             history = core_instance.get_session_history(session_id)
        
        # We return raw history if sanitization is missing, though frontend might struggle.
        return {"history": history}

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

@app.post("/management/shutdown")
async def shutdown_endpoint(persist: bool = False):
    """Generic endpoint to trigger graceful shutdown from Launcher."""
    if persist and core_instance:
        logger.info("Persist flag received. Saving state before shutdown...")
        # Check for method (Lite vs Pro compatibility)
        if hasattr(core_instance, 'save_state_for_restart'):
            core_instance.save_state_for_restart()
        elif hasattr(core_instance, 'chat') and hasattr(core_instance.chat, 'save_state_for_restart'):
            core_instance.chat.save_state_for_restart()
            
    logger.warning("Remote shutdown requested via API.")
    # Simulate CTRL+C to trigger Uvicorn's graceful exit
    # We schedule it slightly in future to allow response to return? 
    # Actually os.kill is instant, but Uvicorn might handle it.
    # Better: use BackgroundTasks to kill after return
    
    def kill_self():
        import time
        time.sleep(1) # Give time for response to flush
        os.kill(os.getpid(), signal.SIGINT)
        
    background = BackgroundTasks()
    background.add_task(kill_self)
    
    # We can't return background tasks directly in simple dict returns usually unless using return Response
    # But we can just spawn a task in asyncio loop.
    asyncio.create_task(shutdown_helper())
    return {"status": "shutting_down"}

async def shutdown_helper():
    await asyncio.sleep(0.5)
    logger.info("Triggering SIGINT...")
    os.kill(os.getpid(), signal.SIGINT)

if __name__ == "__main__":
    # Ensure Uvicorn logs (access & error) go to our file
    # We rely on the fact that we set up root logger or specific loggers before.
    # But Uvicorn configures its own.
    
    # Simple fix: Pass the file path to uvicorn via log_config or simple args if possible?
    # Actually, uvicorn.run has 'log_config'. We can pass a dict. 
    # But simpler: let's just let it print to stderr/stdout, and the Launcher captures it!
    # The launcher sets stderr=f_err. Uvicorn usually prints to stderr.
    # So it SHOULD already be working. 
    # I will just ensure log_level is info.
    uvicorn.run(app, host="127.0.0.1", port=8000, log_config=None, log_level="info", access_log=True)
