# fish/config.py
# This file holds all our settings and constants

import numpy as np

# --- File Paths ---
EXCLAMATION_TEMPLATE = 'fish/templates/exclamation1.png'
CONTINUE_TEMPLATE = 'fish/templates/continue_button.png'
RECAST_PROMPT_TEMPLATE = 'fish/templates/b_prompt.png' # <-- NEW
LEFT_ARROW_TEMPLATE = 'fish/templates/left_arrow.png'   # <-- NEW
RIGHT_ARROW_TEMPLATE = 'fish/templates/right_arrow.png' # <-- NEW
ROD_PROMPT_TEMPLATE = 'fish/templates/fishing_rod_prompt.png' # <-- NEW
ROD_USE_TEMPLATE = 'fish/templates/fishing_rod_use.png'     # <-- NEW

# --- NEW: HSV Color Mask for Orange/Yellow ---
# These values will need tuning.
# Hue(0-179), Saturation(0-255), Value(0-255)
ORANGE_LOWER = np.array([10, 190, 150])
ORANGE_UPPER = np.array([30, 255, 255])

# --- Tuning ---
# Confidence for template matching (0.0 to 1.0)
# Lower this if it's not finding the images
EXCLAMATION_THRESHOLD = 0.7
CONTINUE_THRESHOLD = 0.99
RECAST_THRESHOLD = 0.95 # This is still correct, we need it
ARROW_MATCH_THRESHOLD = 0.65 # <-- NEW: Threshold for matching the arrow *shape*
ROD_PROMPT_THRESHOLD = 0.95   # <-- NEW: For the "+ [M]" prompt (needs to be high)
ROD_USE_THRESHOLD = 0.97      # <-- NEW: For the "Use" button

# How long to wait after clicking "Continue" for the next cast
CAST_WAIT_TIME_SEC = 2.0

# --- FSM (Finite State Machine) States ---
STATE_IDLE = "STATE_IDLE"          # <-- NEW: Not fishing, "B" prompt is visible
STATE_CASTING = "STATE_CASTING"    # <-- NEW: Rod is in the water, waiting for "!"
STATE_REELING = "STATE_REELING"
STATE_CAUGHT = "STATE_CAUGHT"
STATE_SWAP_ROD = "STATE_SWAP_ROD"  # <-- NEW: In the rod swap menu

# --- (Future-Proofing for Tension Bar) ---
# Placeholder for the tension bar region (left, top, width, height)
# You will need to tune this later.
TENSION_BAR_REGION = {'left': 800, 'top': 900, 'width': 320, 'height': 100}