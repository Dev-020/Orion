# orion_core.py (Final Unified Model)
import importlib
import os
import sqlite3
import pkgutil
from datetime import datetime, timezone
import sys
from google import genai
from google.genai import types
import threading
import io
from dotenv import load_dotenv
import json
import pickle
from main_utils import config, main_functions as functions
from system_utils import run_startup_diagnostics, generate_manifests, orion_tts

# --- TTS Integration ---
# Import the speak function from your chosen TTS script.
# Using tts_piper as it's a clean, self-contained implementation.

# This single class now manages everything: state, sessions, and core logic.

# Define instruction files for clarity
INSTRUCTIONS_FILES = [
    'Primary_Directive.md', 
    #'Homebrew_Compendium.md',
    #'General_Prompt_Optimizer.md',
    #'DND_Handout.md',
    'master_manifest.json'
]

# --- Persona Configuration ---
load_dotenv() # Load environment variables from .env file for other modules

# --- Paths ---
INSTRUCTIONS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'instructions')

class OrionCore:
    
    def __init__(self, model_name: str = "gemini-2.5-flash", persona: str = "default"):
        """Initializes the unified AI 'brain', including session management."""
        self.MAX_HISTORY_EXCHANGES = 30 # Set the hard limit for conversation history
        self.restart_pending = False
        self.persona = config.PERSONA = persona
        
        # Initialize or refresh database paths from functions module
        functions.initialize_persona(self.persona)

        # --- NEW: Start the persistent TTS thread ---
        if config.VOICE:
            orion_tts.start_tts_thread()

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
        Dynamically loads tools from the 'main_utils' package based on the active persona.
        It loads all tools from 'main_utils.main_functions' and persona-specific tools
        (e.g., 'main_utils.dnd_functions') if they exist.
        """
        loaded_tools = []
        # Always load main tools from main_functions
        try:
            if hasattr(functions, '__all__'):
                print(f"--- Loading {len(functions.__all__)} main tools from main_functions.py ---")
                for func_name in functions.__all__:
                    loaded_tools.append(getattr(functions, func_name))
        except Exception as e:
            print(f"WARNING: Could not import main functions: {e}")

        # Load persona-specific tools if the persona is not 'default'
        if self.persona != "default":
            persona_module_name = f"main_utils.{self.persona}_functions"
            try:
                persona_module = importlib.import_module(persona_module_name)
                if hasattr(persona_module, '__all__'):
                    print(f"--- Loading {len(persona_module.__all__)} tools from {persona_module_name} ---")
                    for func_name in persona_module.__all__:
                        loaded_tools.append(getattr(persona_module, func_name))
            except ImportError:
                print(f"--- No specific tools module found for persona '{self.persona}'. Loading main tools only. ---")
        
        return loaded_tools

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
            # Reload all modules within the 'main_utils' package
            for loader, modname, is_pkg in pkgutil.walk_packages(path=functions.__path__, prefix=functions.__name__ + '.'):
                if modname in sys.modules:
                    importlib.reload(sys.modules[modname])

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
            with sqlite3.connect(functions.config.DB_FILE) as conn:
                cursor = conn.cursor()
                cursor.execute("DELETE FROM restart_state") # Clear any old state
                
                records_to_save = []
                for session_id, history in self.sessions.items():
                    history_blob = pickle.dumps(history)
                    #excluded_ids_list = self.session_excluded_ids.get(session_id, [])
                    #excluded_ids_blob = pickle.dumps(excluded_ids_list)
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

    def _load_state_on_restart(self) -> bool:
        """Deserializes session histories from the database and rebuilds sessions."""
        try:
            with sqlite3.connect(functions.config.DB_FILE) as conn:
                cursor = conn.cursor()
                # Note the simpler SQL query
                cursor.execute("SELECT session_id, history_blob FROM restart_state")
                rows = cursor.fetchall()
                if not rows:
                    return False # No state to load

                print("--- Restart state detected in database. Loading sessions... ---")
                self.sessions = {}
                # self.session_excluded_ids is gone
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
                with sqlite3.connect(functions.config.DB_FILE) as conn:
                    conn.execute("DELETE FROM restart_state")
                    conn.commit()
            except Exception as cleanup_e:
                print(f"  - CRITICAL: Failed to even clean up restart_state table: {cleanup_e}")
            return False

    def process_prompt(self, session_id: str, user_prompt: str, file_check: list, user_id: str, user_name: str) -> tuple[str | None, int | None, bool]:
        """
        Processes a prompt using automatic function calling and archives the result.
        """
        print(f"----- Processing prompt for session {session_id} and user {user_name} -----")
        try:
            chat_session = self._get_session(session_id)
            
            # The SDK handles the entire tool-use loop automatically.
            # We send the message once and get the final text response.
            
            # Setting up User Content
            timestamp_utc_iso = datetime.now(timezone.utc).isoformat()
            
            # --- CONTEXT INJECTION CONTROL ---
            # Automatic Past-Memory Recall to provide additional context on-demand based on the User Prompt.
            # These recalls will not be saved to the chat history.
            vdb_content = None
            
            # --- MODIFICATION: Dynamically build excluded_ids from session ---
            excluded_ids = []
            for exchange in chat_session:
                if exchange.get("db_id"):
                    excluded_ids.append(exchange["db_id"])
            # --- END OF MODIFICATION ---
            
            # Query 1: Deep Memory (with token limit)
            deep_memory_where = {"source_table": "deep_memory"}
            if excluded_ids:
                deep_memory_where = {"$and": [
                    {"source_table": "deep_memory"},
                    {"source_id": {"$nin": excluded_ids}},
                    {"session_id": session_id}
                ]}

            deep_memory_results_raw = functions.execute_vdb_read(
                query_texts=[user_prompt], 
                n_results=5, 
                where=deep_memory_where
            )

            # Query 2: Long-Term Memory
            long_term_results_raw = functions.execute_vdb_read(
                query_texts=[user_prompt], 
                n_results=3, 
                where={"source_table": "long_term_memory"}
            )
            
            # Query 3: Operational Protocols
            operational_protocols_results_raw = functions.execute_vdb_read(
                query_texts=[user_prompt], 
                n_results=3, 
                where={"source": "Operational_Protocols.md"}
            )
            
            # Combine and format results
            formatted_deep_mem = self._format_vdb_results_for_context(deep_memory_results_raw, "Deep Memory")
            formatted_long_term = self._format_vdb_results_for_context(long_term_results_raw, "Long-Term Memory")
            formatted_op_protocol = self._format_vdb_results_for_context(operational_protocols_results_raw, "Operational Protocols")
            
            # The formatted string for the AI's context
            formatted_vdb_context = f"{formatted_deep_mem}\n{formatted_long_term}\n{formatted_op_protocol}".strip()

            # --- REFACTORED: Store by Reference (ID) instead of by Value ---
            # Extract only the source_ids from the VDB results to be archived.
            # This prevents the recursive data explosion.
            context_ids_for_db = []
            for raw_result in [deep_memory_results_raw, long_term_results_raw, operational_protocols_results_raw]:
                if raw_result:
                    result_data = json.loads(raw_result)
                    if result_data.get('ids') and result_data['ids'][0]:
                        context_ids_for_db.extend(result_data['ids'][0])

            vdb_response = f'[Relevant Semantic Information from Vector DB restricted to only the Memory Entries for user: {user_id}:\n{formatted_vdb_context}]' if formatted_vdb_context else ""
            vdb_content = types.UserContent(parts=types.Part.from_text(text=vdb_response)) if vdb_response else None
            #print(vdb_response)
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
            
            # Wrapping all User Parts into User Content
            final_content=types.UserContent(parts=final_prompt)

            # Sending User Content to Orion
            # --- MODIFICATION: "Unroll" new ExchangeDict structure into flat list ---
            contents_to_send = []
            for exchange in chat_session:
                contents_to_send.append(exchange["user_content"])
                if exchange.get("tool_calls"):
                    contents_to_send.extend(exchange["tool_calls"])
                if exchange.get("model_content"):
                    contents_to_send.append(exchange["model_content"])
            # --- END OF MODIFICATION ---
            
            if vdb_content:
                contents_to_send.append(vdb_content)
            contents_to_send.append(final_content)

            print(f"----- All necessary content prepared. Sending Prompt to Orion. . . -----")
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
            # 1. Isolate only the new tool calls and responses from this turn
            new_tool_turns = []
            if response.automatic_function_calling_history:
                # First, filter the API's history to *only* include tool-related turns.
                all_tool_turns_from_api = [
                    content for content in response.automatic_function_calling_history
                    if any(part.function_call or part.function_response for part in content.parts)
                ]

                # Second, find the tool-related turns already in our session history.
                previous_tool_turn_count = 0
                for exchange in chat_session: # chat_session is our list[ExchangeDict]
                    if exchange.get("tool_calls"):
                        previous_tool_turn_count += len(exchange["tool_calls"])
                
                # The new tool turns are the ones at the end of the filtered API history.
                new_tool_turns = all_tool_turns_from_api[previous_tool_turn_count:]

            # 2. Get the model's final text response and token count
            response_content = response.candidates[0].content
            token_count = response.usage_metadata.total_token_count if response.usage_metadata else 0
            final_text = ""
            if not response_content:
                print(response)
                final_text = None
                #print(final_content)
                #print(vdb_result)
            else:
                for part in response_content.parts:
                    if part.text:
                        final_text += part.text
            
            # 3. Archive the exchange and get its new DB ID
            # (We will modify _archive_exchange_to_db to return the ID)
            new_db_id = self._archive_exchange_to_db(
                session_id,
                user_id,
                user_name,
                user_prompt,
                final_text, 
                attachments_for_db,
                token_count,
                new_tool_turns,
                json.dumps(context_ids_for_db)
            )

            # 4. Create the new ExchangeDict
            new_exchange = {
                "user_content": final_content,
                "tool_calls": new_tool_turns,
                "model_content": response_content,
                "db_id": new_db_id, # Store the new ID
                "token_count": token_count # <-- ADD THIS LINE
            }
            
            # 5. Append the single new exchange to our session
            chat_session.append(new_exchange)
            
            # --- Enforce History Limit ---
            # --- MODIFICATION: Updated to use new unified function ---
            total_exchanges = len(chat_session)
            if total_exchanges > self.MAX_HISTORY_EXCHANGES:
                count_to_remove = 5 # Number of oldest exchanges to remove
                print(f"  - History limit reached. Truncating {count_to_remove} oldest exchange(s)...")
                # Calls the new function with index=0
                self.manage_session_history(session_id, count=count_to_remove, index=0)
            # --- END OF MODIFICATION ---

            print(f"----- Chat History Length: {len(excluded_ids)} -----")
            print(f"----- Current Excluded IDs for session {excluded_ids}. -----")
            print(f"  - Final response generated. Total tokens for exchange: {token_count}")
            #self._archive_exchange_to_db(session_id, user_id, user_name, user_prompt, final_text, attachments_for_db, token_count, new_tool_turns, json.dumps(context_ids_for_db))
            #print(chat_session)
            
            should_restart = self.restart_pending
            if self.restart_pending:
                self.restart_pending = False # Reset flag after it's been captured

            # --- TTS INVOCATION POINT ---
            # If voice is enabled in the config and there's text, speak it.
            # --- MODIFICATION: Add text to the TTS queue ---
            if config.VOICE and final_text:
                orion_tts.speak(final_text)

            return final_text, token_count, should_restart
            
        except Exception as e:
            print(f"ERROR processing prompt for '{session_id}': {e}")
            return "I'm sorry, an internal error occurred while processing your request.", 0, False

    def _format_vdb_results_for_context(self, raw_json: str, source_name: str) -> str:
        """
        Parses the raw JSON output from a VDB query and formats it into a clean,
        human-readable string for the AI's context, including only essential metadata.
        """
        try:
            data = json.loads(raw_json)
            if not data.get('documents') or not data['documents'][0]:
                return "" # No results to format

            output_lines = [f"--- Context from {source_name} ---"]
            
            # Define which metadata keys are useful for the AI's context.
            # Explicitly exclude bulky or irrelevant fields like 'vdb_context'.
            essential_keys = []
            if source_name == "Deep Memory":
                essential_keys = ['source_table', 'source_id', 'user_name', 'timestamp', 'session_id']
            elif source_name == "Long-Term Memory":
                essential_keys = ['source_table', 'source_id', 'category', 'date']
            elif source_name == "Operational Protocols":
                essential_keys = ['source']
            
            for i, doc in enumerate(data['documents'][0]):
                meta = data['metadatas'][0][i]
                distance = data['distances'][0][i]

                # Filter and format the essential metadata
                meta_summary = ", ".join(f"{key}: {meta[key]}" for key in essential_keys if key in meta and meta[key])

                output_lines.append(f"Entry {i+1} (Relevance: {1-distance:.2f}):")
                if meta_summary:
                    output_lines.append(f"  - Metadata: {meta_summary}")
                output_lines.append(f"  - Content: \"{doc}\"")

            return "\n".join(output_lines)

        except (json.JSONDecodeError, IndexError, KeyError, TypeError):
            # If parsing fails, return an empty string to avoid polluting the context.
            return ""

    def _archive_exchange_to_db(self, session_id, user_id, user_name, prompt, response, attachment, token_count, function_call, vdb_context):
        """
        Processes a prompt using automatic function calling and archives the result.
        """
        """Writes the complete conversational exchange to the database."""
        try:
            # --- Prepare data for archival using the high-level execute_write tool ---
            # This tool handles synchronized writes to both SQLite and the Vector DB.
            
            # 1. Prepare the function calls as a JSON string for the database.
            function_calls_json_list = [content_obj.model_dump_json() for content_obj in function_call] if function_call else []
            function_calls_json_string = f"[{', '.join(function_calls_json_list)}]"

            # 2. Construct the data payload for the 'deep_memory' table.
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
            
            print(f"  - [DEBUG] Archiving exchange to deep_memory. Context used: {vdb_context}")

            # 3. Call the high-level orchestrator to perform the synchronized write.
            result = functions.execute_write(table="deep_memory", operation="insert", user_id=user_id, data=data_payload)
            print(f" -> Archival result: {result}")
            
            if "Success" in result:
                latest_id_result = functions.execute_sql_read(query="SELECT id FROM deep_memory ORDER BY id DESC LIMIT 1")
                latest_id_data = json.loads(latest_id_result)
                if latest_id_data:
                    newest_id = str(latest_id_data[0]['id'])
                    print(f"  - Returning new DB ID for session '{session_id}': {newest_id}")
                    return newest_id # <-- MODIFICATION
            
            return None # <-- MODIFICATION

        except Exception as e:
            print(f"ERROR: An unexpected error occurred during archival for user {user_id}: {e}")
            return None # <-- MODIFICATION

    # --- MODIFICATION: Replaced with new unified function as per user spec ---
    def manage_session_history(self, session_id: str, count: int, index: int = 0):
        """
        Manages the active chat session history using count and index.
        - Deletes 'count' items starting from 'index'.
        - If 'index' is 0, it deletes the 'count' oldest.
        - If 'count' is >= (total - index), it truncates from 'index' to the end.
        
        Args:
            session_id: The ID of the session to manage.
            count: The number of exchanges to remove.
            index: The starting index to remove from. Defaults to 0.
        """
        if session_id not in self.sessions:
            print(f"--- manage_session_history: No session found for ID {session_id} ---")
            return "Error: No session found."
        
        if count <= 0:
            return "No action taken: Count must be > 0."
        if index < 0:
            return "No action taken: Index must be >= 0."

        chat_session = self.sessions[session_id]
        total_exchanges = len(chat_session)
        
        if index >= total_exchanges:
            return f"No action taken: Index {index} is out of bounds."

        # Your logic: If count is "too large", clamp it to "delete until end"
        if (index + count) > total_exchanges:
            count = total_exchanges - index # This clamps it
            print(f"--- manage_session_history: Count clamped to {count} (delete until end).")

        print(f"--- manage_session_history: Deleting {count} exchange(s) starting from index {index}. ---")
        
        # This single line handles all cases:
        self.sessions[session_id] = chat_session[:index] + chat_session[index+count:]
        
        return f"Success: {count} exchange(s) removed."
    
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

    def list_sessions(self) -> list[str]:
        """
        Returns a list of all active session IDs currently
        being managed by the core.
        """
        return list(self.sessions.keys())
    
    def shutdown(self):
        """Performs a clean shutdown."""
        print("--- Orion Core shutting down. ---")
        # --- NEW: Stop the TTS thread on shutdown ---
        if config.VOICE:
            orion_tts.stop_tts_thread()
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
