# orion_core_lite.py (Gemma/Lite Edition - Architecturally Aligned)
import os
import json
import sqlite3
import pickle
import sqlite3
import pickle
import sys
import io
import time
import asyncio
import base64
from typing import Generator
from datetime import datetime, timezone
import importlib
from dotenv import load_dotenv
load_dotenv()

# API Backends
from google import genai
from google.genai import types
try:
    import ollama
except ImportError:
    ollama = None 

from main_utils import config, main_functions as functions
from main_utils.chat_object import ChatObject
from main_utils.file_manager import UploadFile
from system_utils import orion_replay, orion_tts

# Define instruction files
INSTRUCTIONS_FILES = [
    'Primary_Directive_Lite.md' 
]

# --- Paths ---
INSTRUCTIONS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'instructions')

import logging
logger = logging.getLogger(__name__)



class OrionLiteCore:
    
    def __init__(self, model_name: str = config.AI_MODEL, persona: str = "default"):
        """
        Initializes the Lite version of Orion Core.
        Architecture mimics OrionCore (Pro) line-for-line where applicable.
        """
        if config.BACKEND == "api":
            logger.info(f"--- [Lite Core] Initializing for model: {model_name} (Backend: {config.BACKEND})     ---")
        else:
            logger.info(f"--- [Lite Core] Initializing for model: {config.LOCAL_MODEL} (Backend: {config.BACKEND}) ---")
            
        self.restart_pending = False
        
        # Core instance accessible to tools (even if tools aren't used, for consistency)
        config.ORION_CORE_INSTANCE = self

        self.current_turn_context = None
        self.model_name = model_name
        self.persona = config.PERSONA = persona
        self.backend = getattr(config, 'BACKEND', 'api').lower()
        self.local_model = getattr(config, 'LOCAL_MODEL', 'gemma3:1b')
        
        # --- Tool Initialization (Ollama Only) ---
        self.tools = []
        self.tool_map = {}
        if self.backend == "ollama":
            self.tools = self._load_tools()
            # Create a name -> callable map for execution
            # self.tools contains the callable functions themselves which Ollama SDK accepts
            self.tool_map = {func.__name__: func for func in self.tools}

        # Initialize Database access
        functions.initialize_persona(self.persona)
        
        # Vision System (Optional)
        self.vision_attachments = {}
        if config.VISION:
            logger.info("--- [Lite Core] Vision Module Activated ---")
            orion_replay.launch_obs_hidden()
            if orion_replay.connect_to_obs():
                 orion_replay.start_replay_watcher(orion_replay.REPLAY_SAVE_PATH, self._vision_file_handler)
                 orion_replay.start_vision_thread()

        # TTS System (Optional)
        if config.VOICE:
            orion_tts.start_tts_thread()
            logger.info("--- [Lite Core] TTS Module Activated ---")
            
        # Refreshing Core Instructions (Simplified)
        logger.info("--- Syncing Core Instructions... ---")
        self.current_instructions = self._read_all_instructions()
        if not self.current_instructions:
            self.current_instructions = "You are Orion, a helpful AI assistant."

        # Setup Client
        self._setup_client()

        # --- ChatObject Integration ---
        self.chat = ChatObject()
        self.sessions = self.chat.sessions # Alias for direct access where needed
        
        # Load persisted state via ChatObject
        if not self.chat.load_state_on_restart():
             pass 
        
        # Load persisted state via ChatObject
        if not self.chat.load_state_on_restart():
             pass 
        
        logger.info(f"--- [Lite Core] Online. Managing {len(self.chat.sessions)} session(s). Backend: {self.backend} ---")

    def _load_tools(self) -> list:
        """
        Dynamically loads tools from the 'main_utils' package based on the active persona.
        Mirrors logic from OrionCore (Pro).
        """
        loaded_tools = []
        # Always load main tools from main_functions
        try:
            if hasattr(functions, '__all__'):
                logger.info(f"--- [Lite Core] Loading {len(functions.__all__)} main tools from main_functions.py ---")
                for func_name in functions.__all__:
                    loaded_tools.append(getattr(functions, func_name))
        except Exception as e:
            logger.warning(f"Could not import main functions: {e}")

        # Load persona-specific tools if the persona is not 'default'
        if self.persona and self.persona != "default":
            persona_module_name = f"main_utils.{self.persona}_functions"
            try:
                persona_module = importlib.import_module(persona_module_name)
                if hasattr(persona_module, '__all__'):
                    logger.info(f"--- [Lite Core] Loading {len(persona_module.__all__)} tools from {persona_module_name} ---")
                    for func_name in persona_module.__all__:
                        loaded_tools.append(getattr(persona_module, func_name))
            except ImportError:
                logger.info(f"--- No specific tools module found for persona '{self.persona}'. Loading main tools only. ---")
        
        return loaded_tools

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

            
            if config.OLLAMA_CLOUD:
                logger.info(f"--- [Lite Core] Using Ollama Cloud: {self.local_model} ---")
                self.client = ollama.Client(
                    host="https://ollama.com",
                    headers={'Authorization': 'Bearer ' + os.environ.get('OLLAMA_API_KEY')}
                )
            else:
                logger.info(f"--- [Lite Core] Using Local Ollama: {self.local_model} ---")
                self.client = ollama.Client()
            
        # --- File Processing Agent Initialization (VLM) ---
        from agents.file_processing_agent import FileProcessingAgent
        self.file_processing_agent = FileProcessingAgent(self)
        
        # --- File Manager Initialization ---
        self.file_manager = UploadFile(
            core_backend=self.backend, 
            client=self.client if self.backend == "api" else None,
            file_processing_agent=self.file_processing_agent
        )
         

    def _read_all_instructions(self) -> str:
        """Reads instruction files."""
        prompt_parts = []
        for filename in INSTRUCTIONS_FILES:
            filepath = os.path.join(INSTRUCTIONS_DIR, filename)
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    prompt_parts.append(f.read())
            except FileNotFoundError:
                logger.warning(f"WARNING: File not found: {filepath}")
        return "\n\n".join(prompt_parts)

    def _vision_file_handler(self, file_path: str):
        """Callback for vision system."""
        try:
             with open(file_path, 'rb') as f:
                self.vision_attachments = {"video_bytes": f.read(), "display_name": os.path.basename(file_path)}
             logger.debug(f"[Vision] Captured {self.vision_attachments['display_name']}")
        except Exception as e:
            logger.error(f"[Vision Error] {e}")

    def _get_session(self, session_id: str) -> list:
        return self.chat.get_session(session_id)

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
        logger.info(f"----- Processing prompt for session {session_id} and user {user_name} -----")
        chat_session = self._get_session(session_id)
        timestamp_utc_iso = datetime.now(timezone.utc).isoformat()
        
        # --- Context Injection ---
        # Exclude only if ID is valid and not placeholder (placeholder check redundant now but safe)
        excluded_ids = [ex["db_id"] for ex in chat_session if ex.get("db_id") and ex["db_id"] != "db_id_placeholder"]
        
        # 1. Memory Lookups
        deep_memory_where = {"source_table": "deep_memory"} 
        if excluded_ids:
             deep_memory_where = {"$and": [{"source_table": "deep_memory"}, {"source_id": {"$nin": excluded_ids}}, {"session_id": session_id}]}

        try:
            # OPTIMIZATION: Skip VDB for Local Ollama backend to save resources
            if config.PAST_MEMORY:
                deep_memory_results_raw = functions.execute_vdb_read(query_texts=[user_prompt], n_results=2, where=deep_memory_where)
                long_term_results_raw = functions.execute_vdb_read(query_texts=[user_prompt], n_results=1, where={"source_table": "long_term_memory"})
            
                formatted_deep_mem = self._format_vdb_results_for_context(deep_memory_results_raw, "Deep Memory")
                formatted_ltm = self._format_vdb_results_for_context(long_term_results_raw, "Long-Term Memory")
                
                formatted_vdb_context = f"{formatted_deep_mem}\\n{formatted_ltm}".strip()
            else:
                formatted_vdb_context = ""
                deep_memory_results_raw = "{}"
                long_term_results_raw = "{}"
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
             self.vision_attachments = {}

        if config.VISION and self.vision_attachments:
             data_envelope["system_notifications"].append(f"[Vision: Attached {self.vision_attachments['display_name']}]")
             self.vision_attachments = {}

        # Construct User Content Part
        
        # --- MODIFICATION: Handle Unified File Objects ---
        final_file_parts = []
        injected_text_buffers = []
        file_injections = []
        
        # Separation: Text Injections vs Real Attachments
        #logger.debug(file_check)
        if file_check:
             for f in file_check:
                 # Check for Text Extraction or Analysis
                 if hasattr(f, 'text_content'):
                     header = f"\n\n--- FILE: {f.display_name} ---\n"
                     if getattr(f, 'is_analysis', False):
                         header = f"\n\n--- FILE ANALYSIS: {f.display_name} ({f.mime_type}) ---\n[System: The following is an AI analysis of the file.]\n"
                     
                     injected_text_buffers.append(f"{header}{f.text_content}")
                     
                     # Add to formal data envelope list
                     file_injections.append({
                        "name": f.display_name,
                        "mime": getattr(f, 'mime_type', 'text/plain'),
                        "content_preview": f.text_content[:200] + "..." if len(f.text_content) > 200 else f.text_content
                     })
                 else:
                     # It's a Media File (API File or Local Base64/Path)
                     # If generic API file (Vertex/Standard) -> Add to parts
                     if hasattr(f, 'uri') and f.uri.startswith('http'): 
                         final_file_parts.append(f)
                     elif self.backend == "ollama" and hasattr(f, 'base64_data'):
                         pass 
 
        # Note: In Lite Core, we usually construct one big 'UserContent'.
        if file_injections:
             data_envelope["file_injections"] = file_injections

        if injected_text_buffers:
            data_envelope["user_prompt"] += "".join(injected_text_buffers)
            
        # Re-serialization of envelope
        final_text_part = types.Part.from_text(text=json.dumps(data_envelope, indent=2))
        
        # --- File Attachment Handling ---
        attachments_for_db = []
        if file_check:
            # Metadata Extraction
            for f in file_check:
                try:
                    # Normalize URI/Name
                    ref = getattr(f, 'name', getattr(f, 'uri', 'unknown'))
                    attachments_for_db.append({
                        "file_ref": ref,
                        "file_name": getattr(f, 'display_name', 'unknown'),
                        "mime_type": getattr(f, 'mime_type', 'unknown'),
                        "size_bytes": getattr(f, 'size_bytes', 0),
                        "text_content": getattr(f, 'text_content', None) 
                    })
                except Exception as e:
                    logger.warning(f"Warning: Could not extract metadata from file handle: {e}")
            
            data_envelope["system_notifications"].append(f"[System: User attached {len(file_check)} file(s)]")
            
            # --- Ollama Rate Limit Warning ---
            if self.backend == "ollama":
                 data_envelope["system_notifications"].append("[System Notice: You are limited to a maximum of 5 function calls per turn. If you reach this limit, you must stop and summarize your findings.]")
            
            # For API Backend: Combine File Parts + Text Part
            if self.backend == "api":
                final_part = final_file_parts + [final_text_part]
            else:
                # For Local/Ollama: We just send the Text Part here.
                # Images need to be passed strictly via the `images` arg in `ollama.chat`.
                # We will attach the raw file objects to the *User Content Object* custom field?
                # Or we rely on `file_check` being passed down? 
                # `_generate_stream_response` signature assumes `contents_to_send`.
                # We need to hack the `UserContent` to hold the image data if we want it to flow to `_generate`.
                # Google Types don't natively support "Base64 Image" parts that aren't API files?
                # Actually they do: types.Part.from_bytes(...)
                # Let's try to convert Base64 to Blob part if possible? 
                # But Ollama client expects specific structure. 
                # EASIEST PATH: We are passing `file_check` via `_finalize` etc? No.
                # `_generate` receives `contents_to_send`.
                # We should embed the images as parts in the UserContent.
                
                ollama_parts = [final_text_part]
                for f in file_check:
                    # Check if base64_data exists AND is not None
                    if getattr(f, 'base64_data', None):
                        # Attach as a "proxy" part or just raw object?
                        # The `_generate` loop iterates parts.
                        # We can attach a custom object if we want.
                        # Let's attach a "Placeholder Part" that holds the image data.
                        # Python allows dynamic attributes.
                        # Use standard GenAI Blob for data storage
                        try:
                            # f.base64_data is text. Decode to bytes for the Part.
                            img_bytes = base64.b64decode(f.base64_data)
                            p = types.Part.from_bytes(data=img_bytes, mime_type=f.mime_type)
                            ollama_parts.append(p)
                        except Exception as e:
                            logger.error(f"Error creating image part: {e}")
                            
                final_part = ollama_parts

        else:
            final_part = [final_text_part]

        user_content_for_db = types.UserContent(parts=[types.Part.from_text(text=json.dumps(data_envelope, indent=2))])
        final_content = types.UserContent(parts=final_part) # This is the object for the API

        # History
        contents_to_send = self.chat.flatten_history(session_id)
        contents_to_send.append(final_content)
        
        return (contents_to_send, data_envelope, context_ids_for_db, attachments_for_db, user_content_for_db)

    def _execute_safe(self, func_name: str, **kwargs):
        """Safe execution wrapper for tools."""
        if func_name in self.tool_map:
            try:
                logger.info(f"--- [Lite Tool Exec] Running: {func_name} with args: {kwargs} ---")
                return self.tool_map[func_name](**kwargs)
            except Exception as e:
                logger.error(f"Error executing tool {func_name}: {e}")
                return f"Error executing tool {func_name}: {e}"
        return f"Error: Tool '{func_name}' not found."

    def _generate_stream_response(self, contents_to_send, data_envelope, session_id, user_id, user_name, user_prompt, attachments_for_db, context_ids_for_db, user_content_for_db):
        """
        Internal helper: Handles streaming generation.
        """
        logger.info(f"----- Sending Prompt to Orion Lite ({config.BACKEND}) . . . -----")
        
        full_response_text = ""
        token_count = 0
        new_tool_turns = [] # Accumulate tool calls for archival
        
        try:
            if self.backend == "api":
                # API Mode - Gemma does NOT support system_instruction in config.
                
                system_content = types.Content(
                    role="user",
                    parts=[types.Part.from_text(text=f"System Context:\n{self.current_instructions}")]
                )
                
                # Prepend to the prompt list
                final_contents = [system_content] + contents_to_send
                
                response_stream = self.client.models.generate_content_stream(
                    model=self.model_name,
                    contents=final_contents,
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
                # 1. Convert History (Delegated to ChatObject)
                ollama_messages = self.chat.convert_history_to_ollama(contents_to_send, self.current_instructions)
                
                # 2. Agentic Loop (While True)
                tool_loop_count = 0
                while True:
                    try:
                        stream_kwargs = {
                            "model": self.local_model,
                            "messages": ollama_messages,
                            "stream": True,
                            "keep_alive": -1
                        }
                        
                        # Add Tools (Native Support)
                        if self.tools:
                             stream_kwargs["tools"] = self.tools

                        # Add Thinking (If Supported/Enabled)
                        if config.THINKING_SUPPORT:
                            stream_kwargs["think"] = True

                        # Verify Ollama client
                        if not self.client: # Should be initialized but sanity check
                             self._setup_client()

                        stream = self.client.chat(**stream_kwargs)
                        
                        # Helper to rebuild the assistant message from chunks
                        final_message = {"role": "assistant", "content": "", "tool_calls": []}

                        # Iterate Stream
                        for chunk in stream:
                            msg_part = chunk.get('message', {})
                            
                            # A. Handle Thinking
                            if msg_part.get('thinking'):
                                think_text = msg_part['thinking']
                                if 'thought_buffer' not in locals():
                                    locals()['thought_buffer'] = []
                                    logger.debug("[Thinking Process Started...]")
                                
                                locals()['thought_buffer'].append(think_text)
                                yield {"type": "thought", "content": think_text}

                            # B. Handle Content
                            content = msg_part.get('content')
                            if content:
                                # Flush thoughts if needed
                                if 'thought_buffer' in locals():
                                    full_thought = "".join(locals()['thought_buffer'])
                                    logger.debug(f"[Detailed Thought Process]: {full_thought}")
                                    logger.debug("[Thinking Process Complete]")
                                    del locals()['thought_buffer']

                                yield {"type": "token", "content": content}
                                final_message["content"] += content
                                full_response_text += content # Accumulate full text for final save
                                if config.VOICE: orion_tts.process_stream_chunk(content)
                            
                            # C. Accumulate Tool Calls
                            if msg_part.get('tool_calls'):
                                for tc in msg_part['tool_calls']:
                                    final_message["tool_calls"].append(tc)

                        # --- End of Stream Chunking ---
                        
                        # 3. Decision Logic
                        if not final_message["tool_calls"]:
                            # No tools called -> Response is complete.
                            break
                        
                        # 4. Tool Execution Phase
                        # Append assistant's "intent" to local history
                        ollama_messages.append(final_message)
                        
                        # --- RATE LIMIT CHECK ---
                        if tool_loop_count >= 5:
                            logger.warning(f"Tool execution limit reached ({tool_loop_count}). Blocking execution.")
                            limit_msg = "System Error: Execution Limit Reached. You have performed 5 function calls, which is the maximum allowed for this turn. Do not re-try. Finalize your response based on the information you have."
                            
                            # Mock error responses for all pending calls
                            for tool in final_message["tool_calls"]:
                                ollama_messages.append({
                                    "role": "tool",
                                    "content": limit_msg
                                })
                                new_tool_turns.append({
                                    "name": "System_Limit_Enforced",
                                    "args": {},
                                    "result": limit_msg
                                })
                        
                        else:
                            # Execute each tool
                            for tool in final_message["tool_calls"]:
                                # Handle Dict vs Object (Robustness)
                                if isinstance(tool, dict):
                                    func_map = tool.get('function', {})
                                    func_name = func_map.get('name')
                                    args = func_map.get('arguments', {})
                                else:
                                    func_name = tool.function.name
                                    args = tool.function.arguments
                                
                                # Execute
                                result = self._execute_safe(func_name, **args)
                                
                                # Append result to local history
                                ollama_messages.append({
                                    "role": "tool",
                                    "tool_name": func_name,
                                    "content": str(result), 
                                    # "name": func_name # Optional in some versions, but content is key
                                })
                                
                                # Capture for archival (generic dict structure)
                                new_tool_turns.append({
                                    "name": func_name,
                                    "args": args,
                                    "result": str(result)
                                })
                        
                        # Increment Loop Count
                        tool_loop_count += 1
                        
                        # Loop continues -> Model gets results -> Generates next step
                    
                    except Exception as e:
                         if "does not support thinking" in str(e):
                            logger.warning("Model does not support thinking. Retrying without it.")
                            config.THINKING_SUPPORT = False
                            continue
                         else:
                            raise e

                # --- Finalization (Post-Loop) ---
                if config.VOICE: orion_tts.flush_stream()
                
                # Estimate tokens
                token_count = len(full_response_text) // 3
                # End of Stream Loop  
        
        except Exception as e:
            logger.error(f"Error in generation: {e}")
            yield {"type": "token", "content": f"[Error: {e}]"}
            return

        # Finalize Exchange
        self._finalize_exchange(
            session_id, user_id, user_name, user_prompt, 
            full_response_text, token_count, attachments_for_db, 
            None, context_ids_for_db, user_content_for_db, 
            types.ModelContent(parts=[types.Part.from_text(text=full_response_text)]) 
        )
        
        # Autosave Removed meant for restart persistence only
        # self.chat.save_state_for_restart()
        yield {"type": "done"}

    def _finalize_exchange(self, session_id, user_id, user_name, user_prompt, response_text, token_count, attachments_for_db, new_tool_turns, context_ids_for_db, user_content_for_db, model_content_obj):
        """
        Internal helper: Handles post-processing.
        Delegates archival to ChatObject.
        """
        self.chat.archive_exchange(
            session_id=session_id,
            user_id=user_id,
            user_name=user_name,
            prompt_text=user_prompt,
            response_text=response_text,
            attachments=attachments_for_db,
            token_count=token_count,
            vdb_context=json.dumps(context_ids_for_db), # Serialize for storage
            model_source=(self.local_model if self.backend == "ollama" else self.model_name),
            user_content_obj=user_content_for_db,
            model_content_obj=model_content_obj,
            tool_calls_list=new_tool_turns
        )
        
        logger.info(f"----- Response Generated ({token_count} tokens) -----")
        return False

    def process_prompt(self, session_id: str, user_prompt: str, file_check: list = None, user_id: str = None, user_name: str = "User", stream: bool = False) -> Generator:
        """
        Orchestrator: Identical to Pro.
        """
        file_check = file_check or [] # Robustness fix
        try:
            yield {"type": "status", "content": "Initializing Request..."}
            
            # --- Smart Truncation Checking via ChatObject ---
            # Enforce 10k token limit for Lite
            self.chat.enforce_token_limit(session_id, token_limit=14000)
            
            yield {"type": "status", "content": "Accessing Memory..."}
            
            (contents_to_send, data_envelope, context_ids_for_db, attachments_for_db, user_content_for_db) = \
                self._prepare_prompt_data(session_id, user_prompt, file_check, user_id, user_name)
            
            yield {"type": "status", "content": "Thinking..."}
            
            generator = self._generate_stream_response(
                contents_to_send, data_envelope, session_id, user_id, user_name, user_prompt, 
                attachments_for_db, context_ids_for_db, user_content_for_db
            )
            for item in generator: yield item

        except Exception as e:
            logger.error(f"Error in process_prompt: {e}")
            yield {"type": "token", "content": f"[System Error: {e}]"}

    # --- Proxy Methods for Compatibility with GUI/Bot ---
    def list_sessions(self) -> list:
        return self.chat.list_sessions()

    def manage_session_history(self, session_id: str, count: int = 0, index: int = -1) -> str:
        return self.chat.manage_session_history(session_id, count, index)

    def save_state_for_restart(self) -> bool:
        return self.chat.save_state_for_restart()
        
    def _load_state_on_restart(self) -> bool:
        return self.chat.load_state_on_restart()
    
    def execute_restart(self):
         # Lite core hard restart just means exit, bot.py handles loop.
         # But to be consistent with main_utils logic we can use python executable.
         python = sys.executable
         os.execl(python, python, *sys.argv)

    def trigger_instruction_refresh(self, full_restart: bool = False):
        """
        WHAT (Purpose): Performs a full "hot-swap or an “Orchestrated Restart” of your core programming. 
        Hot-Swap: It reloads all instruction files from disk AND reloads all of your tools from functions.py, then rebuilds all active chat sessions with this new information.
        Orchestrated Restart: Restarts the current Instance of the Orion Core to reload the tools from functions.py, the instructions files from disk, AND applies any new changes from orion_core.py file from disk.
        HOW (Usage): This tool is called with no arguments for a “Hot-Swap” and a boolean value of True for an “Orchestrated Restart”.
        WHEN (Scenarios): You MUST call this tool immediately after any action that modifies the files that define your context or capabilities.
        For “Hot-Swap” refreshes:
        After a successful apply_proposed_change call.
        After a successful rebuild_manifests call.
        After the Operator confirms that a manual_sync_instructions call was successful.
        For “Orchestrated Restart” refreshes:
        After a successful change was made in the orion_core.py file
        WHY (Strategic Value): This is the critical final step in any self-modification process. It is the command that makes your changes "live" in your current instance without requiring a manual full system restart from the Operator.
        CRITICAL PROTOCOL: Failure to call this tool after a relevant file modification will result in a state where your current instance is out of sync with your source code and instructions, which can lead to errors or unpredictable behavior.
        """
        if full_restart:
            logger.warning("WARNING: 'full_restart' flag ignored in Client-Server mode.")
            return "[System Note]: Full restart ignored in Client-Server mode. Use TUI to restart Server."
        
        self.current_instructions = self._read_all_instructions()
        return "Instructions Refreshed (Hot Swap)"

    def shutdown(self):
        """Performs a clean shutdown."""
        logger.info("--- Orion Core shutting down. ---")
        # --- NEW: Stop the TTS thread on shutdown ---
        if config.VOICE:
            orion_tts.stop_tts_thread()
        if config.VISION:
            orion_replay.shutdown_obs()
        logger.info("--- Orion is now offline. ---")

    def execute_restart(self):
        """
        Executes the final step of the restart by shutting down gracefully
        and then replacing the current process.
        """
        logger.info("  - State saved. Performing graceful shutdown before restart...")
        self.shutdown() # <-- CRITICAL: Call the shutdown method here.
        logger.info("  - Shutdown complete. Executing process replacement...")
        os.execv(sys.executable, ['python'] + sys.argv)

    def upload_file(self, file_bytes: bytes, display_name: str, mime_type: str):
        """
        Delegates to centralized File Manager.
        """
        return self.file_manager.process_file(file_bytes, display_name, mime_type)
