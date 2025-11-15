# fish/perception.py
# The "Brain" of the bot. Runs the FSM logic.

import cv2
import mss
import time
import utils, config
from ultralytics import YOLO  # type: ignore

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
        # left_arrow_template = cv2.imread(config.LEFT_ARROW_TEMPLATE, 0)
        # right_arrow_template = cv2.imread(config.RIGHT_ARROW_TEMPLATE, 0)
        
        # NEW: Load rod swap templates
        rod_prompt_template = cv2.imread(config.ROD_PROMPT_TEMPLATE, 0) # <-- NEW
        rod_use_template = cv2.imread(config.ROD_USE_TEMPLATE, 0)       # <-- NEW
        
    except Exception as e:
        print(f"[Perception] ERROR: Could not load template images. {e}")
        return

    # --- NEW: Load YOLO Model ---
    try:
        print("[Perception] Loading custom YOLO model...")
        # !!! UPDATE THIS PATH to your 'best.pt' file !!!
        model = YOLO(config.YOLO_MODEL)
        print("[Perception] YOLO model loaded successfully.")
    except Exception as e:
        print(f"[Perception] ERROR: Could not load YOLO model from {config.YOLO_MODEL}")
        print(f"Make sure 'best.pt' is at that path. Error: {e}")
        return
    # --- END NEW ---
    
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
                # 3. BGR (for our YOLO model)
                screen_bgr = utils.capture_screen(sct, window_state["monitor_object"], format='bgr')
                
                # --- THIS IS THE FIX ---
                # Add a safety check to ensure our captures worked
                if screen_gray is None or screen_hsv is None or screen_bgr is None:
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
                    
                    # --- THIS IS THE MODIFIED STATE ---
                    elif state == config.STATE_REELING:
                        
                        # --- NEW YOLOv8 DETECTION LOGIC ---
                        
                        # 2. Get screen center and dead zone
                        window_width = bot_state.monitor_object['width']
                        center_x = window_width / 2
                        dead_zone_width = (window_width * config.DEAD_ZONE_PERCENT) / 2
                        dead_zone_left = center_x - dead_zone_width
                        dead_zone_right = center_x + dead_zone_width
                        
                        # 3. Run the YOLO model on the BGR screen capture
                        results = model(screen_bgr, verbose=False, stream=True, imgsz=320)

                        # Check if 'results' is None before looping
                        if results is None:
                            print("[Perception] YOLO model returned None. Skipping frame.")
                            found_fish = False
                        else:
                            found_fish = False
                            # 4. Process the results
                            for r in results:

                                # --- !!! THIS IS THE FIX !!! ---
                                # OBB models store results in 'r.obb', not 'r.boxes'
                                if r.obb is None:
                                    # This is normal, means no fish was detected in this frame
                                    found_fish = False
                                    continue # Go to the next frame/result
                                
                                # Loop over the OBB (Oriented Bounding Box) objects
                                for box in r.obb: 
                                # --- !!! END OF FIX !!! ---
                                
                                    # Check if confidence is high enough
                                    if box.conf[0] > config.CONF_THRESHOLD:
                                        
                                        # Get the standard (non-rotated) bounding box coordinates
                                        # The OBB object handily provides this for us in .xyxy
                                        x1, y1, x2, y2 = box.xyxy[0] 
                                        
                                        # Calculate the center of the fish
                                        fish_center_x = (x1 + x2) / 2
                                        
                                        # 5. Compare fish position to dead zone
                                        if fish_center_x < dead_zone_left:
                                            bot_state.arrow_direction = "LEFT"
                                        elif fish_center_x > dead_zone_right:
                                            bot_state.arrow_direction = "RIGHT"
                                        else:
                                            # Fish is in the dead zone, do nothing
                                            bot_state.arrow_direction = "NONE"
                                            
                                        found_fish = True
                                        break # We only care about the most confident fish
                                if found_fish:
                                    break # Stop processing other results in the batch

                        if not found_fish:
                            # If the model saw nothing (or confidence was too low), don't move.
                            bot_state.arrow_direction = "NONE"
                            
                        # --- END OF NEW YOLOv8 LOGIC ---

                        # 6. Failsafe: Check for "Continue" button (unchanged)
                        if cont_coords:
                            print("[Perception] Fish caught! State changing to CAUGHT.")
                            monitor = bot_state.monitor_object
                            bot_state.cached_button_coords = (cont_coords[0] + monitor['left'], cont_coords[1] + monitor['top'])
                            bot_state.current_state = config.STATE_CAUGHT
                            bot_state.arrow_direction = "NONE" # Clear arrows
                            
                        # 7. Failsafe: Check for "B" prompt (unchanged)
                        elif recast_coords:
                            print("[Perception] Fish got away. State changing to IDLE.")
                            bot_state.current_state = config.STATE_IDLE
                            bot_state.arrow_direction = "NONE"
                        
                    elif state == config.STATE_CAUGHT:
                        # (This state is unchanged)
                        # Look for "Continue" button in the FULL gray screen
                        if not cont_coords:
                            print("[Perception] Button clicked. Waiting for next cycle...")
                            time.sleep(config.CAST_WAIT_TIME_SEC) 
                            print("[Perception] State changing to IDLE.")
                            bot_state.current_state = config.STATE_IDLE
                        
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