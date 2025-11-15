# fish/action.py
# The "Body" of the bot. Performs all mouse actions.

import pyautogui
import time
import config # <-- Make sure config is imported

def run_action(bot_state):
    """
    The main loop for the action thread.
    Reads the FSM state and performs the required action.
    """
    print("[Action] Thread started. Awaiting commands...")
    
    # --- NEW: Action-side Cooldowns ---
    # We use these to prevent spamming clicks
    last_cast_attempt = 0
    last_continue_click = 0
    
    # --- NEW: Track which key we are holding down ---
    current_key_pressed = "NONE"
    
    while bot_state.running:
        try:
            # --- 1. Check for Pause ---
            with bot_state.lock:
                if bot_state.is_paused:
                    # Release ALL keys if paused
                    pyautogui.mouseUp(button='left') 
                    pyautogui.keyUp('a')
                    pyautogui.keyUp('d')
                    current_key_pressed = "NONE"
                    time.sleep(0.5) # Wait half a second before checking again
                    continue 
            
            # --- 2. Read the State ---
            with bot_state.lock:
                state = bot_state.current_state
                # Get the new arrow direction
                arrow_direction = bot_state.arrow_direction
                
            # --- 3. Act based on State (State-Driven Logic) ---
            
            if state == config.STATE_IDLE:
                # We are IDLE, so we need to cast.
                pyautogui.mouseUp(button='left') # Ensure mouse is up
                
                # Check if our cooldown has passed
                if (time.time() - last_cast_attempt) > config.CAST_WAIT_TIME_SEC:
                    print("[Action] State is IDLE. Simulating cast click...")
                    pyautogui.mouseDown(button='left')
                    time.sleep(0.2) # Your proven hold time
                    pyautogui.mouseUp(button='left')
                    
                    # Reset the cooldown timer
                    last_cast_attempt = time.time()
                
            elif state == config.STATE_CASTING:
                # We are waiting for a bite. Make sure no keys are pressed.
                pyautogui.mouseUp(button='left')
                if current_key_pressed != "NONE":
                    pyautogui.keyUp('a')
                    pyautogui.keyUp('d')
                    current_key_pressed = "NONE"
                
                # Reset timers so we're ready for the next state
                last_cast_attempt = 0 
                last_continue_click = 0
                
            elif state == config.STATE_REELING:
                # --- NEW REELING LOGIC ---
                # 1. Hold mouse down continuously
                pyautogui.mouseDown(button='left')
                
                # 2. Manage "A" and "D" keys
                if arrow_direction == "LEFT" and current_key_pressed != "LEFT":
                    pyautogui.keyUp('d') # Release right
                    pyautogui.keyDown('a') # Hold left
                    current_key_pressed = "LEFT"
                    print("[Action] Holding 'A'")
                
                elif arrow_direction == "RIGHT" and current_key_pressed != "RIGHT":
                    pyautogui.keyUp('a') # Release left
                    pyautogui.keyDown('d') # Hold right
                    current_key_pressed = "RIGHT"
                    print("[Action] Holding 'D'")
                
                elif arrow_direction == "NONE" and current_key_pressed != "NONE":
                    pyautogui.keyUp('a') # Release all
                    pyautogui.keyUp('d')
                    current_key_pressed = "NONE"
                    print("[Action] Releasing keys...")
                # --- END NEW REELING LOGIC ---
                    
            elif state == config.STATE_CAUGHT:
                # We are on the "caught" screen. Click "Continue".
                pyautogui.mouseUp(button='left') # Release the reel
                if current_key_pressed != "NONE":
                    pyautogui.keyUp('a')
                    pyautogui.keyUp('d')
                    current_key_pressed = "NONE"
                
                # Check if our click cooldown has passed
                if (time.time() - last_continue_click) > config.CAST_WAIT_TIME_SEC:
                    with bot_state.lock:
                        coords = bot_state.cached_button_coords
                        
                    if coords:
                        print(f"[Action] State is CAUGHT. Clicking 'Continue' at {coords}.")
                        pyautogui.click(coords[0], coords[1])
                        # Reset the click cooldown timer
                        last_continue_click = time.time()
                    else:
                        print("[Action] ERROR: State is CAUGHT but I have no coords to click!")

            # --- NEW: Handle the Rod Swap State ---
            elif state == config.STATE_SWAP_ROD:
                if (time.time() - last_continue_click) > config.CAST_WAIT_TIME_SEC:
                    if bot_state.swap_step == "PRESS_M":
                        print("[Action] Broken rod! Pressing 'M'...")
                        pyautogui.press('m')
                        with bot_state.lock:
                            bot_state.swap_step = "FIND_BUTTON"
                        last_continue_click = time.time()
                    
                    elif bot_state.swap_step == "CLICK_USE":
                        with bot_state.lock:
                            coords = bot_state.swap_rod_coords
                        
                        if coords:
                            print(f"[Action] Clicking 'Use' at {coords}")
                            pyautogui.click(coords[0], coords[1])
                            with bot_state.lock:
                                bot_state.swap_step = "WAIT_FOR_CLOSE"
                            last_continue_click = time.time()
                        else:
                            print("[Action] In CLICK_USE state but no coords found. Brain is slow?")
                            # We just wait, the Brain will provide coords on its next loop
            
            time.sleep(0.03) 
            
        except Exception as e:
            print(f"[Action] Error in FSM loop: {e}")
            pyautogui.mouseUp(button='left') # Failsafe
            time.sleep(1)