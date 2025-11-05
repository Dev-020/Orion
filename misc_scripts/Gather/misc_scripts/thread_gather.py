# full_gatherer_v13_threaded.py

import pyautogui
import pydirectinput
import time
import random
import numpy as np
import cv2
from PIL import Image
import win32gui
from ultralytics import YOLO # type: ignore
import threading
import sys

# --- Configuration (Copied from your script) ---
# --- Game Window ---
WINDOW_TITLE = "Blue Protocol: Star Resonance"
MODEL_PATH = "best.pt"

# --- UI Interaction ---
TRIGGER_IMAGE = 'trigger_prompt.png'
ABS_PROMPT_SEARCH_REGION = (1288, 557, 299, 183) # (Absolute X, Absolute Y, Width, Height)
PYAUTOGUI_SCROLL_CLICKS = -100
GATHER_KEY = 'f'

# --- Navigation (Copied from your script) ---
FORWARD_DURATION = 0.1
MOUSE_TURN_SENSITIVITY = 0.7
SCANNING_TURN_PIXELS = 100
#STRAFE_DURATION = 0.05
DEAD_ZONE_RADIUS = 0.06
SAFE_ZONE_RADIUS = 0.1
STUCK_THRESHOLD = 120
UNSTUCK_STRAFE_DURATION = 0.4

# --- Debug Colors (BGR format for OpenCV) ---
COLOR_YOLO_BOX = (255, 0, 0)        # Blue
COLOR_PROMPT_REGION = (0, 255, 255) # Yellow
COLOR_DEAD_ZONE = (0, 0, 255)       # Red (Obstacle Zone)
COLOR_SAFE_ZONE = (0, 255, 0)       # Green (Go-Forward Zone)


# --- NEW: Thread-Safe Bot State Class ---
# This class acts as the "whiteboard" between the Brain and the Body
class BotState:
    def __init__(self):
        self.state = "SCANNING"  # Initial state
        self.target_x = 0
        self.target_area = 0.0
        self.window_region = None # (win_x, win_y, win_w, win_h)
        self.is_running = True
        self.lock = threading.Lock() # The "talking stick"
        self.debug_frame = None

    def set_state(self, new_state, target_x=0, target_area=0.0):
        """Thread-safe method to update the bot's state."""
        with self.lock:
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

# --- Helper Function (Unchanged) ---
def capture_game_window(window_title):
    try:
        hwnd = win32gui.FindWindow(None, window_title)
        if not hwnd:
            print("Error: Window not found. Is game running?", end="\r", flush=True)
            return None, None
        
        active_hwnd = win32gui.GetForegroundWindow()
        if hwnd != active_hwnd:
            print("Game window is not active. Bot is PAUSED...", end="\r", flush=True)
            return None, None 

        client_rect = win32gui.GetClientRect(hwnd)
        client_width = client_rect[2] - client_rect[0]
        client_height = client_rect[3] - client_rect[1]
        
        screen_x, screen_y = win32gui.ClientToScreen(hwnd, (client_rect[0], client_rect[1]))
        region = (screen_x, screen_y, client_width, client_height)
        
        if client_width <= 0 or client_height <= 0:
            print("Error: Window is minimized or has invalid size.", end="\r", flush=True)
            return None, None
            
        screenshot = pyautogui.screenshot(region=region)
        return region, screenshot
        
    except Exception as e:
        if 'pywintypes.error' in str(e): 
            print("Error: Window handle became invalid (game closed?).", end="\r", flush=True)
            return None, None
        print(f"Error capturing window: {e}", end="\r", flush=True)
        return None, None

