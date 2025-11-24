import sys
import asyncio
import qasync
from PyQt6.QtWidgets import QApplication
from PyQt6.QtGui import QIcon
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

from live.gui.main_window import MainWindow
from live.gui.styles import DARK_THEME

def main():
    # Create QApplication
    app = QApplication(sys.argv)
    app.setStyleSheet(DARK_THEME)
    
    # Setup qasync loop
    loop = qasync.QEventLoop(app)
    asyncio.set_event_loop(loop)
    
    # Create and show Main Window
    window = MainWindow()
    window.show()
    
    # Run event loop
    with loop:
        loop.run_forever()

if __name__ == "__main__":
    main()
