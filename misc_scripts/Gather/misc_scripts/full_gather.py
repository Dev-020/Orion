# full_gatherer_v12_smart_targeting

import pyautogui
import pydirectinput
import time
import random
import numpy as np
import cv2
from PIL import Image
import win32gui
from ultralytics import YOLO # type: ignore

# --- Configuration (UPDATE THESE!) ---
# --- Game Window ---
WINDOW_TITLE = "Blue Protocol: Star Resonance"
MODEL_PATH = "best.pt"

# --- UI Interaction ---
TRIGGER_IMAGE = 'trigger_prompt.png'
ABS_PROMPT_SEARCH_REGION = (1288, 557, 299, 183) # (Absolute X, Absolute Y, Width, Height)
PYAUTOGUI_SCROLL_CLICKS = -100
GATHER_KEY = 'f'

# --- Navigation (TUNE THESE!) ---
FORWARD_DURATION = 0.6  # Your value
MOUSE_TURN_SENSITIVITY = 1  # Your value
SCANNING_TURN_PIXELS = 300  # Your value
STRAFE_DURATION = 0.1     # NEW: How long to tap 'A' or 'D' to strafe

# --- NEW: Navigation Zone Configuration ---
# These zones replace the old "dead_zone" and "target_pct"
# We define zones as percentages from the center (0.0 = center, 0.5 = edge)
# E.g., 0.1 = 10% of the screen's half-width
DEAD_ZONE_RADIUS = 0.1   # 10% radius (e.g., 45%-55%). This is the "Obscured" zone.
SAFE_ZONE_RADIUS = 0.3   # 30% radius (e.g., 35%-65%). This is the "Go Forward" zone.
# Anything outside the SAFE_ZONE (e.g., <35% or >65%) is the "Far Zone" for mouse-turning.

# --- Debug Colors (BGR format for OpenCV) ---
COLOR_YOLO_BOX = (255, 0, 0)        # Blue
COLOR_PROMPT_REGION = (0, 255, 255) # Yellow
COLOR_DEAD_ZONE = (0, 0, 255)       # Red (Obstacle Zone)
COLOR_SAFE_ZONE = (0, 255, 0)       # Green (Go-Forward Zone)

# --- Helper Function to Find and Screenshot the Game Window ---
def capture_game_window(window_title):
    try:
        # 1. Get the handle for the game window
        hwnd = win32gui.FindWindow(None, window_title)
        if not hwnd:
            print("Error: Window not found. Is game running?", end="\r", flush=True)
            return None, None
        
        # --- NEW: Active Window Check ---
        # 2. Get the handle for the currently active (foreground) window
        active_hwnd = win32gui.GetForegroundWindow()
        
        # 3. Compare them. If the game is not the active window, stop.
        if hwnd != active_hwnd:
            print("Game window is not active. Bot is PAUSED...", end="\r", flush=True)
            return None, None # Fail the capture
        # --- [END NEW] ---

        # 4. If we get here, the game IS active. Proceed as normal.
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
        if 'pywintypes.error' in str(e): # Handle if window closes unexpectedly
            print("Error: Window handle became invalid (game closed?).", end="\r", flush=True)
            return None, None
        print(f"Error capturing window: {e}", end="\r", flush=True)
        return None, None

