import subprocess
import time
import os
import keyboard
import dotenv
from obswebsocket import obsws, requests
from pathlib import Path
import threading
import sys

# --- NEW IMPORTS for Graceful Shutdown ---
# pywin32 is required: pip install pywin32
try:
    import win32gui
    import win32con
    import win32process
    WINDOWS_LIBS_AVAILABLE = True
except ImportError:
    WINDOWS_LIBS_AVAILABLE = False
    # Define mocks or handle absence later
    win32gui = None
    win32con = None
    win32process = None

# --- NEW IMPORTS for Watchdog and File Handling ---
import mimetypes
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

sys.path.append(str(Path(__file__).resolve().parent.parent))
from main_utils import config

dotenv.load_dotenv()

# --- 1. CONFIGURE YOUR SETTINGS ---
if os.name == 'nt':
    OBS_PATH = r"C:\Program Files\obs-studio\bin\64bit\obs64.exe"
else:
    # Default Linux path, user might need to adjust or add to PATH
    OBS_PATH = "obs"
WEBSOCKET_PASSWORD = os.getenv("OBS_WEBSOCKET_PASSWORD", "no_password")
PROFILE="Orion"
SAVE_HOTKEY = "`"
REPLAY_TIMER = 30

# --- !!! IMPORTANT: SET THIS !!! ---
# Set this to the *exact* folder where OBS saves your replays.
# Find it in OBS -> Settings -> Output -> Replay Buffer -> Output Path
REPLAY_SAVE_PATH = str(config.PROJECT_ROOT / "databases" / config.PERSONA / "video_replays")

# --- 2. GLOBAL VARIABLES ---
obs_client = None
obs_process = None
file_observer = None # NEW: For the watchdog observer
auto_replay_thread = None # NEW: For the automatic replay thread
stop_auto_replay_event = threading.Event() # NEW: To control the auto-replay loop

# --- 3. CORE FUNCTIONS (No changes to launch, connect, or trigger) ---

def launch_obs_hidden():
    """Launches OBS, minimizes it, and starts the replay buffer."""
    global obs_process
    print("Launching OBS (hidden)...")
    
    obs_directory = os.path.dirname(OBS_PATH)
    
    startup_args = [
        OBS_PATH,
        "--profile", PROFILE,
        "--startreplaybuffer"
        #"--minimize-to-tray"
    ]
    
    try:
        obs_process = subprocess.Popen(startup_args, cwd=obs_directory)
        print("OBS launched with 'Orion' profile and replay buffer acti`ve.")
        
    except Exception as e:
        print(f"Error launching OBS: {e}")
        print("Please check that OBS_PATH is correct.")
        exit()

def connect_to_obs():
    """Connects to the OBS WebSocket server."""
    global obs_client
    obs_client = obsws("localhost", 4455, WEBSOCKET_PASSWORD)
    retries = 10
    for i in range(retries):
        try:
            obs_client.connect()
            print("Successfully connected to OBS WebSocket!")
            return True
        except Exception as e:
            print(f"Connection failed (Attempt {i+1}/{retries})...")
            time.sleep(2)
    print("Could not connect to OBS. Exiting.")
    return False

def trigger_replay_save():
    """Sends the command to OBS to save the current replay buffer."""
    if obs_client:
        try:
            print(f"Hotkey '{SAVE_HOTKEY}' pressed! Sending command...")
            obs_client.call(requests.SaveReplayBuffer())
            print(">>> Replay Save command sent!")
        except Exception as e:
            print(f"Error sending 'SaveReplayBuffer' command: {e}")

# --- NEW: Automatic Replay Buffer Thread ---

def _auto_replay_loop():
    """The main loop for the automatic replay saving thread."""
    print("[Vision] Auto-replay thread started.")
    while not stop_auto_replay_event.is_set():
        # Wait for 30 seconds, but check for the stop event every second
        # This makes the thread more responsive to shutdown commands.
        if stop_auto_replay_event.wait(REPLAY_TIMER):
            break # Exit if the event was set during the wait
        
        print("[Vision] 30-second interval reached. Saving replay...")
        trigger_replay_save()

def start_vision_thread():
    """Starts the automatic replay saving thread."""
    global auto_replay_thread
    if auto_replay_thread is None or not auto_replay_thread.is_alive():
        stop_auto_replay_event.clear()
        auto_replay_thread = threading.Thread(target=_auto_replay_loop, daemon=True)
        auto_replay_thread.start()

