# config.py
# This file contains all configuration variables for the bot.

# --- Game Window ---
WINDOW_TITLE = "Blue Protocol: Star Resonance"
MODEL_PATH = "best.pt" # <-- FIXED: Path is relative to the root 'gather/' folder
TRIGGER_IMAGE = 'trigger_prompt.png' # <-- FIXED: Path is relative to the root 'gather/' folder

# --- UI Interaction ---
ABS_PROMPT_SEARCH_REGION = (1288, 557, 299, 183) # (Absolute X, Absolute Y, Width, Height)
PYAUTOGUI_SCROLL_CLICKS = -100
GATHER_KEY = 'f'

# --- Navigation ---
FORWARD_DURATION = 0.1
MOUSE_TURN_SENSITIVITY = 0.5
SCANNING_TURN_PIXELS = 500
#STRAFE_DURATION = 0.05 # This was in your file, uncomment if needed by movement.py
DEAD_ZONE_RADIUS = 0.06   # 6% radius (e.g., 47%-53%)
SAFE_ZONE_RADIUS = 0.1    # 10% radius (e.g., 45%-55%)

# --- Stuck Detection ---
STUCK_DURATION_SECONDS = 5.0  # NEW: How many seconds of no progress before unstuck
UNSTUCK_STRAFE_DURATION = 0.4 # How long to strafe to get unstuck
SCAN_GRACE_PERIOD = 4         # NEW: How many frames to "coast" before switching to SCANNING

# --- Debug Colors (BGR format for OpenCV) ---
COLOR_YOLO_BOX = (255, 0, 0)        # Blue
COLOR_PROMPT_REGION = (0, 255, 255) # Yellow
COLOR_DEAD_ZONE = (0, 0, 255)       # Red (Obstacle Zone)
COLOR_SAFE_ZONE = (0, 255, 0)       # Green (Go-Forward Zone)

# --- NEW: Data Collection (Active Learning) ---
DATA_COLLECTION_MODE = False # Set to True to enable saving "unsure" images
DATA_COLLECTION_CONF_THRESHOLD = 0.8 # Save images where bot is < 70% confident
DATA_COLLECTION_PATH = "dataset/pending_review/" # Root folder to save new data
DATA_COLLECTION_COOLDOWN = 3.0 # NEW: Seconds to wait between saving images

# --- Misc ---
OVERLAY_VISIBILITY = True # Start with overlay visible or hidden