# --- Main Script ---
def main():
    print("Loading AI model...")
    model = YOLO(MODEL_PATH)
    print("Model loaded successfully.")
    
    print("Starting full gathering bot...")
    print("Switch to your game. Script begins in 5 seconds.")
    for i in range(5, 0, -1):
        print(f"{i}...", end="", flush=True)
        time.sleep(1)
    print("\nScript is now active!")
    print("--- PRESS 'Ctrl+C' IN THE TERMINAL TO STOP THE SCRIPT ---")
    print("--- The bot's vision will be saved to 'debug_output.jpg' ---")

    pyautogui.FAILSAFE = True
    
    # --- NEW: Stuck Detection Memory & Config ---
    last_target_area = 0.0  # Stores the bounding box area from the last frame
    stuck_counter = 0     # Counts consecutive frames we've been stuck
    STUCK_THRESHOLD = 5   # How many stuck frames before we take action
    UNSTUCK_STRAFE_DURATION = 0.5 # How long to strafe to get unstuck
    # --- [END NEW] ---
    
    try:
        while True:
            # --- 1. CAPTURE & PREPARE ---
            window_region, screenshot = capture_game_window(WINDOW_TITLE)
            
            if not window_region or not screenshot:
                print("Game window not found. Retrying...")
                time.sleep(2)
                continue

            frame_np = np.array(screenshot)
            debug_frame = cv2.cvtColor(frame_np, cv2.COLOR_RGB2BGR)
                
            win_x, win_y, screen_width, screen_height = window_region
            
            screen_center_x = screen_width / 2
            
            # --- [NEW] Define pixel boundaries for our zones ---
            dead_zone_left = screen_center_x - (screen_width * DEAD_ZONE_RADIUS / 2)
            dead_zone_right = screen_center_x + (screen_width * DEAD_ZONE_RADIUS / 2)
            
            safe_zone_left = screen_center_x - (screen_width * SAFE_ZONE_RADIUS / 2)
            safe_zone_right = screen_center_x + (screen_width * SAFE_ZONE_RADIUS / 2)
            
            # --- Convert Absolute Prompt Region to Relative Prompt Region ---
            abs_pr = ABS_PROMPT_SEARCH_REGION
            rel_pr_x = abs_pr[0] - win_x
            rel_pr_y = abs_pr[1] - win_y
            rel_pr_w = abs_pr[2]
            rel_pr_h = abs_pr[3]
            rel_prompt_search_region = (rel_pr_x, rel_pr_y, rel_pr_w, rel_pr_h)

            # --- Draw Debug Rectangles (using RELATIVE coordinates) ---
            # Draw Safe Zone (Green)
            cv2.rectangle(debug_frame, (int(safe_zone_left), 0), (int(safe_zone_right), screen_height), COLOR_SAFE_ZONE, 2)
            # Draw Dead Zone (Red) - drawn *inside* the safe zone
            cv2.rectangle(debug_frame, (int(dead_zone_left), 0), (int(dead_zone_right), screen_height), COLOR_DEAD_ZONE, 2)
            # Draw Prompt Search Region
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
                    print("--- STATE: INTERACTING ---")
                    print("Prompt detected. Scrolling down to select default...")
                    pyautogui.scroll(PYAUTOGUI_SCROLL_CLICKS)
                    time.sleep(0.3) 
                    
                    pyautogui.press(GATHER_KEY)
                    print("Gathering complete. Resuming search...")
                    time.sleep(4.0) 
                    continue 

            except pyautogui.ImageNotFoundException:
                pass # Not at a node, continue to navigation

            # --- 3. AI NAVIGATION ---
            print("--- STATE: SEARCHING/NAVIGATING ---")
            results = model(screenshot, verbose=False)
            
            if results and len(results[0].obb.xywhr) > 0:
                
                # --- [FIXED] Target Selection Logic ---
                all_targets = results[0].obb.xywhr
                best_target = min(all_targets, key=lambda t: abs(t[0].item() - screen_center_x))
                target_x_center = best_target[0].item()
                # --- [END FIXED] ---
                
                print(f"Target locked at x: {target_x_center:.0f}. (Center: {screen_center_x:.0f})")

                for obb in results[0].obb.xyxyxyxy:
                    points = obb.cpu().numpy().astype(int)
                    cv2.polylines(debug_frame, [points], True, COLOR_YOLO_BOX, 2)

                # --- [NEW] Strafe-to-Align 5-State Logic ---
                if target_x_center < safe_zone_left:
                    # STATE 1: FAR LEFT - Turn camera right
                    pixel_distance = target_x_center - safe_zone_left
                    turn_amount = int(pixel_distance * MOUSE_TURN_SENSITIVITY)
                    print(f"  Target FAR LEFT. Turning RIGHT by {turn_amount} pixels")
                    pydirectinput.moveRel(turn_amount - 10, 0, relative=True)
                    
                    # After turning, move forward slightly to adjust position
                    pydirectinput.keyDown('w')
                    time.sleep(FORWARD_DURATION)
                    pydirectinput.keyUp('w')
                
                elif target_x_center > safe_zone_right:
                    # STATE 2: FAR RIGHT - Turn camera left
                    pixel_distance = target_x_center - safe_zone_right
                    turn_amount = int(pixel_distance * MOUSE_TURN_SENSITIVITY)
                    print(f"  Target FAR RIGHT. Turning LEFT by {turn_amount} pixels")
                    pydirectinput.moveRel(turn_amount + 10, 0, relative=True)
                
                    # After turning, move forward slightly to adjust position
                    pydirectinput.keyDown('w')
                    time.sleep(FORWARD_DURATION)
                    pydirectinput.keyUp('w')
                    
                elif target_x_center > dead_zone_left and target_x_center < dead_zone_right:
                    # STATE 3: DEAD ZONE (OBSCURED) - Strafe to unblock
                    if target_x_center < screen_center_x:
                        # Target is just left of center, strafe RIGHT to push it left
                        print("  Target OBSCURED. Strafing RIGHT...")
                        pydirectinput.keyDown('d')
                        time.sleep(STRAFE_DURATION)
                        pydirectinput.keyUp('d')
                    else:
                        # Target is just right of center, strafe LEFT to push it right
                        print("  Target OBSCURED. Strafing LEFT...")
                        pydirectinput.keyDown('a')
                        time.sleep(STRAFE_DURATION)
                        pydirectinput.keyUp('a')
                
                else:
                    # STATE 4 & 5: SAFE ZONES - Target is ALIGNED.
                    # --- NEW: Stuck Detection Logic ---
                    
                    # 1. Get the width and height of the ore from the 'best_target'
                    #    In 'xywhr', w is index 2 and h is index 3
                    current_w = best_target[2].item()
                    current_h = best_target[3].item()
                    current_area = current_w * current_h

                    # 2. Check for progress (e.g., area grew by at least 1%)
                    #    (and handle first-time detection where last_target_area is 0.0)
                    if current_area > (last_target_area * 1.01) or last_target_area == 0.0:
                        # --- We are moving closer successfully! ---
                        if last_target_area != 0.0:
                            print(f"  Progress DETECTED. Area: {current_area:.0f} > {last_target_area:.0f}")
                        else:
                            print("  Target acquired. Initializing area check...")
                        stuck_counter = 0 # Reset stuck counter
                        
                        # --- Execute your "Glance-and-Move" logic as normal ---
                        print("  Target is ALIGNED. Executing glance-and-move...")
                        glance_amount = int((target_x_center - screen_center_x) * 1.1)
                        revert_amount = -glance_amount

                        print(f"    Glancing center by {glance_amount}px")
                        pydirectinput.moveRel(glance_amount, 0, relative=True)
                        time.sleep(0.05) 

                        pydirectinput.keyDown('w')
                        time.sleep(FORWARD_DURATION)
                        pydirectinput.keyUp('w')
                        
                        print(f"    Reverting camera by {revert_amount}px")
                        pydirectinput.moveRel(revert_amount, 0, relative=True)
                        # --- End of Glance-and-Move ---

                    else:
                        # --- STUCK! We are NOT moving closer ---
                        stuck_counter += 1
                        print(f"  STUCK! No progress. Area: {current_area:.0f} <= {last_target_area:.0f}. Count: {stuck_counter}")

                        # 3. Check if we have been stuck for too long
                        if stuck_counter >= STUCK_THRESHOLD:
                            print(f"  STUCK LIMIT REACHED! Performing unstuck maneuver...")
                            
                            # --- Execute YOUR proposed unstuck logic ---
                            if target_x_center < screen_center_x:
                                # Ore is on the left, strafe left to "slide"
                                print("    Unstuck: Strafing LEFT...")
                                pydirectinput.keyDown('a')
                                time.sleep(UNSTUCK_STRAFE_DURATION)
                                pydirectinput.keyUp('a')
                            else:
                                # Ore is on the right, strafe right
                                print("    Unstuck: Strafing RIGHT...")
                                pydirectinput.keyDown('d')
                                time.sleep(UNSTUCK_STRAFE_DURATION)
                                pydirectinput.keyUp('d')

                            # Reset memory after maneuver
                            stuck_counter = 0
                            last_target_area = 0.0
                            time.sleep(1.0) # Pause to let the bot rescan from its new position
                        
                    # 4. Update memory for the next loop
                    last_target_area = current_area
                
                # --- [END NEW LOGIC] ---

            else:
                # --- Scan with simple mouse movement ---
                print("No ore found in view. Scanning...")
                pydirectinput.moveRel(SCANNING_TURN_PIXELS, 0, relative=True) 
                #time.sleep(1.0) 
                
                # --- NEW: Reset stuck memory ---
                print("  (Resetting stuck detection memory)")
                last_target_area = 0.0
                stuck_counter = 0

            # --- 4. SAVE THE DEBUG FRAME ---
            cv2.imwrite("debug_output.jpg", debug_frame)
            
            time.sleep(0.1)


    except KeyboardInterrupt:
        print("\nScript stopped by user.")
    
    finally:
        cv2.destroyAllWindows()
        print("Debug windows closed.")

if __name__ == "__main__":
    main()