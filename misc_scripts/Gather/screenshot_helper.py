# screenshot_helper.py

import pyautogui
import win32gui  # Part of pywin32
import keyboard
import time
import os

# --- Configuration ---s
WINDOW_TITLE = "Blue Protocol: Star Resonance"      # Exact title of the game window
FILENAME_PREFIX = "fish"                        # Base name for your files
SAVE_FOLDER = f"dataset/images/{FILENAME_PREFIX}"             # Folder to save screenshots (will be created if needed)
HOTKEY = "'"                                        # The key combination to trigger a screenshot

# --- Global variable for the counter ---
screenshot_counter = 1

# --- Function to take the screenshot ---
def take_screenshot():
    global screenshot_counter
    print(f"Hotkey '{HOTKEY}' pressed. Trying to capture...")

    # 1. Find the game window
    hwnd = win32gui.FindWindow(None, WINDOW_TITLE)
    if not hwnd:
        print(f"Error: Window '{WINDOW_TITLE}' not found.")
        return

    # Bring the window to the foreground briefly (often needed for games)
    try:
        win32gui.SetForegroundWindow(hwnd)
        time.sleep(0.1)
    except Exception as e:
        print(f"Warning: Could not bring window to foreground - {e}")

    # --- UPDATED PART: Get Client Area Coordinates ---
    try:
        # Get coordinates of the client area relative to the window
        client_rect = win32gui.GetClientRect(hwnd)
        client_width = client_rect[2] - client_rect[0]
        client_height = client_rect[3] - client_rect[1]

        # Convert the top-left corner (0,0) of the client area to screen coordinates
        screen_x, screen_y = win32gui.ClientToScreen(hwnd, (client_rect[0], client_rect[1]))

        # Define the region for pyautogui using screen coordinates
        region = (screen_x, screen_y, client_width, client_height)
        print(f"Client area found at screen coordinates {region}")

        # Ensure width and height are positive
        if client_width <= 0 or client_height <= 0:
            print("Error: Client area has invalid dimensions (width or height is zero or negative).")
            return

    except Exception as e:
        print(f"Error getting client area dimensions: {e}")
        return
    # --- END OF UPDATED PART ---

    # 3. Create save folder if it doesn't exist
    if not os.path.exists(SAVE_FOLDER):
        os.makedirs(SAVE_FOLDER)
        print(f"Created folder: {SAVE_FOLDER}")

    # 4. Construct filename and save screenshot
    filename = f"{FILENAME_PREFIX}{screenshot_counter}.png"
    save_path = os.path.join(SAVE_FOLDER, filename)

    try:
        # Ensure the region is valid before taking the screenshot
        if region[2] > 0 and region[3] > 0:
             screenshot = pyautogui.screenshot(region=region)
             screenshot.save(save_path)
             print(f"Screenshot saved as: {save_path}")
             screenshot_counter += 1
        else:
            print("Error: Invalid region dimensions, cannot take screenshot.")
    except Exception as e:
        print(f"Error taking or saving screenshot: {e}")
        print("Make sure the window is not minimized when taking the screenshot.")

# --- Main execution ---
if __name__ == "__main__":
    print(f"Screenshot helper started.")
    print(f" - Press '{HOTKEY}' to capture the '{WINDOW_TITLE}' window.")
    print(f" - Screenshots will be saved in '{SAVE_FOLDER}' with prefix '{FILENAME_PREFIX}'.")
    print(f" - Press 'Ctrl+C' in this terminal to stop the script.")

    # Find the starting counter based on existing files
    if os.path.exists(SAVE_FOLDER):
        files = [f for f in os.listdir(SAVE_FOLDER) if f.startswith(FILENAME_PREFIX) and f.endswith(".png")]
        if files:
            numbers = [int(f.replace(FILENAME_PREFIX, "").replace(".png", "")) for f in files if f.replace(FILENAME_PREFIX, "").replace(".png", "").isdigit()]
            if numbers:
                screenshot_counter = max(numbers) + 1
    print(f"Starting screenshot counter at: {screenshot_counter}")

    # Register the hotkey
    keyboard.add_hotkey(HOTKEY, take_screenshot)

    # Keep the script running to listen for the hotkey
    # You might need to press another key (like Esc) after Ctrl+C to fully exit sometimes
    try:
        keyboard.wait()
    except KeyboardInterrupt:
        print("\nStopping script.")