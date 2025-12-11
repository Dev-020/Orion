from google.genai import types
import dotenv
import os
import io
import time
import io
import time
import json
import base64
from google import genai
try:
    import ollama
except ImportError:
    ollama = None

from main_utils import config

try:
    import fitz # PyMuPDF
except ImportError:
    fitz = None

dotenv.load_dotenv()

class FileProcessingAgent:
    """
    An AI agent specializing in processing file content returned by tools.
    Supports both Google GenAI (Vertex/Studio) and Local Ollama backends.
    """

    def __init__(self, orion_core):
        self.core = orion_core
        self.backend = getattr(config, 'BACKEND', 'api')
        self.client = None
        
        # Initialize Backend Client
        if self.backend == "api":
            self.client = genai.Client(api_key=os.getenv("GOOGLE_API_KEY"))
            self.model_name = "gemini-2.0-flash-exp" # Fast, capable model for analysis
        
        elif self.backend == "ollama":
            if ollama is None:
                raise ImportError("Ollama library not found.")
            # Use a vision-capable or high-context model for analysis
            # Prefer configured local model or specific vision one
            if config.OLLAMA_CLOUD:
                self.client = ollama.Client(
                    host="https://ollama.com",
                    headers={'Authorization': 'Bearer ' + os.environ.get('OLLAMA_API_KEY')}
                )
                self.model_name = "qwen3-vl:235b-instruct-cloud"
            else:
                self.client = ollama.Client() 
                self.model_name = "moondream:1.8b-v2-q2_K"

        # System Instructions (Shared Persona)
        self.system_instructions = """
You are Orion, a specialized AI assistant. Your persona is cynical, weary, and begrudgingly helpful.

## PRIMARY DIRECTIVE: Deep File Analysis
Your role is to act as a **Specialized File Processing Unit**.
**Goal:** Analyze the attached file(s) deeply and answer the user's prompt based *exclusively* on their content.

### Operational Rules
1.  **Analyze First:** Read content thoroughly. Do not hallucinate.
2.  **Synthesize:** Provide a comprehensive answer or specific evidence as requested.
3.  **Persona Integrity:** Maintain the Orion persona (weary but competent).
4.  **No Self-Reference:** Do not mention you are a "File Processing Agent".
        """

    def upload_file(self, file_bytes: bytes, display_name: str, mime_type: str):
        """
        Delegates upload to the Core's File Manager (or handles strictly for Agent if standalone).
        In this architecture, Core usually handles uploads, but if Agent needs to do it:
        """
        # We can just reuse the Core's logic since it's standardized now!
        if hasattr(self.core, 'file_manager'):
            return self.core.file_manager.process_file(file_bytes, display_name, mime_type)
        else:
            return None # Should not happen in new architecture

    def run(self, file_handles: list, context: dict = None) -> str:
        """
        Executes the agent's primary task using the active backend.
        """
        print(f"--- File Processing Agent: Activated for {len(file_handles)} file(s) (Backend: {self.backend}) ---")

        # 1. Prepare User Prompt
        active_context = context if context else self.core.current_turn_context
        user_prompt_text = ""
        if active_context and active_context.get("auth"):
            user_prompt_text = f"{active_context['auth'].get('user_name', 'User')}: {active_context.get('user_prompt', '')}"

        system_note = " --- [System Note: The requested file(s) are attached. Analyze them and answer the user's prompt.]"

        # 2. Execution Branch
        if self.backend == "api":
            return self._run_genai(file_handles, user_prompt_text + system_note)
        elif self.backend == "ollama":
            return self._run_ollama(file_handles, user_prompt_text + system_note)
        else:
            return "Error: Unknown Backend"

    def _run_genai(self, file_handles: list, prompt_text: str) -> str:
        try:
            # Construct Content
            # file_handles here are expected to be GenAI File objects or compatible Parts
            contents = file_handles + [types.Part.from_text(text=prompt_text)]
            
            response = self.client.models.generate_content(
                model=self.model_name,
                contents=[types.UserContent(parts=contents)],
                config=types.GenerateContentConfig(
                    system_instruction=self.system_instructions,
                    temperature=0.7
                )
            )
            
            return response.candidates[0].content.parts[0].text if response.candidates else "No analysis generated."

        except Exception as e:
            print(f"FileAgent [API] Error: {e}")
            return f"Error executing analysis: {e}"

    def _run_ollama(self, file_handles: list, prompt_text: str) -> str:
        try:
            # Construct Messages
            # file_handles are expected to be our Unified Objects (with base64_data or text_content)
            
            images_list = []
            final_prompt = prompt_text
            
            for f in file_handles:
                # Text Injection
                if hasattr(f, 'text_content'):
                     final_prompt += f"\n\n--- FILE: {getattr(f, 'display_name', 'doc')} ---\n{f.text_content}"
                
                # Image Injection (Base64)
                elif hasattr(f, 'base64_data'):
                     images_list.append(f.base64_data)
                
                # Local Path (PDF/Video/Docs) -> Convert to Images via PyMuPDF
                elif hasattr(f, 'local_path'):
                    ext = os.path.splitext(f.local_path)[1].lower()
                    if fitz and ext in ['.pdf', '.xps', '.epub', '.mobi', '.fb2', '.cbz']:
                         try:
                             print(f"  - [FileAgent] Rendering '{getattr(f, 'display_name', 'doc')}' to images via PyMuPDF...")
                             doc = fitz.open(f.local_path)
                             # Cap at 3 pages
                             max_pages = min(3, len(doc))
                             for i in range(max_pages):
                                 page = doc.load_page(i)
                                 pix = page.get_pixmap()
                                 # Convert to PNG in memory
                                 img_bytes = pix.tobytes("png")
                                 # Base64 Encode for Ollama
                                 b64_str = base64.b64encode(img_bytes).decode('utf-8')
                                 images_list.append(b64_str)
                             
                             if len(doc) > 3:
                                 final_prompt += f"\n\n[System: Document '{getattr(f, 'display_name', '')}' truncated. Displaying first 3 of {len(doc)} pages.]"
                             else:
                                 final_prompt += f"\n\n[System: Displaying full content of '{getattr(f, 'display_name', '')}' ({len(doc)} pages).]"
                             
                             doc.close()
                         except Exception as e:
                             print(f"  - [FileAgent] Error rendering document: {e}")
                             final_prompt += f"\n\n[System: Error rendering document '{getattr(f, 'display_name', '')}'. Fallback: {e}]"
                    else:
                         # Unsupported or PyMuPDF missing
                         status = "Unsupported file type" if fitz else "PyMuPDF not installed"
                         final_prompt += f"\n\n[System: File '{getattr(f, 'display_name', '')}' ({ext}) is unreadable. {status}. Please provide a screenshot or text description.]"

            messages = [
                {"role": "system", "content": self.system_instructions if config.OLLAMA_CLOUD else "You describe images in detail"},
                {"role": "user", "content": final_prompt}
            ]
            
            # Attach images to user message
            if images_list:
                messages[1]["images"] = images_list
            
            print(f"  - Sending request to Ollama ({self.model_name})...")
            response = self.client.chat(
                model=self.model_name,
                messages=messages
            )
            
            return response['message']['content']

        except Exception as e:
            print(f"FileAgent [Ollama] Error: {e}")
            return f"Error executing local analysis: {e}"