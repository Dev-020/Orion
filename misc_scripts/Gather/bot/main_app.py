# main_app.py
# This is the main launcher for the bot.
# It creates the transparent overlay, starts the worker threads,
# and brings everything together.

import sys
import pydirectinput
import time
import signal # For catching Ctrl+C
import threading
from ultralytics import YOLO # type: ignore

# --- Import PyQt5 ---
from PyQt5.QtWidgets import QApplication, QWidget, QLabel
from PyQt5.QtGui import QPixmap, QImage, QPainter
from PyQt5.QtCore import Qt, QThread, pyqtSignal, QRect

# --- Import Our Custom Modules ---
from . import config
from .state import BotState
from .utils import capture_game_window
from .vision import VisionThread
from .movement import MovementThread
from .keybinds import KeybindThread

# --- [FIXED] The "Click-Through" Overlay Window ---
class OverlayWindow(QWidget):
    """
    A borderless, transparent, "click-through" window that
    sits on top of the game to display debug info.
    """
    # --- [MODIFIED] Signal now accepts a QPixmap AND a string ---
    update_overlay_signal = pyqtSignal(QImage, str)

    def __init__(self, x, y, w, h):
        super().__init__()
        self.setGeometry(x, y, w, h)
        
        # Set all the window flags for the overlay
        self.setWindowFlags(
            Qt.FramelessWindowHint |
            Qt.WindowStaysOnTopHint
        )
        
        # --- THIS IS THE MAGIC "CLICK-THROUGH" FLAG ---
        self.setAttribute(Qt.WA_TransparentForMouseEvents, True) # type: ignore
        
        # --- YOUR FIX: Make the background transparent ---
        self.setAttribute(Qt.WA_TranslucentBackground, True) # type: ignore
        
        # --- [NEW] We don't use a QLabel. We'll store the pixmap ---
        # and paint it ourselves for true transparency.
        self.current_pixmap = QPixmap()

        # --- [NEW] Create the text label for FPS/State ---
        self.text_label = QLabel(self)
        self.text_label.setGeometry(10, 10, 400, 100) # Position top-left (w, h are max size)
        # Set styling: small white text, bold, with a faint black BG
        self.text_label.setStyleSheet(
            """
            QLabel {
                color: white;
                font-size: 10pt;
                font-weight: bold;
                background-color: rgba(0, 0, 0, 0.5);
                padding: 5px;
                border-radius: 5px;
            }
            """
        )
        self.text_label.setAlignment(Qt.AlignTop | Qt.AlignLeft)
        # This makes the label only as big as its text
        self.text_label.adjustSize() 
        # --- [END NEW] ---
        
        # Connect the signal from the Brain thread to our update slot
        self.update_overlay_signal.connect(self.update_overlay) # type: ignore
        
        if not config.DATA_COLLECTION_MODE and config.OVERLAY_VISIBILITY:
            print("Data Collection Mode is DISABLED. Overlay starts SHOWN.")
            self.setWindowOpacity(100)
        else:
            print("Overlay starts HIDDEN.")
            self.setWindowOpacity(0)
        self.show()

    # --- [FIX 2] ---
    # This slot now receives a QImage, not a QPixmap.
    # It also handles the console printing, making it thread-safe.
    def update_overlay(self, q_image, text):
        """
        Updates both the pixmap (boxes) and the text (status).
        This is a "slot" connected to the VisionThread signal.
        """
        
        # --- [NEW] Convert QImage to QPixmap safely in the GUI thread ---
        if not q_image.isNull():
            self.current_pixmap = QPixmap.fromImage(q_image)
        else:
            self.current_pixmap.fill(Qt.transparent) # Clear the pixmap
        
        self.text_label.setText(text)     # Update the FPS/Status text
        self.text_label.adjustSize()      # Resize label to fit new text
        self.update() # Trigger a repaint

        # --- [NEW] Handle printing safely in the main thread ---
        # This replaces the print from vision.py.
        # It won't deadlock, as it's the only thread printing in a loop.
        print(text, "        ", flush=True)

    def paintEvent(self, a0): # Renamed 'event' to 'a0' to satisfy linter
        """
        This is called every time self.update() is triggered.
        It draws the pixmap directly onto the transparent window.
        """
        if not self.current_pixmap.isNull():
            painter = QPainter(self)
            painter.drawPixmap(0, 0, self.current_pixmap)

    def update_geometry(self, region):
        """Moves and resizes the overlay to match the game window."""
        if region:
            x, y, w, h = region
            self.setGeometry(x, y, w, h)
            
    # --- [NEW] Slot to toggle visibility ---
    def toggle_visibility(self):
        """Slot to hide or show the overlay window."""
        print(self.windowOpacity())
        if self.windowOpacity():
            self.setWindowOpacity(0)
        else:
            self.setWindowOpacity(100)
    # --- [END NEW] ---

