import asyncio
import time
from pathlib import Path

# Import system_log, conversation, and orion_tts
try:
    from test_utils.live.live_ui import system_log, conversation
    from test_utils.live.modules.connection_manager import GoAwayReconnection
except ImportError:
    import sys
    sys.path.append(str(Path(__file__).resolve().parent.parent.parent.parent))
    from test_utils.live.live_ui import system_log, conversation
    # We might need to adjust import for GoAwayReconnection if running differently
    # But since we are in modules, relative import should work if package
    # For now, assume absolute path works if sys.path is set
    from test_utils.live.modules.connection_manager import GoAwayReconnection

try:
    from system_utils import orion_tts
except ImportError:
    import sys
    sys.path.append(str(Path(__file__).resolve().parent.parent.parent.parent))
    from system_utils import orion_tts

# Check if debug mode is enabled
import os
VIDEO_DEBUG = False
PASSIVE_TIMER = 30

class ResponsePipeline:
    def __init__(self, connection_manager, session_manager):
        self.connection_manager = connection_manager
        self.session_manager = session_manager
        self.last_interaction_time = time.time()
        self.session_id = None # Will be set by live.py or session manager

    async def handle_responses(self):
        while True:
            try:
                turn = self.connection_manager.session.receive()
                async for response in turn:
                    if VIDEO_DEBUG:
                        system_log.info(f"Response type: {type(response)}", category="VIDEO")
                    
                    # Handle SessionResumptionUpdate messages
                    if hasattr(response, 'session_resumption_update') and response.session_resumption_update:
                        update = response.session_resumption_update
                        # Fix: Check for new_handle or handle
                        handle = getattr(update, 'new_handle', None) or getattr(update, 'handle', None)
                        
                        if handle:
                            system_log.info(f"Received resumption token: {handle[:30]}...", category="SESSION")
                            try:
                                self.session_manager.save_state(
                                    resumption_handle=handle,
                                    session_id=self.session_id
                                )
                                system_log.info(f"Resumption token saved successfully", category="SESSION")
                            except Exception as e:
                                system_log.info(f"ERROR: Failed to save resumption token: {e}", category="SESSION")
                        else:
                            if VIDEO_DEBUG:
                                system_log.info(f"SessionResumptionUpdate received but no handle found: {update}", category="SESSION")
                    
                    # Handle GoAway message (connection termination warning)
                    if hasattr(response, 'go_away') and response.go_away:
                        go_away = response.go_away
                        time_left_raw = getattr(go_away, 'time_left', 0)
                        
                        # Convert to integer (API may return string like '50s' or int)
                        time_left = 0
                        try:
                            if isinstance(time_left_raw, (int, float)):
                                time_left = int(time_left_raw)
                            elif isinstance(time_left_raw, str):
                                # Handle formats like '50s', '50', etc.
                                time_left_str = time_left_raw.strip().rstrip('sS').strip()
                                time_left = int(time_left_str) if time_left_str else 0
                            else:
                                time_left = int(time_left_raw) if time_left_raw else 0
                        except (ValueError, TypeError) as e:
                            system_log.info(f"Warning: Could not parse time_left '{time_left_raw}' ({type(time_left_raw).__name__}), defaulting to 0. Error: {e}", category="SESSION")
                            time_left = 0
                        
                        system_log.info(f"\n[SESSION] GoAway received. Time left: {time_left} seconds", category="SESSION")
                        self.connection_manager.goaway_received = True
                        # Mark connection as dead (will be reconnected)
                        self.connection_manager.mark_dead("GoAway message received")
                        # Trigger reconnection preparation (runs in background)
                        # We need to signal the main loop to handle GoAway
                        # Ideally, we raise exception here
                        raise GoAwayReconnection("GoAway received, reconnecting...")
                    
                    # Handle context window compression updates (optional monitoring)
                    if hasattr(response, 'context_window_compression_update') and response.context_window_compression_update:
                        if VIDEO_DEBUG:
                            update = response.context_window_compression_update
                            system_log.info(f"Context compression update: {update}", category="SESSION")
                    
                    # Handle text responses
                    if text := response.text:
                        orion_tts.process_stream_chunk(text)
                        conversation.stream_ai(text)
                
                orion_tts.flush_stream()
                conversation.flush_ai()
                
            except GoAwayReconnection:
                # Re-raise to propagate to TaskGroup and exit connection context
                raise
            except Exception as e:
                if not self.connection_manager.goaway_received:  # Don't log errors if we're expecting disconnection
                    system_log.info(f"Error in receive_audio: {e}", category="SESSION")
                # If connection is dead, raise to trigger reconnection
                if not self.connection_manager.connection_alive:
                    system_log.info(f"Connection dead in receive_audio, triggering reconnection...", category="SESSION")
                    raise GoAwayReconnection("Connection dead, reconnecting...")
                break

    async def passive_observer_task(self):
        """Passive observer that triggers AI commentary when user is quiet."""
        while True:
            # Check if AI is speaking first (cheap check)
            if orion_tts.IS_SPEAKING:
                self.last_interaction_time = time.time()
                await asyncio.sleep(1.0)
                continue
            
            # Check connection health before proceeding
            if not self.connection_manager.is_healthy():
                # Connection is dead, wait longer before checking again
                if VIDEO_DEBUG:
                    system_log.info("Connection not healthy, passive observer waiting...", category="PASSIVE")
                await asyncio.sleep(10.0)  # Wait 10 seconds when dead (not 1+5)
                continue
            
            # Check if passive timer has expired
            if time.time() - self.last_interaction_time > PASSIVE_TIMER:
                system_log.info("Triggering Passive Observation", category="PASSIVE")
                try:
                    await self.connection_manager.session.send_realtime_input(text="[SYSTEM: The user has been quiet for a while. Briefly comment on what you see on the screen right now.]")
                    # Reset error counter on successful send
                    if self.connection_manager.connection_error_count > 0:
                        self.connection_manager.connection_error_count = 0
                except Exception as e:
                    is_dead = self.connection_manager.handle_error(e)
                    if is_dead:
                        system_log.info(f"Connection dead, skipping passive prompt. Will retry after reconnection.", category="PASSIVE")
                    else:
                        system_log.info(f"Error sending passive prompt (will retry): {e}", category="PASSIVE")
                self.last_interaction_time = time.time()
            
            # Normal operation: check every second
            await asyncio.sleep(1.0)
