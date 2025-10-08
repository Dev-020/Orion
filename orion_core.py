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

    def _get_session(self, session_id: str, history: list = []) -> list:
        """Retrieves an existing chat session or creates a new one."""
        if session_id not in self.sessions:
            print(f"--- Creating new session for ID: {session_id} ---")
            
            self.sessions[session_id] = history
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
        if self.discord_id:
            functions.manual_sync_instructions(self.discord_id)
        generate_manifests.main()
        self.current_instructions = self._read_all_instructions()
        print(f"--- HOT-SWAP COMPLETE: {len(self.sessions)} session(s) migrated. ---")
        return f'Refresh Complete. Tools and Instructions are all up to date.'

    def save_state_for_restart(self) -> bool:
        """Serializes the comprehensive history of all active sessions to the database."""
        print("--- Saving session states for system restart... ---")
        try:
            with sqlite3.connect(DB_FILE) as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM restart_state") # Clear any old state
                
                preserved_states = {
                    session_id: pickle.dumps(history)
                    for session_id, history in self.sessions.items()
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

    def _find_oldest_timestamp_in_session(self, chat_session: list) -> int | None:
        """Finds the Unix timestamp of the first user message in the session history."""
        for content in chat_session:
            if content.role == 'user':
                try:
                    # The first part of a user content is always the data envelope
                    data_envelope = json.loads(content.parts[0].text)
                    timestamp_iso = data_envelope.get("timestamp_utc")
                    if timestamp_iso:
                        return int(datetime.fromisoformat(timestamp_iso).timestamp())
                except (json.JSONDecodeError, IndexError, KeyError, TypeError):
                    # Ignore malformed or non-standard content parts
                    continue
        return None

    def process_prompt(self, session_id: str, user_prompt: str, file_check: list, user_id: str, user_name: str) -> tuple[str | None, int | None, bool]:
        """
        Processes a prompt using automatic function calling and archives the result.
        """
        print(f"--- Processing prompt for session {session_id} and user {user_name} ---")
        try:
            chat_session = self._get_session(session_id)
            
            # Setting up User Content
            timestamp_utc_iso = datetime.now(timezone.utc).isoformat()
            
            # --- CONTEXT INJECTION CONTROL (V2 - Time Aware) ---
            vdb_result = ""
            vdb_content = None
            if user_id == os.getenv("DISCORD_OWNER_ID"):
                # Find the timestamp of the oldest message in the current chat session
                # to prevent fetching context that's already in the active history.
                oldest_timestamp = self._find_oldest_timestamp_in_session(chat_session)
                
                # 1. Query Deep Memory (Conversational History)
                deep_memory_where = {"source_table": "deep_memory"}
                if oldest_timestamp:
                    # Add a time filter to exclude messages already in the session
                    deep_memory_where["timestamp"] = {"$lt": oldest_timestamp}

                deep_memory_results = functions.execute_vdb_read(
                    query_texts=[user_prompt], 
                    n_results=5, 
                    where=deep_memory_where
                )

                # 2. Query Long-Term Memory (Curated Events) - No time filter needed
                long_term_where = {"source_table": "long_term_memory"}
                long_term_results = functions.execute_vdb_read(
                    query_texts=[user_prompt], 
                    n_results=2,  # Fewer results as these are high-signal entries
                    where=long_term_where
                )
                
                # Combine results for injection
                vdb_result = deep_memory_results + "\n" + long_term_results
                vdb_response = f'[Relevant Semantic Information from Vector DB restricted to only the Memory Entries for user: {user_id}:{vdb_result}]'
                vdb_content = types.UserContent(parts=types.Part.from_text(text=vdb_response))

            data_envelope = {
                "auth": {
                    "user_id": user_id,
                    "user_name": user_name,
                    "session_id": session_id,
                    "authentication_status": "PRIMARY_OPERATOR" if user_id == os.getenv("DISCORD_OWNER_ID") else "EXTERNAL_ENTITY"
                },
                "timestamp_utc": timestamp_utc_iso,
                "prompt": user_prompt,
            }
            
            # Convert vdb result and data_envelope to Parts
            structured_prompt = types.Part.from_text(text=json.dumps(data_envelope))
            
            # Convert File Attachments to Parts
            final_prompt = structured_prompt
            attachments_for_db = []
            if file_check:
                final_prompt = [structured_prompt]
                for file in file_check:
                    final_prompt.append(types.Part.from_uri(file_uri=file.uri, mime_type=file.mime_type))
                    print(f"  - File '{file.display_name}' added to prompt for AI processing.")
                    file_metadata = {
                        "file_ref": file.name,
                        "file_name": file.display_name,
                        "mime_type": file.mime_type,
                        "size_bytes": file.size_bytes
                    }
                    attachments_for_db.append(file_metadata)
            
            # Wrapping all User Parts into User Content
            final_content=types.UserContent(parts=final_prompt)

            # Sending User Content to Orion
            contents_to_send = chat_session + [final_content]
            if vdb_content:
                contents_to_send.append(vdb_content)

            print(f"  - Sending Prompt from Context: {data_envelope} to Orion. . .")
            response = self.client.models.generate_content(
                model=f'{self.model_name}',
                contents=contents_to_send,
                config=types.GenerateContentConfig(
                    system_instruction=self.current_instructions,
                    tools=self.tools,
                    safety_settings=[
                        types.SafetySetting(
                            category=types.HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT,
                            threshold=types.HarmBlockThreshold.BLOCK_ONLY_HIGH
                        )
                    ]
                )
            )
            
            # --- Append to Chat History ---
            chat_session.append(final_content)
            
            new_tool_turns = []
            if response.automatic_function_calling_history:
                all_tool_turns_from_api = [
                    content for content in response.automatic_function_calling_history
                    if any(part.function_call or part.function_response for part in content.parts)
                ]
                previous_tool_turns_in_session = [
                    content for content in chat_session 
                    if any(part.function_call or part.function_response for part in content.parts)
                ]
                new_tool_turns = all_tool_turns_from_api[len(previous_tool_turns_in_session):]
                chat_session.extend(new_tool_turns)

            response_content = response.candidates[0].content
            final_text = ""
            if not response_content:
                print(response)
                final_text = None
            else:
                for part in response_content.parts:
                    if part.text:
                        final_text += part.text
                chat_session.append(response_content)
            
            # --- Enforce History Limit ---
            user_message_indices = [
                i for i, content in enumerate(chat_session) 
                if content.role == 'user' and any(part.text for part in content.parts)
            ]
            if len(user_message_indices) > self.MAX_HISTORY_EXCHANGES:
                trim_until_index = user_message_indices[1]
                original_length = len(chat_session)
                self.sessions[session_id] = chat_session[trim_until_index:]
                items_removed = original_length - len(self.sessions[session_id])
                print(f"  - History limit reached. Truncated session '{session_id}', removing the oldest exchange ({items_removed} items).")

            token_count = response.usage_metadata.total_token_count if response.usage_metadata else 0
            print(f"  - Final response generated. Total tokens for exchange: {token_count}")
            self._archive_exchange_to_db(session_id, user_id, user_name, user_prompt, final_text, attachments_for_db, token_count, new_tool_turns, vdb_result)
            
            should_restart = self.restart_pending
            if self.restart_pending:
                self.restart_pending = False

            return final_text, token_count, should_restart
            
        except Exception as e:
            print(f"ERROR processing prompt for '{session_id}': {e}")
            return "I'm sorry, an internal error occurred while processing your request.", 0, False

    def _archive_exchange_to_db(self, session_id, user_id, user_name, prompt, response, attachment, token_count, function_call, vdb_context):
        """Writes the complete conversational exchange to the database."""
        try:
            function_calls_json_list = [content_obj.model_dump_json() for content_obj in function_call] if function_call else []
            function_calls_json_string = f"[{', '.join(function_calls_json_list)}]"

            data_payload = {
                "session_id": session_id,
                "user_id": user_id,
                "user_name": user_name,
                "timestamp": int(datetime.now(timezone.utc).timestamp()),
                "prompt_text": prompt,
                "response_text": response,
                "attachments_metadata": json.dumps(attachment),
                "token": token_count,
                "function_calls": function_calls_json_string,
                "vdb_context": vdb_context
            }
            
            result = functions.execute_write(table="deep_memory", operation="insert", user_id=user_id, data=data_payload)
            print(f" -> Archival result: {result}")

        except Exception as e:
            print(f"ERROR: An unexpected error occurred during archival for user {user_id}: {e}")

    def upload_file(self, file_bytes: bytes, display_name: str, mime_type: str):
        """Uploads a file-like object to the GenAI File API."""
        try:
            print(f"  - Uploading file '{display_name}' to the File API...")
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
        """Executes the final step of the restart by replacing the current process."""
        print("  - State saved. Executing restart...")
        os.execv(sys.executable, ['python'] + sys.argv)