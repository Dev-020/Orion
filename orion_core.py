# orion_core.py (Final Unified Model)
import importlib
import os
import sqlite3
from datetime import datetime, timezone
import sys
from google import genai
from google.genai import types
import functions
import io
from dotenv import load_dotenv
import json
import pickle
from system_utils import run_startup_diagnostics, generate_manifests

# This single class now manages everything: state, sessions, and core logic.

# Define instruction files for clarity
INSTRUCTIONS_FILES = [
    'Project_Overview.md', 
    #'Homebrew_Compendium.md',
    'General_Prompt_Optimizer.md',
    'DND_Handout.md',
    'master_manifest.json'
]
INSTRUCTIONS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'instructions')
DB_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'orion_database.sqlite')
load_dotenv() # Load environment variables from .env file

class OrionCore:
    
    def __init__(self, model_name: str = "gemini-1.5-pro"):
        """Initializes the unified AI 'brain', including session management."""
        self.MAX_HISTORY_EXCHANGES = 30 # Set the hard limit for conversation history
        self.restart_pending = False
        
        # NEW: Initialize the session state for excluded source IDs
        self.session_excluded_ids: dict[str, list[str]] = {}

        # Refreshing Core Instructions
        print("--- Syncing Core Instructions... ---")
        self.discord_id = os.getenv("DISCORD_OWNER_ID")
        if self.discord_id:
            functions.manual_sync_instructions(self.discord_id)
        generate_manifests.main()
        print("--- Core Instructions Successfully synced.... ---")
        
        # Initializes Orion AI
        print("--- Initializing Orion Core (Unified Model) ---")
        self.model_name = model_name
        self.client = genai.Client(
            api_key=os.getenv("GOOGLE_API_KEY"),
            http_options=types.HttpOptions(api_version='v1alpha')
        )
        self.tools = self._load_tools()
        self.tools.append(self.trigger_instruction_refresh)
        
        # --- Run Startup Diagnostics ---
        tools_dict = {func.__name__: func for func in self.tools}
        diagnostics_passed = run_startup_diagnostics.run_heartbeat_check(tools_dict)
        diagnostic_message = "[System Diagnostic: All core tools passed the initial heartbeat check and are considered operational.]" if diagnostics_passed else "[System Diagnostic: WARNING - One or more core tools failed the initial heartbeat check. Functionality may be impaired. Advise the Primary Operator.]"
        
        base_instructions = self._read_all_instructions()
        self.current_instructions = f"{base_instructions}\n\n---\n\n{diagnostic_message}"

        if not self._load_state_on_restart():
            self.sessions: dict[str, list] = {}
        
        print(f"--- Orion Core is online and ready. Managing {len(self.sessions)} session(s). ---")
        
    def _read_all_instructions(self) -> str:
        """Reads and concatenates all specified instruction files."""
        prompt_parts = []
        for filename in INSTRUCTIONS_FILES:
            filepath = os.path.join(INSTRUCTIONS_DIR, filename)
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    prompt_parts.append(f.read())
            except FileNotFoundError:
                print(f"WARNING: Instruction file not found, skipping: {filepath}")
        return "\n\n---\n\n".join(prompt_parts)

    def _load_tools(self) -> list:
        """Dynamically loads tools from the 'functions' module."""
        if hasattr(functions, '__all__'):
            print(f"--- Loading {len(functions.__all__)} tools from functions.__all__ ---")
            return [getattr(functions, func_name) for func_name in functions.__all__]
        else:
            print("WARNING: 'functions.py' does not define __all__. No tools will be loaded.")
            return []

    def _get_session(self, session_id: str, history: list = []) -> list:
        """Retrieves or creates a chat session."""
        if session_id not in self.sessions:
            print(f"--- Creating new session for ID: {session_id} ---")
            self.sessions[session_id] = history
            self.session_excluded_ids.setdefault(session_id, []) # Ensure an exclusion list exists
        return self.sessions[session_id]

    def trigger_instruction_refresh(self, full_restart: bool = False):
        """Performs a hot-swap or initiates a full system restart."""
        if full_restart:
            print("---! FULL SYSTEM RESTART INITIATED !---")
            self.restart_pending = True
            return "[System Note]: Restart sequence initiated. The system will reboot after this response."
        
        print("---! HOT-SWAP INSTRUCTIONS TRIGGERED !---")
        try:
            importlib.reload(functions)
            self.tools = self._load_tools()
            self.tools.append(self.trigger_instruction_refresh)
            print("  - Tools have been successfully reloaded.")
        except Exception as e:
            print(f"  - ERROR: Failed to reload tools: {e}")
        
        if self.discord_id:
            functions.manual_sync_instructions(self.discord_id)
        generate_manifests.main()
        self.current_instructions = self._read_all_instructions()
        print(f"--- HOT-SWAP COMPLETE: {len(self.sessions)} session(s) migrated. ---")
        return 'Refresh Complete. Tools and Instructions are all up to date.'

    def save_state_for_restart(self) -> bool:
        """Serializes the comprehensive state of all active sessions to the database."""
        print("--- Saving session states for system restart... ---")
        try:
            with sqlite3.connect(DB_FILE) as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM restart_state")
                
                records_to_save = []
                for session_id, history in self.sessions.items():
                    history_blob = pickle.dumps(history)
                    excluded_ids_list = self.session_excluded_ids.get(session_id, [])
                    excluded_ids_blob = pickle.dumps(excluded_ids_list)
                    records_to_save.append((session_id, history_blob, excluded_ids_blob))

                cursor.executemany(
                    "INSERT INTO restart_state (session_id, history_blob, excluded_ids_blob) VALUES (?, ?, ?)",
                    records_to_save
                )
                conn.commit()
                print(f"  - State for {len(records_to_save)} session(s) saved to database.")
                return True
        except Exception as e:
            print(f"  - ERROR: Failed to save state for restart: {e}")
            return False

    def _load_state_on_restart(self) -> bool:
        """Deserializes session states from the database and rebuilds sessions."""
        try:
            with sqlite3.connect(DB_FILE) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT session_id, history_blob, excluded_ids_blob FROM restart_state")
                rows = cursor.fetchall()
                if not rows:
                    return False

                print("--- Restart state detected in database. Loading sessions... ---")
                self.sessions = {}
                self.session_excluded_ids = {}
                for session_id, history_blob, excluded_ids_blob in rows:
                    self._get_session(session_id, history=pickle.loads(history_blob))
                    if excluded_ids_blob:
                        self.session_excluded_ids[session_id] = pickle.loads(excluded_ids_blob)
                
                cursor.execute("DELETE FROM restart_state")
                conn.commit()
                print(f"  - Successfully loaded state for {len(self.sessions)} session(s).")
                return True
        except Exception as e:
            print(f"  - ERROR: Failed to load restart state: {e}. Starting with a clean slate.")
            try:
                with sqlite3.connect(DB_FILE) as conn:
                    conn.execute("DELETE FROM restart_state")
                    conn.commit()
            except Exception as cleanup_e:
                print(f"  - CRITICAL: Failed to even clean up restart_state table: {cleanup_e}")
            return False

    def process_prompt(self, session_id: str, user_prompt: str, file_check: list, user_id: str, user_name: str) -> tuple[str | None, int | None, bool]:
        """Processes a prompt and archives the result."""
        print(f"--- Processing prompt for session {session_id} and user {user_name} ---")
        try:
            chat_session = self._get_session(session_id)
            timestamp_utc_iso = datetime.now(timezone.utc).isoformat()
            
            # --- CONTEXT INJECTION CONTROL (V3 - Persistent State) ---
            vdb_result = ""
            vdb_content = None
            if user_id == os.getenv("DISCORD_OWNER_ID"):
                excluded_ids = self.session_excluded_ids.get(session_id, [])
                
                # Query Deep Memory, excluding IDs already in the session
                deep_memory_where = {"source_table": "deep_memory"}
                if excluded_ids:
                    deep_memory_where["id"] = {"$nin": excluded_ids}
                
                deep_memory_results = functions.execute_vdb_read(query_texts=[user_prompt], n_results=5, where=deep_memory_where)

                # Query Long-Term Memory (no exclusion needed)
                long_term_results = functions.execute_vdb_read(query_texts=[user_prompt], n_results=2, where={"source_table": "long_term_memory"})
                
                vdb_result = deep_memory_results + "\n" + long_term_results
                vdb_response = f'[Relevant Semantic Information from Vector DB:{vdb_result}]'
                vdb_content = types.UserContent(parts=types.Part.from_text(text=vdb_response))

            data_envelope = {"auth": {"user_id": user_id, "user_name": user_name, "session_id": session_id, "authentication_status": "PRIMARY_OPERATOR" if user_id == os.getenv("DISCORD_OWNER_ID") else "EXTERNAL_ENTITY"}, "timestamp_utc": timestamp_utc_iso, "prompt": user_prompt}
            
            structured_prompt = types.Part.from_text(text=json.dumps(data_envelope))
            final_prompt_parts = [structured_prompt]
            attachments_for_db = []
            if file_check:
                for file in file_check:
                    final_prompt_parts.append(types.Part.from_uri(file_uri=file.uri, mime_type=file.mime_type))
                    attachments_for_db.append({"file_ref": file.name, "file_name": file.display_name, "mime_type": file.mime_type, "size_bytes": file.size_bytes})
            
            final_content = types.UserContent(parts=final_prompt_parts)
            contents_to_send = chat_session + ([vdb_content] if vdb_content else []) + [final_content]

            print(f"  - Sending Prompt to Orion...")
            response = self.client.models.generate_content(model=f'{self.model_name}', contents=contents_to_send, config=types.GenerateContentConfig(system_instruction=self.current_instructions, tools=self.tools))
            
            chat_session.append(final_content)
            
            if response.automatic_function_calling_history:
                chat_session.extend(response.automatic_function_calling_history)

            final_text = "".join(part.text for part in response.candidates[0].content.parts) if response.candidates[0].content else ""
            chat_session.append(response.candidates[0].content)
            
            if len(chat_session) > self.MAX_HISTORY_EXCHANGES * 2: # Simple approximation
                 user_message_indices = [i for i, content in enumerate(chat_session) if content.role == 'user' and any(part.text for part in content.parts)]
                 if len(user_message_indices) > self.MAX_HISTORY_EXCHANGES:
                     trim_until_index = user_message_indices[1]
                     self.sessions[session_id] = chat_session[trim_until_index:]
            
            token_count = response.usage_metadata.total_token_count if response.usage_metadata else 0
            self._archive_exchange_to_db(session_id, user_id, user_name, user_prompt, final_text, attachments_for_db, token_count, response.automatic_function_calling_history, vdb_result)
            
            should_restart = self.restart_pending
            if self.restart_pending: self.restart_pending = False
            return final_text, token_count, should_restart
            
        except Exception as e:
            print(f"ERROR processing prompt for '{session_id}': {e}")
            return "I'm sorry, an internal error occurred while processing your request.", 0, False

    def _archive_exchange_to_db(self, session_id, user_id, user_name, prompt, response, attachment, token_count, function_call, vdb_context):
        """Writes the exchange to the database and updates the session's excluded ID list."""
        try:
            function_calls_json_string = json.dumps([content.model_dump() for content in function_call]) if function_call else "[]"
            data_payload = {"session_id": session_id, "user_id": user_id, "user_name": user_name, "timestamp": int(datetime.now(timezone.utc).timestamp()), "prompt_text": prompt, "response_text": response, "attachments_metadata": json.dumps(attachment), "token": token_count, "function_calls": function_calls_json_string, "vdb_context": vdb_context}
            
            write_result = functions.execute_write(table="deep_memory", operation="insert", user_id=user_id, data=data_payload)
            print(f" -> Archival result: {write_result}")

            # NEW: Incrementally update the exclusion list
            if "Success" in write_result:
                latest_id_result = functions.execute_sql_read(query="SELECT id FROM deep_memory ORDER BY id DESC LIMIT 1")
                latest_id_data = json.loads(latest_id_result)
                if latest_id_data:
                    newest_id = str(latest_id_data[0]['id'])
                    self.session_excluded_ids.setdefault(session_id, []).append(newest_id)
                    print(f"  - Updated session '{session_id}' exclusion list with new ID: {newest_id}")

        except Exception as e:
            print(f"ERROR: An unexpected error occurred during archival for user {user_id}: {e}")

    def upload_file(self, file_bytes: bytes, display_name: str, mime_type: str):
        """Uploads a file to the GenAI File API."""
        try:
            print(f"  - Uploading file '{display_name}' to the File API...")
            return self.client.files.upload(file=io.BytesIO(file_bytes), config=types.UploadFileConfig(mime_type=mime_type, display_name=display_name))
        except Exception as e:
            print(f"ERROR: File API upload failed for '{display_name}'. Error: {e}")
            return None

    def shutdown(self):
        """Performs a clean shutdown."""
        print("--- Orion Core shutting down. ---")

    def execute_restart(self):
        """Executes the final step of the restart."""
        print("  - State saved. Executing restart...")
        os.execv(sys.executable, ['python'] + sys.argv)