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
    app = QApplication(sys.argv)
    
    # Create main window
    window = MainWindow()
    window.show()
    
    # Create orchestrator with GUI signals
    print("Creating orchestrator...")
    orchestrator = LiveSessionOrchestrator(
        video_mode="screen",
        audio_mode=False,
        signals=window.signals
    )
    print("Orchestrator created successfully")
    
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