# --- NEW, CORRECTED HELPER FUNCTION ---
# (Replace your old get_window_handle_for_pid with this)

def get_window_handle_for_pid(pid):
    """
    Finds the main window handle (HWND) for a given Process ID (PID).
    This version does NOT check for visibility, so it can find
    windows that are minimized to the tray.
    """
    if not WINDOWS_LIBS_AVAILABLE:
        return None

    result_hwnd = None
    
    def callback(hwnd, _):
        nonlocal result_hwnd # We want to modify the outer variable
        
        # Get the PID for the window
        _, found_pid = win32process.GetWindowThreadProcessId(hwnd)
        
        if found_pid == pid:
            # Found it. Store the handle.
            result_hwnd = hwnd
            # Stop enumerating. We found our match.
            return False 
        
        # Continue enumerating
        return True 

    # Enumerate all top-level windows
    try:
        win32gui.EnumWindows(callback, None)
    except Exception as e:
        # This can happen if a window is destroyed during enumeration
        print(f"[Debug] Error during window enumeration: {e}")
        
    return result_hwnd

# --- 4. MODIFIED: SHUTDOWN FUNCTION ---

def shutdown_obs():
    """
    Gracefully stops the file observer, replay buffer, disconnects,
    and *politely requests* the OBS process to close.
    """
    global obs_client, obs_process, file_observer, auto_replay_thread
    
    print("\nShutting down...")

    # 1. Stop the file observer (no change)
    if file_observer:
        try:
            print("Stopping file observer...")
            file_observer.stop()
            file_observer.join() 
            print("File observer stopped.")
        except Exception as e:
            print(f"Error stopping file observer: {e}")

    # NEW: Stop the auto-replay thread
    if auto_replay_thread and auto_replay_thread.is_alive():
        print("Stopping auto-replay thread...")
        stop_auto_replay_event.set()
        auto_replay_thread.join(timeout=2)
        print("Auto-replay thread stopped.")
    
    # 2. Stop OBS replay buffer (no change)
    if obs_client:
        try:
            print("Stopping Replay Buffer...")
            obs_client.call(requests.StopReplayBuffer())
            time.sleep(0.5) 
        except Exception as e:
            print(f"Could not politely stop buffer (will terminate anyway): {e}")
        
        obs_client.disconnect()
        print("WebSocket client disconnected.")
    
    # --- 3. MODIFIED: Terminate OBS process ---
    if obs_process:
        try:
            print("Sending graceful close request to OBS...")
            
            # Find the main window handle for our OBS process
            hwnd = None
            if WINDOWS_LIBS_AVAILABLE:
                hwnd = get_window_handle_for_pid(obs_process.pid)
            
            if hwnd:
                # Send the WM_CLOSE message (like clicking the 'X')
                win32gui.PostMessage(hwnd, win32con.WM_CLOSE, 0, 0)
                
                # Wait for the process to exit
                obs_process.wait(timeout=30) # Give it 30s to shut down
                print("OBS process closed gracefully.")
            
            else:
                # Fallback if we couldn't find the window handle or strictly Linux (no win32)
                print("Could not find OBS window handle or running on Linux. Falling back to terminate().")
                obs_process.terminate()
                obs_process.wait(timeout=5)
                print("OBS process terminated (fallback).")
                
        except Exception as e:
            # Catch errors (like "timeout expired" if it's stuck)
            print(f"Error during graceful shutdown: {e}")
            print("Forcing termination...")
            try:
                obs_process.kill() # Last resort
                obs_process.wait(timeout=30)
                print("OBS process killed.")
            except Exception as kill_e:
                print(f"Could not kill OBS: {kill_e}")
                
        finally:
            obs_process = None # Clear the global
            
    print("Shutdown complete.")

# --- 5. NEW: WATCHDOG FILE MONITOR ---