# --- [NEW] Thread 1: The "Brain" (Vision & Logging) ---
def vision_thread(bot_state, model):
    """
    This thread's ONLY job is to look, analyze, and update the bot_state.
    It is the ONLY thread allowed to print status updates.
    """
    global_status = "" # To hold the latest status for printing
    
    while bot_state.is_bot_running():
        try:
            # --- 1. CAPTURE & PREPARE ---
            window_region, screenshot = capture_game_window(WINDOW_TITLE)
            bot_state.set_window_region(window_region) # Share window info
            
            if not window_region or not screenshot:
                global_status = "--- STATE: PAUSED (Game not active) ---"
                print(global_status, end="\r", flush=True)
                time.sleep(1.0)
                continue

            frame_np = np.array(screenshot)
            debug_frame = cv2.cvtColor(frame_np, cv2.COLOR_RGB2BGR)
                
            win_x, win_y, screen_width, screen_height = window_region
            screen_center_x = screen_width / 2
            
            dead_zone_left = screen_center_x - (screen_width * DEAD_ZONE_RADIUS / 2)
            dead_zone_right = screen_center_x + (screen_width * DEAD_ZONE_RADIUS / 2)
            safe_zone_left = screen_center_x - (screen_width * SAFE_ZONE_RADIUS / 2)
            safe_zone_right = screen_center_x + (screen_width * SAFE_ZONE_RADIUS / 2)
            
            abs_pr = ABS_PROMPT_SEARCH_REGION
            rel_pr_x = abs_pr[0] - win_x
            rel_pr_y = abs_pr[1] - win_y
            rel_pr_w = abs_pr[2]
            rel_pr_h = abs_pr[3]
            rel_prompt_search_region = (rel_pr_x, rel_pr_y, rel_pr_w, rel_pr_h)

            # --- Draw Debug Rectangles ---
            cv2.rectangle(debug_frame, (int(safe_zone_left), 0), (int(safe_zone_right), screen_height), COLOR_SAFE_ZONE, 2)
            cv2.rectangle(debug_frame, (int(dead_zone_left), 0), (int(dead_zone_right), screen_height), COLOR_DEAD_ZONE, 2)
            pr = rel_prompt_search_region
            cv2.rectangle(debug_frame, (pr[0], pr[1]), (pr[0] + pr[2], pr[1] + pr[3]), COLOR_PROMPT_REGION, 2)
            
            # --- 2. INTERACTION CHECK ---
            try:
                interaction_prompt = pyautogui.locate(
                    TRIGGER_IMAGE, 
                    screenshot, 
                    confidence=0.8, 
                    grayscale=True,
                    region=rel_prompt_search_region 
                )
                
                if interaction_prompt:
                    # --- [NEW] Handshake Logic ---
                    # Check the state *before* setting it
                    current_state, _, _ = bot_state.get_state()
                    
                    if current_state not in ["INTERACTING", "BUSY_INTERACTING"]:
                        # Only trigger an interaction if we're not already in one
                        global_status = "--- STATE: INTERACTING ---\nPrompt detected. Telling Body to act..."
                        bot_state.set_state("INTERACTING")
                    else:
                        # The Body is already busy, so the Brain just reports
                        global_status = "--- STATE: BUSY_INTERACTING ---\n(Gathering in progress...)"
                    # --- [END NEW] ---
                else:
                    raise pyautogui.ImageNotFoundException # Jump to AI navigation

            except pyautogui.ImageNotFoundException:
                # --- 3. AI NAVIGATION ---
                global_status = "--- STATE: SEARCHING/NAVIGATING ---"
                results = model(screenshot, verbose=False)
                
                if results and len(results[0].obb.xywhr) > 0:
                    all_targets = results[0].obb.xywhr
                    best_target = min(all_targets, key=lambda t: abs(t[0].item() - screen_center_x))
                    
                    target_x_center = best_target[0].item()
                    current_w = best_target[2].item()
                    current_h = best_target[3].item()
                    current_area = current_w * current_h

                    global_status += f"\nTarget locked at x: {target_x_center:.0f}. (Center: {screen_center_x:.0f})"
                    bot_state.set_state("NAVIGATING", target_x=target_x_center, target_area=current_area)

                    for obb in results[0].obb.xyxyxyxy:
                        points = obb.cpu().numpy().astype(int)
                        cv2.polylines(debug_frame, [points], True, COLOR_YOLO_BOX, 2)
                
                else:
                    # --- 4. SCANNING ---
                    global_status = "--- STATE: SCANNING ---\nNo ore found in view. Scanning..."
                    bot_state.set_state("SCANNING")

            # --- 5. FINALIZE FRAME & PRINT ---
            cv2.imwrite("debug_output.jpg", debug_frame)
            bot_state.set_debug_frame(debug_frame) # Store frame for Body if needed

            # Clear console (optional, can be noisy)
            # os.system('cls' if os.name == 'nt' else 'clear') 
            print(global_status, "        ", end="\r", flush=True) # Overwrite last line
            
            time.sleep(0.005) # Brain runs at ~20 FPS

        except Exception as e:
            print(f"\n--- VISION THREAD ERROR: {e} ---")
            time.sleep(1)


