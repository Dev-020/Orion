import json
import os
import time
from datetime import datetime, timezone
from typing import Optional
from pathlib import Path

# Import system_log from live_ui (assuming Orion root is in sys.path)
import sys
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

from main_utils import config
from live.live_ui import system_log

# Session state file path
SESSION_STATE_FILE = os.path.join(config.PROJECT_ROOT, "data", "live_session_state.json")

class LiveSessionState:
    """Manages Live API session state for resumption."""
    
    def __init__(self, state_file: str = SESSION_STATE_FILE):
        self.state_file = state_file
        self.resumption_handle = None
        self.session_id = None
        self.last_update = None
        self._ensure_state_directory()
    
    def _ensure_state_directory(self):
        """Ensure the directory for state file exists."""
        state_dir = os.path.dirname(self.state_file)
        if state_dir and not os.path.exists(state_dir):
            os.makedirs(state_dir, exist_ok=True)
    
    def load_state(self) -> Optional[str]:
        """
        Load saved resumption handle.
        Automatically handles expiration (2-hour window from last update).
        Returns None if handle is expired or doesn't exist.
        """
        try:
            if os.path.exists(self.state_file):
                with open(self.state_file, 'r') as f:
                    state = json.load(f)
                    self.resumption_handle = state.get("resumption_handle")
                    self.session_id = state.get("session_id")
                    self.last_update = state.get("last_update")
                    
                    # Check if handle is still valid (2 hour window from last update)
                    if self.last_update:
                        try:
                            # Parse timestamp (handle both with and without 'Z' suffix)
                            last_update_str = self.last_update.replace('Z', '+00:00')
                            last_update_time = datetime.fromisoformat(last_update_str)
                            time_diff = (datetime.now(timezone.utc) - last_update_time).total_seconds()
                            
                            if time_diff > 7200:  # 2 hours = 7200 seconds
                                hours_old = time_diff / 3600
                                system_log.info(f"Resumption handle expired ({hours_old:.1f} hours old, >2 hour limit). Starting new session.", category="SESSION")
                                self.clear_state()
                                return None
                            else:
                                # Handle is still valid
                                hours_remaining = (7200 - time_diff) / 3600
                                if self.resumption_handle:
                                    system_log.info(f"Loaded resumption handle: {self.resumption_handle[:30]}... (valid for {hours_remaining:.1f} more hours)", category="SESSION")
                                    return self.resumption_handle
                        except (ValueError, TypeError) as e:
                            system_log.info(f"Error parsing timestamp '{self.last_update}': {e}. Starting new session.", category="SESSION")
                            self.clear_state()
                            return None
                    else:
                        # No timestamp, assume expired
                        system_log.info("No timestamp in session state. Starting new session.", category="SESSION")
                        self.clear_state()
                        return None
        except json.JSONDecodeError as e:
            system_log.info(f"Error parsing session state file (corrupted?): {e}. Starting new session.", category="SESSION")
            self.clear_state()
            return None
        except Exception as e:
            system_log.info(f"Error loading session state: {e}. Starting new session.", category="SESSION")
            return None
        
        return None
    
    def save_state(self, resumption_handle: str, session_id: Optional[str] = None):
        """Save resumption handle for future use."""
        try:
            state = {
                "resumption_handle": resumption_handle,
                "session_id": session_id or self.session_id,
                "last_update": datetime.now(timezone.utc).isoformat()
            }
            with open(self.state_file, 'w') as f:
                json.dump(state, f, indent=2)
            self.resumption_handle = resumption_handle
            if session_id:
                self.session_id = session_id
            self.last_update = state["last_update"]
            system_log.info(f"Saved resumption handle: {resumption_handle[:30]}...", category="SESSION")
        except Exception as e:
            system_log.info(f"Error saving session state: {e}", category="SESSION")
    
    def clear_state(self):
        """Clear saved state (after successful resumption or expiration)."""
        try:
            if os.path.exists(self.state_file):
                os.remove(self.state_file)
            self.resumption_handle = None
            self.session_id = None
            self.last_update = None
            system_log.info("Cleared session state", category="SESSION")
        except Exception as e:
            system_log.info(f"Error clearing session state: {e}", category="SESSION")
