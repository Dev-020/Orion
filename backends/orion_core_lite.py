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

        # --- ChatObject Integration ---
        self.chat = ChatObject()
        self.sessions = self.chat.sessions # Alias for direct access where needed
        
        # Load persisted state via ChatObject
        if not self.chat.load_state_on_restart():
             pass 
        
        print(f"--- [Lite Core] Online. Managing {len(self.chat.sessions)} session(s). ---")

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
                print(f"--- [Lite Core] Using Ollama Cloud: {self.local_model} ---")
                self.client = ollama.Client(
                    host="https://ollama.com",
                    headers={'Authorization': 'Bearer ' + os.environ.get('OLLAMA_API_KEY')}
                )
            else:
                print(f"--- [Lite Core] Using Local Ollama: {self.local_model} ---")
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
        return self.chat.get_session(session_id)

    def flatten_history(self, session_id: str) -> list:
        """
        Takes a session ID, retrieves the custom ExchangeDict history, and flattens
        it into the format required by the GenAI API (list[Content]).
        For Ollama, we do a different flattening in _generate, or we assume this is just for API usage.
        """
        chat_session = self.chat.get_session(session_id)
        contents_to_send = []
        
        # PRO History Structure: List of objects/dicts. 
        # We assume consistent keys "user_content", "model_content"
        
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
                        "size_bytes": getattr(f, 'size_bytes', 0)
                    })
                except Exception as e:
                    print(f"Warning: Could not extract metadata from file handle: {e}")
            
            data_envelope["system_notifications"].append(f"[System: User attached {len(file_check)} file(s)]")
            
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
                    if hasattr(f, 'base64_data'):
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
                            print(f"Error creating image part: {e}")
                        
                final_part = ollama_parts

        else:
            final_part = [final_text_part]

        user_content_for_db = types.UserContent(parts=[types.Part.from_text(text=json.dumps(data_envelope, indent=2))])
        final_content = types.UserContent(parts=final_part) # This is the object for the API

        # History
        contents_to_send = self.flatten_history(session_id)
        contents_to_send.append(final_content)
        
        return (contents_to_send, data_envelope, context_ids_for_db, attachments_for_db, user_content_for_db)

    def _generate_stream_response(self, contents_to_send, data_envelope, session_id, user_id, user_name, user_prompt, attachments_for_db, context_ids_for_db, user_content_for_db):
        """
        Internal helper: Handles streaming generation.
        """
        print(f"----- Sending Prompt to Orion Lite ({config.BACKEND}) . . . -----")
        
        full_response_text = ""
        token_count = 0
        
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
                # Ollama Mode - Requires Conversion from `contents_to_send` (Google Types) to List[Dict]
                ollama_messages = []
                
                # System Prompt
                # Append Lite-Specific Directive to stabilize small models
                lite_directive = (
                    "\n\n[SYSTEM NOTE: You are running on a lightweight local backend. "
                    "Input metadata is provided in headers (e.g., [Metadata:...]). "
                    "Do NOT analyze the data structure. Do NOT mention JSON. "
                    "Respond naturally as the persona defined above.]"
                )
                ollama_messages.append({"role": "system", "content": self.current_instructions + lite_directive})
                
                # History (Convert Google Types to Dict)
                for content in contents_to_send:
                    role = "user" if content.role == "user" else "assistant"
                    
                    # Text Extraction
                    text_parts = []
                    images_list = []
                    
                    if content.parts:
                        for p in content.parts:
                            if hasattr(p, 'text') and p.text:
                                text_parts.append(p.text)
                            
                            # Handle Standard GenAI Image Part (Blob)
                            if hasattr(p, 'inline_data') and p.inline_data:
                                try:
                                    # Convert bytes back to Base64 String for Ollama
                                    b64_img = base64.b64encode(p.inline_data.data).decode('utf-8')
                                    images_list.append(b64_img)
                                except Exception as e:
                                    print(f"Error extracting image for Ollama: {e}")
                                
                    full_text = "\n".join(text_parts)
                    
                    # --- UNWRAP JSON ENVELOPE FOR OLLAMA ---
                    # DeepSeek/Ollama models confuse the JSON wrapper with instructions.
                    # We parse it to extract just the human-readable Prompt + System Notes.
                    if role == "user":
                        try:
                            data = json.loads(full_text)
                            if "user_prompt" in data:
                                clean_prompt = data["user_prompt"]
                                # Prepend System Notifications if any
                                if "system_notifications" in data and data["system_notifications"]:
                                    notes = "\n".join(data["system_notifications"])
                                    clean_prompt = f"{notes}\n\n{clean_prompt}"
                                
                                # Prepend Vector Context if any
                                if "vdb_context" in data and data["vdb_context"]:
                                    clean_prompt = f"{data['vdb_context']}\n\n{clean_prompt}"
                                    
                                # Prepend Metadata (Auth/Time) formatted for Reader
                                meta_header = ""
                                if "auth" in data:
                                    auth = data["auth"]
                                    u_name = auth.get("user_name", "Unknown")
                                    u_id = auth.get("user_id", "?")
                                    ts = data.get("timestamp_utc", "")
                                    meta_header = f"[Metadata: User='{u_name}' (ID: {u_id}) | Time='{ts}']\n"
                                
                                clean_prompt = f"{meta_header}{clean_prompt}"
                                    
                            
                            full_text = clean_prompt
                        except:
                            # Not JSON or parse error, use raw text
                            pass

                    ollama_msg = {"role": role, "content": full_text}
                    if images_list:
                        ollama_msg["images"] = images_list
                        
                    ollama_messages.append(ollama_msg)
                
                # Streaming with Compatibility Fallback
                
                while True:
                    try:
                        stream_kwargs = {
                            "model": self.local_model,
                            "messages": ollama_messages,
                            "stream": True,
                            "keep_alive": -1
                        }
                        # ONLY add the 'think' parameter if globally enabled.
                        if config.THINKING_SUPPORT:
                            stream_kwargs["think"] = True

                        stream = self.client.chat(**stream_kwargs)
                        
                        # We must iterate inside the try block to catch lazy errors
                        for chunk in stream:
                             # Access dictionary keys safely    
                            msg = chunk.get('message', {})
                            
                            # 1. Handle Thinking (Terminal Only + Yield)
                            if msg.get('thinking'):
                                think_text = msg['thinking']
                                print(f"\033[90m{think_text}\033[0m", end='', flush=True)
                                yield {"type": "thought", "content": think_text}
                            
                            # 2. Handle Content (Yield to Discord)
                            content = msg.get('content')
                            if content:
                                yield {"type": "token", "content": content}
                                full_response_text += content
                                if config.VOICE: orion_tts.process_stream_chunk(content)
                        
                        # If we finish the loop successfully, break the while loop
                        break

                    except Exception as e:
                        # Check if error is due to 'think' parameter (Status 400 / "does not support thinking")
                        if "does not support thinking" in str(e):
                            print(f"--- Model does not support Thinking. Retrying without it. (Error: {e}) ---")
                            print(f"--- Disabling Thinking Mode for this session to improve performance. ---")
                            config.THINKING_SUPPORT = False # Persist flag change for this runtime
                            continue # Retry loop
                        else:
                            # Genuine error, re-raise to outer block
                            raise e
                
                # Ollama doesn't give usage in stream? Stubbing.
                token_count = len(full_response_text) // 3
                # End of Stream Loop  
        
        except Exception as e:
            print(f"Error in generation: {e}")
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
        
        print(f"----- Response Generated ({token_count} tokens) -----")
        return False

    def process_prompt(self, session_id: str, user_prompt: str, file_check: list, user_id: str, user_name: str, stream: bool = False) -> Generator:
        """
        Orchestrator: Identical to Pro.
        """
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
            print(f"Error in process_prompt: {e}")
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
        if full_restart:
            self.execute_restart()
        else:
            self.current_instructions = self._read_all_instructions()
            return "Instructions Refreshed"

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

    def upload_file(self, file_bytes: bytes, display_name: str, mime_type: str):
        """
        Delegates to centralized File Manager.
        """
        return self.file_manager.process_file(file_bytes, display_name, mime_type)
