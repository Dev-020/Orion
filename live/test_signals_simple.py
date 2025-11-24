"""
Simple test to verify signals integration without running Qt application.
"""
import sys
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.append(str(PROJECT_ROOT))

from live.gui.signals import OrionSignals
from live.modules.video_pipeline import VideoPipeline
from live.modules.response_pipeline import ResponsePipeline
from live.modules.connection_manager import ConnectionManager  
from live.modules.session_manager import LiveSessionState

def test_signals_integration():
    """Test that pipelines accept and store signals"""
    
    # Create signals
    signals = OrionSignals()
    print("✓ Created OrionSignals")
    
    # Create connection manager and session state
    connection_manager = ConnectionManager()
    session_state = LiveSessionState()
    print("✓ Created ConnectionManager and LiveSessionState")
    
    # Create video pipeline with signals
    video_pipeline = VideoPipeline(connection_manager, mode="screen", signals=signals)
    print(f"✓ Created VideoPipeline with signals: {video_pipeline.signals is not None}")
    
    # Create response pipeline with signals  
    response_pipeline = ResponsePipeline(connection_manager, session_state, signals=signals)
    print(f"✓ Created ResponsePipeline with signals: {response_pipeline.signals is not None}")
    
    # Verify signals are the same object
    assert video_pipeline.signals is signals, "VideoPipeline signals mismatch"
    assert response_pipeline.signals is signals, "ResponsePipeline signals mismatch"
    print("✓ Signal references are correct")
    
    # Test signal emission
    test_results = []
    signals.log_received.connect(lambda msg, cat: test_results.append((msg, cat)))
    signals.log_received.emit("Test message", "TEST")
    assert len(test_results) == 1, "Signal not emitted"
    assert test_results[0] == ("Test message", "TEST"), "Signal data incorrect"
    print("✓ Signal emission test passed")
    
    print("\n✅ All integration tests passed!")
    print("✅ Backend is ready for GUI integration.")
    print("\nNext steps:")
    print("  1. Update live.py to accept signals parameter")
    print("  2. Emit signals from video and response pipelines")  
    print("  3. Connect signals to GUI widgets in main_window.py")

if __name__ == "__main__":
    test_signals_integration()