# --- The Main "Launcher" Function ---
def main():
    print("Starting Orion Gather Bot...")

    # --- 1. Load AI Model ---
    print("Loading AI model...")
    model = YOLO(config.MODEL_PATH)
    print("Model loaded successfully.")
    
    # --- 2. Find Game Window ---
    window_region, screenshot = capture_game_window()
    while not window_region:
        print(f"Searching for game window: '{config.WINDOW_TITLE}'...")
        # --- [NEW] Add a 5-second delay so you can switch to the game ---
        for i in range(5, 0, -1):
            print(f"Switch to game... {i}", end="\r", flush=True)
            time.sleep(1)
        
        window_region, screenshot = capture_game_window() # Uses config
        if window_region:
            print(f"\nGame window found at {window_region}. Launching overlay...")
            break
        
        print(f"\nCRITICAL: Game window '{config.WINDOW_TITLE}' not found.")
        print("Please start the game *and* make it the active window, then run again.")
    
    # --- 3. Create the Application & Shared State ---
    # We must create the QApplication *before* the threads
    app = QApplication(sys.argv)
    
    bot_state = BotState()
    bot_state.set_window_region(window_region) # Set initial position

    # --- 4. Create the GUI Overlay ---
    overlay = OverlayWindow(window_region[0], window_region[1], window_region[2], window_region[3])
    
    # --- 5. Create the Worker Threads ---
    print("Starting Vision (Brain) and Movement (Body) threads...")
    
    vision_worker = VisionThread(bot_state, model)
    movement_worker = MovementThread(bot_state)
    keybind_worker = KeybindThread(bot_state)
    
    # --- [NEW] Centralized shutdown slot ---
    # This function will be called by both F12 and Ctrl+C
    def handle_graceful_shutdown():
        print("\n--- Initiating graceful shutdown... ---")
        bot_state.stop() # Signal all worker threads to stop
        app.quit()       # Terminate the QApplication event loop

    # --- 6. Connect Signals ---
    # --- [MODIFIED] Connect to the new signal slot ---
    vision_worker.update_debug_frame_signal.connect(overlay.update_overlay_signal)
    # Connect the KeybindThread's shutdown signal to our centralized handler
    keybind_worker.shutdown_signal.connect(handle_graceful_shutdown)
    # --- [NEW] Connect the hotkey toggle signal to the overlay's slot ---
    keybind_worker.toggle_overlay_signal.connect(overlay.toggle_visibility)
    # --- Sends status messages from KeybindThread to console ---
    keybind_worker.status_print_signal.connect(lambda msg: print(msg, flush=True))
    
    # --- Handle Ctrl+C (SIGINT) for graceful shutdown ---
    # This lambda emits a PyQt signal, which is safer than direct calls
    signal.signal(signal.SIGINT, lambda sig, frame: handle_graceful_shutdown)
    
    # --- 7. Start Threads ---
    movement_worker.start()
    vision_worker.start()
    keybind_worker.start()

    print("Bot is now active!")
    print("--- F10 = Pause/Resume | F11 = Toggle Overlay | F12 = Quit | Ctrl+C = Quit ---")
    
    try:
        # Start the GUI event loop. This will block until appw.quit() is called.
        app.exec_() # We remove sys.exit() to allow for a cleaner shutdown

    finally:
        # --- 8. Cleanup ---
        print("Waiting for threads to stop...")
        # 3. Wait for threads to finish cleanly
        vision_worker.wait()
        movement_worker.wait()
        keybind_worker.wait()
        
        # 4. Failsafe: Make sure all keys are released on exit
        print("Releasing all keys as a failsafe...")
        pydirectinput.keyUp('w')
        pydirectinput.keyUp('a')
        pydirectinput.keyUp('s')
        pydirectinput.keyUp('d')
        print("All threads stopped. Script terminated.")


if __name__ == "__main__":
    main()