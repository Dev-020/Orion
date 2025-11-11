# fish/main_fish.py
# The main launcher for the fishing bot.

import threading
import time
import pyautogui
import perception, action, utils # <-- MODIFIED: Import utils
from fish_state import BotState

def start_bot():
    
    print("Waiting for game window... (e.g., 'Blue Protocol')")
    print("Please click into the game. The script will retry every 3 seconds.")
    
    game_hwnd = None
    monitor_object = None
    
    # !!! You MUST change this title to match your game's window title !!!
    window_title_to_find = "Blue Protocol: Star Resonance"
    
    while True: # The window-finding loop
        try:
            # --- MODIFIED: Using the new util function ---
            game_hwnd = utils.find_game_window(window_title_to_find)
            
            # Now, get the window's state to check it
            state = utils.get_window_state(game_hwnd)

            if state["is_valid"]:
                monitor_object = state["monitor_object"]
                print(f"Found window: '{window_title_to_find}' at ({monitor_object['left']}, {monitor_object['top']})")
                break # Exit the loop
            else:
                print("Game window is minimized or invalid. Retrying...")
                
        except (IndexError):
            print("Window not found. Retrying in 3 seconds...")
        except Exception as e:
            print(f"An error occurred while finding window: {e}. Retrying...")
            
        time.sleep(3)
    
    # 1. Create the ONE BotState instance
    bot_state = BotState(monitor_object, game_hwnd)
    
    # 2. Create the threads
    perception_thread = threading.Thread(
        target=perception.run_perception, 
        args=(bot_state,), # Pass the whole state object
        daemon=True
    )
    
    action_thread = threading.Thread(
        target=action.run_action, 
        args=(bot_state,), # Pass the whole state object
        daemon=True
    )
    
    print("[Main] Starting bot... Press Ctrl+C to stop.")
    perception_thread.start()
    action_thread.start()
    
    # 3. Main thread just keeps the script alive
    try:
        while True:
            time.sleep(1)
            if not perception_thread.is_alive() or not action_thread.is_alive():
                print("[Main] A thread has died. Stopping bot.")
                raise KeyboardInterrupt
                
    except KeyboardInterrupt:
        print("\n[Main] Stopping bot...")
        with bot_state.lock:
            bot_state.running = False # Tell threads to stop
        pyautogui.mouseUp(button='left') # Failsafe mouse release
        time.sleep(1) 
        print("[Main] Bot stopped.")

if __name__ == "__main__":
    start_bot()