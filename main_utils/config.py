# c:/GitBash/Orion/main_utils/config.py

"""
Shared configuration variables for all function modules.
This module is initialized by orion_core.py at startup.
"""
import os

# --- DYNAMIC PATHS ---
# These are initialized by orion_core.py
DB_FILE = ""
CHROMA_DB_PATH = ""
COLLECTION_NAME = ""

# --- STATIC PATHS ---
# These are constant and can be used directly.
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUTPUT_DIR = os.path.join(PROJECT_ROOT, "instructions")

# --- GLOBAL VARIABLES ---
PERSONA = "default"
VOICE = True
VISION = False
ORION_CORE_INSTANCE = None
VERTEX = False
SAVE = False