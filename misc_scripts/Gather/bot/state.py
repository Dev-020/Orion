# state.py
# This file contains the thread-safe class for communication.

import threading
from . import config

# --- NEW: Thread-Safe Bot State Class ---co
# This class acts as the "whiteboard" between the Brain and the Body
class BotState:
    def __init__(self):
        self.state = "SCANNING"  # Initial state
        self.target_x = 0
        self.target_area = 0.0
        self.window_region = None # (win_x, win_y, win_w, win_h)
        self.is_running = True
        self._is_paused = False # NEW
        self.lock = threading.Lock() # The "talking stick"
        self.debug_frame = None
        self._overlay_visible = config.OVERLAY_VISIBILITY # NEW

    def set_state(self, new_state, target_x=0, target_area=0.0):
        """Thread-safe method to update the bot's state."""
        with self.lock:
            # Check if running, otherwise this could cause issues on shutdown
            if self.is_running:
                self.state = new_state
                self.target_x = target_x
                self.target_area = target_area

    def get_state(self):
        """Thread-safe method to read the bot's state."""
        with self.lock:
            return self.state, self.target_x, self.target_area

    def set_window_region(self, region):
        with self.lock:
            self.window_region = region
            
    def get_window_region(self):
        with self.lock:
            return self.window_region
            
    def set_debug_frame(self, frame):
        with self.lock:
            self.debug_frame = frame

    def get_debug_frame(self):
        with self.lock:
            return self.debug_frame

    def stop(self):
        with self.lock:
            self.is_running = False

    def is_bot_running(self):
        with self.lock:
            return self.is_running
    
    def toggle_pause(self):
        """Thread-safe method to pause or resume the bot."""
        with self.lock:
            self._is_paused = not self._is_paused
            return self._is_paused

    def is_paused(self):
        """Thread-safe method to check if paused."""
        with self.lock:
            return self._is_paused
        
    def set_overlay_visible(self, is_visible: bool):
        with self.lock:
            self._overlay_visible = is_visible
            
    def is_overlay_visible(self):
        with self.lock:
            return self._overlay_visible