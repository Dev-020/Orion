# vision.py
# This is the "Brain" thread.
# It watches the screen, analyzes with YOLO, and updates the BotState.

import pyautogui
import numpy as np
import cv2
import time
from ultralytics import YOLO # type: ignore
from PIL import Image

# Import PyQt5 for the signal and image conversion
from PyQt5.QtCore import QThread, pyqtSignal
from PyQt5.QtGui import QPixmap, QImage

# Use relative imports to get our custom modules
from . import config
from .state import BotState
from .utils import capture_game_window, check_and_save_for_review

class VisionThread(QThread):
    """
    The "Brain" thread.
    - Emits 'update_debug_frame_signal' with a QPixmap for the GUI.
    - Updates the 'bot_state' with its findings.
    - Handles all console printing.
    """
    # This signal will send the transparent debug image to the GUI
    update_debug_frame_signal = pyqtSignal(QImage, str)

    def __init__(self, bot_state: BotState, model: YOLO):
        super().__init__()
        self.bot_state = bot_state
        self.model = model
        self.global_status = "" # For printing clean status updates
        
        # --- NEW: Memory for Stuck & Grace Period ---
        self.last_target_area = 0.0
        self.stuck_start_time = None
        self.scan_grace_counter = 0 # Our new "jitter" counter
        self.last_known_target_x = 0 # Remembers where the ore was
        self.last_known_target_area = 0.0
        
        # --- [NEW] For FPS Calculation ---
        self.current_fps = 0.0
        self.fps_buffer = []
        
        # --- [NEW] For Data Collection Cooldown ---
        self.last_data_save_time = 0.0
        
        print("Vision thread initialized.")

    def run(self):
        """This thread's ONLY job is to look, analyze, and update the bot_state."""
        
        while self.bot_state.is_bot_running():
            # --- [NEW] Pause Check ---
            if self.bot_state.is_paused():
                # If we are paused, just sleep and check again
                time.sleep(0.5)
                continue # Skip the rest of the loop
            # --- [END NEW] ---
            
            # --- [NEW] Start FPS timer ---
            start_time = time.monotonic()
            
            try:
                # --- 1. CAPTURE & PREPARE ---
                window_region, screenshot = capture_game_window(config.WINDOW_TITLE)
                self.bot_state.set_window_region(window_region) # Share window info
                
                if not window_region or not screenshot:
                    self.global_status = "--- STATE: PAUSED (Game not active) ---"
                    print(self.global_status, end="\r", flush=True)
                    
                    # --- [FIXED] Replace deep sleep with a busy-wait ---
                    # This keeps the Python interpreter active enough to
                    # receive shutdown signals from other threads.
                    pause_start_time = time.monotonic()
                    while (time.monotonic() - pause_start_time) < 1.0:
                        # We must check for stop/pause signals *inside* the wait
                        if not self.bot_state.is_bot_running():
                            raise KeyboardInterrupt # Break out to stop the thread
                        if self.bot_state.is_paused():
                            time.sleep(0.1) # It's okay to sleep if paused
                        else:
                            time.sleep(0.01) # Short, active wait
                    # --- [END FIXED] ---
                    
                    continue

                frame_np = np.array(screenshot)
                debug_overlay = np.zeros((window_region[3], window_region[2], 4), dtype=np.uint8)
                
                win_x, win_y, screen_width, screen_height = window_region
                screen_center_x = screen_width / 2
                
                dead_zone_left = screen_center_x - (screen_width * config.DEAD_ZONE_RADIUS / 2)
                dead_zone_right = screen_center_x + (screen_width * config.DEAD_ZONE_RADIUS / 2)
                safe_zone_left = screen_center_x - (screen_width * config.SAFE_ZONE_RADIUS / 2)
                safe_zone_right = screen_center_x + (screen_width * config.SAFE_ZONE_RADIUS / 2)
                
                abs_pr = config.ABS_PROMPT_SEARCH_REGION
                rel_pr_x = abs_pr[0] - win_x
                rel_pr_y = abs_pr[1] - win_y
                rel_pr_w = abs_pr[2]
                rel_pr_h = abs_pr[3]
                rel_prompt_search_region = (rel_pr_x, rel_pr_y, rel_pr_w, rel_pr_h)

                # --- Draw Debug Rectangles (on the transparent overlay) ---
                cv2.rectangle(debug_overlay, (int(safe_zone_left), 0), (int(safe_zone_right), screen_height), (config.COLOR_SAFE_ZONE[0], config.COLOR_SAFE_ZONE[1], config.COLOR_SAFE_ZONE[2], 255), 2)
                cv2.rectangle(debug_overlay, (int(dead_zone_left), 0), (int(dead_zone_right), screen_height), (config.COLOR_DEAD_ZONE[0], config.COLOR_DEAD_ZONE[1], config.COLOR_DEAD_ZONE[2], 255), 2)
                pr = rel_prompt_search_region
                cv2.rectangle(debug_overlay, (pr[0], pr[1]), (pr[0] + pr[2], pr[1] + pr[3]), (config.COLOR_PROMPT_REGION[0], config.COLOR_PROMPT_REGION[1], config.COLOR_PROMPT_REGION[2], 255), 2)
                
                # --- 2. INTERACTION CHECK ---
                try:
                    interaction_prompt = pyautogui.locate(
                        config.TRIGGER_IMAGE, 
                        screenshot, 
                        confidence=0.8, 
                        grayscale=True,
                        region=rel_prompt_search_region 
                    )
                    
                    
                    if interaction_prompt:
                        current_state, _, _ = self.bot_state.get_state()
                        
                        if current_state not in ["INTERACTING", "BUSY_INTERACTING"]:
                            self.global_status = "--- STATE: INTERACTING ---\nPrompt detected. Telling Body to act..."
                            self.bot_state.set_state("INTERACTING")
                        else:
                            self.global_status = "--- STATE: BUSY_INTERACTING ---\n(Gathering in progress...)"
                        
                        # Reset memory when we start gathering
                        self.last_target_area = 0.0
                        self.stuck_start_time = None
                        self.scan_grace_counter = 0

                    else:
                        raise pyautogui.ImageNotFoundException # Jump to AI navigation

                except pyautogui.ImageNotFoundException:
                    # --- 3. AI NAVIGATION ---
                    print("Analyzing screenshot...", flush=True)
                    results = self.model(
                        screenshot, 
                        verbose=False,
                        imgsz=320
                    )
                    print("Screenshot Analyzed ! ! !", flush=True)
                    if results and len(results[0].obb.xywhr) > 0:
                        # --- [NEW] We found an ore! Reset the grace counter ---
                        print("Found Ore !!!!", flush=True)
                        
                        self.scan_grace_counter = 0
                        
                        all_targets = results[0].obb.xywhr
                        best_target = min(all_targets, key=lambda t: abs(t[0].item() - screen_center_x))
                        
                        target_x_center = best_target[0].item()
                        current_w = best_target[2].item()
                        current_h = best_target[3].item()
                        current_area = current_w * current_h

                        # --- [NEW] Store the "last known" good data ---
                        self.last_known_target_x = target_x_center
                        self.last_known_target_area = current_area

                        print("Checking Data Collection...", flush=True)
                        # --- [NEW DATA COLLECTION LOGIC] ---
                        current_time = time.monotonic()
                        if config.DATA_COLLECTION_MODE and (current_time - self.last_data_save_time) > config.DATA_COLLECTION_COOLDOWN:
                            
                            # Call the new function (no longer needs screen_center_x)
                            save_status = check_and_save_for_review(results, screenshot)
                            
                            if save_status: # Will return a string like "saved: generated_baru_ore_1"
                                print(f"\n--- [Data Collection] Saved low-confidence frame: {save_status} ---")
                                self.last_data_save_time = current_time # Reset cooldown
                        # --- [END NEW LOGIC] ---
                        
                        print("Processing Target and Stuck Detection...", flush=True)
                        # --- Stuck Detection Logic (now in the Brain) ---
                        if current_area > (self.last_target_area * 1.01) or self.last_target_area == 0.0:
                            self.stuck_start_time = None # Not stuck
                            self.global_status = f"--- STATE: NAVIGATING ---\nTarget locked at x: {target_x_center:.0f}. (Progress: {current_area:.0f})"
                            self.bot_state.set_state("NAVIGATING", target_x=target_x_center, target_area=current_area)
                        else:
                            # --- STUCK (or no progress) ---
                            if self.stuck_start_time is None:
                                self.stuck_start_time = time.monotonic()
                                self.global_status = f"--- STATE: NAVIGATING ---\nTarget locked. Checking for stuck... (Timer Started)"
                                self.bot_state.set_state("NAVIGATING", target_x=target_x_center, target_area=current_area)
                            
                            elif (time.monotonic() - self.stuck_start_time) > config.STUCK_DURATION_SECONDS:
                                self.global_status = f"--- STATE: STUCK ---\nStuck for {config.STUCK_DURATION_SECONDS}s. Telling Body to unstuck..."
                                self.bot_state.set_state("STUCK", target_x=target_x_center)
                                self.stuck_start_time = None # Reset stopwatch
                            
                            else:
                                stuck_time = time.monotonic() - self.stuck_start_time
                                self.global_status = f"--- STATE: NAVIGATING ---\nTarget locked. No progress... (Stuck for {stuck_time:.1f}s)"
                                self.bot_state.set_state("NAVIGATING", target_x=target_x_center, target_area=current_area)
                        
                        self.last_target_area = current_area
                        # --- [END Stuck Logic] ---

                        for obb in results[0].obb.xyxyxyxy:
                            points = obb.cpu().numpy().astype(int)
                            cv2.polylines(debug_overlay, [points], True, (config.COLOR_YOLO_BOX[0], config.COLOR_YOLO_BOX[1], config.COLOR_YOLO_BOX[2], 255), 2)
                    
                    else:
                        # --- 4. NO ORE FOUND ---
                        
                        # --- [NEW] Grace Period Logic ---
                        # Check if we *just* lost the target
                        current_state, _, _ = self.bot_state.get_state()
                        
                        if current_state in ["NAVIGATING", "STUCK"] and self.scan_grace_counter < config.SCAN_GRACE_PERIOD:
                            # --- GRACE PERIOD ACTIVE ---
                            # We lie to the Body and tell it to keep navigating
                            # to the *last known position* of the ore.
                            self.scan_grace_counter += 1
                            self.global_status = f"--- STATE: NAVIGATING ---\nTarget lost! Re-acquiring... (Grace: {self.scan_grace_counter}/{config.SCAN_GRACE_PERIOD})"
                            
                            # Tell Body to use the "remembered" data
                            self.bot_state.set_state("NAVIGATING", 
                                                     target_x=self.last_known_target_x, 
                                                     target_area=self.last_known_target_area)
                        
                        else:
                            # --- GRACE PERIOD OVER (or we were already scanning) ---
                            self.global_status = "--- STATE: SCANNING ---\nNo ore found in view. Scanning..."
                            self.bot_state.set_state("SCANNING")
                            # Reset all memory
                            self.last_target_area = 0.0
                            self.stuck_start_time = None
                            self.scan_grace_counter = 0
                        # --- [END NEW GRACE PERIOD LOGIC] ---

                # --- 5. FINALIZE FRAME & EMIT SIGNAL ---
                
                # --- [FIX 2] ---
                # We REMOVE the `if self.bot_state.is_overlay_visible():` check.
                # The Vision thread's job is to report, not to decide
                # if the GUI is visible. It should *always* emit.
                
                h, w, c = debug_overlay.shape
                bytes_per_line = c * w
                
                # Create the thread-safe QImage
                q_image = QImage(debug_overlay.data, w, h, bytes_per_line, QImage.Format_ARGB32)
                
                # --- [FIX 3] ---
                # We DO NOT create a QPixmap here.
                
                # Calculate FPS (this logic is fine)
                end_time = time.monotonic()
                loop_time = end_time - start_time
                if loop_time > 0:
                    current_loop_fps = 1.0 / loop_time
                    self.fps_buffer.append(current_loop_fps)
                    if len(self.fps_buffer) > 10:
                        self.fps_buffer.pop(0)
                    self.current_fps = np.mean(self.fps_buffer)
                
                # Create status text
                status_text = f"FPS: {self.current_fps:.1f}\n{self.global_status}"
                
                # Emit the QImage and the text
                self.update_debug_frame_signal.emit(q_image, status_text)
                
                # --- [FIX] ---
                # Add a 1ms Qt-aware sleep. This yields control back
                # to the Qt event loop, preventing this thread from
                # starving the main loop and causing a deadlock.
                self.msleep(1)
                # --- [END FIX] ---

                # --- [FIX 4] ---
                # REMOVE the print statement! This is the cause of the deadlock.
                # print(status_text, "        ", end="\r", flush=True) # <-- DELETE THIS LINE

            except Exception as e:
                print(f"\n--- VISION THREAD ERROR: {e} ---")
                time.sleep(1)