class ReplayFileHandler(FileSystemEventHandler):
    """A watchdog event handler that waits for new files and calls a callback."""
    
    def __init__(self, callback_function):
        self.callback = callback_function
        self.processing = False # Simple lock to avoid double-triggers
        
    def on_created(self, event):
        """Called when a file or directory is created."""
        if not event.is_directory and not self.processing:
            
            file_path = event.src_path
            print(f"\n[Watchdog] New file detected: {file_path}")
            
            # This lock prevents a rapid-fire on_created/on_modified
            # from triggering the upload multiple times for the same file.
            self.processing = True 
            
            try:
                # Give OBS a moment (e.g., 2s) to finish writing and 
                # release the file lock.
                time.sleep(2.0) 
                
                # Now, pass the *safe* file path to the callback function
                print(f"[Watchdog] Processing file: {file_path}")
                self.callback(file_path)
                
            except Exception as e:
                print(f"[Watchdog] Error processing file {file_path}: {e}")
            finally:
                # Release the lock after a small delay
                time.sleep(1) # Extra buffer
                self.processing = False

def start_replay_watcher(path, callback_func):
    """Starts the watchdog observer in a separate thread."""
    global file_observer
    if not os.path.exists(path):
        print(f"[Watchdog] Replay path not found: {path}. Creating it now...")
        try:
            os.makedirs(path, exist_ok=True)
            print(f"[Watchdog] Successfully created directory: {path}")
        except Exception as e:
            print(f"[ERROR] Could not create directory {path}: {e}")
            return False
        
    event_handler = ReplayFileHandler(callback_func)
    file_observer = Observer()
    file_observer.schedule(event_handler, path, recursive=False)
    
    try:
        file_observer.start()
        print(f"Watching for new replays in: {path}")
        return True
    except Exception as e:
        print(f"Could not start file observer: {e}")
        return False

# --- 6. MODIFIED: MAIN EXECUTION ---

def main(file_processor_callback):
    """
    Main script function to be called from your LLM script.
    
    :param file_processor_callback: A function that will be called
                                  when a new file is saved. This function
                                  must accept one argument: the file path (str).
    """
    try:
        launch_obs_hidden()
        
        if not connect_to_obs():
            return

        # Start the file watcher
        if not start_replay_watcher(REPLAY_SAVE_PATH, file_processor_callback):
            # If watcher fails, we must shut down
            raise Exception("Failed to start file watcher. Check REPLAY_SAVE_PATH.")

        keyboard.add_hotkey(SAVE_HOTKEY, trigger_replay_save)
        print(f"Hotkey '{SAVE_HOTKEY}' is active.")
        print("Script is running. Press Ctrl+C in this window to stop.")
        
        while True:
            # Keep the main thread alive.
            # Your main LLM script's loop will handle this.
            time.sleep(0.1)
            
    except (KeyboardInterrupt, Exception) as e:
        if isinstance(e, KeyboardInterrupt):
            print("\nKeyboard interrupt detected. Stopping script...")
        else:
            print(f"\nAn error occurred: {e}")
    finally:
        # Call our new, clean shutdown function
        shutdown_obs()

# --- 7. NEW: EXAMPLE USAGE BLOCK ---

if __name__ == "__main__":
    # --- This block runs when you execute this script *directly* ---
    # --- It's an example of how your LLM script will use it ---
    
    def example_file_processor(file_path):
        """`
        This is an example callback function.
        Your main LLM script will pass its *own* function here.
        This function will have access to 'self' and 'self.client'.
        """
        print(f"\n[Example Processor] Received new file: {file_path}")
        
        # 1. Get display name
        display_name = os.path.basename(file_path)
        
        # 2. Guess MIME type
        mime_type, _ = mimetypes.guess_type(file_path)
        if mime_type is None:
            mime_type = "application/octet-stream" # Default
        
        # 3. Read bytes
        try:
            with open(file_path, 'rb') as f:
                file_bytes = f.read()
            
            print(f"  - Name: {display_name}")
            print(f"  - Type: {mime_type}")
            print(f"  - Size: {len(file_bytes) / (1024*1024):.2f} MB")
            
            # ----------------------------------------------------
            # In your REAL script, you would do this:
            #
            # print("  - Uploading to LLM...")
            # # 'self' would be your LLM class instance
            # # self.upload_file(file_bytes, display_name, mime_type) ``
            # ----------------------------------------------------
            
        except Exception as e:
            print(f"  - Error reading file: {e}")

    # Start the main loop, passing in our example processor
    # Your LLM script will call main() in a similar way.
    main(example_file_processor)