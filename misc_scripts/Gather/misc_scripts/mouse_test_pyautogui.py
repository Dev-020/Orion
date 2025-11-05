# mouse_test_pyautogui.py
import pyautogui
import time

print("--- PyAutoGUI Mouse Test ---")
print("Switch to your game window NOW. Test will begin in 5 seconds.")
for i in range(5, 0, -1):
    print(f"{i}...", end="", flush=True)
    time.sleep(1)
print("\nTest active! Press Ctrl+C in this terminal to stop.")
print("Watch your in-game mouse cursor.")

pyautogui.FAILSAFE = True

try:
    while True:
        print("Moving mouse left with pyautogui...")
        # Move 50 pixels left from current position over 0.25s
        pyautogui.moveRel(-500, 0, duration=0.25) 
        time.sleep(2)
        
        print("Moving mouse right with pyautogui...")
        # Move 50 pixels right from current position over 0.25s
        pyautogui.moveRel(500, 0, duration=0.25)
        time.sleep(2)

except KeyboardInterrupt:
    print("\nPyAutoGUI test stopped.")