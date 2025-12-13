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
from main_utils.chat_object import ChatObject
from main_utils.file_manager import UploadFile
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
    
    def __init__(self, model_name: str = config.AI_MODEL, persona: str = "default"):
        """Initializes the unified AI 'brain', including session management."""
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
            self.client = genai.Client(vertexai=True, project=os.getenv("GOOGLE_CLOUD_PROJECT_ID"), location="global")
        else:
            self.client = genai.Client(api_key=os.getenv("GOOGLE_API_KEY"))
        
        # --- File Manager Initialization ---
        self.file_manager = UploadFile(
            core_backend="api", # Pro Core is always API based (Vertex or Standard)
            client=self.client,
            file_processing_agent=None # Will be lazy loaded if Vertex
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
        
        # --- Inject diagnostic result and voice notification into instructions ---
        base_instructions = self._read_all_instructions()
        self.current_instructions = f"{base_instructions}\n\n---\n\n{diagnostic_message}"
        if voice_notification:
            self.current_instructions += f"\n\n---\n\n{voice_notification}"

        # --- Initialize Context Caching ---
        self.cache_manager = None
        self.cached_content = None
        
        if config.CONTEXT_CACHING:
            from system_utils.gemini_cache_manager import GeminiCacheManager
            self.cache_manager = GeminiCacheManager(
                client=self.client,
                db_file=functions.config.DB_FILE,
                model_name=self.model_name,
                system_instructions=self.current_instructions,
                persona=self.persona
                # Tools NOT in cache - passed per-request based on mode
            )
            try:
                self.cached_content = self.cache_manager.get_or_create_cache()
            except Exception as e:
                print(f"WARNING: Cache initialization failed: {e}. Proceeding without cache.")
                self.cached_content = None
        else:
            print("--- Context Caching DISABLED by config ---")

        # --- ChatObject Integration ---
        self.chat = ChatObject()
        self.sessions = self.chat.sessions # Alias for compatibility
        
        if not self.chat.load_state_on_restart():
             pass 
            
        print(f"--- Orion Core is online and ready. Managing {len(self.chat.sessions)} session(s). ---")
        
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
        chat_session = self.chat.get_session(session_id)
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
        return self.chat.get_session(session_id, history)

    def trigger_instruction_refresh(self, full_restart: bool = False):
        """Performs a full hot-swap. It reloads instructions AND reloads the tools
        from functions.py, then rebuilds all active chat sessions."""
        print("---! HOT-SWAP INSTRUCTIONS TRIGGERED !---")
        
        if full_restart:
            print("WARNING: 'full_restart' flag ignored in Client-Server mode. Use TUI to restart Server.")
            return "[System Note]: Full restart ignored in Client-Server mode. Use TUI to restart Server."

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
        
        # --- Invalidate and recreate cache with new instructions ---
        if self.cache_manager:
            self.cache_manager.system_instructions = self.current_instructions
            self.cached_content = self.cache_manager.invalidate_and_recreate()
        
        print(f"--- HOT-SWAP COMPLETE: {len(self.sessions)} session(s) migrated. Cache recreated. ---")
        return f'Refresh Complete. Tools and Instructions are all up to date.'

    def save_state_for_restart(self) -> bool:
        return self.chat.save_state_for_restart()

    def _load_state_on_restart(self) -> bool:
        return self.chat.load_state_on_restart()
    
    def execute_restart(self):
         """Executes a hard restart of the script."""
         # Re-uses logic compatible with main_utils
         python = sys.executable
         os.execl(python, python, *sys.argv)
    
    def get_session_mode(self, session_id: str) -> str:
        return self.chat.get_session_mode(session_id)

    def set_session_mode(self, session_id: str, mode: str) -> str:
        return self.chat.set_session_mode(session_id, mode)
    
    def list_sessions(self) -> list:
        return self.chat.list_sessions()
    
    def manage_session_history(self, session_id: str, count: int = 0, index: int = -1) -> str:
        return self.chat.manage_session_history(session_id, count, index)

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
        formatted_vdb_context = f"{formatted_deep_mem}\\n{formatted_long_term}\\n{formatted_op_protocol}".strip()

        # Extract only the source_ids from the VDB results to be archived.
        context_ids_for_db = []
        for raw_result in [deep_memory_results_raw, long_term_results_raw, operational_protocols_results_raw]:
            if raw_result:
                result_data = json.loads(raw_result)
                if result_data.get('ids') and result_data['ids'][0]:
                    context_ids_for_db.extend(result_data['ids'][0])

        vdb_response = f'[Relevant Semantic Information from Vector DB restricted to only the Memory Entries for user: {user_id}:\\n{formatted_vdb_context}]' if formatted_vdb_context else ""
        
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
                "[OPERATIONAL MODE: Function Calling] All tools are available. "
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
                
                # Normalize 'name' vs 'uri' access
                file_uri = getattr(file, 'name', getattr(file, 'uri', 'unknown_uri'))
                
                file_metadata = {
                    "file_ref": file_uri,
                    "file_name": file.display_name,
                    "mime_type": file.mime_type,
                    "size_bytes": getattr(file, 'size_bytes', 0)
                }
                attachments_for_db.append(file_metadata)
            print(f"--- Processed a total of {len(file_check)} files ---")
        user_content_for_db = types.UserContent(parts=[types.Part.from_text(text=json.dumps(data_envelope, indent=2))])
        
        # Finalize User Content Structure
        # Finalize User Content Structure
        data_envelope["vdb_context"] = vdb_response
        final_text_part_text = json.dumps(data_envelope, indent=2)
        
        # --- MODIFICATION: Handle Injected Text Content ---
        # Some files (code, logs OR Vertex Analysis) are now returned as objects with 'text_content'
        injected_text_buffers = []
        api_part_files = []
        file_injections = []
        
        for f in file_check:
            if hasattr(f, 'text_content'):
                # It's an injected text file or Analysis
                # We inject it into the prompt text
                header = f"\n\n--- FILE: {f.display_name} ({f.mime_type}) ---\n"
                
                # If it's an analysis, maybe add a specific header?
                if getattr(f, 'is_analysis', False):
                    header = f"\n\n--- FILE ANALYSIS: {f.display_name} ({f.mime_type}) ---\n[System: The following is an AI analysis of the file.]\n"
                
                content_block = f"{header}{f.text_content}"
                injected_text_buffers.append(content_block)
                
                # Add to formal data envelope list for frontend/logging
                file_injections.append({
                    "name": f.display_name,
                    "mime": f.mime_type,
                    "content_preview": f.text_content[:200] + "..." if len(f.text_content) > 200 else f.text_content
                })
            else:
                # It's a real API file object (Video/PDF/Image)
                api_part_files.append(f)

        # Update Envelope with specific injections list
        if file_injections:
            data_envelope["file_injections"] = file_injections
            # Re-dump the envelope to include the new field
            final_text_part_text = json.dumps(data_envelope, indent=2)

        # Append injected text to the main prompt text
        if injected_text_buffers:
             final_text_part_text += "".join(injected_text_buffers)

        final_text_part = types.Part.from_text(text=final_text_part_text)
        
        # Standard GenAI behavior: Attach API files directly + Text Part
        # (Vertex Analysis objects were filtered into injected_text_buffers, so they won't be in api_part_files)
        final_part = api_part_files + [final_text_part]

        final_content = types.UserContent(parts=final_part)
        
        # Prepare history
        contents_to_send = self.flatten_history(session_id)
        contents_to_send.append(final_content)

        return (contents_to_send, data_envelope, context_ids_for_db, attachments_for_db, user_content_for_db)

    def _get_generation_config(self, session_id: str, stream: bool = True):
        """
        Dynamically returns the generation config based on the session mode.
        If mode is 'cache', we do NOT provide tools.
        If mode is 'function', we provide tools.
        """
        mode = self.get_session_mode(session_id)
        
        # Config for Context Caching Mode (No Tools)
        if mode == "cache":
            # Just send standard config
            if config.VERTEX:
                 return types.GenerateContentConfig(
                    max_output_tokens=8192,
                    temperature=0.9,
                    response_modalities=["TEXT"], 
                    system_instruction=self.cached_content # <--- Pass valid CachedContent object
                 )
            else:
                 return types.GenerateContentConfig(
                    max_output_tokens=8192,
                    temperature=0.9,
                    system_instruction=self.cached_content 
                 )
                 
        # Config for Function Calling Mode (Tools)
        else:
             # We can't reuse the CacheContent object if we want standard tools?
             # Actually, Gemini API says tools and cache are mutually exclusive sometimes
             # or imply distinct billing.
             # But here we simply WON'T pass the cached_content object to system_instruction
             # implying standard context window usage.
             if config.VERTEX:
                 return types.GenerateContentConfig(
                    tools=self.tools,
                    automatic_function_calling={'disable': False, 'maximum_remote_calls': 10},
                    max_output_tokens=8192,
                    temperature=0.9,
                    response_modalities=["TEXT"],
                    system_instruction=self.current_instructions
                 )
             else:
                 return types.GenerateContentConfig(
                    tools=self.tools,
                    automatic_function_calling={'disable': False, 'maximum_remote_calls': 10},
                    max_output_tokens=8192,
                    temperature=0.9,
                    system_instruction=self.current_instructions
                 )

    def _generate_full_response(self, contents_to_send, data_envelope, session_id, user_id, user_name, user_prompt, attachments_for_db, context_ids_for_db, user_content_for_db):
        """
        Internal helper: Handles non-streaming generation (for quick tool calls).
        """
        self.current_turn_context = data_envelope
        print("----- Sending Prompt to Orion (Full Response) . . . -----")
        
        try:
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=contents_to_send,
                config=self._get_generation_config(session_id, stream=False)
            )

            self.current_turn_context = None

            # Handle Tool Calls (Automatic by SDK, but we capture for logs)
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
            if response.usage_metadata:
                 print(f"Token Count: {token_count} (Cached: {response.usage_metadata.cached_content_token_count})")
            
            final_text = ""
            if response_content:
                for part in response_content.parts:
                    if part.text:
                        final_text += part.text
            
            # TTS Side Effect
            if config.VOICE and final_text:
                orion_tts.speak(final_text)

            # Update cache TTL (rolling heartbeat)
            if self.cache_manager and self.cached_content:
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
                    
            if last_chunk and last_chunk.usage_metadata:
                 print(last_chunk.usage_metadata.cached_content_token_count)
            
            if config.VOICE:
                orion_tts.flush_stream()
                
            self.current_turn_context = None

            # Update cache TTL (rolling heartbeat)
            if self.cache_manager:
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
            
            # --- Smart Truncation Checking via ChatObject ---
            # Enforce 1M token limit for Pro
            self.chat.enforce_token_limit(session_id, token_limit=1000000)

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

            return "\\n".join(output_lines)

        except (json.JSONDecodeError, IndexError, KeyError, TypeError):
            # If parsing fails, return an empty string to avoid polluting the context.
            return ""

    def _finalize_exchange(self, session_id, user_id, user_name, user_prompt, response_text, token_count, attachments_for_db, new_tool_turns, context_ids_for_db, user_content_for_db, model_content_obj):
        """
        Internal helper: Handles post-processing, database archival, and history management.
        Returns boolean indicating if a restart is pending.
        """
        # Archive via ChatObject
        new_db_id = self.chat.archive_exchange(
            session_id=session_id,
            user_id=user_id,
            user_name=user_name,
            prompt_text=user_prompt,
            response_text=response_text,
            attachments=attachments_for_db,
            token_count=token_count,
            vdb_context=json.dumps(context_ids_for_db), # Serialize for storage
            model_source=(self.local_model if None else self.model_name), # Fixme: No self.local_model access? OrionPro uses API model
            user_content_obj=user_content_for_db,
            model_content_obj=model_content_obj,
            tool_calls_list=new_tool_turns
        )
        
        print(f"----- Response Generated ({token_count} tokens) -----")
        return self.restart_pending

    def upload_file(self, file_bytes: bytes, display_name: str, mime_type: str):
        """
        Delegates upload logic to the centralized File Manager.
        """
        # Lazy inject Agent if needed by Manager for Vertex
        if config.VERTEX and self.file_manager.file_processing_agent is None:
             from agents.file_processing_agent import FileProcessingAgent
             self.file_processing_agent = FileProcessingAgent(self)
             self.file_manager.file_processing_agent = self.file_processing_agent
             
        # The manager handles everything (including Vertex analysis)
        return self.file_manager.process_file(file_bytes, display_name, mime_type)
    
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
