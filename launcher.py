
import sys
from pathlib import Path

# Add project root to sys.path just in case
sys.path.append(str(Path(__file__).resolve().parent))

try:
    from launcher_app.main import OrionLauncherApp
except ImportError as e:
    print(f"Failed to import Launcher App: {e}")
    print("Ensure 'textual' is installed: pip install textual")
    sys.exit(1)

if __name__ == "__main__":
    app = OrionLauncherApp()
    app.run()
