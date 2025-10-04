# orion_core.py (Final Unified Model)
import importlib
import os
import sqlite3
from datetime import datetime, timezone
import sys
from google import genai
from google.genai import types, chats
import functions
import io
from dotenv import load_dotenv
import json
import pickle
from system_utils import run_startup_diagnostics, generate_manifests

# This single class now manages everything: state, sessions, and core logic.

# Define instruction files for clarity
INSTRUCTIONS_FILES = [
    'Project_Overview.txt', 
    'Homebrew_Compedium.txt',
    'General_Prompt_Optimizer.txt',
    'DND_Handout.txt',
    'master_manifest.json'
]
INSTRUCTIONS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'instructions')
DB_FILE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'orion_database.sqlite')
load_dotenv() # Load environment variables from .env file

class OrionCore:
    
    def __init__(self, model_name: str = "gemini-2.5-pro"):
        """Initializes the unified AI 'brain', including session management."""
        self.restart_pending = False

        # Refreshing Core Instructions
        print("--- Syncing Core Instructions... ---")
        discord_id = os.getenv("DISCORD_OWNER_ID")
        if discord_id:
            functions.manual_sync_instructions(discord_id)
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
        # This check runs once per startup/restart.
        tools_dict = {func.__name__: func for func in self.tools}
        diagnostics_passed = run_startup_diagnostics.run_heartbeat_check(tools_dict)
        if diagnostics_passed:
            diagnostic_message = "[System Diagnostic: All core tools passed the initial heartbeat check and are considered operational.]"
        else:
            diagnostic_message = "[System Diagnostic: WARNING - One or more core tools failed the initial heartbeat check. Functionality may be impaired. Advise the Primary Operator.]"
        
        # --- Inject diagnostic result into instructions ---
        base_instructions = self._read_all_instructions()
        self.current_instructions = f"{base_instructions}\n\n---\n\n{diagnostic_message}"

        if not self._load_state_on_restart():
            self.sessions: dict[str, chats.Chat] = {}
        
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
        """
        Dynamically loads only the tools explicitly defined in the `__all__`
        list within the 'functions' module. This is a robust and safe method
        for tool discovery.
        """
        if hasattr(functions, '__all__'):
            print(f"--- Loading {len(functions.__all__)} tools from functions.__all__ ---")
            return [getattr(functions, func_name) for func_name in functions.__all__]
        else:
            print("WARNING: 'functions.py' does not define __all__. No tools will be loaded.")
            return []

    def _get_session(self, session_id: str, history: list = []) -> chats.Chat:
        """Retrieves an existing chat session or creates a new one."""
        if session_id not in self.sessions:
            print(f"--- Creating new session for ID: {session_id} ---")
            self.sessions[session_id] = self.client.chats.create(
                model=f'{self.model_name}',
                config=types.GenerateContentConfig(
                    system_instruction=self.current_instructions,
                    tools=self.tools,
                    max_output_tokens=8192,  # Limit the response to 8192 tokens
                    safety_settings=[
                        types.SafetySetting(
                            category=types.HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT,
                            threshold=types.HarmBlockThreshold.BLOCK_ONLY_HIGH

                        )
                    ]
                ),
                history=history
            )
        return self.sessions[session_id]

    def trigger_instruction_refresh(self, full_restart: bool = False):
        """Performs a full hot-swap. It reloads instructions AND reloads the tools
        from functions.py, then rebuilds all active chat sessions."""
        if full_restart:
            print("---! FULL SYSTEM RESTART INITIATED !---")
            self.restart_pending = True
            return "[System Note]: Skipped Hot-Swap. Restart sequence initiated. The system will reboot after this response. Please do not perform any actions to avoid looping the restart."
        
        print("---! HOT-SWAP INSTRUCTIONS TRIGGERED !---")
        # --- NEW: Reload the tools first ---
        try:
            importlib.reload(functions) # Force Python to re-read functions.py
            self.tools = self._load_tools() # Re-run our tool discovery
            self.tools.append(self.trigger_instruction_refresh) # Adds the tools found in the same file
            print("  - Tools have been successfully reloaded.")
        except Exception as e:
            print(f"  - ERROR: Failed to reload tools from functions.py: {e}")
            # We can decide if we want to continue or abort the refresh here.
            # For now, we'll continue with the old tools.
        
        # --- Instruction refresh logic remains the same ---
        self.current_instructions = self._read_all_instructions()
        preserved_states = {
            session_id: chat._comprehensive_history for session_id, chat in self.sessions.items()
        }
        print(f"  - Preserved state for {len(preserved_states)} session(s).")
        
        self.sessions.clear()
        for session_id, history in preserved_states.items():
            self._get_session(session_id, history=history)
        print(f"--- HOT-SWAP COMPLETE: {len(self.sessions)} session(s) migrated. ---")
        

    def save_state_for_restart(self) -> bool:
        """Serializes the comprehensive history of all active sessions to the database."""
        print("--- Saving session states for system restart... ---")
        try:
            with sqlite3.connect(DB_FILE) as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM restart_state") # Clear any old state
                
                preserved_states = {
                    session_id: pickle.dumps(chat._comprehensive_history)
                    for session_id, chat in self.sessions.items()
                }
                
                cursor.executemany(
                    "INSERT INTO restart_state (session_id, history_blob) VALUES (?, ?)",
                    preserved_states.items()
                )
                conn.commit()
                print(f"  - State for {len(preserved_states)} session(s) saved to database.")
                return True
        except Exception as e:
            print(f"  - ERROR: Failed to save state for restart: {e}")
            return False

    def _load_state_on_restart(self) -> bool:
        """Deserializes session histories from the database and rebuilds sessions."""
        try:
            with sqlite3.connect(DB_FILE) as conn:
                cursor = conn.cursor()
                cursor.execute("SELECT session_id, history_blob FROM restart_state")
                rows = cursor.fetchall()
                if not rows:
                    return False # No state to load

                print("--- Restart state detected in database. Loading sessions... ---")
                self.sessions = {}
                for session_id, history_blob in rows:
                    history = pickle.loads(history_blob)
                    self._get_session(session_id, history=history)
                
                cursor.execute("DELETE FROM restart_state") # Clean up the state table
                conn.commit()
                print(f"  - Successfully loaded state for {len(self.sessions)} session(s).")
                return True
        except Exception as e:
            print(f"  - ERROR: Failed to load restart state: {e}. Starting with a clean slate.")
            # Attempt to clean up a potentially corrupted table
            try:
                with sqlite3.connect(DB_FILE) as conn:
                    conn.execute("DELETE FROM restart_state")
                    conn.commit()
            except Exception as cleanup_e:
                print(f"  - CRITICAL: Failed to even clean up restart_state table: {cleanup_e}")
            return False

    def process_prompt(self, session_id: str, user_prompt: str, file_check: list, user_id: str, user_name: str) -> tuple[str | None, int | None, bool]:
        """
        Processes a prompt using automatic function calling and archives the result.
        """
        print(f"--- Processing prompt for session {session_id} and user {user_name} ---")
        try:
            chat_session = self._get_session(session_id)
            
            # The SDK handles the entire tool-use loop automatically.
            # We send the message once and get the final text response.
            
            # Performing Identification Step for Orion
            timestamp_utc_iso = datetime.now(timezone.utc).isoformat()
            data_envelope = {
                "auth": {
                    "user_id": user_id,
                    "user_name": user_name,
                    "session_id": session_id,
                    "authentication_status": "PRIMARY_OPERATOR" if user_id == os.getenv("DISCORD_OWNER_ID") else "EXTERNAL_ENTITY"
                },
                "timestamp_utc": timestamp_utc_iso,
                "prompt": user_prompt
            }
            structured_prompt = types.Part.from_text(text=json.dumps(data_envelope))
            final_prompt = structured_prompt
            print("test run")
            attachments_for_db = []
            if file_check:
                # print("IT RUNS 2")
                for file in file_check:
                    # This adds the file object to the prompt for immediate use by the AI
                    final_prompt = [structured_prompt]
                    final_prompt.append(types.Part.from_uri(file_uri=file.uri, mime_type=file.mime_type))
                    
                    print(f"  - File '{file.display_name}' added to prompt for AI processing.")
                    # This creates a clean dictionary with the most essential, permanent
                    # data to be archived in your database.
                    file_metadata = {
                        "file_ref": file.name,           # CRITICAL: The permanent API reference
                        "file_name": file.display_name,  # The original, human-readable name
                        "mime_type": file.mime_type,     # The type of the file
                        "size_bytes": file.size_bytes    # The size of the file
                    }
                    print(f"  - Prepared metadata for DB: {file_metadata}")
                    attachments_for_db.append(file_metadata)
            
            print(f"  - Sending Prompt from Context: {data_envelope} to Orion. . .")
            response = chat_session.send_message(final_prompt)
            #print(response)
           
            final_text = response.text
            token_count = response.usage_metadata.total_token_count if response.usage_metadata else 0

            print(f"  - Final response generated. Total tokens for exchange: {token_count}")
            
            self._archive_exchange_to_db(session_id, user_id, user_name, user_prompt, final_text, attachments_for_db)
                  
            should_restart = self.restart_pending
            if self.restart_pending:
                self.restart_pending = False # Reset flag after it's been captured

            return final_text, token_count, should_restart
            
        except Exception as e:
            print(f"ERROR processing prompt for '{session_id}': {e}")
            return "I'm sorry, an internal error occurred while processing your request.", 0, False

    def _archive_exchange_to_db(self, session_id, user_id, user_name, prompt, response, attachment):
        """Writes the complete conversational exchange to the database."""
        try:
            with sqlite3.connect(DB_FILE) as conn:
                cursor = conn.cursor()
                # The full history from the session object can be serialized to JSON for a complete record.
                # NOTE: The genai history objects need a custom converter to be JSON serializable.
                # For now, we will store the prompt/response pair.
                ts_unix = int(datetime.now(timezone.utc).timestamp())
                sql = "INSERT INTO deep_memory (session_id, user_id, user_name, timestamp, prompt_text, response_text, attachments_metadata) VALUES (?, ?, ?, ?, ?, ?, ?)" # noqa
                params = (session_id, user_id, user_name, ts_unix, prompt, response, str(attachment))
                cursor.execute(sql, params)
                conn.commit()
                print(f" -> Exchange for user {user_id} archived.")
        except sqlite3.Error as e:
            print(f"ERROR: Database error during archival for user {user_id}: {e}")


# ... inside the OrionCore class ...
    def upload_file(self, file_bytes: bytes, display_name: str, mime_type: str):
        """
        Uploads a file-like object to the GenAI File API via the client.
        Returns a File handle object on success, or an error string on failure.
        """
        try:
            print(f"  - Uploading file '{display_name}' to the File API...")
            # Use the central client to access the 'files' service and upload
            # The 'file' parameter correctly takes a file-like object.
            file_handle = self.client.files.upload(
                file=io.BytesIO(file_bytes),
                config=types.UploadFileConfig(
                    mime_type=mime_type,
                    display_name=display_name
                )
            )
            print(f"  - Upload successful. URI: {file_handle.uri}")
            return file_handle
        except Exception as e:
            print(f"ERROR: File API upload failed for '{display_name}'. Error: {e}")
            return None

    def shutdown(self):
        """Performs a clean shutdown."""
        print("--- Orion Core shutting down. ---")
        print("--- Orion is now offline. ---")

    def execute_restart(self):
        """
        Executes the final step of the restart by replacing the current process.
        This should only be called after the state has been successfully saved.
        """
        print("  - State saved. Executing restart...")
        os.execv(sys.executable, ['python'] + sys.argv)