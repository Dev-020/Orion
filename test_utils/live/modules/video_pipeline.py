import asyncio
import io
import time
import cv2
import mss
import numpy as np
from PIL import Image
from pathlib import Path
from typing import Optional

# Import system_log and debug monitor
try:
    from test_utils.live.live_ui import system_log
    from test_utils.live.debug_monitor import get_monitor
except ImportError:
    import sys
    sys.path.append(str(Path(__file__).resolve().parent.parent.parent.parent))
    from test_utils.live.live_ui import system_log
    from test_utils.live.debug_monitor import get_monitor

# Check if debug mode is enabled
import os
VIDEO_DEBUG = False
VIDEO_CAPTURE_INTERVAL = 0.2  # Seconds between frame captures

class VideoPipeline:
    def __init__(self, connection_manager, mode="screen"):
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

    async def get_screen(self):
        """
        Captures screen frames using MSS and puts them in the queue.
        """
        sct = None
        try:
            sct = mss.mss()
            # Get the primary monitor
            monitor = sct.monitors[1]
            
            while True:
                # Check connection health before capturing
                if not self.connection_manager.is_healthy():
                    if VIDEO_DEBUG:
                        system_log.info("Connection not healthy, pausing screen capture...", category="VIDEO")
                    await asyncio.sleep(5.0)  # Wait longer when connection is dead
                    continue
                
                start_time = time.time()
                
                # Capture screen
                screenshot = sct.grab(monitor)
                
                # Convert to PIL Image
                img = Image.frombytes("RGB", screenshot.size, screenshot.bgra, "raw", "BGRX")
                
                # Convert to bytes
                img_byte_arr = io.BytesIO()
                img.save(img_byte_arr, format='JPEG', quality=80)
                img_bytes = img_byte_arr.getvalue()
                
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
                
                # Wait for next capture interval
                elapsed = time.time() - start_time
                wait_time = max(0, VIDEO_CAPTURE_INTERVAL - elapsed)
                await asyncio.sleep(wait_time)
        except Exception as e:
            system_log.info(f"Screen capture error: {e}", category="VIDEO")
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
                
            # Encode to JPEG
            _, buffer = cv2.imencode('.jpg', frame)
            img_bytes = buffer.tobytes()
            
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
            
            # Prepare frame for API (remove timestamp)
            api_frame = {
                "mime_type": frame["mime_type"],
                "data": frame["data"]
            }
            
            send_start = time.time()
            try:
                await self.connection_manager.session.send_realtime_input(media=api_frame)
                self.frame_stats["sent"] += 1
                
                # Feed to debug monitor
                if self.debug_monitor:
                    self.debug_monitor.update_video_frame(frame["data"], frame["mime_type"])
                
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
                # Note: session duration formatting is in live.py, we might skip it here or pass a callback
                # For simplicity, we'll just print stats
                system_log.info(f"Captured: {self.frame_stats['captured']}, "
                      f"Sent: {self.frame_stats['sent']}, "
                      f"Dropped: {self.frame_stats['dropped']}, "
                      f"Avg Latency: {avg_latency:.2f}s, "
                      f"Max Latency: {self.frame_stats['max_latency']:.2f}s", category="VIDEO")
