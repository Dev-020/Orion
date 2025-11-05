# movement.py
# This is the "Body" thread.
# It is 100% silent and only performs actions based on the BotState.

import pydirectinput
import pyautogui
import time
from PyQt5.QtCore import QThread

# Use relative imports
from . import config
from .state import BotState

class MovementThread(QThread):
    """
    This thread's ONLY job is to act based on the bot_state.
    It is 100% SILENT and does not print.
    """
    def __init__(self, bot_state: BotState):
        super().__init__()
        self.bot_state = bot_state
        # --- [NEW] Internal Memory for TIME-BASED Stuck Detection ---
        self.last_target_area = 0.0
        self.stuck_start_time = None  # This is our new stopwatch
        self.is_walking = False # State flag to control the 'w' key

    def run(self):
        while self.bot_state.is_bot_running():
            # --- [NEW] Pause Check ---
            if self.bot_state.is_paused():
                # If we are paused, just sleep and check again
                time.sleep(0.5)
                continue # Skip the rest of the loop
            # --- [END NEW] ---
            
            try:
                # Get the latest orders from the "Brain"
                state, target_x, current_area = self.bot_state.get_state()
                window_region = self.bot_state.get_window_region()

                if not window_region:
                    if self.is_walking:
                        pydirectinput.keyUp('w')
                        self.is_walking = False
                    time.sleep(0.5)
                    continue

                win_x, win_y, screen_width, screen_height = window_region
                screen_center_x = screen_width / 2

                # --- State Machine for Action ---
                if state == "INTERACTING":
                    # (This block is unchanged)
                    if self.is_walking:
                        pydirectinput.keyUp('w')
                        self.is_walking = False
                    pyautogui.scroll(config.PYAUTOGUI_SCROLL_CLICKS)
                    time.sleep(0.3)
                    pyautogui.press(config.GATHER_KEY)
                    self.bot_state.set_state("BUSY_INTERACTING")

                elif state == "BUSY_INTERACTING":
                    # (This block is unchanged)
                    time.sleep(0.5) 
                
                elif state == "NAVIGATING":
                    # --- [NEW] Simplified "Dumb" Navigation ---
                    # The Body no longer thinks about being stuck. It just steers.
                    if not self.is_walking:
                        pydirectinput.keyDown('w')
                        self.is_walking = True

                    # Define zones
                    dead_zone_left = screen_center_x - (screen_width * config.DEAD_ZONE_RADIUS / 2)
                    dead_zone_right = screen_center_x + (screen_width * config.DEAD_ZONE_RADIUS / 2)
                    safe_zone_left = screen_center_x - (screen_width * config.SAFE_ZONE_RADIUS / 2)
                    safe_zone_right = screen_center_x + (screen_width * config.SAFE_ZONE_RADIUS / 2)
                    
                    if target_x < safe_zone_left:
                        # STATE 1: FAR LEFT - Steer camera right
                        pixel_distance = target_x - safe_zone_left
                        if pixel_distance < -900:
                            pixel_distance = -900
                        turn_amount = int(pixel_distance * config.MOUSE_TURN_SENSITIVITY)
                        pydirectinput.moveRel(turn_amount - 10, 0, relative=True)
                        time.sleep(abs(pixel_distance) / 1800)
                    
                    elif target_x > safe_zone_right:
                        # STATE 2: FAR RIGHT - Steer camera left
                        pixel_distance = target_x - safe_zone_right
                        if pixel_distance > 900:
                            pixel_distance = 900
                        turn_amount = int(pixel_distance * config.MOUSE_TURN_SENSITIVITY)
                        pydirectinput.moveRel(turn_amount + 10, 0, relative=True)
                        time.sleep(abs(pixel_distance) / 1800)
                    
                    elif target_x > dead_zone_left and target_x < dead_zone_right:
                        # STATE 3: DEAD ZONE (OBSCURED) - Nudge with camera
                        if target_x < screen_center_x:
                            pydirectinput.moveRel(int(config.MOUSE_TURN_SENSITIVITY * 20), 0, relative=True)
                        else:
                            pydirectinput.moveRel(int(-config.MOUSE_TURN_SENSITIVITY * 20), 0, relative=True)
                    
                    else:
                        # STATE 4 & 5: SAFE ZONES - Target is ALIGNED.
                        pass # Continue holding 'W'
                    # --- [END NEW] ---
                
                elif state == "STUCK":
                    # --- [NEW] Dedicated Unstuck State ---
                    # The Brain has determined we are stuck.
                    if self.is_walking:
                        pydirectinput.keyUp('w')
                        self.is_walking = False
                    
                    # Execute your directional strafe logic
                    if target_x < screen_center_x:
                        pydirectinput.keyDown('d') # Your fix
                        time.sleep(config.UNSTUCK_STRAFE_DURATION)
                        pydirectinput.keyUp('d')
                    else:
                        pydirectinput.keyDown('a') # Your fix
                        time.sleep(config.UNSTUCK_STRAFE_DURATION)
                        pydirectinput.keyUp('a')
                    
                    # Wait for the Brain to give a new order
                    time.sleep(1.0) 
                    # --- [END NEW] ---

                elif state == "SCANNING":
                    if self.is_walking:
                        pydirectinput.keyUp('w')
                        self.is_walking = False
                    
                    pydirectinput.moveRel(config.SCANNING_TURN_PIXELS, 0, relative=True) 
                    time.sleep(1) # Your value
                
                # (End-of-loop sleep removed as requested)

            except Exception as e:
                print(f"\n--- MOVEMENT THREAD ERROR: {e} ---")
                pydirectinput.keyUp('w') # Failsafe
                self.is_walking = False
                time.sleep(1)