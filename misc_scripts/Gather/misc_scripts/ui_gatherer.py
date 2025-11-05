# ui_gatherer.py (Updated with Area Averaging and Scroll Wheel)

import pyautogui
import time
import random
import numpy as np
import os

# --- Configuration ---
# !!! REPLACE THIS WITH THE OUTPUT FROM THE HELPER SCRIPT !!!
# (x, y, width, height) of the text area to check
TARGET_REGION = (1392, 596, 124, 28)

# --- Constants ---
TRIGGER_IMAGE = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'trigger_prompt.png')
GATHER_KEY = 'f'
# pyautogui uses a larger value for smooth scrolling. Negative is down.
SCROLL_AMOUNT = -100

# --- Helper Function ---
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

# --- Main Logic ---
print("Starting UI gathering script...")
print("Switch to your game now. The script will begin in 5 seconds.")

for i in range(5, 0, -1):
    print(f"{i}...", end="", flush=True)
    time.sleep(1)
print("\nScript is now active!")

pyautogui.FAILSAFE = True

try:
    while True:
        trigger_location = None
        try:
            trigger_location = pyautogui.locateOnScreen(TRIGGER_IMAGE, confidence=0.9, grayscale=True)
        except pyautogui.ImageNotFoundException:
            pass

        if trigger_location:
            print("Gather prompt detected. Checking state...")

            # Get the average color of the entire region
            avg_color = get_average_color(TARGET_REGION)
            r, g, b = avg_color[0], avg_color[1], avg_color[2]

            print(f"Average color in region is RGB: ({r:.0f}, {g:.0f}, {b:.0f})")

            # Check if the average color is reddish
            #if r > (g) and r > (b):
            #    print("Action is RED. Scrolling down...")
            #    pyautogui.scroll(SCROLL_AMOUNT) # <-- Using scroll wheel
            #    time.sleep(0.3)
            
            pyautogui.scroll(SCROLL_AMOUNT)
            time.sleep(0.3)
            print(f"Pressing '{GATHER_KEY}' to gather...")
            pyautogui.press(GATHER_KEY) # <-- Using keyboard press
            
            print("Action complete. Waiting before next search...")
            time.sleep(4.5 + random.uniform(0.1, 0.5))

        else:
            print("No gather prompt found. Searching...", end="\r", flush=True)
            time.sleep(0.5)

except KeyboardInterrupt:
    print("\nScript stopped by user.")