# --- [NEW] Thread 2: The "Body" (Movement & Actions) ---
def movement_thread(bot_state):
    """
    This thread's ONLY job is to act based on the bot_state.
    It is 100% SILENT and does not print.
    """
    # --- Internal Memory for Stuck Detection ---
    last_target_area = 0.0
    stuck_counter = 0
    is_walking = False # State flag to control the 'w' key

    while bot_state.is_bot_running():
        try:
            # Get the latest orders from the "Brain"
            state, target_x, current_area = bot_state.get_state()
            window_region = bot_state.get_window_region()

            if not window_region:
                # If window isn't active, make sure we stop walking
                if is_walking:
                    pydirectinput.keyUp('w')
                    is_walking = False
                time.sleep(0.5)
                continue

            # Get window dimensions
            win_x, win_y, screen_width, screen_height = window_region
            screen_center_x = screen_width / 2

            # --- State Machine for Action ---
            if state == "INTERACTING":
                # --- [NEW] This state is now *only* the trigger ---
                # Stop all movement
                if is_walking:
                    pydirectinput.keyUp('w')
                    is_walking = False

                # Perform the *instant* actions
                pyautogui.scroll(PYAUTOGUI_SCROLL_CLICKS)
                time.sleep(0.3)
                pyautogui.press(GATHER_KEY)
                
                # Reset stuck memory for the next node
                last_target_area = 0.0
                stuck_counter = 0
                
                # --- [NEW] Handshake: Tell Brain we are busy ---
                bot_state.set_state("BUSY_INTERACTING")

            elif state == "BUSY_INTERACTING":
                # --- [NEW] This is our 5-second "wait for animation" state ---
                # The Brain sees this state and will not send new "INTERACTING" signals
                time.sleep(0.5) # Your 1-second gather time
                
                # We are done, set state back to SCANNING
                #bot_state.set_state("SCANNING")
            
            elif state == "NAVIGATING":
                # --- This is the new "Move-and-Steer" logic ---
                
                # 1. Start walking if we aren't already
                if not is_walking:
                    pydirectinput.keyDown('w')
                    is_walking = True

                # 2. Check if we are stuck *before* we do anything else
                if not (current_area > (last_target_area * 1.01) or last_target_area == 0.0):
                    # --- STUCK! We are NOT moving closer ---
                    stuck_counter += 1
                    
                    if stuck_counter >= STUCK_THRESHOLD:
                        # Stop walking to perform maneuver
                        if is_walking:
                            pydirectinput.keyUp('w')
                            is_walking = False
                            
                        # Execute YOUR proposed unstuck logic
                        if target_x < screen_center_x:
                            pydirectinput.keyDown('a')
                            time.sleep(UNSTUCK_STRAFE_DURATION)
                            pydirectinput.keyUp('a')
                        else:
                            pydirectinput.keyDown('d')
                            time.sleep(UNSTUCK_STRAFE_DURATION)
                            pydirectinput.keyUp('d')

                        # Reset memory after maneuver
                        stuck_counter = 0
                        last_target_area = 0.0
                        time.sleep(1.0) # Pause to let brain rescan
                else:
                    # --- NOT STUCK: Proceed with alignment ---
                    stuck_counter = 0 # Reset stuck counter

                    # Define zones based on the *current* screen state
                    dead_zone_left = screen_center_x - (screen_width * DEAD_ZONE_RADIUS / 2)
                    dead_zone_right = screen_center_x + (screen_width * DEAD_ZONE_RADIUS / 2)
                    safe_zone_left = screen_center_x - (screen_width * SAFE_ZONE_RADIUS / 2)
                    safe_zone_right = screen_center_x + (screen_width * SAFE_ZONE_RADIUS / 2)

                    if target_x < safe_zone_left:
                        # STATE 1: FAR LEFT - Steer camera right
                        pixel_distance = target_x - safe_zone_left
                        turn_amount = int(pixel_distance * MOUSE_TURN_SENSITIVITY)
                        pydirectinput.moveRel(turn_amount - 10, 0, relative=True)
                    
                    elif target_x > safe_zone_right:
                        # STATE 2: FAR RIGHT - Steer camera left
                        pixel_distance = target_x - safe_zone_right
                        turn_amount = int(pixel_distance * MOUSE_TURN_SENSITIVITY)
                        pydirectinput.moveRel(turn_amount + 10, 0, relative=True)
                    
                    elif target_x > dead_zone_left and target_x < dead_zone_right:
                        # STATE 3: DEAD ZONE (OBSCURED) - Nudge with camera (your new proposal)
                        if target_x < screen_center_x:
                            # Target is just left of center, nudge camera RIGHT
                            pydirectinput.moveRel(int(MOUSE_TURN_SENSITIVITY * 20), 0, relative=True)
                        else:
                            # Target is just right of center, nudge camera LEFT
                            pydirectinput.moveRel(int(-MOUSE_TURN_SENSITIVITY * 20), 0, relative=True)
                    
                    else:
                        # STATE 4 & 5: SAFE ZONES - Target is ALIGNED.
                        # We are already holding 'W', so we just "coast"
                        # and let the "Glance-and-Move" handle the final approach if we want.
                        # For now, we just keep walking.
                        
                        # (You can re-add your "Glance-and-Move" here if you find
                        # the bot overshoots, but a continuous 'W' hold
                        # with steering should be much smoother)
                        pass # Continue holding 'W'
                
                # Update memory for the next loop
                last_target_area = current_area
            
            elif state == "SCANNING":
                # Stop all movement
                if is_walking:
                    pydirectinput.keyUp('w')
                    is_walking = False
                
                # Scan
                pydirectinput.moveRel(SCANNING_TURN_PIXELS, 0, relative=True) 
                time.sleep(0.03) # Your value
                
                # Reset stuck memory
                last_target_area = 0.0
                stuck_counter = 0

            # Short pause for the Body thread
            time.sleep(0.01) 

        except Exception as e:
            # We must print here, otherwise the thread fails silently
            print(f"\n--- MOVEMENT THREAD ERROR: {e} ---")
            # Failsafe key release
            pydirectinput.keyUp('w')
            is_walking = False
            time.sleep(1)

