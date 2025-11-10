# fish/config.py
# This file holds all our settings and constants

# --- File Paths ---
EXCLAMATION_TEMPLATE = 'fish/templates/exclamation.png'
CONTINUE_TEMPLATE = 'fish/templates/continue_button.png'

# --- Tuning ---
# Confidence for template matching (0.0 to 1.0)
# Lower this if it's not finding the images
CONFIDENCE_THRESHOLD = 0.8

# How long to wait after clicking "Continue" for the next cast
CAST_WAIT_TIME_SEC = 3.0

# --- FSM (Finite State Machine) States ---
STATE_WAITING = "WAITING"
STATE_REELING = "REELING"
STATE_CAUGHT = "CAUGHT"

# --- (Future-Proofing for Tension Bar) ---
# Placeholder for the tension bar region (left, top, width, height)
# You will need to tune this later.
TENSION_BAR_REGION = {'left': 800, 'top': 900, 'width': 320, 'height': 100}