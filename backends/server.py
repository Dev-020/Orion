
import sys
import asyncio
import logging
from pathlib import Path
from typing import Optional, Dict, Any, List
from fastapi import FastAPI, UploadFile, File, Form, HTTPException, BackgroundTasks, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse, JSONResponse, FileResponse
from pydantic import BaseModel
import json
import uvicorn
import contextlib
import signal
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
    type: str  # 'file' or 'directory'
    size: Optional[int] = None
    modification_time: Optional[float] = None

class UserRegister(BaseModel):
    username: str
    password: str

class UserLogin(BaseModel):
    username: str
    password: str
    mime_type: Optional[str] = None
    size_bytes: Optional[int] = 0
    text_content: Optional[str] = None # CRITICAL: Allow analysis text to pass through validation

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
        # Ensure we pass the analysis text if present (for VLM results)
        self.text_content = data.get("text_content")
        # Add any other attrs Core expects access to

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
    allow_origins=["*"],  # For development, allow all. In prod, restrict this!
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

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

from fastapi import Depends, Header

async def verify_auth_header(authorization: Optional[str] = Header(None)):
    if not auth_manager:
        return None # Auth disabled, proceed as anonymous or fail? For now, allow?
    
    if not authorization:
        raise HTTPException(status_code=401, detail="Missing Authorization Header")
    
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer":
        raise HTTPException(status_code=401, detail="Invalid Authentication Scheme")
    
    user_payload = auth_manager.verify_token(token)
    if not user_payload:
        raise HTTPException(status_code=401, detail="Invalid or Expired Token")
        
    return user_payload

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
                     
                     async with core_lock:
                        if not core_instance:
                             await websocket.send_text(json.dumps({"type": "error", "content": "Core not initialized"}))
                             continue

                        # Process Prompt
                        iterator = core_instance.process_prompt(
                            session_id=session_id, # Enforce User's specific session
                            user_prompt=user_prompt,
                            file_check=[], 
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
async def get_history_endpoint(user: dict = Depends(verify_auth_header)):
    """
    Retrieves the chat history for the authenticated user (session_id = user_id).
    """
    session_id = user['user_id']
    
    async with core_lock:
        history = []
        # Check if core has 'chat' attribute (Pro/Lite compatibility)
        if hasattr(core_instance, 'chat'):
             history = core_instance.chat.get_session(session_id)
        # Fallback if core itself tracks history (unlikely but safe)
        elif hasattr(core_instance, 'get_session_history'):
             history = core_instance.get_session_history(session_id)
             
        # Helper to clean/parse history items
        clean_history = []
        for exchange in history:
            clean_ex = exchange.copy()
            
            # 1. Parse User Content
            u_content = clean_ex.get('user_content')
            # Handle String (Legacy/Error case)
            if isinstance(u_content, str):
                try:
                    if u_content.strip().startswith('{'):
                        clean_ex['user_content'] = json.loads(u_content)
                except: pass
            
            # Handle Dict/Object (Standard UserContent)
            # The 'text' inside parts is often a JSON string envelope. We want to unwrap it.
            elif u_content: # Object or Dict
                try:
                    # Generic access to 'parts' (obj or dict)
                    parts = getattr(u_content, 'parts', None)
                    if parts is None and isinstance(u_content, dict):
                        parts = u_content.get('parts')
                    
                    if parts:
                        # Taking first part's text
                        first_part = parts[0]
                        text = getattr(first_part, 'text', None)
                        if text is None and isinstance(first_part, dict):
                            text = first_part.get('text')
                        
                        # If that text looks like JSON, parse it
                        if text and isinstance(text, str) and text.strip().startswith('{'):
                            try:
                                payload = json.loads(text)
                                if 'user_prompt' in payload:
                                    clean_ex['user_content'] = payload['user_prompt'] # Simplified to just text
                            except:
                                clean_ex['user_content'] = text # Fallback to raw text
                except Exception as e:
                    pass
            
            # 2. Parse Model Content (if it happens to be structured)
            m_content = clean_ex.get('model_content')
            if isinstance(m_content, str):
                try:
                    if m_content.strip().startswith('{'):
                         clean_ex['model_content'] = json.loads(m_content)
                except:
                    pass

            clean_history.append(clean_ex)

        return {"history": clean_history}

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
