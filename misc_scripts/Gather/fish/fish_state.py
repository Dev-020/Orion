# fish/fish_state.py
# Contains the BotState class, which is the "Data Hub" for all threads.

import threading
import config

class BotState:
    def __init__(self, monitor_object, game_hwnd):
        # --- Thread Safety ---
        self.lock = threading.Lock()
        
        # --- Bot Status ---
        self.running = True
        self.is_paused = False
        
        # --- Window Info ---
        self.monitor_object = monitor_object 
        self.hwnd = game_hwnd  # <-- MODIFIED: Storing the window handle (int)
        
        # --- FSM State ---
        self.current_state = config.STATE_IDLE # <-- MODIFIED: Start in IDLE state
        
        # --- Perception Data (What the "Eyes" see) ---
        self.exclamation_coords = None
        self.continue_coords = None
        
        # --- Action Data (What the "Hands" should do) ---
        self.cached_button_coords = None
        # --- NEW: For Arrow Direction ---
        # Can be "NONE", "LEFT", or "RIGHT"
        self.arrow_direction = "NONE"
        # --- NEW: Rod Swap State ---
        self.swap_step = "NONE"          # Can be "NONE", "PRESS_M", "CLICK_USE"
        self.swap_rod_coords = None      # Stores 'Use' button coords