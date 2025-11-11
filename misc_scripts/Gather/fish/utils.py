# fish/utils.py
# Helper functions for screen capture, template matching, AND window management

import cv2
import mss
import numpy as np
import win32gui # <-- Added to utils
import win32con # <-- Added to utils

# --- Screen Capture & Template Matching (Unchanged) ---

def capture_screen(sct, monitor_object, format='gray'):
    """
    Captures the specified window region and returns an OpenCV image.
    format: 'gray', 'bgr' (color), or 'hsv'
    """
    sct_img = sct.grab(monitor_object)
    screen_cv = np.array(sct_img)
    
    if format == 'gray':
        return cv2.cvtColor(screen_cv, cv2.COLOR_BGR2GRAY)
    if format == 'bgr':
        return screen_cv
    if format == 'hsv':
        # Convert to BGR (from BGRA) and then to HSV
        screen_bgr = cv2.cvtColor(screen_cv, cv2.COLOR_BGRA2BGR)
        return cv2.cvtColor(screen_bgr, cv2.COLOR_BGR2HSV)
        
    return None # Should not happen

def find_template(screen_gray, template_cv, threshold):
    """
    Finds a template image on the screen.
    Returns (x, y) coordinates of the center, or None.
    """
    res = cv2.matchTemplate(screen_gray, template_cv, cv2.TM_CCOEFF_NORMED)
    min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(res)
    
    if max_val >= threshold:
        h, w = template_cv.shape[:2]
        center_x = max_loc[0] + w // 2
        center_y = max_loc[1] + h // 2
        return (center_x, center_y)
        
    return None

# --- NEW: Window Management Utilities ---

def find_game_window(window_title):
    """
    Finds the window handle (hwnd) for a window with a matching title.
    Returns the hwnd (int) or 0 if not found.
    """
    hwnd = win32gui.FindWindow(None, window_title)
    if hwnd == 0:
        # Window not found, try to find by partial title
        def enum_windows_proc(top_hwnd, results):
            if window_title in win32gui.GetWindowText(top_hwnd):
                results.append(top_hwnd)
        
        results = []
        win32gui.EnumWindows(enum_windows_proc, results)
        if results:
            hwnd = results[0]
            
    if hwnd == 0:
        raise IndexError(f"Window '{window_title}' not found.")
        
    return hwnd

def get_window_state(hwnd):
    """
    Takes a window handle (hwnd) and returns its current state.
    """
    try:
        # 1. Get Focus State
        is_focused = (hwnd == win32gui.GetForegroundWindow())
        
        # 2. Get Minimized State
        is_minimized = win32gui.IsIconic(hwnd)
        
        # 3. Get Position
        rect = win32gui.GetWindowRect(hwnd)
        left = rect[0]
        top = rect[1]
        width = rect[2] - left
        height = rect[3] - top
        
        # 4. Check if it's a valid, visible window
        is_valid = (width > 0 and height > 0) and not is_minimized
        
        monitor_object = {
            'left': left,
            'top': top,
            'width': width,
            'height': height
        }
        
        return {
            "is_focused": is_focused,
            "is_minimized": is_minimized,
            "is_valid": is_valid,
            "monitor_object": monitor_object
        }
        
    except Exception as e:
        # This happens if the window was closed (invalid handle)
        return {
            "is_focused": False,
            "is_minimized": True,
            "is_valid": False,
            "monitor_object": None
        }