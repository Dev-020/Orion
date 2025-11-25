"""
GUI Application Entry Point for Orion Live
"""
import sys
import asyncio
import threading
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

from PyQt6.QtWidgets import QApplication

from live.gui.main_window import MainWindow
from live.live import LiveSessionOrchestrator

def run_backend_thread(orchestrator):
    """Run backend in separate thread with its own event loop"""
    print("Backend thread starting...")
    try:
        asyncio.run(orchestrator.run())
    except Exception as e:
        print(f"Backend error: {e}")
        import traceback
        traceback.print_exc()

def main():
    """Main function"""

    def toggle_session():
        """Toggle between starting and stopping the session."""
        nonlocal backend_thread
        
        # If running, stop it
        if orchestrator.shutdown_requested is False:
            print("Stopping session...")
            orchestrator.stop_session()
        else:
            # If stopped, start a new one
            print("Starting new session...")
            
            # Reset shutdown flag
            orchestrator.shutdown_requested = False
            
            # Create new thread if the old one is dead
            if backend_thread is None or not backend_thread.is_alive():
                backend_thread = threading.Thread(
                    target=run_backend_thread, 
                    args=(orchestrator,), 
                    daemon=True
                )
                backend_thread.start()
    
    app = QApplication(sys.argv)
    
    # Create main window
    window = MainWindow()
    window.show()
    
    # Create orchestrator with GUI signals
    print("Creating orchestrator...")
    orchestrator = LiveSessionOrchestrator(
        video_mode="window",
        audio_mode=True,
        signals=window.signals
    )
    print("Orchestrator created successfully")

    # [NEW] Connect GUI signals to Backend Orchestrator
    print("Connecting GUI signals...")
    
    # 1. Send Message
    # Connect the chat panel's signal to the orchestrator's submit method
    window.chat_panel.message_sent.connect(orchestrator.submit_user_message)
        
    # 2. Window Selection (Request)
    # CORRECTED: Signal name is 'refresh_windows'
    window.control_panel.refresh_windows.connect(orchestrator.request_window_list)
    
    # 3. Window Selection (Response)
    # [NEW] Connect the orchestrator's response signal to the control panel's update method
    window.signals.window_list_updated.connect(window.control_panel.update_window_list)
    
    # 4. Session Toggle (Start/Stop)
    # [NEW] Connect to toggle_session instead of stop_session
    # Remove the old connection to window.close if you added it!
    try:
        window.control_panel.stop_session.disconnect()
    except:
        pass
        
    window.control_panel.stop_session.connect(toggle_session)

    # 5. Window Selection (Action)
    # [NEW] Connect the dropdown selection signal to the orchestrator
    window.control_panel.window_changed.connect(orchestrator.select_window_by_hwnd)
    
    # 6. Token Usage (Display)
    window.signals.token_usage_updated.connect(window.video_display.update_token_display)
    
    # 7. Stats
    window.signals.stats_updated.connect(window.video_display.update_stats)
    window.control_panel.stats_toggled.connect(window.video_display.toggle_stats)

    print("GUI signals connected")
    
    # Run backend in separate daemon thread
    backend_thread = threading.Thread(
        target=run_backend_thread,
        args=(orchestrator,),
        daemon=True
    )
    backend_thread.start()
    print("Backend thread started")
    
    # Run Qt event loop (blocking)
    sys.exit(app.exec())

if __name__ == "__main__":
    main()

