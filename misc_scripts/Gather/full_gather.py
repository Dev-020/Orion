# full_gatherer.py

import pyautogui
import pydirectinput
import time
import random
import numpy as np
from PIL import Image
import win32gui  # For capturing the game window
from ultralytics import YOLO # type: ignore

# --- Configuration (UPDATE THESE!) ---
# --- Game Window ---
WINDOW_TITLE = "Blue Protocol: Star Resonance"  # Exact title of the game window
MODEL_PATH = "best.pt"                       # Path to your trained model file

# --- UI Interaction (from your working ui_gatherer.py) ---
TRIGGER_IMAGE = 'trigger_prompt.png'     # The '[F]' prompt image
TARGET_REGION = (1392, 596, 124, 28)     # (x, y, w, h) of the red text area
PYDIRECTINPUT_SCROLL_CLICKS = -100
GATHER_KEY = 'f'

# --- Navigation (TUNE THESE!) ---
TURN_DURATION = 0.05      # How long to press A/D to turn. (Start small!)
FORWARD_DURATION = 0.3    # How long to press W to walk forward in each step.
CENTER_DEAD_ZONE_PCT = 0.20 # 20% of screen width. If target is in this zone, we walk.

# --- Helper Function for Color Averaging (from ui_gatherer.py) ---
def get_average_color(region):
    """Takes a screenshot of a region and returns its average RGB color."""
    try:
        screenshot = pyautogui.screenshot(region=region)
        img_array = np.array(screenshot)
        avg_color = img_array.mean(axis=(0, 1))
        return avg_color
    except Exception as e:
        print(f"Error getting average color: {e}")
        return (0, 0, 0)

# --- Helper Function to Find and Screenshot the Game Window ---
def capture_game_window(window_title):
    """Finds the game window and returns its region and a screenshot."""
    try:
        hwnd = win32gui.FindWindow(None, window_title)
        if not hwnd:
            print(f"Error: Window '{window_title}' not found.")
            return None, None
        
        # Get client area coordinates (the part *inside* the border)
        client_rect = win32gui.GetClientRect(hwnd)
        client_width = client_rect[2] - client_rect[0]
        client_height = client_rect[3] - client_rect[1]
        
        # Convert the client area's top-left corner to screen coordinates
        screen_x, screen_y = win32gui.ClientToScreen(hwnd, (client_rect[0], client_rect[1]))

        # Define the region for pyautogui
        region = (screen_x, screen_y, client_width, client_height)
        
        # Ensure window is not minimized
        if client_width <= 0 or client_height <= 0:
            print("Error: Window is minimized or has invalid size.")
            return None, None
            
        # Take the screenshot
        screenshot = pyautogui.screenshot(region=region)
        return region, screenshot
        
    except Exception as e:
        print(f"Error capturing window: {e}")
        return None, None

# --- Main Script ---
def main():
    print("Loading AI model...")
    model = YOLO(MODEL_PATH)  # Load your custom-trained OBB model
    print("Model loaded successfully.")
    
    print("Starting full gathering bot...")
    print("Switch to your game. Script begins in 5 seconds.")
    for i in range(5, 0, -1):
        print(f"{i}...", end="", flush=True)
        time.sleep(1)
    print("\nScript is now active!")

    pyautogui.FAILSAFE = True
    
    try:
        while True:
            # --- 1. CAPTURE & CHECK FOR INTERACTION ---
            
            # Capture the current game window
            window_region, screenshot = capture_game_window(WINDOW_TITLE)
            
            if not screenshot:
                print("Game window not found. Retrying in 2 seconds...")
                time.sleep(2)
                continue
                
            # Get screen center (relative to the window)
            screen_width = window_region[2]
            screen_center_x = screen_width / 2
            dead_zone_width = screen_width * CENTER_DEAD_ZONE_PCT
            dead_zone_left = screen_center_x - (dead_zone_width / 2)
            dead_zone_right = screen_center_x + (dead_zone_width / 2)

            # --- HIGHEST PRIORITY: Check for [F] prompt (the handoff) ---
            # We search for the trigger *within* the screenshot we just took.
            try:
                # We need to find the trigger's coordinates relative to the window, not the whole screen
                interaction_prompt = pyautogui.locate(TRIGGER_IMAGE, screenshot, confidence=0.8, grayscale=True)
                
                if interaction_prompt:
                    print("--- STATE: INTERACTING ---")
                    print("Gather prompt detected. Running UI logic...")
                    
                    # --- Run your proven UI script logic ---
                    # We must add the window's top-left corner (window_region[0], window_region[1])
                    # to the TARGET_REGION coordinates to get the correct *screen* coordinates
                    # for the color check.
                    screen_target_region = (
                        window_region[0] + TARGET_REGION[0],
                        window_region[1] + TARGET_REGION[1],
                        TARGET_REGION[2],
                        TARGET_REGION[3]
                    )
                    
                    avg_color = get_average_color(screen_target_region)
                    r, g, b = avg_color[0], avg_color[1], avg_color[2]
                    print(f"Average color in region is RGB: ({r:.0f}, {g:.0f}, {b:.0f})")

                    #if r > (g + 20) and r > (b + 20):
                    #    print("Action is RED. Scrolling down...")
                    #    pyautogui.scroll(PYDIRECTINPUT_SCROLL_CLICKS)
                    #    time.sleep(0.3)
                    
                    pyautogui.scroll(PYDIRECTINPUT_SCROLL_CLICKS)
                    time.sleep(0.3)
                    pydirectinput.press(GATHER_KEY) # Use pydirectinput for reliability
                    print("Gathering complete. Resuming search...")
                    time.sleep(4.0) # Wait for gather animation
                    continue # Restart the loop (go back to searching)

            except pyautogui.ImageNotFoundException:
                pass # This is normal, it means we're not close enough yet.

            # --- 2. AI NAVIGATION ---
            print("--- STATE: SEARCHING/NAVIGATING ---")
            
            # Feed the screenshot to the YOLO model
            # verbose=False stops it from printing tons of text
            results = model(screenshot, verbose=False)
            
            if results and len(results[0].obb.xywh) > 0:
                # --- An ore was found! ---
                # Get the first detection (you could add logic to find the closest one)
                # .obb.xywh gives [x_center, y_center, width, height, rotation]
                target = results[0].obb.xywh[0] 
                target_x_center = target[0].item() # Get the x-coordinate of its center
                
                print(f"Ore detected at x: {target_x_center:.0f}. (Screen center: {screen_center_x:.0f})")

                # --- Run Navigation Logic ---
                if target_x_center < dead_zone_left:
                    print("  Turning LEFT")
                    pydirectinput.press('a', duration=TURN_DURATION)
                elif target_x_center > dead_zone_right:
                    print("  Turning RIGHT")
                    pydirectinput.press('d', duration=TURN_DURATION)
                else:
                    print("  Target is centered. Moving FORWARD.")
                    pydirectinput.press('w', duration=FORWARD_DURATION)
                
                time.sleep(0.1) # Small pause between actions

            else:
                # --- No ore was found ---
                print("No ore found in view. Scanning...")
                pydirectinput.press('d', duration=0.3) # Turn right to scan the area
                time.sleep(1.0) # Wait a second while turning

    except KeyboardInterrupt:
        print("\nScript stopped by user.")

# --- Run the main script ---
if __name__ == "__main__":
    # We must have administrator privileges for pydirectinput and the window capture
    main()