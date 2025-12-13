# c:/GitBash/Orion/main_utils/config.py

"""
Shared configuration variables for all function modules.
This module is initialized by orion_core.py at startup.
"""
import os
from pathlib import Path

# --- DYNAMIC PATHS ---
# These are initialized by orion_core.py
DB_FILE = ""
CHROMA_DB_PATH = ""
COLLECTION_NAME = ""

# --- STATIC PATHS ---
# These are constant and can be used directly.
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
# New Data Directory
BACKEND_ROOT = PROJECT_ROOT / "backends"
OUTPUT_DIR = BACKEND_ROOT / "instructions"
# New Data Directory
BACKEND_ROOT = PROJECT_ROOT / "backends"
DATA_DIR = BACKEND_ROOT / "data"

# --- GLOBAL VARIABLES ---
PERSONA = "default"
VERTEX = False # VertexAI SDK / GenAI SDK
BACKEND = "ollama" # "api" or "ollama"

# --- UTIL VARIABLES ---
LOCAL_CONTEXT_WINDOW = 4096 * 4 # Context window for local models
PAST_MEMORY = False # Past Semantic Memory Support
SAVE = False # Disables saving TTS voice to local
EDIT_TIME = 1.5 # Frequency of editing discord messages in seconds
VOICE = False # TTS voice support
VISION = False # Vision support
BUFFER_SIZE = 30 # Number of messages to keep in buffer

# --- CORE CONFIGS ---
ORION_CORE_INSTANCE = None # Where the core instance is stored
THINKING_SUPPORT = True # Global flag: Auto-disables if model rejects 'think'
CONTEXT_CACHING = False # Master switch for Context Caching (Free Tier limit protection)
OLLAMA_CLOUD = True # Uses Ollama Cloud instead of local

# --- AI MODELS ---
LOCAL_MODEL = "deepseek-v3.1:671b-cloud" # Local model Ollama API
AI_MODEL = "gemini-2.5-flash" # AI model for Gemini API

# --- FILE CONFIGURATION ---
TEXT_FILE_EXTENSIONS = ('.json', '.xml', '.txt', '.py', '.md', '.log', '.yml', '.yaml', '.sh', '.bat', '.css', '.html', '.js')

"""
LIST OF LOCAL MODELS THAT RUN ON THE LAPTOP:
WITH PAST MEMORY SUPPORT
llama3.2:3b-instruct-q4_1
smallthinker:3b-preview-q4_K_M

NO PAST MEMORY SUPPORT
ibm/granite3.3:2b-instruct-q6_K
ibm/granite3.3:2b-instruct-q4_K_M
qwen3:1.7b-q8_0

Gemma Models:
models/gemma-3-27b-it
models/gemma-3-12b-it
models/gemma-3-4b-it
models/gemma-3-1b-it

Gemini Models:
gemini-2.5-flash

Ollama Cloud Models:
qwen3-vl:235b-instruct-cloud
deepseek-v3.1:671b-cloud
"""