# fish/perception.py
# The "Brain" of the bot. Runs the FSM logic.

import cv2
import mss
import time
import utils, config

def run_perception(bot_state):
    """
    The main loop for the perception thread.
    Manages the FSM, checks window status, and finds templates.
    """
    print("[Perception] Loading templates...")
    try:
        #exclamation_template = cv2.imread(config.EXCLAMATION_TEMPLATE, 0)
        continue_template = cv2.imread(config.CONTINUE_TEMPLATE, 0)
        recast_template = cv2.imread(config.RECAST_PROMPT_TEMPLATE, 0)
        
        # NEW: Load arrow templates (also grayscale) for shape matching
        left_arrow_template = cv2.imread(config.LEFT_ARROW_TEMPLATE, 0)
        right_arrow_template = cv2.imread(config.RIGHT_ARROW_TEMPLATE, 0)
        
        # NEW: Load rod swap templates
        rod_prompt_template = cv2.imread(config.ROD_PROMPT_TEMPLATE, 0) # <-- NEW
        rod_use_template = cv2.imread(config.ROD_USE_TEMPLATE, 0)       # <-- NEW
        
    except Exception as e:
        print(f"[Perception] ERROR: Could not load template images. {e}")
        return

    print("[Perception] Thread started. Managing FSM...")
    
    with bot_state.lock:
        hwnd = bot_state.hwnd # Get the handle once

    with mss.mss() as sct:
        while bot_state.running:
            try:
                # --- 1. Window Status Check (Correct and Unchanged) ---
                window_state = utils.get_window_state(hwnd)
                is_paused = not window_state["is_focused"] or not window_state["is_valid"]
                with bot_state.lock:
                    bot_state.is_paused = is_paused
                
                if is_paused:
                    print("[Perception] Window not focused. Paused.", end="\r")
                    time.sleep(1) 
                    continue 
                
                # --- 2. Window Position Update (Correct and Unchanged) ---
                with bot_state.lock:
                    bot_state.monitor_object = window_state["monitor_object"]
                
                # --- 3. Perception (The "Eyes") ---
                # We need TWO captures:
                # 1. Grayscale (for gray UI)
                screen_gray = utils.capture_screen(sct, window_state["monitor_object"], format='gray')
                # 2. HSV (for color UI)
                screen_hsv = utils.capture_screen(sct, window_state["monitor_object"], format='hsv')
                
                # --- THIS IS THE FIX ---
                # Add a safety check to ensure our captures worked
                if screen_gray is None or screen_hsv is None:
                    print("[Perception] Screen capture failed. Skipping frame.", end="\r")
                    time.sleep(0.5) # Wait a bit before retrying
                    continue
                # --- END OF FIX ---
                
                # --- NEW: Define and Crop our Region of Interest (ROI) ---
                # We'll slice the image to get the top 75%, ignoring the botto  m
                # (where the tension bar is).
                window_width = window_state["monitor_object"]['width']
                window_height = window_state["monitor_object"]['height']
                roi_height = int(window_height * 0.75) # Crop to top 75%
                
                # Create the "Region of Interest" (ROI) versions
                # This is a super-fast numpy array slice
                screen_gray_roi = screen_gray[0:roi_height, :]
                screen_hsv_roi = screen_hsv[0:roi_height, :]
                # --- END NEW SECTION ---
                
                # We find all templates *before* the logic
                #excl_coords = utils.find_template(
                #    screen_gray, exclamation_template, config.EXCLAMATION_THRESHOLD
                #)
                cont_coords = utils.find_template(
                    screen_gray, continue_template, config.CONTINUE_THRESHOLD
                )
                recast_coords = utils.find_template(
                            screen_gray, recast_template, config.RECAST_THRESHOLD
                        )
                
                # --- 4. FSM Logic (Your New, Robust FSM) ---
                with bot_state.lock:
                    state = bot_state.current_state 
                    
                    if state == config.STATE_IDLE:
                        # --- MODIFIED: Check for broken rod FIRST ---
                        rod_prompt_coords = utils.find_template(
                            screen_gray, rod_prompt_template, config.ROD_PROMPT_THRESHOLD
                        )
                        
                        if rod_prompt_coords:
                            print("[Perception] Broken rod detected! State changing to SWAP_ROD.")
                            bot_state.current_state = config.STATE_SWAP_ROD
                            bot_state.swap_step = "PRESS_M"
                        elif not recast_coords:
                            # "B" prompt is gone, meaning we successfully cast
                            print("[Perception] Cast successful. State changing to CASTING.")
                            bot_state.current_state = config.STATE_CASTING
                        # If recast_coords is visible, we do nothing and let the Action thread click
                    
                    elif state == config.STATE_CASTING:
                        # --- NEW "!" LOGIC ---
                        # Look for the "!" in the CROPPED HSV image
                        mask = cv2.inRange(screen_hsv_roi, config.ORANGE_LOWER, config.ORANGE_UPPER)
                        contours, _ = cv2.findContours(mask, cv2.RETR_TREE, cv2.CHAIN_APPROX_SIMPLE)
                        
                        found_exclamation = False
                        for cnt in contours:
                            x, y, w, h = cv2.boundingRect(cnt)
                            # Check middle of the *ROI*, which is safe
                            is_tall = h > w * 1.5 
                            is_middle = (x > (window_state["monitor_object"]['width'] * 0.4) and
                                         x < (window_state["monitor_object"]['width'] * 0.6))
                            
                            if is_tall and is_middle:
                                found_exclamation = True
                                break
                        
                        if found_exclamation:
                            print("[Perception] BITE! (Color Mask). State changing to REELING.")
                            bot_state.current_state = config.STATE_REELING
                        
                        # Failsafe: Check for "B" prompt in the FULL gray screen
                        elif utils.find_template(screen_gray, recast_template, config.RECAST_THRESHOLD):
                            bot_state.current_state = config.STATE_IDLE
                    
                    elif state == config.STATE_REELING:
                        ## --- NEW: Create a smaller ROI just for arrows ---
                        # Crop 25% from all sides
                        y_start = int(window_height * 0.25)
                        y_end = int(window_height * 0.75) # (h * 1.0) - (h * 0.25)
                        x_start = int(window_width * 0.25)
                        x_end = int(window_width * 0.75) # (w * 1.0) - (w * 0.25)
                        
                        # Create the new, smaller "arrow" ROIs
                        screen_gray_roi_reeling = screen_gray[y_start:y_end, x_start:x_end]
                        # screen_hsv_roi_reeling = screen_hsv[y_start:y_end, x_start:x_end]
                        
                        # --- MODIFIED: Use the new 'reeling' ROI ---
                        
                        # 1. Look for the left arrow in the SMALLER cropped gray image
                        left_coords = utils.find_template(
                            screen_gray_roi_reeling, left_arrow_template, config.ARROW_MATCH_THRESHOLD
                        )
                        
                        # 2. Look for the right arrow in the SMALLER cropped gray image
                        right_coords = utils.find_template(
                            screen_gray_roi_reeling, right_arrow_template, config.ARROW_MATCH_THRESHOLD
                        )
                        
                        # 3. Decide the direction
                        if left_coords:
                            bot_state.arrow_direction = "LEFT"
                        elif right_coords:
                            bot_state.arrow_direction = "RIGHT"
                        else:
                            bot_state.arrow_direction = "NONE"

                        # 4. Failsafe: Check for "Continue" button (unchanged)
                        cont_coords = utils.find_template(screen_gray, continue_template, config.CONTINUE_THRESHOLD)
                        if cont_coords:
                            print("[Perception] Fish caught! State changing to CAUGHT.")
                            monitor = bot_state.monitor_object
                            bot_state.cached_button_coords = (cont_coords[0] + monitor['left'], cont_coords[1] + monitor['top'])
                            bot_state.current_state = config.STATE_CAUGHT
                            bot_state.arrow_direction = "NONE" # Clear arrows
                        # 5. Failsafe: Check for "B" prompt (unchanged)
                        elif utils.find_template(screen_gray, recast_template, config.RECAST_THRESHOLD):
                            bot_state.current_state = config.STATE_IDLE
                            bot_state.arrow_direction = "NONE"
                        # --- END OF NEW LOGIC ---
                        
                    elif state == config.STATE_CAUGHT:
                        # Look for "Continue" button in the FULL gray screen
                        if not cont_coords:
                            print("[Perception] Button clicked. Waiting for next cycle...")
                            time.sleep(config.CAST_WAIT_TIME_SEC) 
                            print("[Perception] State changing to IDLE.")
                            bot_state.current_state = config.STATE_IDLE

                    # --- NEW FSM STATE ---
                    elif state == config.STATE_SWAP_ROD:
                        step = bot_state.swap_step
                        
                        if step == "FIND_BUTTON":
                            # The "Body" has pressed 'M', now we look for the "Use" button
                            use_coords = utils.find_template(
                                screen_gray, rod_use_template, config.ROD_USE_THRESHOLD
                            )
                            if use_coords:
                                print(f"[Perception] Found 'Use' button at {use_coords}")
                                monitor = bot_state.monitor_object
                                screen_x = use_coords[0] + monitor['left']
                                screen_y = use_coords[1] + monitor['top']
                                bot_state.swap_rod_coords = (screen_x, screen_y)
                                bot_state.swap_step = "CLICK_USE"
                        
                        elif step == "WAIT_FOR_CLOSE":
                            # The "Body" has clicked "Use", now we wait for the menu to close
                            use_coords = utils.find_template(
                                screen_gray, rod_use_template, config.ROD_USE_THRESHOLD
                            )
                            if not use_coords:
                                print("[Perception] Rod swap complete. Returning to IDLE.")
                                bot_state.current_state = config.STATE_IDLE
                                bot_state.swap_step = "NONE"
                                time.sleep(1.0) # Wait for UI to settle
                    
                #time.sleep(0.1) 
                
            except Exception as e:
                print(f"[Perception] Error in loop: {e}")
                time.sleep(1)