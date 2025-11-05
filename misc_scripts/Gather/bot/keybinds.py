# keybinds.py
# This is the "Hotkey" thread.
# It uses the 'keyboard' library instead of 'pynput'.

from PyQt5.QtCore import QThread, pyqtSignal
import keyboard  # <-- Import the new library
from .state import BotState

class KeybindThread(QThread):
    """
    This thread's ONLY job is to listen for global hotkeys.
    It emits signals to the Main (GUI) thread.
    
    This version uses the 'keyboard' library, which may have
    different performance characteristics than 'pynput'.
    """
    # --- Signals (these are all unchanged) ---
    shutdown_signal = pyqtSignal()
    toggle_overlay_signal = pyqtSignal()
    status_print_signal = pyqtSignal(str) # From our previous fix

    def __init__(self, bot_state: BotState):
        super().__init__()
        self.bot_state = bot_state

    # --- [NEW] Callback functions for each hotkey ---

    def on_f10(self):
        """Callback for F10 (Pause/Resume)"""
        try:
            is_now_paused = self.bot_state.toggle_pause()
            status = f"\n--- HOTKEY: Bot is now {'PAUSED' if is_now_paused else 'RESUMED'} ---"
            self.status_print_signal.emit(status)
        except Exception as e:
            self.status_print_signal.emit(f"\n--- HOTKEY THREAD ERROR: {e} ---")

    def on_f11(self):
        """Callback for F11 (Toggle Overlay)"""
        try:
            self.status_print_signal.emit("\n--- HOTKEY: Toggling GUI Overlay Visibility ---")
            self.bot_state.set_overlay_visible(not self.bot_state.is_overlay_visible())
            self.toggle_overlay_signal.emit()
        except Exception as e:
            self.status_print_signal.emit(f"\n--- HOTKEY THREAD ERROR: {e} ---")

    def on_f12(self):
        """Callback for F12 (Shutdown)"""
        try:
            self.status_print_signal.emit("\n--- HOTKEY: Shutdown signal (F12) received. Stopping bot... ---")
            
            # 1. Tell worker threads to stop
            self.bot_state.stop() 
            
            # 2. Emit the signal to tell the GUI (Main Thread) to quit
            self.shutdown_signal.emit()
            
            # 3. Stop this listener (by breaking the run loop)
            # (The run loop will exit because bot_state is set to not running)

        except Exception as e:
            self.status_print_signal.emit(f"\n--- HOTKEY THREAD ERROR: {e} ---")

    def run(self):
        """
        Starts the keyboard listener.
        This function registers the hotkeys and then
        waits until the bot is no longer running.
        """
        print("Hotkey listener (F10=Pause, F11=Toggle Overlay, F12=Quit) is active.")
        
        try:
            # --- [NEW] Register hotkeys ---
            # This function maps a string to a callback function.
            # The 'keyboard' library manages these in its own background hook.
            keyboard.add_hotkey('f10', self.on_f10)
            keyboard.add_hotkey('f11', self.on_f11)
            keyboard.add_hotkey('f12', self.on_f12)

            # --- [NEW] Wait for shutdown signal ---
            # Unlike pynput's listener.join(), we just need this
            # QThread to stay alive until the bot shuts down.
            # We check the bot_state in a loop.
            while self.bot_state.is_bot_running():
                self.msleep(100) # Sleep for 100ms to save CPU
            
        except Exception as e:
            self.status_print_signal.emit(f"\n--- HOTKEY THREAD ERROR: {e} ---")
        
        finally:
            # --- [NEW] Cleanup ---
            print("Hotkey listener stopping...")
            keyboard.clear_all_hotkeys()
        
        print("Hotkey listener stopped.")