# --- [NEW] Main Function to Start Threads ---
def main():
    print("Loading AI model...")
    model = YOLO(MODEL_PATH)
    print("Model loaded successfully.")
    
    # Create the shared state object
    bot_state = BotState()

    print("Starting Vision (Brain) and Movement (Body) threads...")
    # Create the threads
    brain = threading.Thread(target=vision_thread, args=(bot_state, model), daemon=True)
    body = threading.Thread(target=movement_thread, args=(bot_state,), daemon=True)

    # Start the threads
    brain.start()
    body.start()

    print("Starting full gathering bot...")
    print("Switch to your game. Script is now active!")
    print("--- PRESS 'Ctrl+C' IN THIS TERMINAL TO STOP THE SCRIPT ---")

    try:
        # Keep the main thread alive to listen for Ctrl+C
        while True:
            time.sleep(1)
            # We can also save the debug image here to avoid file-write conflicts
            debug_frame = bot_state.get_debug_frame()
            if debug_frame is not None:
                cv2.imwrite("debug_output.jpg", debug_frame)

    except KeyboardInterrupt:
        print("\n--- 'Ctrl+C' detected. Stopping bot... ---")
        bot_state.stop() # Signal threads to stop
        brain.join() # Wait for brain thread to finish
        body.join() # Wait for body thread to finish
        print("Threads stopped.")
    
    finally:
        # Failsafe: Make sure all keys are released on exit
        pydirectinput.keyUp('w')
        pydirectinput.keyUp('a')
        pydirectinput.keyUp('s')
        pydirectinput.keyUp('d')
        print("All keys released. Script terminated.")


if __name__ == "__main__":
    main()