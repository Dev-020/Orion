import asyncio
import threading
import time
from pathlib import Path

# Import system_log
import sys
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

from live_ui import system_log

class InputPipeline:
    def __init__(self, connection_manager):
        self.connection_manager = connection_manager
        self.user_input_queue = asyncio.Queue(maxsize=20)
        self.input_thread = None
        
    def start(self, loop):
        """Start the persistent input thread."""
        if self.input_thread is None or not self.input_thread.is_alive():
            self.input_thread = threading.Thread(target=self._input_loop, args=(loop,), daemon=True)
            self.input_thread.start()
            system_log.info("Persistent input thread started", category="SESSION")

    def _input_loop(self, loop):
        """
        Background thread to read user input without blocking the async loop.
        Survives session reconnections.
        """
        system_log.info("Input thread started", category="INPUT")
        while True:
            try:
                # This blocks the thread, not the async loop
                text = input()
                
                # Put into async queue safely
                if loop.is_running():
                    loop.call_soon_threadsafe(self.user_input_queue.put_nowait, text)
                else:
                    system_log.info("Loop not running, exiting input thread", category="INPUT")
                    break
            except EOFError:
                system_log.info("EOF received, exiting input thread", category="INPUT")
                break
            except Exception as e:
                system_log.info(f"Error in input thread: {e}", category="INPUT")
                # Brief pause to avoid tight loop on error
                time.sleep(0.1)

    async def send_text(self):
        """Send text input to the session with connection health checks."""
        while True:
            try:
                # Read from persistent queue instead of blocking input()
                text = await self.user_input_queue.get()
                
                if text.lower() == "q":
                    raise asyncio.CancelledError("User requested exit")
                
                if not self.connection_manager.is_healthy():
                    # Put back in queue to retry
                    await self.user_input_queue.put(text)
                    queue_size = self.user_input_queue.qsize()
                    if queue_size > 10:  # Warn if queue is filling up
                        system_log.info(f"User input queue accumulating ({queue_size}/20 messages). Connection unhealthy.", category="INPUT")
                    await asyncio.sleep(1)
                    continue

                await self.connection_manager.session.send_realtime_input(text=text)
                
                # Reset error counter on successful send
                if self.connection_manager.connection_error_count > 0:
                    self.connection_manager.connection_error_count = 0
                    
            except asyncio.CancelledError:
                raise
            except Exception as e:
                is_dead = self.connection_manager.handle_error(e)
                if is_dead:
                    system_log.info(f"Connection dead, text send failed.", category="SESSION")
                else:
                    system_log.info(f"Error sending text: {e}", category="SESSION")
                await asyncio.sleep(0.1)
