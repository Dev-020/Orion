import os
import sys
import json
import logging
import subprocess
import time
from typing import Generator
from datetime import datetime, timezone

from google.genai import types

from main_utils import config, main_functions as functions
from main_utils.chat_object import ChatObject
from main_utils.file_manager import UploadFile
from system_utils import orion_replay, orion_tts

logger = logging.getLogger(__name__)

class OrionCoreGeminiCLI:
    def __init__(self, model_name: str = config.AI_MODEL, persona: str = "default"):
        """
        Initializes the Gemini CLI wrapper version of Orion Core.
        Architecture mimics OrionCore but uses an ephemeral terminal process per-generation as the brain.
        """
        logger.info(f"--- [CLI Core] Initializing Gemini CLI wrapper ---")
        
        self.restart_pending = False
        config.ORION_CORE_INSTANCE = self

        self.current_turn_context = None
        self.model_name = model_name
        self.persona = config.PERSONA = persona
        self.backend = "cli"
        
        # Tools: Let CLI handle them natively if configured
        self.tools = []
        self.tool_map = {}

        # Initialize Database access
        functions.initialize_persona(self.persona)
        
        # Vision System (Optional)
        self.vision_attachments = {}
        if config.VISION:
            logger.info("--- [CLI Core] Vision Module Activated ---")
            orion_replay.launch_obs_hidden()
            if orion_replay.connect_to_obs():
                 orion_replay.start_replay_watcher(orion_replay.REPLAY_SAVE_PATH, self._vision_file_handler)
                 orion_replay.start_vision_thread()

        # TTS System (Optional)
        if config.VOICE:
            orion_tts.start_tts_thread()
            logger.info("--- [CLI Core] TTS Module Activated ---")

        # --- File Manager Initialization ---
        self.file_manager = UploadFile(
            core_backend=self.backend, 
            client=None,
            file_processing_agent=None
        )

        # --- ChatObject Integration ---
        self.chat = ChatObject()
        self.sessions = self.chat.sessions
        
        if not self.chat.load_state_on_restart():
             pass 
        
        logger.info(f"--- [CLI Core] Online. Ready for headless prompt execution. ---")


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
        try:
            data = json.loads(raw_json)
            if not data.get('documents') or not data['documents'][0]:
                return ""

            output_lines = [f"--- Context from {source_name} ---"]
            for i, doc in enumerate(data['documents'][0]):
                 output_lines.append(f"- {doc}")
            return "\\n".join(output_lines)
        except:
            return ""

    def _prepare_prompt_data(self, session_id: str, user_prompt: str, file_check: list, user_id: str, user_name: str):
        logger.info(f"----- Processing prompt for session {session_id} and user {user_name} -----")
        chat_session = self._get_session(session_id)
        
        excluded_ids = [ex["db_id"] for ex in chat_session if ex.get("db_id") and ex["db_id"] != "db_id_placeholder"]
        
        deep_memory_where = {"source_table": "deep_memory"} 
        if excluded_ids:
             deep_memory_where = {"$and": [{"source_table": "deep_memory"}, {"source_id": {"$nin": excluded_ids}}, {"session_id": session_id}]}

        try:
            if getattr(config, 'PAST_MEMORY', False):
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

        data_envelope = {
            "system_notifications": [],
            "user_prompt": user_prompt,
            "vdb_context": vdb_response
        }

        if config.VISION and self.vision_attachments:
             data_envelope["system_notifications"].append(f"[Vision: Attached {self.vision_attachments['display_name']}]")
             self.vision_attachments = {}

        injected_text_buffers = []
        file_attachments_for_cli = []
        attachments_for_db = []

        if file_check:
             for f in file_check:
                 try:
                     ref = getattr(f, 'name', getattr(f, 'uri', 'unknown'))
                     attachments_for_db.append({
                         "file_ref": ref,
                         "file_name": getattr(f, 'display_name', 'unknown'),
                         "mime_type": getattr(f, 'mime_type', 'unknown'),
                         "size_bytes": getattr(f, 'size_bytes', 0),
                         "text_content": getattr(f, 'text_content', None) 
                     })
                 except Exception as e:
                     logger.warning(f"Metadata extract warning: {e}")

                 # Provide file path directly to CLI if local
                 local_path = getattr(f, 'local_path', None)
                 if local_path and os.path.exists(local_path):
                     file_attachments_for_cli.append(f"@{local_path}")
                 elif hasattr(f, 'text_content'):
                     header = f"\n\n--- FILE: {f.display_name} ---\n"
                     if getattr(f, 'is_analysis', False):
                         header = f"\n\n--- FILE ANALYSIS: {f.display_name} ({f.mime_type}) ---\n[System: The following is an AI analysis of the file.]\n"
                     injected_text_buffers.append(f"{header}{f.text_content}")

        if file_attachments_for_cli:
             data_envelope["system_notifications"].extend(file_attachments_for_cli)

        if injected_text_buffers:
            data_envelope["user_prompt"] += "".join(injected_text_buffers)

        # Re-build for db purposes
        user_content_for_db = types.UserContent(parts=[types.Part.from_text(text=json.dumps(data_envelope, indent=2))])

        return (None, data_envelope, context_ids_for_db, attachments_for_db, user_content_for_db)

    def _generate_stream_response(self, data_envelope, session_id, user_id, user_name, user_prompt, attachments_for_db, context_ids_for_db, user_content_for_db):
        """Handles streaming generation by spawning an ephemeral CLI subprocess."""
        logger.info(f"----- Sending Prompt to Orion CLI Core . . . -----")
        
        full_response_text = ""
        token_count = 0
        new_tool_turns = []
        temp_file_path = None

        try:
            # 1. Gather Chat History
            chat_session = self._get_session(session_id)
            history_text = []
            if chat_session:
                history_text.append("--- PREVIOUS CHAT HISTORY ---")
                for exchange in chat_session[-10:]: # Pass last 10 messages context to CLI
                    history_text.append(f"User: {exchange.get('prompt', '')}")
                    history_text.append(f"Assistant: {exchange.get('response', '')}")
                history_text.append("-----------------------------")

            # 2. Format the payload string
            parts_to_send = []
            if history_text:
                parts_to_send.extend(history_text)
            
            if data_envelope.get("vdb_context"):
                parts_to_send.append(data_envelope["vdb_context"])
            
            for note in data_envelope.get("system_notifications", []):
                parts_to_send.append(note)
                
            # Only add "User: " if we have history or other context parts
            if parts_to_send:
                parts_to_send.append(f"User: {data_envelope['user_prompt']}")
            else:
                parts_to_send.append(data_envelope['user_prompt'])
            
            final_prompt_string = "\n".join(parts_to_send)
            logger.info(f"--- [DEBUG] Final Prompt being sent to CLI: ---")
            logger.info(final_prompt_string)
            logger.info(f"--- [DEBUG] END OF PROMPT ---")
            
            import uuid
            # Use a local relative filename to avoid absolute path/backslash issues on Windows
            temp_filename = f"orion_prompt_{uuid.uuid4().hex[:8]}.txt"
            with open(temp_filename, "w", encoding="utf-8") as f:
                f.write(final_prompt_string)
            temp_file_path = temp_filename
            
            # 3. Spawn Subprocess and inject prompt
            import sys
            
            # Bypassing the cmd wrapper on Windows for cleaner stdin handling
            try:
                npm_root = subprocess.check_output(['npm', 'root', '-g'], shell=True if sys.platform == 'win32' else False).decode().strip()
                cli_js_path = os.path.join(npm_root, '@google', 'gemini-cli', 'dist', 'index.js')
            except Exception as e:
                logger.warning(f"Failed to find npm global root: {e}")
                cli_js_path = "gemini" # Fallback

            # Construct the command as a single string to use with shell=True
            # This ensures the CLI receives the arguments exactly as if run in the terminal.
            cmd_str = f'node "{cli_js_path}" --prompt "@{temp_filename}" --yolo -o stream-json -e none'
            logger.info(f"--- [DEBUG] Executing Shell Command: {cmd_str}")

            cli_process = subprocess.Popen(
                cmd_str,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding='utf-8',
                bufsize=1,
                shell=True
            )

            # 4. Stream Loop Reading
            for line in iter(cli_process.stdout.readline, ''):
                logger.debug(f"[CLI RAW] {line.strip()}")
                if not line.strip():
                    continue
                try:
                    data = json.loads(line)
                    msg_type = data.get("type")
                    
                    if msg_type == "init":
                        logger.info(f"[CLI Core] Initialized with Session ID: {data.get('session_id')}")
                    
                    elif msg_type == "message" and data.get("role") == "assistant":
                        content = data.get("content", "")
                        if content:
                            yield {"type": "token", "content": content}
                            full_response_text += content
                            if getattr(config, 'VOICE', False): orion_tts.process_stream_chunk(content)
                            
                    elif msg_type == "tool_use":
                        tool_name = data.get("tool_name", "unknown")
                        logger.info(f"[CLI Core] Tool Called: {tool_name}")
                        yield {"type": "status", "content": f"Running tool: {tool_name}"}
                        
                    elif msg_type == "tool_result":
                        tool_name = data.get("tool_id", "unknown")
                        output = data.get("output", "")
                        logger.info(f"[CLI Core] Tool Result Received: {tool_name}")
                        new_tool_turns.append({
                            "name": tool_name,
                            "args": {},
                            "result": str(output)
                        })
                        yield {"type": "status", "content": f"Tool result parsed"}
                        
                    elif msg_type == "result":
                        logger.info(f"[CLI Core] End of generation flagged directly by CLI result state.")
                        break
                        
                except json.JSONDecodeError as jde:
                    # Ignore non-JSON terminal noise unless it looks like it should have been JSON
                    if "{" in line:
                        logger.debug(f"[CLI JSON Error] {jde} on line: {line.strip()}")
                    pass
            
            if not full_response_text:
                logger.warning("[CLI Core] No content was received from the CLI process.")
                yield {"type": "token", "content": "[No response from CLI core]"}
                    
            # Cleanup process
            cli_process.wait(timeout=30.0)

        except Exception as e:
            logger.error(f"Error in generation: {e}")
            yield {"type": "token", "content": f"[Error: {e}]"}
        finally:
            if temp_file_path and os.path.exists(temp_file_path):
                try:
                    os.remove(temp_file_path)
                except Exception as cleanup_err:
                    logger.warning(f"Failed to cleanup temp file {temp_file_path}: {cleanup_err}")

        if getattr(config, 'VOICE', False): orion_tts.flush_stream()
        token_count = len(full_response_text) // 3

        # Finalize Exchange
        logger.info(f"--- [CLI Core] Archiving exchange to database... ---")
        try:
            self.chat.archive_exchange(
                session_id=session_id,
                user_id=user_id,
                user_name=user_name,
                prompt_text=user_prompt,
                response_text=full_response_text,
                attachments=attachments_for_db,
                token_count=token_count,
                vdb_context=json.dumps(context_ids_for_db),
                model_source=(self.model_name),
                user_content_obj=user_content_for_db,
                model_content_obj=types.ModelContent(parts=[types.Part.from_text(text=full_response_text)]),
                tool_calls_list=new_tool_turns
            )
        except Exception as arch_err:
            logger.error(f"--- [CLI Core] Archival Error: {arch_err} ---")
            # We don't yield this error as the exchange was successfully presented to the user.
        
        logger.info(f"----- Response Generated ({token_count} tokens) -----")
        yield {"type": "done"}

    def process_prompt(self, session_id: str, user_prompt: str, file_check: list = None, user_id: str = None, user_name: str = "User", stream: bool = False) -> Generator:
        file_check = file_check or []
        try:
            yield {"type": "status", "content": "Initializing Request via CLI..."}
            
            # Enforce 10k token limit buffer
            self.chat.enforce_token_limit(session_id, token_limit=14000)
            
            yield {"type": "status", "content": "Preparing Wrapper Context..."}
            
            (_, data_envelope, context_ids_for_db, attachments_for_db, user_content_for_db) = \
                self._prepare_prompt_data(session_id, user_prompt, file_check, user_id, user_name)
            
            yield {"type": "status", "content": "Thinking..."}
            
            generator = self._generate_stream_response(
                data_envelope, session_id, user_id, user_name, user_prompt, 
                attachments_for_db, context_ids_for_db, user_content_for_db
            )
            for item in generator: yield item

        except Exception as e:
            logger.error(f"Error in process_prompt: {e}")
            yield {"type": "token", "content": f"[System Error: {e}]"}

    # --- Proxy Methods ---
    def list_sessions(self) -> list:
        return self.chat.list_sessions()

    def manage_session_history(self, session_id: str, count: int = 0, index: int = -1) -> str:
        return self.chat.manage_session_history(session_id, count, index)

    def save_state_for_restart(self) -> bool:
        return self.chat.save_state_for_restart()
        
    def _load_state_on_restart(self) -> bool:
        return self.chat.load_state_on_restart()
    
    def trigger_instruction_refresh(self, full_restart: bool = False):
        return "Instructions Refreshed. CLI automatically handles local dir."

    def shutdown(self):
        logger.info("--- CLI Core shutting down. ---")
        if getattr(config, 'VOICE', False):
            orion_tts.stop_tts_thread()
        if getattr(config, 'VISION', False):
            orion_replay.stop_replay_watcher()
            orion_replay.stop_vision_thread()
            orion_replay.shutdown() 

    def execute_restart(self):
        """
        Executes the final step of the restart by shutting down gracefully
        and then replacing the current process.
        """
        logger.info("  - State saved. Performing graceful shutdown before restart...")
        self.shutdown() # <-- CRITICAL: Call the shutdown method here.
        logger.info("  - Shutdown complete. Executing process replacement...")
        os.execv(sys.executable, ['python'] + sys.argv)
