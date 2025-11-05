# utils.py
# This file contains shared helper functions for the bot.

import os
import numpy as np
import pyautogui
import win32gui
import time

# Use a relative import to get settings from config.py
from . import config

def capture_game_window(window_title = config.WINDOW_TITLE):
    """
    Finds the game window, checks if it's active,
    and returns its region and a screenshot.
    """
    try:
        # Use the window_title if provided, else use the default from config
        hwnd = win32gui.FindWindow(None, window_title)
        if not hwnd:
            print(f"Error: Window '{window_title}' not found.", end="\r", flush=True)
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
        print(f"\n--- CAPTURE WINDOW ERROR ---")
        print(f"Error: {e}")
        import traceback
        traceback.print_exc()
        print("----------------------------")
        return None, None
    
# --- [NEW] Self-Populating Data Collection Function ---
def check_and_save_for_review(results, screenshot):
    """
    Checks if ANY detected target is "unsure" (below confidence)
    and saves the image and ALL YOLO labels to a class-specific
    folder for manual review.
    
    Returns a status string if it saved, otherwise None.
    """
    try:
        # We need the model's class names map (e.g., {0: 'baru_ore', 1: 'mushroom'})
        class_names_map = results[0].names
        
        # 1. Check if ANY target is "unsure"
        is_unsure = False
        first_unsure_class_name = "unknown"
        
        for conf, cls in zip(results[0].obb.conf, results[0].obb.cls):
            if conf.item() < config.DATA_COLLECTION_CONF_THRESHOLD:
                is_unsure = True
                # Get the class name for our new filename and folder
                first_unsure_class_name = class_names_map[int(cls.item())]
                break # We found one, that's all we need
        
        if is_unsure:
            # --- [FIXED] Create class-specific sub-folders ---
            image_dir = os.path.join(config.DATA_COLLECTION_PATH, 'images', first_unsure_class_name)
            label_dir = os.path.join(config.DATA_COLLECTION_PATH, 'labels', first_unsure_class_name)
            os.makedirs(image_dir, exist_ok=True)
            os.makedirs(label_dir, exist_ok=True)

            # 3. Find the next available number for this class
            pattern = f"generated_{first_unsure_class_name}_"
            
            # --- [FIXED] Search the new, specific image_dir ---
            current_files = os.listdir(image_dir)
            existing_nums = []
            
            for f in current_files:
                if f.startswith(pattern) and f.endswith(".png"):
                    try:
                        num_str = f.replace(pattern, "").replace(".png", "")
                        existing_nums.append(int(num_str))
                    except ValueError:
                        continue # File name is in an unexpected format
            
            next_num = max(existing_nums) + 1 if existing_nums else 1

            # 4. Create new filenames
            base_filename = f"generated_{first_unsure_class_name}_{next_num}"
            image_filename = os.path.join(image_dir, f"{base_filename}.png")
            label_filename = os.path.join(label_dir, f"{base_filename}.txt")
            
            # 5. Save the Image and ALL labels from that frame
            screenshot.save(image_filename)
            # save_txt saves all labels found in the 'results' object
            results[0].save_txt(label_filename, save_conf=False) 
            
            return f"saved: {base_filename}" # Return a useful status
    
    except Exception as e:
        print(f"\n--- DATA COLLECTION ERROR: {e} ---")
    
    return None # No save was needed