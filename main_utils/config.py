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
BACKEND = "api" # "api" or "ollama"
LOCAL_MODEL = "gemma3:4b"  # Verified safe for hardware
LOCAL_CONTEXT_WINDOW = 4096 # Safe limit for 16GB RAM

# --- FILE CONFIGURATION ---
TEXT_FILE_EXTENSIONS = ('.json', '.xml', '.txt', '.py', '.md', '.log', '.yml', '.yaml', '.sh', '.bat', '.css', '.html', '.js')