# get_region_info.py
import pyautogui
import time

print("--- Step 1: Find the Top-Left Corner ---")
print("Move your mouse to the TOP-LEFT corner of your target area.")
input("Press Enter when your mouse is in position...")
topLeft_x, topLeft_y = pyautogui.position()
print(f"Top-Left corner recorded at: ({topLeft_x}, {topLeft_y})\n")

print("--- Step 2: Find the Bottom-Right Corner ---")
print("Move your mouse to the BOTTOM-RIGHT corner of your target area.")
input("Press Enter when your mouse is in position...")
bottomRight_x, bottomRight_y = pyautogui.position()
print(f"Bottom-Right corner recorded at: ({bottomRight_x}, {bottomRight_y})\n")

# Calculate width and height
width = bottomRight_x - topLeft_x
height = bottomRight_y - topLeft_y

print("--- Your Region Info ---")
print(f"TARGET_REGION = ({topLeft_x}, {topLeft_y}, {width}, {height})")
print("Copy the line above into your main script.")