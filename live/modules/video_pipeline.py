import asyncio
import io
import time
import cv2
import mss
import numpy as np
from PIL import Image
from pathlib import Path
from typing import Optional, List, Dict

# Import system_log and debug monitor
# Import system_log and debug monitor
import sys
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

from live.live_ui import system_log
from live.debug_monitor import get_monitor
from live.modules.window_selector import WindowSelector
from google.genai import types

# Check if debug mode is enabled
import os
VIDEO_DEBUG = False
VIDEO_CAPTURE_INTERVAL = 4.0  # Seconds between frame captures

class VideoPipeline:
    def __init__(self, connection_manager, mode="screen", signals=None):
        self.connection_manager = connection_manager
        self.mode = mode
        self.video_out_queue = asyncio.Queue(maxsize=1)
        self.frame_stats = {
            "captured": 0,
            "sent": 0,
            "dropped": 0,
            "total_latency": 0.0,
            "max_latency": 0.0,
        }
        self.debug_monitor = get_monitor()
        self.signals = signals
        
        # Visual Momentum State
        self.last_frame_gray = None
        self.momentum_score = 0.0
        self.momentum_history = []
        
        # Window capture support
        self.window_selector = WindowSelector() if mode == "window" else None
        self.selected_window_hwnd = None
        self.selected_window_title = None
        self.window_capture_fallback = False  # If window capture fails, fallback to screen
        
        # Start stats task
        self.stats_task = None

    def _calculate_momentum(self, frame_data):
        """
        Calculate visual momentum (motion intensity) from frame differences.
        """
        try:
            # Decode frame to numpy array
            nparr = np.frombuffer(frame_data, np.uint8)
            frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            
            if frame is None:
                return

            # Convert to grayscale for simpler diffing
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            
            if self.last_frame_gray is not None:
                # Calculate absolute difference
                diff = cv2.absdiff(gray, self.last_frame_gray)
                # Mean intensity of difference (0-255)
                score = np.mean(diff)
                
                # Update rolling average (smooth out spikes)
                self.momentum_score = (self.momentum_score * 0.7) + (score * 0.3)
                
                # Update debug monitor
                if self.debug_monitor:
                    # We can add a momentum bar or just log it
                    pass
            
            self.last_frame_gray = gray
            
        except Exception as e:
            if VIDEO_DEBUG:
                system_log.info(f"Momentum calc error: {e}", category="VIDEO")

    def get_momentum(self):
        """Return current momentum score."""
        return self.momentum_score

    async def get_screen(self):
        """
        Captures screen frames using MSS or window capture based on mode.
        Supports both full screen capture and selective window capture.
        """
        sct = None
        try:
            # Initialize MSS for screen capture mode or fallback
            if self.mode == "screen" or not self.window_selector:
                sct = mss.mss()
                monitor = sct.monitors[1]
                system_log.info("Starting screen capture mode", category="VIDEO")
            else:
                system_log.info(f"Starting window capture mode (window: {self.selected_window_title or 'not selected'})", category="VIDEO")
            
            while True:
                # Check connection health before capturing
                if not self.connection_manager.is_healthy():
                    if VIDEO_DEBUG:
                        system_log.info("Connection not healthy, pausing capture...", category="VIDEO")
                    await asyncio.sleep(5.0)
                    continue
                
                start_time = time.time()
                img = None
                
                # Determine capture method
                if self.mode == "window" and self.window_selector and not self.window_capture_fallback:
                    # Try window capture
                    if not self.window_selector.is_window_valid():
                        system_log.info("Selected window is no longer valid, falling back to screen capture", category="VIDEO")
                        self.window_capture_fallback = True
                        # Initialize MSS for fallback
                        if sct is None:
                            sct = mss.mss()
                            monitor = sct.monitors[1]
                    else:
                        # Capture window
                        frame_array = self.window_selector.capture_window()
                        if frame_array is not None:
                            img = Image.fromarray(frame_array)
                        else:
                            # Window capture failed, try again next iteration
                            if VIDEO_DEBUG:
                                system_log.info("Window capture failed, retrying...", category="VIDEO")
                            await asyncio.sleep(VIDEO_CAPTURE_INTERVAL)
                            continue
                
                # Fall back to screen capture if needed or if in screen mode
                if img is None:
                    if sct is None:
                        sct = mss.mss()
                        monitor = sct.monitors[1]
                    
                    screenshot = sct.grab(monitor)
                    img = Image.frombytes("RGB", screenshot.size, screenshot.bgra, "raw", "BGRX")

                # Resize to reduce token usage (max 1024px)
                # Gemini 2.0+ tiles large images (258 tokens per 768x768 tile)
                # 1080p (1920x1080) -> ~6 tiles -> ~1548 tokens
                # Resizing to 1024x576 -> ~2 tiles -> ~516 tokens
                # Resizing to 768x432 -> 1 tile -> 258 tokens
                img.thumbnail((768, 432))
                
                # Convert to bytes
                img_byte_arr = io.BytesIO()
                img.save(img_byte_arr, format='JPEG', quality=80)
                img_bytes = img_byte_arr.getvalue()
                
                # Calculate momentum
                self._calculate_momentum(img_bytes)
                
                # Put in queue (non-blocking if full, drop old frames if needed)
                if self.video_out_queue.full():
                    try:
                        self.video_out_queue.get_nowait()
                        self.frame_stats["dropped"] += 1
                    except asyncio.QueueEmpty:
                        pass
                
                await self.video_out_queue.put({
                    "mime_type": "image/jpeg",
                    "data": img_bytes,
                    "timestamp": time.time()
                })
                
                self.frame_stats["captured"] += 1
                
                # Feed to debug monitor
                if self.debug_monitor:
                    self.debug_monitor.update_video_frame(img_bytes)
                
                # Wait for next capture interval
                elapsed = time.time() - start_time
                wait_time = max(0, VIDEO_CAPTURE_INTERVAL - elapsed)
                await asyncio.sleep(wait_time)
        except Exception as e:
            system_log.info(f"Capture error: {e}", category="VIDEO")
            import traceback
            traceback.print_exc()
        finally:
            # Ensure MSS context is closed even if task is cancelled
            if sct is not None:
                sct.close()
                if VIDEO_DEBUG: 
                    system_log.info("MSS context closed", category="VIDEO")

    async def get_frames(self):
        """
        Captures camera frames using OpenCV and puts them in the queue.
        """
        cap = cv2.VideoCapture(0)
        
        if not cap.isOpened():
            system_log.info("Cannot open camera", category="VIDEO")
            return
            
        while True:
            if not self.connection_manager.is_healthy():
                if VIDEO_DEBUG:
                    system_log.info("Connection not healthy, pausing camera capture...", category="VIDEO")
                await asyncio.sleep(5.0)  # Wait longer when connection is dead
                continue
            
            start_time = time.time()
            
            ret, frame = cap.read()
            if not ret:
                system_log.info("Can't receive frame (stream end?). Exiting ...", category="VIDEO")
                break
            
            # Resize frame for token optimization
            # cv2.resize expects (width, height)
            height, width = frame.shape[:2]
            if width > 1024 or height > 1024:
                scale = 1024 / max(width, height)
                new_width = int(width * scale)
                new_height = int(height * scale)
                frame = cv2.resize(frame, (new_width, new_height))

            # Encode to JPEG
            _, buffer = cv2.imencode('.jpg', frame)
            img_bytes = buffer.tobytes()
            
            # Calculate momentum
            self._calculate_momentum(img_bytes)
            
            # Put in queue
            if self.video_out_queue.full():
                try:
                    self.video_out_queue.get_nowait()
                    self.frame_stats["dropped"] += 1
                except asyncio.QueueEmpty:
                    pass
            
            await self.video_out_queue.put({
                "mime_type": "image/jpeg",
                "data": img_bytes,
                "timestamp": time.time()
            })
            
            self.frame_stats["captured"] += 1
            
            # Feed to debug monitor
            if self.debug_monitor:
                self.debug_monitor.update_video_frame(img_bytes)
            
            # Wait for next capture interval
            elapsed = time.time() - start_time
            wait_time = max(0, VIDEO_CAPTURE_INTERVAL - elapsed)
            await asyncio.sleep(wait_time)

    async def send_realtime_image(self):
        """
        Sends frames from queue to the API.
        Tracks latency from frame capture to API send.
        Includes connection health checks to prevent sending to dead connections.
        """
        consecutive_skips = 0
        max_consecutive_skips = 10  # Drop frames if connection is dead for too long
        
        while True:
            frame = await self.video_out_queue.get()
            
            # Check connection health before processing
            if not self.connection_manager.is_healthy():
                consecutive_skips += 1
                if consecutive_skips <= max_consecutive_skips:
                    if VIDEO_DEBUG or consecutive_skips % 5 == 0:
                        system_log.info(f"Connection not healthy, skipping frame ({consecutive_skips}/{max_consecutive_skips}). Waiting for reconnection...", category="VIDEO")
                    continue
                else:
                    # Too many skips, drop frame and wait
                    if VIDEO_DEBUG:
                        system_log.info(f"Dropping frame due to dead connection (skipped {consecutive_skips} frames)", category="VIDEO")
                    await asyncio.sleep(1)  # Brief pause before checking again
                    continue
            
            # Reset skip counter on successful health check
            if consecutive_skips > 0:
                if VIDEO_DEBUG:
                    system_log.info(f"Connection restored, resuming frame sending", category="VIDEO")
                consecutive_skips = 0
            
            # Calculate latency if timestamp exists
            if frame.get("timestamp"):
                latency = time.time() - frame["timestamp"]
                self.frame_stats["total_latency"] += latency
                self.frame_stats["max_latency"] = max(self.frame_stats["max_latency"], latency)
                
                if VIDEO_DEBUG:
                    system_log.info(f"Sending frame (latency: {latency:.2f}s)", category="VIDEO")
                elif latency > 3.0:  # Warn about high latency even without debug mode
                    system_log.info(f"WARNING: High frame latency: {latency:.2f}s", category="VIDEO")
            
            send_start = time.time()
            try:
                # Prepare frame for API (remove timestamp)
                api_frame = {
                    "mime_type": frame["mime_type"],
                    "data": frame["data"]
                }
                await self.connection_manager.session.send_realtime_input(media=api_frame)
                self.frame_stats["sent"] += 1
                
                # Feed to debug monitor
                if self.debug_monitor:
                    self.debug_monitor.update_video_frame(frame["data"], frame["mime_type"])
                    self.debug_monitor.report_video_tokens(258)
                
                # Emit signal for GUI (if connected)
                if self.signals:
                    self.signals.video_frame_ready.emit(frame["data"])  
                
                # Reset error counter on successful send
                if self.connection_manager.connection_error_count > 0:
                    self.connection_manager.connection_error_count = 0
                
                if VIDEO_DEBUG:
                    send_time = time.time() - send_start
                    system_log.info(f"Frame sent to API in {send_time:.3f}s", category="VIDEO")
            except Exception as e:
                is_dead = self.connection_manager.handle_error(e)
                if is_dead:
                    # Connection is dead, skip this frame and wait
                    system_log.info(f"Connection dead, skipping frame. Will resume after reconnection.", category="VIDEO")
                    await asyncio.sleep(1)  # Wait before trying next frame
                else:
                    # Transient error, log and continue
                    system_log.info(f"Failed to send frame (will retry): {e}", category="VIDEO")
                    if VIDEO_DEBUG:  # Add extra detail in debug mode
                        import traceback
                        system_log.info(f"Frame send error traceback: {traceback.format_exc()}", category="VIDEO")
                    await asyncio.sleep(0.1)  # Brief pause before retry

    async def video_stats_task(self):
        """Periodically print video pipeline statistics for debugging."""
        if not VIDEO_DEBUG:
            return
        
        while True:
            await asyncio.sleep(30.0)  # Print stats every 30 seconds
            if self.frame_stats["sent"] > 0:
                avg_latency = self.frame_stats["total_latency"] / self.frame_stats["sent"]
                system_log.info(f"Captured: {self.frame_stats['captured']}, "
                      f"Sent: {self.frame_stats['sent']}, "
                      f"Dropped: {self.frame_stats['dropped']}, "
                      f"Avg Latency: {avg_latency:.2f}s, "
                      f"Max Latency: {self.frame_stats['max_latency']:.2f}s, "
                      f"Momentum: {self.momentum_score:.1f}", category="VIDEO")
    
    def list_windows(self) -> List[Dict]:
        """
        Get list of capturable windows.
        
        Returns:
            List of window dictionaries with hwnd, title, executable, etc.
        """
        if self.window_selector:
            return self.window_selector.enumerate_windows()
        return []
    
    def select_window_by_title(self, title: str) -> bool:
        """
        Select window to capture by searching for title substring.
        
        Args:
            title: Window title or substring to search for
            
        Returns:
            True if window was found and selected, False otherwise
        """
        if self.window_selector:
            success = self.window_selector.select_window_by_title(title)
            if success:
                self.selected_window_title = self.window_selector.selected_title
                self.selected_window_hwnd = self.window_selector.selected_hwnd
                self.window_capture_fallback = False  # Reset fallback flag
                system_log.info(f"Selected window: {self.selected_window_title}", category="VIDEO")
            return success
        return False
    
    def select_window_by_hwnd(self, hwnd) -> bool:
        """
        Select window to capture by window handle.
        
        Args:
            hwnd: Window handle (HWND)
            
        Returns:
            True if window was selected, False otherwise
        """
        if self.window_selector:
            try:
                self.window_selector.select_window(hwnd)
                self.selected_window_title = self.window_selector.selected_title
                self.selected_window_hwnd = hwnd
                self.window_capture_fallback = False  # Reset fallback flag
                system_log.info(f"Selected window by HWND: {self.selected_window_title}", category="VIDEO")
                return True
            except Exception as e:
                system_log.info(f"Error selecting window by HWND: {e}", category="VIDEO")
                return False
        return False

    def reset_fallback(self):
        """Reset the window capture fallback flag."""
        self.window_capture_fallback = False
        system_log.info("Window capture fallback reset", category="VIDEO")

