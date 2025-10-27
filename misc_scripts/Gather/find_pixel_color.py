# find_pixel_color.py
import pyautogui
import time

print("Move your mouse over the target pixel in the game.")
print("The script will print the X, Y, and RGB values.")
print("Press Ctrl+C to stop.")

try:
    while True:
        x, y = pyautogui.position()
        pixel_color = pyautogui.pixel(x, y)
        
        position_str = f'X: {str(x).rjust(4)} Y: {str(y).rjust(4)}  '
        color_str = f'RGB: ({str(pixel_color[0]).rjust(3)}, {str(pixel_color[1]).rjust(3)}, {str(pixel_color[2]).rjust(3)})'
        
        print(position_str + color_str, end='')
        print('\b' * (len(position_str) + len(color_str)), end='', flush=True)
        time.sleep(0.1)
        
except KeyboardInterrupt:
    print("\nDone.")