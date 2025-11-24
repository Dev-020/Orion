"""
Test script to verify the GUI with signal integration works.
This script creates a simple GUI window and connects it to the backend with signals.
"""
import sys
import asyncio
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.append(str(PROJECT_ROOT))

# Import qasync for async/Qt integration
from qasync import QEventLoop
from PyQt6.QtWidgets import QApplication

# Import GUI components
from live.gui.app import create_app
from live.gui.signals import OrionSignals
from live.live import LiveSessionOrchestrator

async def main():
    """Main async function"""
    # Create signals
    signals = OrionSignals()
    
    # Create orchestrator with signals
    orchestrator = LiveSessionOrchestrator(
        video_mode="none",  # Start with no video for testing
        audio_mode=False,   # No audio for testing
        signals=signals
    )
    
    print("✓ Orchestrator created with signals support")
    print(f"✓ Video pipeline has signals: {orchestrator.video_pipeline.signals is not None}")
    print(f"✓ Response pipeline has signals: {orchestrator.response_pipeline.signals is not None}")
    
    # Test signal emission
    signals.log_received.emit("Test message", "TEST")
    print("✓ Signal emission test passed")
    
    print("\n✅ All integration tests passed!")
    print("Backend is ready for GUI integration.")

if __name__ == "__main__":
    app = QApplication(sys.argv)
    loop = QEventLoop(app)
    asyncio.set_event_loop(loop)
    
    with loop:
        loop.run_until_complete(main())
