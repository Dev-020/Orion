import requests
import json
import os
import sys
from pathlib import Path
from typing import Optional, Generator
from main_utils.orion_logger import setup_logging, get_orion_logger
from main_utils import config

# Configure logger
# We don't want to setup_logging globally here as it might be imported by Server which has its own setup.
# In Client usage (standalone script or Bot), the caller (bot.py) usually sets up logging.
# But for the library's internal logs, we just get the logger.
logger = get_orion_logger("OrionClient")

class OrionClient:
    """
    A drop-in replacement for OrionCore that communicates with the backend Server.
    """
    def __init__(self, base_url: str = "http://127.0.0.1:8000"):
        self.base_url = base_url.rstrip("/")
        logger.info(f"OrionClient initialized with Server URL: {self.base_url}")
    
    def process_prompt(
        self, 
        session_id: str,
        user_prompt: str,
        file_check: list, # List of file objects/dicts
        user_id: str,
        user_name: str,
        stream: bool = True
    ) -> Generator[dict, None, None]:
        """
        Streams response from the server as a generator.
        Matches OrionCore.process_prompt signature.
        """
        url = f"{self.base_url}/process_prompt"
        logger.info(f"Sending prompt to {url} | User: {user_name} | Session: {session_id}")
        
        # Serialize file objects to simple dicts for JSON payload
        files_payload = []
        for f in file_check:
            # Check if it's already a dict or object
            if isinstance(f, dict): files_payload.append(f)
            else:
                # Assume its a namespace or similar object
                files_payload.append({
                    "name": getattr(f, 'name', None),
                    "uri": getattr(f, 'uri', None), 
                    "display_name": getattr(f, 'display_name', None),
                    "mime_type": getattr(f, 'mime_type', None),
                    "size_bytes": getattr(f, 'size_bytes', 0),
                    "text_content": getattr(f, 'text_content', None) # Pass analysis text
                })

        payload = {
            "prompt": user_prompt,
            "session_id": session_id,
            "user_id": str(user_id),
            "username": user_name,
            "files": files_payload,
            "stream": stream
        }
        
        try:
            # timeout bumped for long thinking
            with requests.post(url, json=payload, stream=True) as response:
                response.raise_for_status() # Raise an exception for bad status codes (4xx or 5xx)
                # Server sends NDJSON (newline delimited JSON)
                for line in response.iter_lines():
                    if line:
                        decoded_line = line.decode('utf-8')
                        try:
                            chunk = json.loads(decoded_line)
                            yield chunk
                        except json.JSONDecodeError:
                            logger.error(f"Failed to decode JSON line: {decoded_line}")
                            yield {"type": "token", "content": f"[Chunk Error] {line}"}
            logger.info("Response stream completed successfully.")

        except requests.exceptions.ConnectionError:
            logger.error("[System Error] Could not connect to Orion Server. Is it running?")
            yield {"type": "token", "content": "[System Error] Could not connect to Orion Server. Is it running?"}
        except requests.exceptions.RequestException as e:
            logger.error(f"Error processing prompt: {e}")
            yield {"type": "token", "content": f"[System Error] Server request failed: {e}"}
        except Exception as e:
            logger.error(f"[System Error] Client exception: {e}")
            yield {"type": "token", "content": f"[System Error] Client exception: {e}"}

    async def async_upload_file(self, file_path: str = None, mime_type: str = None, file_obj=None, display_name=None):
        """
        Async version of upload_file using httpx.
        PREVENTS BLOCKING the Discord Bot event loop.
        """
        url = f"{self.base_url}/upload_file" 
        
        try:
            import httpx
            
            files = {}
            data = {"mime_type": mime_type}
            
            if file_path:
                path = Path(file_path)
                if not path.exists():
                    logger.error(f"File not found: {file_path}")
                    return None
                files = {"file": (path.name, open(file_path, 'rb'), mime_type)}
                data["display_name"] = path.name
                
            elif file_obj:
                # Handle bytes or file-like
                import io
                if isinstance(file_obj, bytes):
                    f_stream = io.BytesIO(file_obj)
                else:
                    f_stream = file_obj
                    
                filename = display_name or "uploaded_file"
                files = {"file": (filename, f_stream, mime_type)}
                data["display_name"] = filename
            else:
                logger.error("upload_file requires either file_path or file_obj")
                return None

            async with httpx.AsyncClient(timeout=300.0) as client:
                resp = await client.post(url, files=files, data=data)
            
            if resp.status_code == 200:
                logger.info("Async File upload successful.")
                data_json = resp.json()
                from types import SimpleNamespace
                return SimpleNamespace(**data_json)
            else:
                logger.error(f"Async File upload failed [URL: {url}]: {resp.text}")
                return None
        except Exception as e:
            logger.error(f"Async Error during file upload [URL: {url}]: {e}")
            return None

    async def async_process_prompt(
        self, 
        session_id: str,
        user_prompt: str,
        file_check: list, 
        user_id: str,
        user_name: str,
        stream: bool = True
    ):
        """
        Async generator for streaming response.
        """
        url = f"{self.base_url}/process_prompt"
        logger.info(f"Async Sending prompt to {url} | User: {user_name}")

        # Serialize file objects
        files_payload = []
        for f in file_check:
            if isinstance(f, dict): files_payload.append(f)
            else:
                files_payload.append({
                    "name": getattr(f, 'name', None),
                    "uri": getattr(f, 'uri', None), 
                    "display_name": getattr(f, 'display_name', None),
                    "mime_type": getattr(f, 'mime_type', None),
                    "size_bytes": getattr(f, 'size_bytes', 0),
                    "text_content": getattr(f, 'text_content', None)
                })

        payload = {
            "prompt": user_prompt,
            "session_id": session_id,
            "user_id": str(user_id),
            "username": user_name,
            "files": files_payload,
            "stream": stream
        }
        
        try:
            import httpx
            async with httpx.AsyncClient(timeout=300.0) as client:
                async with client.stream("POST", url, json=payload) as response:
                    if response.status_code != 200:
                        yield {"type": "token", "content": f"[Error: Server returned {response.status_code}]"}
                        return

                    async for line in response.aiter_lines():
                        if line:
                            try:
                                chunk = json.loads(line)
                                yield chunk
                            except json.JSONDecodeError:
                                pass
            logger.info("Async Response stream completed.")

        except Exception as e:
            logger.error(f"Async Error processing prompt: {e}")
            yield {"type": "token", "content": f"[System Error] {e}"}

    def upload_file(self, file_path: str = None, mime_type: str = None, file_obj=None, display_name=None):
        """
        Uploads a file to the server.
        Args:
            file_path: Path to file on disk (optional if file_obj provided).
            mime_type: MIME type of the file.
            file_obj: Bytes or file-like object (optional, used if file_path is None).
            display_name: Filename to use if uploading from memory.
        """
        url = f"{self.base_url}/upload_file" # CORRECTED endpoint
        
        try:
            files = {}
            data = {"mime_type": mime_type}
            
            if file_path:
                path = Path(file_path)
                if not path.exists():
                    logger.error(f"File not found: {file_path}")
                    return None
                files = {"file": (path.name, open(file_path, 'rb'), mime_type)}
                data["display_name"] = path.name
                
            elif file_obj:
                # Handle bytes or file-like
                import io
                if isinstance(file_obj, bytes):
                    f_stream = io.BytesIO(file_obj)
                else:
                    f_stream = file_obj
                    
                filename = display_name or "uploaded_file"
                files = {"file": (filename, f_stream, mime_type)}
                data["display_name"] = filename
            else:
                logger.error("upload_file requires either file_path or file_obj")
                return None

            # INCREASED TIMEOUT to 300s
            resp = requests.post(url, files=files, data=data, timeout=300)
            
            if resp.status_code == 200:
                logger.info("File upload successful.")
                data_json = resp.json()
                from types import SimpleNamespace
                return SimpleNamespace(**data_json)
            else:
                logger.error(f"File upload failed [URL: {url}]: {resp.text}")
                return None
        except Exception as e:
            logger.error(f"Error during file upload [URL: {url}]: {e}")
            return None

    def save_state_for_restart(self) -> bool:
        """
        Server manages state, so this is mostly a no-op or a signal to server.
        For now, we return True so bot logic proceeds.
        """
        # In a real impl, maybe POST /save_state
        logger.info("save_state_for_restart called. Returning True as server manages state.")
        return True

    def execute_restart(self):
        """
        If the bot calls this, it usually terminates itself or the whole app.
        In Client-Server, if Bot terminates, Launcher might restart it.
        """
        logger.info("Client requested restart. Exiting process...")
        sys.exit(0) # Launcher should handle the restart if configured.
    # --- Session Management ---
    def list_sessions(self) -> list:
        try:
            resp = requests.get(f"{self.base_url}/list_sessions")
            if resp.status_code == 200:
                return resp.json().get("sessions", [])
        except Exception as e:
            logger.error(f"Failed to list sessions: {e}")
        return []

    def get_session_mode(self, session_id: str) -> str:
        # For now client doesn't track this locally, ask server?
        # Or simple workaround: default to cache. Server needs endpoint.
        try:
            resp = requests.get(f"{self.base_url}/get_mode", params={"session_id": session_id}, timeout=5)
            if resp.status_code == 200:
                return resp.json().get("mode", "default")
        except Exception as e:
            logger.error(f"Failed to get session mode for {session_id}: {e}")
        return "default"

    def set_session_mode(self, session_id: str, mode: str):
        requests.post(f"{self.base_url}/switch_mode", json={"session_id": session_id, "mode": mode})

    def manage_session_history(self, session_id: str, count: int, index: int):
        # Truncation logic
        payload = {"session_id": session_id, "count": count, "index": index}
        requests.post(f"{self.base_url}/truncate_history", json=payload)

    # --- System ---
    def trigger_instruction_refresh(self, full_restart: bool = False) -> str:
        try:
            resp = requests.post(f"{self.base_url}/refresh_instructions", json={"restart": full_restart}, timeout=10)
            if resp.status_code == 200:
                return resp.json().get("status", "Refresh Triggered")
        except Exception as e: return f"Error: {e}"
        return "Failed"
    
    # --- Passthrough properties for GUI that might access .sessions directly ---
    # GUI accesses core.sessions[id] -> list of dicts.
    # We can property emulate this or fetch on demand.
    @property
    def sessions(self):
        # This is expensive if GUI polls it. 
        # Better to have GUI call get_history explicitly, but for refactor compat:
        return self._fetch_all_sessions_mock()

    def _fetch_all_sessions_mock(self):
        # Minimal mock: return empty dict or fetch active one?
        # Real implementation would be complex.
        # For now, return a defaultdict that fetches history on access?
        class RemoteSessionDict(dict):
            def __init__(self, client):
                self.client = client
                super().__init__()
            def get(self, key, default=None):
                # Fetch history for this key
                try:
                    resp = requests.get(f"{self.client.base_url}/history", params={"session_id": key, "limit": 50})
                    if resp.status_code == 200:
                        return resp.json().get("history", [])
                except: pass
                return default or []
            def __getitem__(self, key):
                val = self.get(key)
                if val is None: raise KeyError(key)
                return val
        return RemoteSessionDict(self)

    # --- Legacy/Deprecated Methods (Stubs to prevent crashes) ---
    def save_state_for_restart(self):
        logger.warning("Client: save_state_for_restart called but not supported in Client-Server mode.")
        return False

    def execute_restart(self):
        logger.warning("Client: execute_restart called. Please use the Launcher TUI to restart services.")
        pass

    def shutdown(self):
        # Client shutdown, generic cleanup
        pass
