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
PROJECT_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = PROJECT_ROOT / "instructions"

# --- GLOBAL VARIABLES ---
PERSONA = "default"
VOICE = True
VISION = False
ORION_CORE_INSTANCE = None
VERTEX = False
SAVE = False
EDIT_TIME = 1.5
AI_MODEL = "gemma-3-27b-it"
BACKEND = "ollama" # "api" or "ollama"
LOCAL_MODEL = "qwen3:1.7b-q8_0"  # Faster, stable, no 'thinking' overhead
LOCAL_CONTEXT_WINDOW = 4096 * 4
THINKING_SUPPORT = True # Global flag: Auto-disables if model rejects 'think'
PAST_MEMORY = False

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
"""