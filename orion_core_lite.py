# orion_core_lite.py (Gemma/Lite Edition - Refactored)
import os
import json
import sqlite3
import pickle
from typing import Generator
from datetime import datetime, timezone
from dotenv import load_dotenv

# API Backends
from google import genai
from google.genai import types
try:
    import ollama
except ImportError:
    ollama = None 

from main_utils import config, main_functions as functions
from system_utils import orion_replay, orion_tts

# Define instruction files
INSTRUCTIONS_FILES = [
    'Primary_Directive_Lite.md' 
    #'master_manifest.json'
]

# --- Paths ---
INSTRUCTIONS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'instructions')

class OrionLiteCore:
    def __init__(self, model_name: str = config.AI_MODEL, persona: str = "default"):
        """
        Initializes the Lite version of Orion Core.
        Architecture mimics OrionCore (Pro) but optimized for Lite/Gemma models.
        """
        print(f"--- [Lite Core] Initializing for model: {model_name} (Backend: {config.BACKEND}) ---")
        self.model_name = model_name
        self.persona = config.PERSONA = persona
        self.backend = config.BACKEND.lower() # "api" or "ollama"
        self.local_model = config.LOCAL_MODEL
        
        # Initialize Database access
        functions.initialize_persona(self.persona)
        
        # Load Instructions
        self.current_instructions = self._read_all_instructions()
        if not self.current_instructions:
            self.current_instructions = "You are Orion, a helpful AI assistant."

        # Setup Client
        self._setup_client()

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

        # Session Management
        self.sessions = {}
        if not self._load_state_on_restart():
             self.sessions = {}
        
        config.ORION_CORE_INSTANCE = self
        print(f"--- [Lite Core] Online. Managing {len(self.sessions)} session(s). ---")

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
            print(f"--- [Lite Core] Using Local Ollama: {self.local_model} ---")
            self.client = ollama.Client() 

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
        if session_id not in self.sessions:
            self.sessions[session_id] = []
        return self.sessions[session_id]

    # --- Core Logic Split ---

    def _prepare_prompt_data(self, session_id: str, user_prompt: str, file_check: list, user_id: str, user_name: str) -> dict:
        """
        Gathers context, history, and constructs the messages payload.
        Returns a dict containing 'messages' and 'system_instruction'.
        """
        use_vdb = True # Enabled for both API and Ollama now that tokens are optimized
        max_history = 30 if self.backend == "ollama" else 10 # Increased from 4 -> 10 for API
        
        session_history = self._get_session(session_id)
        
        # 1. VDB Lookup
        vdb_context = ""
        if use_vdb:
            try:
                print(f"Checking Memory for session {session_id}...")
                
                # Query 1: Deep Memory (Conversation History) - Limit 3
                results_deep = functions.execute_vdb_read(query_texts=[user_prompt], n_results=3, where={"source_table": "deep_memory"})
                
                # Query 2: Long Term Memory (Facts/Events) - Limit 2
                results_ltm = functions.execute_vdb_read(query_texts=[user_prompt], n_results=2, where={"source_table": "long_term_memory"})
                
                combined_context = []
                vdb_ids = []

                # Helper to process results
                def process_vdb_results(results, name):
                    if results and "documents" in results and results["documents"]:
                        # Add content to LLM Context
                        combined_context.append(f"{name}: {results['documents']}")
                        
                        # Add IDs to Archival List
                        # Structure: results['metadatas'] is list of list of dicts
                        # We want source_table + source_id
                        if "metadatas" in results and results["metadatas"]:
                            for meta_list in results["metadatas"]:
                                for meta in meta_list:
                                    table = meta.get("source_table", "unknown")
                                    sid = meta.get("source_id", "unknown")
                                    vdb_ids.append(f"{table}_{sid}")

                process_vdb_results(results_deep, "Deep Memory (Conversations)")
                process_vdb_results(results_ltm, "Long Term Memory (Facts)")
                     
                if combined_context:
                    vdb_context = "Memory Context:\n" + "\n".join(combined_context)
                
                vdb_ids_json = json.dumps(vdb_ids)

            except Exception as e:
                print(f"VDB Error: {e}")

        # 2. System Instruction Content
        final_system_instruction = self.current_instructions
        if vdb_context:
            final_system_instruction += f"\n\n{vdb_context}"

        # ... (rest of function) ...
        
        # 3. Build Logical Message Sequence
        # ...

        # 4. Final Processing
        # ...

        return {
            "messages": final_messages, 
            "system_instruction": system_instruction_param,
            "session_history_ref": session_history,
            "vdb_string": vdb_context, # For prompt (handled internally)
            "vdb_ids_json": vdb_ids_json # For DB Archival
        }

        # 3. Build Logical Message Sequence
        # We construct a clean list of dicts first, then format for backend.
        logical_messages = []
        
        # A. System Turn
        # For API (Gemma), we use "user" role because "system" is not supported.
        # For Ollama, we utilize "system" role.
        sys_role = "system" if self.backend == "ollama" else "user"
        logical_messages.append({"role": sys_role, "content": final_system_instruction})

        # B. History (Truncated)
        effective_history = session_history
        if len(session_history) > max_history:
             effective_history = session_history[-max_history:]
        
        for turn in effective_history:
            # Normalize internal "model" to backend specific
            # Ollama: "assistant", GenAI: "model"
            # But here we stick to abstract "model" or "user" and map later? 
            # Let's map to standard "user"/"model" now, correcting for specific backend quirks later.
            r = "assistant" if (self.backend == "ollama" and turn["role"] == "model") else turn["role"]
            logical_messages.append({"role": r, "content": turn["content"]})
            
        # C. Current User Prompt
        logical_messages.append({"role": "user", "content": user_prompt})

        # 4. Final Processing & Formatting
        final_messages = []
        
        if self.backend == "ollama":
            # Ollama handles the list as-is
            final_messages = logical_messages
            system_instruction_param = None
            
        else: # Google GenAI API
            # GenAI enforces strict User-Model-User alternation.
            # We must collapse consecutive "user" messages (like System + First User).
            
            collapsed_messages = []
            if logical_messages:
                current_turn = logical_messages[0]
                
                for i in range(1, len(logical_messages)):
                    next_turn = logical_messages[i]
                    if current_turn["role"] == "user" and next_turn["role"] == "user":
                        # Merge content
                        current_turn["content"] += f"\n\n---\n\n{next_turn['content']}"
                    else:
                        collapsed_messages.append(current_turn)
                        current_turn = next_turn
                
                collapsed_messages.append(current_turn)
            
            # Convert to GenAI Content Objects
            for turn in collapsed_messages:
                final_messages.append(types.Content(role=turn["role"], parts=[types.Part.from_text(text=turn["content"])]))

            system_instruction_param = None # We embedded it

        return {
            "messages": final_messages, 
            "system_instruction": system_instruction_param,
            "session_history_ref": session_history,
            "vdb_string": vdb_context,
            "vdb_ids_json": vdb_ids_json
        }

    def _generate_stream_response(self, prompt_data: dict):
        """
        Handles the streaming generation call to the specific backend.
        Yields chunks ({"type": "token", "content": ...}).
        """
        messages = prompt_data["messages"]
        system_instruction = prompt_data["system_instruction"]
        
        full_text = ""
        token_count = 0
        
        try:
            if self.backend == "api":
                gen_config = types.GenerateContentConfig(
                    system_instruction=system_instruction, # likely None now
                    max_output_tokens=8192,
                    temperature=0.7
                )
                stream_resp = self.client.models.generate_content_stream(
                    model=self.model_name,
                    contents=messages,
                    config=gen_config
                )
                for chunk in stream_resp:
                     if chunk.candidates and chunk.candidates[0].content.parts:
                          text = chunk.candidates[0].content.parts[0].text
                          if text:
                              yield {"type": "token", "content": text}
                              full_text += text
                              if config.VOICE: orion_tts.process_stream_chunk(text)
                     if chunk.usage_metadata:
                          token_count = chunk.usage_metadata.total_token_count

            elif self.backend == "ollama":
                stream_resp = self.client.chat(
                    model=self.local_model,
                    messages=messages,
                    stream=True
                )
                for chunk in stream_resp:
                    content = chunk['message']['content']
                    if content:
                        yield {"type": "token", "content": content}
                        full_text += content
                        if config.VOICE: orion_tts.process_stream_chunk(content)
                token_count = 0 # Placeholder for Ollama

        except Exception as e:
            print(f"Generation Error: {e}")
            yield {"type": "token", "content": f"[Error: {e}]"}
            full_text = f"[Error: {e}]" # Ensure meaningful text for history

        if config.VOICE: orion_tts.flush_stream()
        
        # Internal Yield for process_prompt to capture
        yield {"type": "usage_internal", "token_count": token_count}
        
        # Return summary for finalization (legacy return, generator ignores this in loop)
        return {"full_text": full_text, "token_count": token_count}

    def _finalize_exchange(self, session_id: str, user_prompt: str, response_text: str, token_count: int, vdb_context: str, user_id: str, user_name: str):
        """
        Updates session history and performs archival tasks.
        """
        new_entry_user = {"role": "user", "content": user_prompt}
        new_entry_model = {"role": "model", "content": response_text}
        
        session = self._get_session(session_id)
        session.append(new_entry_user)
        session.append(new_entry_model)
        
        print(f"----- Exchange Finalized ({token_count} tokens) -----")
        
        # --- Archival ---
        # Lite Core = No Tools, No Attachments (Simplified)
        self._archive_exchange_to_db(session_id, user_id, user_name, user_prompt, response_text, token_count, vdb_context) 

    def _archive_exchange_to_db(self, session_id, user_id, user_name, prompt, response, token_count, vdb_context=""):
        """
        Writes the exchange to the database. Ported from OrionCore.
        """
        try:
             # Determine Model Source Name
             source_name = self.local_model if self.backend == "ollama" else self.model_name
             
             data_payload = {
                "session_id": session_id,
                "user_id": user_id,
                "user_name": user_name,
                "timestamp": int(datetime.now(timezone.utc).timestamp()),
                "prompt_text": prompt,
                "response_text": response,
                "attachments_metadata": "[]", # Empty for Lite
                "token": token_count,
                "function_calls": "[]", # Empty for Lite
                "vdb_context": vdb_context,
                "model_source": source_name 
            }
             
             print(f"  - [Lite] Archiving to deep_memory (Source: {source_name})...")
             result = functions.execute_write(table="deep_memory", operation="insert", user_id=user_id, data=data_payload)
             print(f"  - Result: {result}")
             
        except Exception as e:
            print(f"[Lite Archival Error] {e}")

    # --- Main Orchestrator ---

    def process_prompt(self, session_id: str, user_prompt: str, file_check: list, user_id: str, user_name: str, stream: bool = True) -> Generator:
        """
        Main entry point. Orchestrates the pipeline: Prepare -> Generate -> Finalize.
        """
        yield {"type": "status", "content": f"Processing ({self.backend})..."}
        
        # 1. Prepare
        # Capture vdb_context from prepare step?
        # Refactor: _prepare_prompt_data returns dict.
        prompt_data = self._prepare_prompt_data(session_id, user_prompt, file_check, user_id, user_name)
        vdb_ids_for_db = prompt_data.get("vdb_ids_json", "[]") # Use the IDs list for DB

        
        # 2. Generate (Stream)
        yield {"type": "status", "content": f"Thinking..."}
        
        generator = self._generate_stream_response(prompt_data)
        
        full_text = ""
        token_count = 0
        
        for chunk in generator:
            if chunk.get("type") == "usage_internal":
                token_count = chunk["token_count"]
                continue # Don't yield this to bot
                
            yield chunk 
            if chunk["type"] == "token":
                full_text += chunk["content"]
        
        # 3. Finalize
        self._finalize_exchange(session_id, user_prompt, full_text, token_count, vdb_ids_for_db, user_id, user_name)
        # Call Archival here (since finalize signature is limited or update it)
        self._archive_exchange_to_db(session_id, user_id, user_name, user_prompt, full_text, token_count, vdb_context_str)
        
        yield {
            "type": "usage",
            "token_count": token_count,
            "restart_pending": False
        }

    
    def _load_state_on_restart(self) -> bool:
        """Loads session state after a restart."""
        try:
            state_file = f"{config.DB_FILE}-x-restart_state.pkl"
            state_blob_file = f"{config.DB_FILE}-x-restart_state-1-excluded_ids_blob.bin" # Unused in Lite but clearing for hygiene
            
            if os.path.exists(state_file):
                print(f"--- Found restart state file: {state_file} ---")
                with open(state_file, 'rb') as f:
                    data = pickle.load(f)
                    self.sessions = data.get('sessions', {})
                    # Lite doesn't really have advanced state like excluded_ids, but we load sessions
                
                # Cleanup
                os.remove(state_file)
                if os.path.exists(state_blob_file): os.remove(state_blob_file)
                
                print(f"--- State restored. {len(self.sessions)} session(s) recovered. ---")
                return True
        except Exception as e:
            print(f"State Load Error: {e}")
        return False

    def save_state_for_restart(self) -> bool:
        """Saves current sessions to a pickle file."""
        try:
            state_file = f"{config.DB_FILE}-x-restart_state.pkl"
            print(f"--- Saving state to {state_file} ---")
            
            data = {
                'sessions': self.sessions,
            }
            
            with open(state_file, 'wb') as f:
                pickle.dump(data, f)
            return True
        except Exception as e:
            print(f"State Save Error: {e}")
            return False

    def execute_restart(self):
        """Restarts the bot process."""
        print("--- Executing Process Restart ---")
        import sys
        import subprocess
        # Similar logic to Pro core
        args = [sys.executable] + sys.argv
        print(f"Restarting with args: {args}")
        subprocess.Popen(args)
        os._exit(0)

    def trigger_instruction_refresh(self, full_restart=False):
        """Refreshes instructions (Soft) or triggers restart (Hard)."""
        if full_restart:
            if self.save_state_for_restart():
                self.execute_restart()
        else:
            print("--- Soft Refreshing Instructions (Lite) ---")
            # 1. Re-run manifest generator
            functions.rebuild_manifests()
            # 2. Re-read instructions
            self.current_instructions = self._read_all_instructions()
            print("--- Instructions Refreshed. ---")

    def shutdown(self):
        """Performs a clean shutdown."""
        print("--- Orion Lite Core shutting down. ---")
        if config.VOICE:
            orion_tts.stop_tts_thread()
        if config.VISION:
             orion_replay.shutdown_obs()
        print("--- Orion Lite is now offline. ---")
