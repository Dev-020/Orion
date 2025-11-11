# fish/tune_hsv.py
import cv2
import numpy as np

# --- CONFIGURATION ---
# 1. Put a screenshot of your game (with an arrow or "!") in the 'fish' folder
IMAGE_TO_TEST = 'fish/my_screenshot1.png' 
# 2. (Optional) Resize so it fits on your screen
RESIZE_PERCENT = 50 
# ---------------------

def on_trackbar(val):
    # This function does nothing but is required by OpenCV
    pass

# Load the image
image = cv2.imread(IMAGE_TO_TEST)
if image is None:
    print(f"ERROR: Could not load image at '{IMAGE_TO_TEST}'")
    exit()

# Resize
if RESIZE_PERCENT != 100:
    width = int(image.shape[1] * RESIZE_PERCENT / 100)
    height = int(image.shape[0] * RESIZE_PERCENT / 100)
    image = cv2.resize(image, (width, height), interpolation=cv2.INTER_AREA)

# --- NEW: Crop to the same ROI as the perception script ---
# We slice the image to get the top 75%, ignoring the bottom
# (where the tension bar is).
full_height = image.shape[0]
roi_height = int(full_height * 0.75) # Crop to top 75%

# This is a super-fast numpy array slice
image = image[0:roi_height, :] 
# --- END NEW SECTION ---

# Convert to HSV
image_hsv = cv2.cvtColor(image, cv2.COLOR_BGR2HSV)

# Create a window to hold the controls
cv2.namedWindow('Trackbars')
cv2.resizeWindow('Trackbars', 600, 300)

# Create trackbars for H, S, V (Lower and Upper)
# Use your last good values as the starting point
cv2.createTrackbar('H_MIN', 'Trackbars', 10, 179, on_trackbar)
cv2.createTrackbar('S_MIN', 'Trackbars', 190, 255, on_trackbar)
cv2.createTrackbar('V_MIN', 'Trackbars', 150, 255, on_trackbar)
cv2.createTrackbar('H_MAX', 'Trackbars', 30, 179, on_trackbar) # Your value from the screenshot
cv2.createTrackbar('S_MAX', 'Trackbars', 255, 255, on_trackbar)
cv2.createTrackbar('V_MAX', 'Trackbars', 255, 255, on_trackbar)

print("Tuning started. Move the sliders in the 'Trackbars' window.")
print("Your goal is to make the 'Mask' window show ONLY the arrows/!")
print("Press 'q' to quit and print your final values.")

while True:
    # 1. Read the slider values
    h_min = cv2.getTrackbarPos('H_MIN', 'Trackbars')
    s_min = cv2.getTrackbarPos('S_MIN', 'Trackbars')
    v_min = cv2.getTrackbarPos('V_MIN', 'Trackbars')
    h_max = cv2.getTrackbarPos('H_MAX', 'Trackbars')
    s_max = cv2.getTrackbarPos('S_MAX', 'Trackbars')
    v_max = cv2.getTrackbarPos('V_MAX', 'Trackbars')

    # 2. Create the lower and upper bounds
    lower_bound = np.array([h_min, s_min, v_min])
    upper_bound = np.array([h_max, s_max, v_max])

    # 3. Create the mask
    mask = cv2.inRange(image_hsv, lower_bound, upper_bound)

    # 4. (Optional) Show the result
    result = cv2.bitwise_and(image, image, mask=mask)

    # 5. Display the windows
    cv2.imshow('Original Image (Cropped)', image) # <-- Name changed
    cv2.imshow('Mask (Your Goal)', mask)
    cv2.imshow('Result (What the bot sees)', result)

    # Wait for 'q' key to be pressed
    if cv2.waitKey(1) & 0xFF == ord('q'):
        break

# Print the final values for you to copy
print("\n--- Your Tuned Values ---")
print(f"ORANGE_LOWER = np.array([{h_min}, {s_min}, {v_min}])")
print(f"ORANGE_UPPER = np.array([{h_max}, {s_max}, {v_max}])")

cv2.destroyAllWindows()