# orion_core.py (Final Unified Model)
import importlib
from typing import Generator
import os
import sqlite3
import pkgutil
from datetime import datetime, timezone
import sys
import time
from google import genai
from google.genai import types
import threading
import io
from dotenv import load_dotenv
import json
import pickle
from main_utils import config, main_functions as functions
from system_utils import orion_replay, run_startup_diagnostics, generate_manifests, orion_tts

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
    
    def __init__(self, model_name: str = "gemini-3-pro-preview", persona: str = "default"):
        """Initializes the unified AI 'brain', including session management."""
        self.MAX_HISTORY_EXCHANGES = 30 # Set the hard limit for conversation history
        self.restart_pending = False
        # --- MODIFICATION: Make the core instance accessible to tools ---
        config.ORION_CORE_INSTANCE = self

        # --- NEW: Context holder for the current turn ---
        self.current_turn_context = None

        self.persona = config.PERSONA = persona
        
        # Initialize or refresh database paths from functions module
        functions.initialize_persona(self.persona)

        self.vision_attachments = {} # NEW: To store incoming video file handles
        self.file_processing_agent = None # NEW: For delegating file tasks on Vertex

        # --- NEW: Start the persistent TTS thread ---
        voice_notification = None
        if config.VOICE:
            orion_tts.start_tts_thread()
            print("--- TTS Module is Activated. ---")
            voice_notification = "Voice Module: Your voice is activated. Structure your response to be spoken aloud. Use a conversational, direct-to-user tone. Avoid complex formatting like large tables, code blocks, or deeply nested lists that are difficult to read verbally. Instead, summarize complex data and present it in a clear, narrative style."

        # --- NEW: Start the persistent Vision thread ---
        if config.VISION:
            print("--- Vision Module is Activated. ---")
            orion_replay.launch_obs_hidden()
            if orion_replay.connect_to_obs():
                orion_replay.start_replay_watcher(orion_replay.REPLAY_SAVE_PATH, self._vision_file_handler)
                orion_replay.start_vision_thread()

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
        if config.VERTEX:
            self.client = genai.Client(vertexai=True, project=os.getenv("GEMINI_PROJECT_ID"), location="global")
        else:
            self.client = genai.Client(api_key=os.getenv("GOOGLE_API_KEY"))
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
        
        # --- Inject diagnostic result and voice notification into instructions ---
        base_instructions = self._read_all_instructions()
        self.current_instructions = f"{base_instructions}\n\n---\n\n{diagnostic_message}"
        if voice_notification:
            self.current_instructions += f"\n\n---\n\n{voice_notification}"

        # --- Initialize Context Caching ---
        from system_utils.gemini_cache_manager import GeminiCacheManager
        self.cache_manager = GeminiCacheManager(
            client=self.client,
            db_file=functions.config.DB_FILE,
            model_name=self.model_name,
            system_instructions=self.current_instructions,
            persona=self.persona
            # Tools NOT in cache - passed per-request based on mode
        )
        self.cached_content = self.cache_manager.get_or_create_cache()

        if not self._load_state_on_restart():
            self.sessions: dict[str, list] = {}
        
        # NEW: Track function calling mode per session
        self.session_modes: dict[str, str] = {}  # session_id -> "cache" | "function"
        self.default_mode = "cache"  # Default to cost-optimized mode
            
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

    def flatten_history(self, session_id: str) -> list:
        """
        Takes a session ID, retrieves the custom ExchangeDict history, and flattens
        it into the simple list[Content] format required by the GenAI API.
        """
        chat_session = self.sessions.get(session_id, [])
        contents_to_send = []
        for exchange in chat_session:
            if exchange.get("user_content"):
                contents_to_send.append(exchange["user_content"])
            if exchange.get("tool_calls"):
                contents_to_send.extend(exchange["tool_calls"])
            if exchange.get("model_content"):
                contents_to_send.append(exchange["model_content"])
        return contents_to_send

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

    def get_session_mode(self, session_id: str) -> str:
        """Get current mode for session. Returns 'cache' or 'function'."""
        return self.session_modes.get(session_id, self.default_mode)

    def set_session_mode(self, session_id: str, mode: str) -> str:
        """
        Set mode for session. 
        Args:
            mode: Either 'cache' or 'function'
        Returns:
            Confirmation message
        """
        if mode not in ["cache", "function"]:
            return f"Error: Invalid mode '{mode}'. Must be 'cache' or 'function'."
        
        self.session_modes[session_id] = mode
        mode_name = "Context Caching" if mode == "cache" else "Function Calling"
        print(f"[Mode Switch] Session '{session_id}' set to: {mode_name}")
        return f"Session mode set to: {mode_name}"

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
            for loader, modname, is_pkg in pkgutil.walk_packages(path=functions.__all__, prefix=functions.__name__ + '.'):
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
        
        # --- Invalidate and recreate cache with new instructions ---
        self.cache_manager.system_instructions = self.current_instructions
        self.cached_content = self.cache_manager.invalidate_and_recreate()
        
        print(f"--- HOT-SWAP COMPLETE: {len(self.sessions)} session(s) migrated. Cache recreated. ---")
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

    def _vision_file_handler(self, file_path: str):
        """Callback function for the replay_buffer's file watcher."""
        print(f"[Vision Handler] New replay file detected: {file_path}")
        try:
            display_name = os.path.basename(file_path)
            mime_type = "video/mp4"
            
            with open(file_path, 'rb') as f:
                video_bytes = f.read()

            self.vision_attachments = {"video_bytes": video_bytes, "display_name": display_name, "mime_type": mime_type}
            print(f"[Vision Handler] '{display_name}' uploaded and queued for next prompt.")
        except Exception as e:
            print(f"[Vision Handler] Error processing vision file: {e}")

    def _prepare_prompt_data(self, session_id: str, user_prompt: str, file_check: list, user_id: str, user_name: str):
        """
        Internal helper: Prepares all data, context, and file attachments for the AI prompt.
        Returns a tuple of collected data needed for generation and archival.
        """
        print(f"----- Processing prompt for session {session_id} and user {user_name} -----")
        chat_session = self._get_session(session_id)
        
        # Setting up User Content
        timestamp_utc_iso = datetime.now(timezone.utc).isoformat()
        
        # --- CONTEXT INJECTION CONTROL ---
        # Dynamically build excluded_ids from session
        excluded_ids = []
        for exchange in chat_session:
            if exchange.get("db_id"):
                excluded_ids.append(exchange["db_id"])
        
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

        # Extract only the source_ids from the VDB results to be archived.
        context_ids_for_db = []
        for raw_result in [deep_memory_results_raw, long_term_results_raw, operational_protocols_results_raw]:
            if raw_result:
                result_data = json.loads(raw_result)
                if result_data.get('ids') and result_data['ids'][0]:
                    context_ids_for_db.extend(result_data['ids'][0])

        vdb_response = f'[Relevant Semantic Information from Vector DB restricted to only the Memory Entries for user: {user_id}:\n{formatted_vdb_context}]' if formatted_vdb_context else ""
        
        # Format User Content
        data_envelope = {
            "auth": {
                "user_id": user_id,
                "user_name": user_name,
                "session_id": session_id,
                "authentication_status": "PRIMARY_OPERATOR" if user_id == os.getenv("DISCORD_OWNER_ID") else "EXTERNAL_ENTITY"
            },
            "timestamp_utc": timestamp_utc_iso,
            "system_notifications": [],
            "user_prompt": user_prompt,
        }
        
        # NEW: Inject mode notification
        current_mode = self.get_session_mode(session_id)
        if current_mode == "cache":
            mode_msg = (
                "[OPERATIONAL MODE: Context Caching] You are currently in cost-optimized mode. "
                "Function calling is DISABLED. If the user requests tool usage (file operations, "
                "database queries, system commands), inform them that function calling mode must "
                "be enabled first."
            )
        else:
            mode_msg = (
                "[OPERATIONAL MODE: Function Calling] All 45 tools are available. "
                "Automatic Function Calling is ENABLED. Context caching is disabled "
                "in this mode for compatibility."
            )
        
        data_envelope["system_notifications"].append(mode_msg)
        
        # --- Vision Module Notification ---
        if config.VISION and self.vision_attachments:
            print(f"  - Attaching {self.vision_attachments['display_name']} queued vision captures...")
            uploaded_file = self.upload_file(
                self.vision_attachments["video_bytes"], 
                self.vision_attachments["display_name"],
                self.vision_attachments["mime_type"]
            )
            if uploaded_file:
                file_check.append(uploaded_file)
                data_envelope["system_notifications"].append(f"[Vision Module: The following video file '{self.vision_attachments['display_name']}' is from an autonomous replay buffer system. They represent the last 30 seconds of screen activity prior to your activation. Analyze them for any relevant context or interesting events that may have occurred.]")
            else:
                data_envelope["system_notifications"].append(f"[Vision Module: A video file named '{self.vision_attachments['display_name']}' was detected by the replay buffer but failed to be processed by the File API. Inform the user that the video context for this prompt is missing.]")
            
            self.vision_attachments = {} # Clear the queue regardless of success
        
        # Convert File Attachments to Parts
        attachments_for_db = []
        if file_check: 
            for file in file_check:
                print(f"  - File '{file.display_name}' added to prompt for AI processing.")
                file_metadata = {
                    "file_ref": file.name,
                    "file_name": file.display_name,
                    "mime_type": file.mime_type,
                    "size_bytes": file.size_bytes
                }
                attachments_for_db.append(file_metadata)
            print(f"--- Processed a total of {len(file_check)} files ---")
        user_content_for_db = types.UserContent(parts=[types.Part.from_text(text=json.dumps(data_envelope, indent=2))])
        
        # Finalize User Content Structure
        data_envelope["vdb_context"] = vdb_response
        final_text_part = types.Part.from_text(text=json.dumps(data_envelope, indent=2))
        
        # The final user turn consists of file parts + consolidated text part
        
        # --- MODIFICATION: Agent Pre-Processing for VertexAI ---
        if config.VERTEX and file_check:
            print("--- [System] VertexAI detected with files. Engaging FileProcessingAgent for pre-analysis... ---")
            try:
                if self.file_processing_agent is None:
                    from agents.file_processing_agent import FileProcessingAgent
                    self.file_processing_agent = FileProcessingAgent(self)
                
                # The agent analyzes the files and returns a text description
                agent_analysis_text = self.file_processing_agent.run(file_check, context=data_envelope)
                
                # We inject this analysis into the prompt instead of the raw file handles
                analysis_context = f"\n\n[System: The user attached {len(file_check)} file(s). The File Processing Agent analyzed them and provided this context:]\n{agent_analysis_text}"
                
                # Update the final text part to include this analysis
                # We need to reconstruct the text part since we can't easily append to the object
                current_text = json.dumps(data_envelope, indent=2)
                combined_text = current_text + analysis_context
                final_text_part = types.Part.from_text(text=combined_text)
                
                # For Vertex, we DO NOT send the file handles, only the text analysis
                final_part = [final_text_part]
                print("--- [System] File analysis complete. Context injected. Raw files detached from Vertex prompt. ---")
                
            except Exception as e:
                print(f"ERROR: File Processing Agent failed: {e}")
                # Fallback? If we send files to Vertex it might crash, but let's try or just send text
                final_part = [final_text_part] # Send text only to be safe
                data_envelope["system_notifications"].append(f"[System Error: File analysis failed: {e}]")
        else:
            # Standard GenAI behavior: Attach files directly
            final_part = file_check + [final_text_part]

        final_content = types.UserContent(parts=final_part)
        
        # Prepare history
        contents_to_send = self.flatten_history(session_id)
        contents_to_send.append(final_content)

        return (contents_to_send, data_envelope, context_ids_for_db, attachments_for_db, user_content_for_db)

    def _finalize_exchange(self, session_id, user_id, user_name, user_prompt, response_text, token_count, attachments_for_db, new_tool_turns, context_ids_for_db, user_content_for_db, model_content_obj):
        """
        Internal helper: Handles post-processing, database archival, and history management.
        Returns boolean indicating if a restart is pending.
        """

        # 2. Archive to Database
        new_db_id = self._archive_exchange_to_db(
            session_id,
            user_id,
            user_name,
            user_prompt,
            response_text, 
            attachments_for_db,
            token_count,
            new_tool_turns,
            json.dumps(context_ids_for_db)
        )

        # 3. Update Session History
        new_exchange = {
            "user_content": user_content_for_db,
            "tool_calls": new_tool_turns,
            "model_content": model_content_obj,
            "db_id": new_db_id,
            "token_count": token_count
        }
        
        chat_session = self._get_session(session_id)
        chat_session.append(new_exchange)
        
        # 4. Enforce History Limit
        total_exchanges = len(chat_session)
        if total_exchanges > self.MAX_HISTORY_EXCHANGES:
            count_to_remove = 5
            print(f"  - History limit reached. Truncating {count_to_remove} oldest exchange(s)...")
            self.manage_session_history(session_id, count=count_to_remove, index=0)

        print(f"----- Response Generated ({token_count} tokens) -----")
        
        should_restart = self.restart_pending
        if self.restart_pending:
            self.restart_pending = False 

        return should_restart

    def _get_generation_config(self, session_id: str, stream: bool = False):
        """
        Returns appropriate GenerateContentConfig based on session mode.
        Cache mode: Uses cached content, NO tools
        Function mode: Uses system instructions + tools, NO cache
        """
        mode = self.get_session_mode(session_id)
        
        # Shared config parameters
        thinking_level = types.ThinkingLevel.LOW if stream else types.ThinkingLevel.HIGH
        safety_settings = [
            types.SafetySetting(
                category=types.HarmCategory.HARM_CATEGORY_SEXUALLY_EXPLICIT,
                threshold=types.HarmBlockThreshold.BLOCK_ONLY_HIGH
            )
        ]
        
        if mode == "cache":
            # CACHE MODE: Use cached content, NO tools
            print(f"[Gen Config] Using CACHE mode (tools disabled)")
            return types.GenerateContentConfig(
                cached_content=self.cached_content.name,
                thinking_config=types.ThinkingConfig(thinking_level=thinking_level),
                safety_settings=safety_settings
            )
        else:
            # FUNCTION MODE: Use tools, NO cache
            print(f"[Gen Config] Using FUNCTION mode (tools enabled, no cache)")
            return types.GenerateContentConfig(
                system_instruction=self.current_instructions,
                tools=self.tools,
                thinking_config=types.ThinkingConfig(thinking_level=thinking_level),
                safety_settings=safety_settings
            )

    def _generate_full_response(self, contents_to_send, data_envelope, session_id, user_id, user_name, user_prompt, attachments_for_db, context_ids_for_db, user_content_for_db):
        """
        Internal helper: Handles non-streaming generation.
        """
        self.current_turn_context = data_envelope
        print("----- Sending Prompt to Orion (Non-Streaming) . . . -----")
        
        try:
            response = self.client.models.generate_content(
                model=f'{self.model_name}',
                contents=contents_to_send,
                config=self._get_generation_config(session_id, stream=False)
            )
            
            self.current_turn_context = None # Clear context

            # Handle Tool Calls
            new_tool_turns = []
            if response.automatic_function_calling_history:
                all_tool_turns_from_api = [
                    content for content in response.automatic_function_calling_history
                    if any(part.function_call or part.function_response for part in content.parts)
                ]
                # Filter out tools from previous turns (simplified logic)
                chat_session = self._get_session(session_id)
                previous_tool_turn_count = 0
                for exchange in chat_session:
                    if exchange.get("tool_calls"):
                        previous_tool_turn_count += len(exchange["tool_calls"])
                new_tool_turns = all_tool_turns_from_api[previous_tool_turn_count:]

            # Extract Text and Tokens
            response_content = response.candidates[0].content
            token_count = response.usage_metadata.total_token_count if response.usage_metadata else 0
            print(response.usage_metadata.cached_content_token_count if response.usage_metadata else 0)
            final_text = ""
            if response_content:
                for part in response_content.parts:
                    if part.text:
                        final_text += part.text
            
            # TTS Side Effect
            if config.VOICE and final_text:
                orion_tts.speak(final_text)

            # Update cache TTL (rolling heartbeat)
            self.cache_manager.update_cache_ttl(self.cached_content.name)

            # Finalize
            should_restart = self._finalize_exchange(
                session_id, user_id, user_name, user_prompt, final_text, token_count,
                attachments_for_db, new_tool_turns, context_ids_for_db, user_content_for_db, response_content
            )
            
            return final_text, token_count, should_restart

        except Exception as e:
            print(f"ERROR in _generate_full_response: {e}")
            return f"[System Error: {e}]", 0, False

    def _generate_stream_response(self, contents_to_send, data_envelope, session_id, user_id, user_name, user_prompt, attachments_for_db, context_ids_for_db, user_content_for_db):
        """
        Internal helper: Handles streaming generation.
        Yields chunks of text, then yields a final metadata dict.
        """
        self.current_turn_context = data_envelope
        print("----- Sending Prompt to Orion (Streaming) . . . -----")
        
        full_response_text = ""
        token_count = 0

        #if config.VERTEX:
        #    model_name = self.model_name
        #else:
        #    model_name = "gemini-2.5-pro"

        try:
            response_stream = self.client.models.generate_content_stream(
                model=self.model_name,
                contents=contents_to_send,
                config=self._get_generation_config(session_id, stream=True)
            )

            last_chunk = None
            for chunk in response_stream:
                # Print what we receive
                last_chunk = chunk
                #print(chunk)
                if chunk.candidates:
                    for part in chunk.candidates[0].content.parts:
                        #if part.function_call:
                            #print(f"CHUNK: Function Call -> {part.function_call.name}")
                        if part.text:
                            #print(f"CHUNK: Text -> {part.text.strip()}")
                            if config.VOICE:
                                orion_tts.process_stream_chunk(part.text)
                            
                            # Yield token chunk
                            yield {"type": "token", "content": part.text}
                            full_response_text += part.text
                else:
                    print(f"CHUNK: No candidates (Usage/Other) -> {chunk}")
                
                if chunk.usage_metadata:
                    token_count = chunk.usage_metadata.total_token_count
                    
            print(last_chunk.usage_metadata.cached_content_token_count)
            if config.VOICE:
                orion_tts.flush_stream()
                
            self.current_turn_context = None

            # Update cache TTL (rolling heartbeat)
            self.cache_manager.update_cache_ttl(self.cached_content.name)

            # Reconstruct Model Content (Simplified for Stream)
            model_content_obj = types.Content(
                role="model",
                parts=[types.Part.from_text(text=full_response_text)]
            )

            # Handle Tool Calls
            new_tool_turns = []
            if last_chunk and last_chunk.automatic_function_calling_history:
                all_tool_turns_from_api = [
                    content for content in last_chunk.automatic_function_calling_history
                    if any(part.function_call or part.function_response for part in content.parts)
                ]
                # Filter out tools from previous turns (simplified logic)
                chat_session = self._get_session(session_id)
                previous_tool_turn_count = 0
                for exchange in chat_session:
                    if exchange.get("tool_calls"):
                        previous_tool_turn_count += len(exchange["tool_calls"])
                new_tool_turns = all_tool_turns_from_api[previous_tool_turn_count:]
            
            # Finalize
            should_restart = self._finalize_exchange(
                session_id, user_id, user_name, user_prompt, full_response_text, token_count,
                attachments_for_db, new_tool_turns, context_ids_for_db, user_content_for_db, model_content_obj
            )
            
            yield {
                "type": "usage",
                "token_count": token_count,
                "restart_pending": should_restart
            }

        except Exception as e:
            print(f"ERROR in _generate_stream_response: {e}")
            yield {"type": "token", "content": f"[System Error: {e}]"}

    def process_prompt(self, session_id: str, user_prompt: str, file_check: list, user_id: str, user_name: str, stream: bool = False) -> Generator:
        """
        Orchestrator: Processes a prompt by preparing data, delegating to the appropriate
        generation method (stream vs full), and ensuring proper archival.
        Now a generator function to provide immediate status feedback.
        """
        try:
            # Yield initial status
            yield {"type": "status", "content": "Initializing Request..."}

            # 1. Prepare Data (This includes VDB lookups and File Uploads)
            # We yield a status before this potentially blocking call
            yield {"type": "status", "content": "Accessing Memory & Processing Files..."}
            
            (contents_to_send, data_envelope, context_ids_for_db, attachments_for_db, user_content_for_db) = \
                self._prepare_prompt_data(session_id, user_prompt, file_check, user_id, user_name)
            
            # 2. Generate Response (Stream or Full)
            yield {"type": "status", "content": "Thinking..."}
            
            if stream:
                yield from self._generate_stream_response(
                    contents_to_send, data_envelope, session_id, user_id, user_name, user_prompt,
                    attachments_for_db, context_ids_for_db, user_content_for_db
                )
            else:
                final_text, token_count, restart = self._generate_full_response(
                    contents_to_send, data_envelope, session_id, user_id, user_name, user_prompt,
                    attachments_for_db, context_ids_for_db, user_content_for_db
                )
                yield {
                    "type": "full_response", 
                    "text": final_text, 
                    "token_count": token_count, 
                    "restart_pending": restart
                }

        except Exception as e:
            print(f"CRITICAL ERROR in process_prompt: {e}")
            yield {"type": "token", "content": f"I'm sorry, an internal error occurred: {e}"}

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
        # --- MODIFICATION: Delegate to Agent if on VertexAI ---
        if config.VERTEX:
            try:
                if self.file_processing_agent is None:
                    from agents.file_processing_agent import FileProcessingAgent
                    self.file_processing_agent = FileProcessingAgent(self)
                
                print(f"  - [System] VertexAI detected. Delegating upload of '{display_name}' to FileProcessingAgent...")
                return self.file_processing_agent.upload_file(file_bytes, display_name, mime_type)
            except Exception as e:
                print(f"ERROR: Failed to delegate upload to agent: {e}")
                return None
        
        # --- Original Logic for GenAI SDK ---
        try:
            print(f"  - Uploading file '{display_name}' to the File API...")
            # 1. Upload the file
            file_handle = self.client.files.upload(
                file=io.BytesIO(file_bytes),
                config=types.UploadFileConfig(
                    mime_type=mime_type,
                    display_name=display_name
                )
            )
            print(f"  - Upload successful. File Name: {file_handle.name}. Waiting for processing...")

            # 2. Poll for ACTIVE state
            while file_handle.state.name == "PROCESSING":
                time.sleep(1) # Wait for 1 seconds before checking again
                file_handle = self.client.files.get(name=file_handle.name)

            # 3. Check final state
            if file_handle.state.name == "FAILED":
                print(f"ERROR: File '{display_name}' failed processing by the API.")
                # Optionally, delete the failed file to clean up
                self.client.files.delete(name=file_handle.name)
                return None
            
            print(f"  - File '{display_name}' is now ACTIVE and ready. URI: {file_handle.uri}")
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
