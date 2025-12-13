
import requests
import json
import os
import sys
from pathlib import Path
from typing import Optional, Generator

class OrionClient:
    """
    A drop-in replacement for OrionCore that communicates with the backend Server.
    """
    def __init__(self, base_url: str = "http://127.0.0.1:8000"):
        self.base_url = base_url.rstrip("/")
        # Verify connection immediately? No, let it fail gracefully on first request or handled by Launcher.
    
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
                    "size_bytes": getattr(f, 'size_bytes', 0)
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
            with requests.post(url, json=payload, stream=True, timeout=120) as response:
                if response.status_code != 200:
                    yield {"type": "token", "content": f"Error from server: {response.text}"}
                    return

                # Server sends NDJSON (newline delimited JSON)
                for line in response.iter_lines():
                    if line:
                        try:
                            chunk = json.loads(line)
                            yield chunk
                        except json.JSONDecodeError:
                            yield {"type": "token", "content": f"[Chunk Error] {line}"}

        except requests.exceptions.ConnectionError:
            yield {"type": "token", "content": "[System Error] Could not connect to Orion Server. Is it running?"}
        except Exception as e:
            yield {"type": "token", "content": f"[System Error] Client exception: {e}"}

    def upload_file(self, file_bytes: bytes, display_name: str, mime_type: str) -> object:
        """
        Uploads bytes to server. Returns a SimpleNamespace object mimicking the Core's return.
        """
        url = f"{self.base_url}/upload_file"
        
        try:
            # We send using multipart/form-data
            files = {"file": (display_name, file_bytes, mime_type)}
            data = {"display_name": display_name, "mime_type": mime_type}
            
            resp = requests.post(url, files=files, data=data, timeout=60)
            
            if resp.status_code == 200:
                data = resp.json()
                # Return object with .name, .uri access
                from types import SimpleNamespace
                return SimpleNamespace(**data)
            else:
                print(f"Upload failed: {resp.text}")
                return None
        except Exception as e:
            print(f"Upload exception: {e}")
            return None

    def save_state_for_restart(self) -> bool:
        """
        Server manages state, so this is mostly a no-op or a signal to server.
        For now, we return True so bot logic proceeds.
        """
        # In a real impl, maybe POST /save_state
        return True

    def execute_restart(self):
        """
        If the bot calls this, it usually terminates itself or the whole app.
        In Client-Server, if Bot terminates, Launcher might restart it.
        """
        print("Client requested restart. Exiting process...")
        sys.exit(0) # Launcher should handle the restart if configured.
    # --- Session Management ---
    def list_sessions(self) -> list:
        try:
            resp = requests.get(f"{self.base_url}/list_sessions", timeout=5)
            if resp.status_code == 200:
                return resp.json().get("sessions", [])
        except: pass
        return []

    def get_session_mode(self, session_id: str) -> str:
        # For now client doesn't track this locally, ask server?
        # Or simple workaround: default to cache. Server needs endpoint.
        try:
            resp = requests.get(f"{self.base_url}/get_mode", params={"session_id": session_id}, timeout=5)
            if resp.status_code == 200:
                return resp.json().get("mode", "cache")
        except: pass
        return "cache"

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

    def shutdown(self):
        # Client shutdown, generic cleanup
        pass
