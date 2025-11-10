# fish/utils.py
# Helper functions for screen capture and template matching

import cv2
import mss
import numpy as np

def capture_screen_gray(sct, monitor=1):
    """
    Captures the specified monitor and returns it as a grayscale OpenCV image.
    Monitor 1 is typically the primary monitor.
    """
    # Grab the monitor
    sct_img = sct.grab(sct.monitors[monitor])
    
    # Convert to an OpenCV image
    screen_cv = np.array(sct_img)
    
    # Convert to grayscale
    screen_gray = cv2.cvtColor(screen_cv, cv2.COLOR_BGR2GRAY)
    return screen_gray

def find_template(screen_gray, template_cv, threshold):
    """
    Finds a template image on the screen.
    Returns (x, y) coordinates of the center, or None.
    """
    # Run template matching
    res = cv2.matchTemplate(screen_gray, template_cv, cv2.TM_CCOEFF_NORMED)
    
    # Get the best match
    min_val, max_val, min_loc, max_loc = cv2.minMaxLoc(res)
    
    if max_val >= threshold:
        # Get the size of the template
        h, w = template_cv.shape[:2]
        
        # Calculate the center of the found object
        center_x = max_loc[0] + w // 2
        center_y = max_loc[1] + h // 2
        return (center_x, center_y)
        
    return None