import os
from pathlib import Path

# Import system_log from live_ui
try:
    from test_utils.live.live_ui import system_log
except ImportError:
    import sys
    sys.path.append(str(Path(__file__).resolve().parent.parent.parent.parent))
    from test_utils.live.live_ui import system_log

# Check if debug mode is enabled
VIDEO_DEBUG = os.getenv("VIDEO_DEBUG", "false").lower() == "true"

class GoAwayReconnection(Exception):
    """Exception raised when GoAway is received to trigger reconnection."""
    pass

class ConnectionManager:
    """Manages connection health and error handling."""
    
    def __init__(self):
        self.connection_alive = False
        self.connection_error_count = 0
        self.max_connection_errors = 3
        self.goaway_received = False
        self.session = None  # Reference to the active session
    
    def set_session(self, session):
        """Set the active session."""
        self.session = session

    def is_healthy(self) -> bool:
        """
        Check if the connection is healthy and ready to accept input.
        Returns False if connection is dead, None, or too many errors occurred.
        """
        if not self.connection_alive:
            return False
        if self.session is None:
            return False
        if self.goaway_received:
            return False
        if self.connection_error_count >= self.max_connection_errors:
            return False
        return True
    
    def mark_dead(self, reason: str = "Unknown"):
        """Mark connection as dead and log the reason."""
        if self.connection_alive:  # Only log if it was previously alive
            system_log.info(f"Marking connection as dead: {reason}", category="CONNECTION")
        self.connection_alive = False
        self.connection_error_count = 0  # Reset counter
    
    def mark_alive(self):
        """Mark connection as alive and reset error counter."""
        if not self.connection_alive:
            system_log.info("Connection marked as alive", category="CONNECTION")
        self.connection_alive = True
        self.connection_error_count = 0
    
    def handle_error(self, error: Exception) -> bool:
        """
        Handle connection errors and determine if connection should be marked as dead.
        Returns True if connection should be considered dead, False otherwise.
        """
        error_str = str(error).lower()
        error_type = type(error).__name__
        
        # Check for specific error patterns that indicate dead connection
        dead_connection_indicators = [
            "deadline expired",
            "connection closed",
            "connection reset",
            "connection aborted",
            "broken pipe",
            "1011",  # WebSocket close code for internal error
            "websocket",
            "session expired",
            "invalid session",
        ]
        
        # Increment error counter
        self.connection_error_count += 1
        
        # Check if error indicates dead connection
        is_dead = any(indicator in error_str for indicator in dead_connection_indicators)
        
        if is_dead or self.connection_error_count >= self.max_connection_errors:
            self.mark_dead(f"{error_type}: {error}")
            return True
        
        # For transient errors, just log and continue
        if self.connection_error_count < self.max_connection_errors:
            if VIDEO_DEBUG:
                system_log.info(f"Transient error ({self.connection_error_count}/{self.max_connection_errors}): {error_type}: {error}", category="CONNECTION")
        
        return False
