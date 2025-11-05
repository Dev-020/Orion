# mouse_test_pydirectinput.py
import pydirectinput
import time

# --- Make sure pydirectinput is installed: pip install pydirectinput ---

print("--- PyDirectInput Mouse Test ---")
print("Switch to your game window NOW. Test will begin in 5 seconds.")
for i in range(5, 0, -1):
    print(f"{i}...", end="", flush=True)
    time.sleep(1)
print("\nTest active! Press Ctrl+C in this terminal to stop.")
print("Watch your in-game mouse cursor.")

pydirectinput.FAILSAFE = True

try:
    while True:
        print("Moving mouse left with pydirectinput...")
        # Move 50 pixels left from current position over 0.25s
        pydirectinput.moveRel(-500, 0, duration=5, relative=True) 
        time.sleep(2)
        
        print("Moving mouse right with pydirectinput...")
        # Move 50 pixels right from current position over 0.25s
        pydirectinput.moveRel(500, 0, duration=5, relative=True)
        time.sleep(2)

except KeyboardInterrupt:
    print("\nPyDirectInput test stopped.")