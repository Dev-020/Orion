# orion_core_lite.py (Gemma/Lite Edition - Architecturally Aligned)
import os
import json
import sqlite3
import pickle
import sys
from typing import Generator
from datetime import datetime, timezone
from dotenv import load_dotenv

# API Backends
from google import genai
from google.genai import types
try:
    import ollama
except ImportError:
    ollama = None 

from main_utils import config, main_functions as functions
from system_utils import orion_replay, orion_tts

# Define instruction files
INSTRUCTIONS_FILES = [
    'Primary_Directive_Lite.md' 
]

# --- Paths ---
INSTRUCTIONS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'instructions')

class OrionLiteCore:
    
    def __init__(self, model_name: str = config.AI_MODEL, persona: str = "default"):
        """
        Initializes the Lite version of Orion Core.
        Architecture mimics OrionCore (Pro) line-for-line where applicable.
        """
        if config.BACKEND == "api":
            print(f"--- [Lite Core] Initializing for model: {model_name} (Backend: {config.BACKEND})     ---")
        else:
            print(f"--- [Lite Core] Initializing for model: {config.LOCAL_MODEL} (Backend: {config.BACKEND}) ---")
        self.MAX_HISTORY_EXCHANGES = 30 
        self.restart_pending = False
        
        # Core instance accessible to tools (even if tools aren't used, for consistency)
        config.ORION_CORE_INSTANCE = self

        self.current_turn_context = None
        self.model_name = model_name
        self.persona = config.PERSONA = persona
        self.backend = getattr(config, 'BACKEND', 'api').lower()
        self.local_model = getattr(config, 'LOCAL_MODEL', 'gemma3:1b')
        
        # Initialize Database access
        functions.initialize_persona(self.persona)
        
        # Vision System (Optional)
        self.vision_attachments = {}
        if config.VISION:
            print("--- [Lite Core] Vision Module Activated ---")
            orion_replay.launch_obs_hidden()
            if orion_replay.connect_to_obs():
                 orion_replay.start_replay_watcher(orion_replay.REPLAY_SAVE_PATH, self._vision_file_handler)
                 orion_replay.start_vision_thread()

        # TTS System (Optional)
        if config.VOICE:
            orion_tts.start_tts_thread()
            print("--- [Lite Core] TTS Module Activated ---")
            
        # Refreshing Core Instructions (Simplified)
        print("--- Syncing Core Instructions... ---")
        self.current_instructions = self._read_all_instructions()
        if not self.current_instructions:
            self.current_instructions = "You are Orion, a helpful AI assistant."

        # Setup Client
        self._setup_client()

        # Session Management
        self.sessions = {}
        if not self._load_state_on_restart():
             self.sessions = {}
        
        print(f"--- [Lite Core] Online. Managing {len(self.sessions)} session(s). ---")

    def _setup_client(self):
        """Initializes the appropriate API client."""
        if self.backend == "api":
            if config.VERTEX:
                self.client = genai.Client(vertexai=True, project=os.getenv("GOOGLE_CLOUD_PROJECT_ID"), location="global")
            else:
                self.client = genai.Client(api_key=os.getenv("GOOGLE_API_KEY"))
        elif self.backend == "ollama":
            if ollama is None:
                raise ImportError("Ollama library not found. Please install with `pip install ollama`.")
            print(f"--- [Lite Core] Using Local Ollama: {self.local_model} ---")
            self.client = ollama.Client() 

    def _read_all_instructions(self) -> str:
        """Reads instruction files."""
        prompt_parts = []
        for filename in INSTRUCTIONS_FILES:
            filepath = os.path.join(INSTRUCTIONS_DIR, filename)
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    prompt_parts.append(f.read())
            except FileNotFoundError:
                print(f"WARNING: File not found: {filepath}")
        return "\n\n".join(prompt_parts)

    def _vision_file_handler(self, file_path: str):
        """Callback for vision system."""
        try:
             with open(file_path, 'rb') as f:
                self.vision_attachments = {"video_bytes": f.read(), "display_name": os.path.basename(file_path)}
             print(f"[Vision] Captured {self.vision_attachments['display_name']}")
        except Exception as e:
            print(f"[Vision Error] {e}")

    def _get_session(self, session_id: str) -> list:
        if session_id not in self.sessions:
            print(f"--- Creating new session for ID: {session_id} ---")
            self.sessions[session_id] = []
        return self.sessions[session_id]

    def flatten_history(self, session_id: str) -> list:
        """
        Takes a session ID, retrieves the custom ExchangeDict history, and flattens
        it into the format required by the GenAI API (list[Content]).
        For Ollama, we do a different flattening in _generate, or we assume this is just for API usage.
        """
        chat_session = self.sessions.get(session_id, [])
        contents_to_send = []
        
        # API requires alternation. We must ensure User -> Model -> User
        # If we use the Pro logic directly, it works for Pro history structure.
        # But Lite history structure is simpler? No, let's keep it consistent.
        # [{"user_content":..., "model_content": ...}]? 
        # Actually Pro history is list of dicts with keys "user_content", "model_content".
        
        for exchange in chat_session:
            if exchange.get("user_content"):
                contents_to_send.append(exchange["user_content"])
            # Lite has no tools, so skip tool_calls check or keep for compatibility
            if exchange.get("model_content"):
                contents_to_send.append(exchange["model_content"])
        return contents_to_send

    def _format_vdb_results_for_context(self, raw_json: str, source_name: str) -> str:
        """
        Parses VDB results. Identical logic to Pro.
        """
        try:
            data = json.loads(raw_json)
            if not data.get('documents') or not data['documents'][0]:
                return ""

            output_lines = [f"--- Context from {source_name} ---"]
            for i, doc in enumerate(data['documents'][0]):
                 # Simplified formatting
                 output_lines.append(f"- {doc}")
            return "\\n".join(output_lines)
        except:
            return ""

    def _prepare_prompt_data(self, session_id: str, user_prompt: str, file_check: list, user_id: str, user_name: str):
        """
        Internal helper: Prepares all data, context, and file attachments.
        Returns the standard 5-tuple used in OrionCore.
        """
        print(f"----- Processing prompt for session {session_id} and user {user_name} -----")
        chat_session = self._get_session(session_id)
        timestamp_utc_iso = datetime.now(timezone.utc).isoformat()
        
        # --- Context Injection ---
        excluded_ids = [ex["db_id"] for ex in chat_session if ex.get("db_id")]
        
        # 1. Memory Lookups (Simplified but structurally identical)
        deep_memory_where = {"source_table": "deep_memory"} 
        if excluded_ids:
             deep_memory_where = {"$and": [{"source_table": "deep_memory"}, {"source_id": {"$nin": excluded_ids}}, {"session_id": session_id}]}

        try:
            deep_memory_results_raw = functions.execute_vdb_read(query_texts=[user_prompt], n_results=3, where=deep_memory_where)
            long_term_results_raw = functions.execute_vdb_read(query_texts=[user_prompt], n_results=2, where={"source_table": "long_term_memory"})
            
            formatted_deep_mem = self._format_vdb_results_for_context(deep_memory_results_raw, "Deep Memory")
            formatted_ltm = self._format_vdb_results_for_context(long_term_results_raw, "Long-Term Memory")
            
            formatted_vdb_context = f"{formatted_deep_mem}\\n{formatted_ltm}".strip()
        except:
            formatted_vdb_context = ""
            deep_memory_results_raw = "{}"
            long_term_results_raw = "{}"

        # ID Extraction
        context_ids_for_db = []
        for raw_result in [deep_memory_results_raw, long_term_results_raw]:
            if raw_result:
                try:
                    result_data = json.loads(raw_result)
                    if result_data.get('ids') and result_data['ids'][0]:
                        context_ids_for_db.extend(result_data['ids'][0])
                except Exception:
                    pass

        vdb_response = f'[Relevant Context:\\n{formatted_vdb_context}]' if formatted_vdb_context else ""

        # Format User Content
        data_envelope = {
            "auth": { "user_id": user_id, "user_name": user_name, "session_id": session_id },
            "timestamp_utc": timestamp_utc_iso,
            "system_notifications": [],
            "user_prompt": user_prompt,
            "vdb_context": vdb_response
        }

        # Vision Attachment (Simplified)
        if config.VISION and self.vision_attachments:
             data_envelope["system_notifications"].append(f"[Vision: Attached {self.vision_attachments['display_name']}]")
             # logic to actually attach bytes would go here, identical to Pro
             self.vision_attachments = {}

        # Construct User Content Part
        final_text_part = types.Part.from_text(text=json.dumps(data_envelope, indent=2))
        
        # Lite excludes file_check generally, but if we wanted to support it via API we could.
        # For now, we assume Lite = No Files to be safe, or we blindly attach them if API.
        final_part = [final_text_part]
        
        user_content_for_db = types.UserContent(parts=[types.Part.from_text(text=json.dumps(data_envelope, indent=2))])
        final_content = types.UserContent(parts=final_part) # This is the object for the API

        # History
        contents_to_send = self.flatten_history(session_id)
        contents_to_send.append(final_content)
        
        attachments_for_db = [] # simplified
        
        return (contents_to_send, data_envelope, context_ids_for_db, attachments_for_db, user_content_for_db)

    def _generate_stream_response(self, contents_to_send, data_envelope, session_id, user_id, user_name, user_prompt, attachments_for_db, context_ids_for_db, user_content_for_db):
        """
        Internal helper: Handles streaming generation.
        mimics signature of Pro, but branches for backend.
        """
        print(f"----- Sending Prompt to Orion Lite ({config.BACKEND}) . . . -----")
        
        full_response_text = ""
        token_count = 0
        
        try:
            if self.backend == "api":
                # API Mode - Gemma does NOT support system_instruction in config.
                # We must prepend it to the history as a User message.
                
                system_content = types.Content(
                    role="user",
                    parts=[types.Part.from_text(text=f"System Context:\n{self.current_instructions}")]
                )
                
                # Prepend to the prompt list
                final_contents = [system_content] + contents_to_send
                
                response_stream = self.client.models.generate_content_stream(
                    model=self.model_name,
                    contents=final_contents,
                    # Config: Standard, NO system_instruction param
                    config=types.GenerateContentConfig(
                        max_output_tokens=8192,
                        temperature=0.7
                    )
                )
                
                for chunk in response_stream:
                    if chunk.candidates and chunk.candidates[0].content.parts:
                        text = chunk.candidates[0].content.parts[0].text
                        if text:
                            yield {"type": "token", "content": text}
                            full_response_text += text
                            if config.VOICE: orion_tts.process_stream_chunk(text)
                    if chunk.usage_metadata:
                          token_count = chunk.usage_metadata.total_token_count

            elif self.backend == "ollama":
                # Ollama Mode - Requires Conversion from `contents_to_send` (Google Types) to List[Dict]
                ollama_messages = []
                
                # System Prompt
                ollama_messages.append({"role": "system", "content": self.current_instructions})
                
                # History
                # We iterate contents_to_send, which are types.Content objects
                for content in contents_to_send:
                    role = "user" if content.role == "user" else "assistant"
                    text_parts = [p.text for p in content.parts if p.text]
                    full_content_text = "\\n".join(text_parts)
                    ollama_messages.append({"role": role, "content": full_content_text})
                
                # Generate
                stream_resp = self.client.chat(
                    model=self.local_model,
                    messages=ollama_messages,
                    stream=True,
                    options={
                        'num_ctx': config.LOCAL_CONTEXT_WINDOW,
                        'temperature': 0.7
                    }
                )
                for chunk in stream_resp:
                    content = chunk['message']['content']
                    if content:
                        print(f"{content}", end="", flush=True) # DEBUG: Printing chunks directly
                        yield {"type": "token", "content": content}
                        full_response_text += content
                        if config.VOICE: orion_tts.process_stream_chunk(content)
            
            if config.VOICE: orion_tts.flush_stream()
            
            # Reconstruct Model Content Object (for consistency)
            model_content_obj = types.Content(
                role="model",
                parts=[types.Part.from_text(text=full_response_text)]
            )
            
            # Finalize
            should_restart = self._finalize_exchange(
                session_id, user_id, user_name, user_prompt, full_response_text, token_count,
                 attachments_for_db, [], context_ids_for_db, user_content_for_db, model_content_obj
            )
            
            yield {
                "type": "usage",
                "token_count": token_count,
                "restart_pending": should_restart
            }

        except Exception as e:
            print(f"ERROR: {e}")
            yield {"type": "token", "content": f"[System Error: {e}]"}

    def _finalize_exchange(self, session_id, user_id, user_name, user_prompt, response_text, token_count, attachments_for_db, new_tool_turns, context_ids_for_db, user_content_for_db, model_content_obj):
        """
        Internal helper: Handles post-processing. Identical signature to Pro.
        """
        # Archive
        new_db_id = self._archive_exchange_to_db(
             session_id, user_id, user_name, user_prompt, response_text, 
             attachments_for_db, token_count, json.dumps(context_ids_for_db)
        )
        
        # Update History
        new_exchange = {
            "user_content": user_content_for_db,
            "tool_calls": [], # Lite has no tools
            "model_content": model_content_obj,
            "db_id": new_db_id,
            "token_count": token_count
        }
        
        chat_session = self._get_session(session_id)
        chat_session.append(new_exchange)
        
        # Limit History
        if len(chat_session) > self.MAX_HISTORY_EXCHANGES:
             # simple truncation
             del chat_session[:5]
             
        print(f"----- Response Generated ({token_count} tokens) -----")
        return False

    def _archive_exchange_to_db(self, session_id, user_id, user_name, prompt, response, attachments, token_count, vdb_context):
        """
        Writes to DB.
        """
        try:
             source = self.local_model if self.backend == "ollama" else self.model_name
             data = {
                "session_id": session_id,
                "user_id": user_id,
                "user_name": user_name,
                "timestamp": int(datetime.now(timezone.utc).timestamp()),
                "prompt_text": prompt,
                "response_text": response,
                "attachments_metadata": json.dumps(attachments),
                "token": token_count,
                "function_calls": "[]",
                "vdb_context": vdb_context, 
                "model_source": source
            }
             result = functions.execute_write(table="deep_memory", operation="insert", user_id=user_id, data=data)
             
             # Fetch the new ID for context exclusion
             latest_id_result = functions.execute_sql_read(query="SELECT id FROM deep_memory ORDER BY id DESC LIMIT 1")
             latest_id_data = json.loads(latest_id_result)
             if latest_id_data and latest_id_data[0].get('id'):
                 return str(latest_id_data[0]['id'])
             
             return "db_id_placeholder"
        except Exception as e:
            print(f"Archival/DB Error: {e}")
            return None

    def process_prompt(self, session_id: str, user_prompt: str, file_check: list, user_id: str, user_name: str, stream: bool = False) -> Generator:
        """
        Orchestrator: Identical to Pro.
        """
        try:
            yield {"type": "status", "content": "Initializing Request..."}
            
            # --- Smart Truncation (Token Safety) ---
            # Gemma API has a ~15k token limit usually. We enforce a safe rolling window.
            SAFE_TOKEN_LIMIT = 10000 
            chat_session = self._get_session(session_id)
            
            # Estimate current load
            estimated_prompt_tokens = len(user_prompt) // 3 + 500 # + overhead
            current_history_tokens = sum(ex.get("token_count", 0) for ex in chat_session)
            
            while chat_session and (current_history_tokens + estimated_prompt_tokens > SAFE_TOKEN_LIMIT):
                removed = chat_session.pop(0)
                current_history_tokens -= removed.get("token_count", 0)
                print(f"--- [Lite Core] Truncating history for token safety. Removed exchange with {removed.get('token_count', 0)} tokens. ---")
            
            yield {"type": "status", "content": "Accessing Memory..."}
            
            (contents_to_send, data_envelope, context_ids_for_db, attachments_for_db, user_content_for_db) = \
                self._prepare_prompt_data(session_id, user_prompt, file_check, user_id, user_name)
            
            yield {"type": "status", "content": "Thinking..."}
            
            # Lite only supports streaming for now in this impl, or we redirect
            yield from self._generate_stream_response(
                contents_to_send, data_envelope, session_id, user_id, user_name, user_prompt,
                attachments_for_db, context_ids_for_db, user_content_for_db
            )
            
        except Exception as e:
            print(f"CRITICAL ERROR: {e}")
            yield {"type": "token", "content": f"[System Error: {e}]"}

    def _load_state_on_restart(self) -> bool:
        """Deserializes session histories from the database and rebuilds sessions."""
        try:
            with sqlite3.connect(functions.config.DB_FILE) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT session_id, history_blob FROM restart_state")
                rows = cursor.fetchall()
                if not rows:
                    return False 

                print("--- [Lite Core] Restart state detected. Loading sessions... ---")
                self.sessions = {}
                for session_id, history_blob in rows:
                    history = pickle.loads(history_blob)
                    self._get_session(session_id, history=history)

                cursor.execute("DELETE FROM restart_state") 
                conn.commit()
                print(f"  - Successfully loaded state for {len(self.sessions)} session(s).")
                return True
        except Exception as e:
             print(f"  - ERROR: Failed to load restart state: {e}")
             return False

    def list_sessions(self) -> list:
        """Returns a list of all active session IDs."""
        return list(self.sessions.keys())

    def manage_session_history(self, session_id: str, count: int = 0, index: int = -1) -> str:
        """
        Manages the history of a specific session.
        If count > 0, it removes that many recent exchanges.
        If index >= 0, it truncates history from that index onwards.
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

    def get_session_mode(self, session_id: str) -> str:
        """Compatible stub for Lite Core."""
        return "lite"

    def set_session_mode(self, session_id: str, mode: str) -> str:
        """Compatible stub for Lite Core."""
        return "Lite Core does not support mode switching."
    
    def save_state_for_restart(self) -> bool:
        """Serializes the comprehensive history of all active sessions to the database."""
        print("--- [Lite Core] Saving session states for system restart... ---")
        try:
            with sqlite3.connect(functions.config.DB_FILE) as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM restart_state") # Clear any old state
                
                records_to_save = []
                for session_id, history in self.sessions.items():
                    history_blob = pickle.dumps(history)
                    records_to_save.append((session_id, history_blob))
                
                cursor.executemany(
                    "INSERT INTO restart_state (session_id, history_blob) VALUES (?, ?)",
                    records_to_save
                )
                conn.commit()
                print(f"  - State for {len(records_to_save)} session(s) saved to database.")
                return True
        except Exception as e:
            print(f"  - ERROR: Failed to save state for restart: {e}")
            return False

    def trigger_instruction_refresh(self, full_restart=False):
        # Stub logic
        self.current_instructions = self._read_all_instructions()
        print("Instructions refreshed.")

    def shutdown(self):
        """Performs a clean shutdown."""
        print("--- Orion Core shutting down. ---")
        # --- NEW: Stop the TTS thread on shutdown ---
        if config.VOICE:
            orion_tts.stop_tts_thread()
        if config.VISION:
            orion_replay.shutdown_obs()
        print("--- Orion is now offline. ---")

    def execute_restart(self):
        """
        Executes the final step of the restart by shutting down gracefully
        and then replacing the current process.
        """
        print("  - State saved. Performing graceful shutdown before restart...")
        self.shutdown() # <-- CRITICAL: Call the shutdown method here.
        print("  - Shutdown complete. Executing process replacement...")
        os.execv(sys.executable, ['python'] + sys.argv)
