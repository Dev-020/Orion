import os
import json
import sqlite3
import pickle
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any, Union
from main_utils import config, main_functions as functions

# Type alias matching the structure used in Cores
# UserContent/ModelContent are typically objects, but here we treat them generically or use dicts from Lite
# For strict typing we'd need to import the exact types, but for now we'll use dynamic typing for the content objects.

class ChatObject:
    def __init__(self):
        """
        Centralized handler for:
        - Session Storage (in-memory)
        - Session Persistence (SQLite restart_state)
        - Database Archival (deep_memory)
        - History Management (Truncation & Token Limits)
        """
        self.sessions: Dict[str, List] = {}
        self.session_modes: Dict[str, str] = {} # Tracks "cache" vs "function"
        self.default_mode = "cache"

    # --- Session Management ---
    def get_session(self, session_id: str, history: List = None) -> List:
        """Retrieves an existing session or creates a new one."""
        if session_id not in self.sessions:
            print(f"--- [ChatObject] Creating new session for ID: {session_id} ---")
            self.sessions[session_id] = history if history is not None else []
        return self.sessions[session_id]

    def list_sessions(self) -> List[str]:
        """Returns a list of all active session IDs."""
        return list(self.sessions.keys())

    def manage_session_history(self, session_id: str, count: int = 0, index: int = -1) -> str:
        """
        Manages the history of a specific session (deletion/truncation).
        """
        if session_id not in self.sessions:
            return f"Session '{session_id}' not found."
        
        history = self.sessions[session_id]
        
        if index >= 0:
            if index < len(history):
                removed = len(history) - index
                self.sessions[session_id] = history[:index]
                return f"Truncated session '{session_id}' at index {index}. Removed {removed} exchanges."
            else:
                return f"Index {index} out of range for session '{session_id}'."
        
        elif count > 0:
            if count >= len(history):
                self.sessions[session_id] = []
                return f"Cleared all history for session '{session_id}'."
            else:
                self.sessions[session_id] = history[:-count]
                return f"Removed last {count} exchanges from session '{session_id}'."
            
        return "No action taken."

    # --- Mode Management ---
    def get_session_mode(self, session_id: str) -> str:
        return self.session_modes.get(session_id, self.default_mode)

    def set_session_mode(self, session_id: str, mode: str) -> str:
        if mode not in ["cache", "function"]:
            return f"Invalid mode '{mode}'. Use 'cache' or 'function'."
        self.session_modes[session_id] = mode
        return f"Session '{session_id}' switched to {mode.upper()} mode."

    # --- Token Safety ---
    def enforce_token_limit(self, session_id: str, token_limit: int):
        """
        Smart Truncation:
        Iteratively removes the oldest exchanges until the total history token count
        is below the specified `token_limit`.
        """
        if session_id not in self.sessions: return
        
        history = self.sessions[session_id]
        if not history: return

        # Calculate current total
        current_tokens = sum(ex.get("token_count", 0) for ex in history)
        
        # If we are already safe, do nothing
        if current_tokens <= token_limit:
            return

        print(f"--- [ChatObject] Enforcing limit {token_limit}. Current: {current_tokens} ---")
        
        while history and current_tokens > token_limit:
            removed = history.pop(0)
            removed_tokens = removed.get("token_count", 0)
            current_tokens -= removed_tokens
            # print(f"  - Removed exchange ({removed_tokens} tokens). New Total: {current_tokens}")
        
        print(f"--- [ChatObject] Truncation complete. Final: {current_tokens} tokens. ---")

    # --- Archival ---
    def archive_exchange(self, session_id, user_id, user_name, prompt_text, response_text, 
                         attachments, token_count, vdb_context, model_source,
                         user_content_obj, model_content_obj, tool_calls_list=None):
        """
        1. Writes the interaction to the `deep_memory` database table.
        2. Retrieves the new DB ID (for correct VDB context exclusion).
        3. Appends the structured exchange to the in-memory history.
        """
        
        # 1. DB Write
        try:
            # Handle function calls data
            function_calls_json = "[]"
            if tool_calls_list:
                # Assuming tool_calls_list is a list of objects that have model_dump_json()
                # or are already dicts. Need generic handling.
                try:
                    jsons = [t.model_dump_json() for t in tool_calls_list]
                    function_calls_json = f"[{', '.join(jsons)}]"
                except:
                    # Fallback for Lite/Dict-based
                    function_calls_json = json.dumps(tool_calls_list)

            data = {
                "session_id": session_id,
                "user_id": user_id,
                "user_name": user_name,
                "timestamp": int(datetime.now(timezone.utc).timestamp()),
                "prompt_text": prompt_text,
                "response_text": response_text,
                "attachments_metadata": json.dumps(attachments),
                "token": token_count,
                "function_calls": function_calls_json,
                "vdb_context": vdb_context, 
                "model_source": model_source
            }
            
            functions.execute_write(table="deep_memory", operation="insert", user_id=user_id, data=data)
            
            # 2. Fetch ID
            new_db_id = "db_id_placeholder"
            latest_id_result = functions.execute_sql_read(query="SELECT id FROM deep_memory ORDER BY id DESC LIMIT 1")
            try:
                latest_id_data = json.loads(latest_id_result)
                if latest_id_data and latest_id_data[0].get('id'):
                    new_db_id = str(latest_id_data[0]['id'])
            except: pass

        except Exception as e:
            print(f"[ChatObject] Archival/DB Error: {e}")
            new_db_id = None

        # 3. Update History
        new_exchange = {
            "user_content": user_content_obj,
            "tool_calls": tool_calls_list if tool_calls_list else [],
            "model_content": model_content_obj,
            "db_id": new_db_id,
            "token_count": token_count
        }
        
        self.get_session(session_id).append(new_exchange)
        return new_db_id

    # --- Persistence ---
    def save_state_for_restart(self) -> bool:
        """Serializes current sessions to sqlite for restart."""
        print("--- [ChatObject] Saving session states... ---")
        try:
            with sqlite3.connect(functions.config.DB_FILE) as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM restart_state")
                
                records = []
                for sid, hist in self.sessions.items():
                    blob = pickle.dumps(hist)
                    records.append((sid, blob))
                
                cursor.executemany("INSERT INTO restart_state (session_id, history_blob) VALUES (?, ?)", records)
                conn.commit()
            print(f"  - Saved {len(records)} sessions.")
            return True
        except Exception as e:
            print(f"  - ERROR Saving State: {e}")
            return False

    def load_state_on_restart(self) -> bool:
        """Loads sessions from sqlite after restart."""
        try:
            with sqlite3.connect(functions.config.DB_FILE) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT session_id, history_blob FROM restart_state")
                rows = cursor.fetchall()
                if not rows: return False

                print("--- [ChatObject] Loading persistent state... ---")
                self.sessions = {}
                for sid, blob in rows:
                    self.sessions[sid] = pickle.loads(blob)
                
                cursor.execute("DELETE FROM restart_state")
                conn.commit()
                print(f"  - Loaded {len(self.sessions)} sessions.")
                return True
        except Exception as e:
            print(f"  - ERROR Loading State: {e}")
            return False
