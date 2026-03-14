import os
import sys
import json
import logging
import subprocess
import uuid
import time
from typing import Generator, Dict, Optional
from datetime import datetime, timezone

from google.genai import types

from main_utils import config, main_functions as functions
from main_utils.chat_object import ChatObject
from main_utils.file_manager import UploadFile
from system_utils import orion_replay, orion_tts

logger = logging.getLogger(__name__)

# --- Paths ---
INSTRUCTIONS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'instructions')
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GEMINI_MD_PATH = os.path.join(PROJECT_ROOT, 'GEMINI.md')

INSTRUCTIONS_FILES = [
    'Primary_Directive.md', 
    'master_manifest.json'
]


class OrionCoreGeminiCLI:
    def __init__(self, model_name: str = config.AI_MODEL, persona: str = "default"):
        """
        Initializes the Gemini CLI "Thin Wrapper" version of Orion Core.
        Delegates chat history, tool execution, and persona to the Gemini CLI natively.
        """
        logger.info(f"--- [CLI Core] Initializing Gemini CLI Thin Wrapper ---")
        
        self.restart_pending = False
        config.ORION_CORE_INSTANCE = self

        self.current_turn_context = None
        self.model_name = model_name
        self.persona = config.PERSONA = persona
        self.backend = "cli"
        
        # Tools: CLI handles them natively
        self.tools = []
        self.tool_map = {}

        # Initialize Database access
        functions.initialize_persona(self.persona)
        
        # --- CLI Path Resolution (cached once) ---
        self.cli_js_path = self._resolve_cli_path()
        
        # --- CLI Session ID Mapping ---
        # Maps Orion session IDs (from frontend/server) to Gemini CLI session IDs
        self.cli_sessions: Dict[str, str] = {}

        # --- Generate GEMINI.md from Primary Directive ---
        self._generate_gemini_md()
        
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
        
        logger.info(f"--- [CLI Core] Online. Thin Wrapper ready. CLI: {self.cli_js_path} ---")

    # =========================================================================
    # INITIALIZATION HELPERS
    # =========================================================================

    def _resolve_cli_path(self) -> str:
        """Resolves the Gemini CLI entry point path once at startup."""
        try:
            npm_root = subprocess.check_output(
                ['npm', 'root', '-g'], 
                shell=True if sys.platform == 'win32' else False
            ).decode().strip()
            cli_path = os.path.join(npm_root, '@google', 'gemini-cli', 'dist', 'index.js')
            if os.path.exists(cli_path):
                logger.info(f"--- [CLI Core] Resolved CLI path: {cli_path} ---")
                return cli_path
        except Exception as e:
            logger.warning(f"Failed to resolve CLI via npm root: {e}")
        
        # Fallback: assume 'gemini' is in PATH
        logger.warning("--- [CLI Core] Falling back to 'gemini' command ---")
        return "gemini"

    def _generate_gemini_md(self):
        """
        Reads all instruction files and writes a processed GEMINI.md to the project root.
        The Gemini CLI auto-loads this file as persistent system context.
        """
        prompt_parts = []
        for filename in INSTRUCTIONS_FILES:
            filepath = os.path.join(INSTRUCTIONS_DIR, filename)
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    prompt_parts.append(f.read())
            except FileNotFoundError:
                logger.warning(f"Instruction file not found, skipping: {filepath}")

        if not prompt_parts:
            logger.error("--- [CLI Core] No instruction files found! GEMINI.md will be empty. ---")
            return

        # Process content for CLI compatibility
        content = "\n\n---\n\n".join(prompt_parts)
        
        try:
            with open(GEMINI_MD_PATH, 'w', encoding='utf-8') as f:
                f.write(content)
            logger.info(f"--- [CLI Core] Generated GEMINI.md at {GEMINI_MD_PATH} ---")
        except Exception as e:
            logger.error(f"--- [CLI Core] Failed to write GEMINI.md: {e} ---")

    # =========================================================================
    # CALLBACKS
    # =========================================================================

    def _vision_file_handler(self, file_path: str):
        """Callback for vision system."""
        try:
             with open(file_path, 'rb') as f:
                self.vision_attachments = {"video_bytes": f.read(), "display_name": os.path.basename(file_path)}
             logger.debug(f"[Vision] Captured {self.vision_attachments['display_name']}")
        except Exception as e:
            logger.error(f"[Vision Error] {e}")

    # =========================================================================
    # PROMPT PREPARATION (Simplified — CLI handles history & persona)
    # =========================================================================

    def _get_session(self, session_id: str) -> list:
        return self.chat.get_session(session_id)

    def _format_vdb_results_for_context(self, raw_json: str, source_name: str) -> str:
        try:
            data = json.loads(raw_json)
            if not data.get('documents') or not data['documents'][0]:
                return ""
            output_lines = [f"--- Context from {source_name} ---"]
            for doc in data['documents'][0]:
                 output_lines.append(f"- {doc}")
            return "\n".join(output_lines)
        except:
            return ""

    def _prepare_prompt_data(self, session_id: str, user_prompt: str, file_check: list, user_id: str, user_name: str):
        """
        Builds the data envelope with VDB context, user metadata, and prompt.
        History and persona are handled by the CLI via --resume and GEMINI.md.
        """
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
                
                formatted_vdb_context = f"{formatted_deep_mem}\n{formatted_ltm}".strip()
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

        vdb_response = f'[Relevant Context:\n{formatted_vdb_context}]' if formatted_vdb_context else ""

        # --- Build Data Envelope ---
        data_envelope = {
            "system_notifications": [],
            "user_prompt": user_prompt,
            "vdb_context": vdb_response,
            "auth": {
                "user_id": user_id,
                "user_name": user_name,
                "session_id": session_id
            },
            "timestamp_utc": datetime.now(timezone.utc).isoformat()
        }

        if config.VISION and self.vision_attachments:
             data_envelope["system_notifications"].append(f"[Vision: Attached {self.vision_attachments['display_name']}]")
             self.vision_attachments = {}

        # --- File Handling ---
        # Files are passed directly to the CLI — no pre-processing needed.
        file_paths_for_cli = []
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

                 # Pass file paths directly to CLI
                 local_path = getattr(f, 'local_path', None)
                 if local_path and os.path.exists(local_path):
                     file_paths_for_cli.append(local_path)
                 elif hasattr(f, 'text_content') and f.text_content:
                     # For text-extracted files, inject content into the prompt
                     header = f"\n\n--- FILE: {f.display_name} ---\n"
                     if getattr(f, 'is_analysis', False):
                         header = f"\n\n--- FILE ANALYSIS: {f.display_name} ({f.mime_type}) ---\n[System: The following is an AI analysis of the file.]\n"
                     data_envelope["user_prompt"] += f"{header}{f.text_content}"

        # Store for DB archival
        user_content_for_db = types.UserContent(parts=[types.Part.from_text(text=json.dumps(data_envelope, indent=2))])

        return (data_envelope, context_ids_for_db, attachments_for_db, user_content_for_db, file_paths_for_cli)

    # =========================================================================
    # GENERATION (Thin Wrapper — spawn CLI with --resume)
    # =========================================================================

    def _generate_stream_response(self, data_envelope, session_id, user_id, user_name, user_prompt, attachments_for_db, context_ids_for_db, user_content_for_db, file_paths_for_cli):
        """Spawns CLI with --resume and streams JSONL output back to the frontend."""
        logger.info(f"----- Sending Prompt to Gemini CLI (Thin Wrapper) . . . -----")
        
        full_response_text = ""
        token_count = 0
        new_tool_turns = []
        temp_file_path = None

        try:
            # 1. Write data envelope to JSON temp file
            temp_filename = f"orion_prompt_{uuid.uuid4().hex[:8]}.json"
            with open(temp_filename, "w", encoding="utf-8") as f:
                json.dump(data_envelope, f, indent=2, ensure_ascii=False)
            temp_file_path = temp_filename
            
            # 2. Build CLI command
            cmd_parts = [f'node "{self.cli_js_path}"']
            
            # Resume existing CLI session if we have a mapping
            cli_session_id = self.cli_sessions.get(session_id)
            if cli_session_id:
                cmd_parts.append(f'--resume {cli_session_id}')
            
            cmd_parts.append(f'--prompt "@{temp_filename}"')
            cmd_parts.append('-o stream-json')
            cmd_parts.append('--yolo')
            
            # Append file references directly
            for fpath in file_paths_for_cli:
                cmd_parts.append(f'"@{fpath}"')

            cmd_str = ' '.join(cmd_parts)
            logger.info(f"--- [CLI Core] Executing: {cmd_str}")

            # 3. Spawn subprocess
            cli_process = subprocess.Popen(
                cmd_str,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding='utf-8',
                bufsize=1,
                shell=True,
                cwd=PROJECT_ROOT  # Run from project root so GEMINI.md is found
            )

            # 4. Stream JSONL output
            for line in iter(cli_process.stdout.readline, ''):
                if not line.strip():
                    continue
                
                logger.debug(f"[CLI RAW] {line.strip()}")
                
                try:
                    data = json.loads(line)
                    msg_type = data.get("type")
                    
                    if msg_type == "init":
                        # Capture CLI session ID for future --resume calls
                        new_cli_session_id = data.get("session_id")
                        if new_cli_session_id:
                            self.cli_sessions[session_id] = new_cli_session_id
                            logger.info(f"[CLI Core] Session mapped: {session_id} -> {new_cli_session_id}")
                    
                    elif msg_type == "message" and data.get("role") == "assistant":
                        content = data.get("content", "")
                        if content:
                            yield {"type": "token", "content": content}
                            full_response_text += content
                            if getattr(config, 'VOICE', False):
                                orion_tts.process_stream_chunk(content)
                                
                    elif msg_type == "tool_use":
                        tool_name = data.get("tool_name", "unknown")
                        logger.info(f"[CLI Core] Tool Called: {tool_name}")
                        yield {"type": "status", "content": f"Running tool: {tool_name}"}
                        
                    elif msg_type == "tool_result":
                        tool_name = data.get("tool_id", "unknown")
                        output = data.get("output", "")
                        logger.info(f"[CLI Core] Tool Result: {tool_name}")
                        new_tool_turns.append({
                            "name": tool_name,
                            "args": {},
                            "result": str(output)
                        })
                        yield {"type": "status", "content": f"Tool result parsed"}
                        
                    elif msg_type == "result":
                        # Extract token usage if available
                        usage = data.get("usage", {})
                        if usage:
                            token_count = usage.get("total_tokens", 0)
                        logger.info(f"[CLI Core] Generation complete.")
                        break
                        
                except json.JSONDecodeError as jde:
                    if "{" in line:
                        logger.debug(f"[CLI JSON Error] {jde} on line: {line.strip()}")
            
            if not full_response_text:
                logger.warning("[CLI Core] No content received from CLI process.")
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

        if getattr(config, 'VOICE', False):
            orion_tts.flush_stream()
        
        # Fallback token estimate if CLI didn't provide usage
        if token_count == 0:
            token_count = len(full_response_text) // 3

        # --- Archive Exchange ---
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
        
        logger.info(f"----- Response Generated ({token_count} tokens) -----")
        yield {"type": "usage", "token_count": token_count, "restart_pending": self.restart_pending}

    # =========================================================================
    # PUBLIC API (matches interface expected by server.py)
    # =========================================================================

    def process_prompt(self, session_id: str, user_prompt: str, file_check: list = None, user_id: str = None, user_name: str = "User", stream: bool = False) -> Generator:
        file_check = file_check or []
        try:
            yield {"type": "status", "content": "Initializing Request via CLI..."}
            
            # Enforce token limit buffer
            self.chat.enforce_token_limit(session_id, token_limit=14000)
            
            yield {"type": "status", "content": "Preparing Context..."}
            
            (data_envelope, context_ids_for_db, attachments_for_db, user_content_for_db, file_paths_for_cli) = \
                self._prepare_prompt_data(session_id, user_prompt, file_check, user_id, user_name)
            
            yield {"type": "status", "content": "Thinking..."}
            
            generator = self._generate_stream_response(
                data_envelope, session_id, user_id, user_name, user_prompt, 
                attachments_for_db, context_ids_for_db, user_content_for_db, file_paths_for_cli
            )
            for item in generator:
                yield item

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
        # Re-generate GEMINI.md from latest instruction files
        self._generate_gemini_md()
        return "GEMINI.md regenerated. CLI will auto-load on next prompt."

    def shutdown(self):
        logger.info("--- CLI Core shutting down. ---")
        if getattr(config, 'VOICE', False):
            orion_tts.stop_tts_thread()
        if getattr(config, 'VISION', False):
            orion_replay.stop_replay_watcher()
            orion_replay.stop_vision_thread()
            orion_replay.shutdown() 

    def execute_restart(self):
        """Graceful shutdown + process replacement."""
        logger.info("  - State saved. Performing graceful shutdown before restart...")
        self.shutdown()
        logger.info("  - Shutdown complete. Executing process replacement...")
        os.execv(sys.executable, ['python'] + sys.argv)
