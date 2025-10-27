# find_pixel_coords.py
import pyautogui
import time

print("Move your mouse over the red '(Focused)' text in-game.")
print("Switch back here and press Ctrl+C to get the coordinates.")

try:
    while True:
        x, y = pyautogui.position()
        position_str = f'X: {str(x).rjust(4)} Y: {str(y).rjust(4)}'
        print(position_str, end='')
        print('\b' * len(position_str), end='', flush=True)
        time.sleep(0.1)
except KeyboardInterrupt:
    print("\nDone.")