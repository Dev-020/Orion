"""
Visual Debug Monitor for Live API
Shows what frames and audio the AI is seeing in real-time
"""

import cv2
import numpy as np
import time
from collections import deque
import threading

class DebugMonitor:
    """Visual debug monitor showing video frames and audio levels sent to AI"""
    
    def __init__(self, show_video=True, show_audio=True):
        self.show_video = show_video
        self.show_audio = show_audio
        self.enabled = show_video or show_audio
        
        # Video frame tracking
        self.current_frame = None
        self.frame_count = 0
        self.last_frame_time = time.time()
        self.fps = 0.0
        
        # Audio tracking
        self.audio_levels = deque(maxlen=100)  # Last 100 audio chunks
        self.audio_peak = 0
        self.audio_count = 0
        self.audio_drops = 0  # ← ADD THIS
        self.last_audio_time = time.time()
        self.audio_rate = 0.0  # Chunks per second
        
        # Token Usage Tracking (Estimated)
        self.token_counts = {"audio": 0, "video": 0}
        self.token_rates = {"audio": 0.0, "video": 0.0}
        self.last_token_update = time.time()
        
        # Display window
        self.window_name = "AI Debug Monitor"
        self.running = False
        self.lock = threading.Lock()
        
    def start(self):
        """Start the debug monitor in a separate thread"""
        if not self.enabled:
            return
            
        self.running = True
        self.thread = threading.Thread(target=self._display_loop, daemon=True)
        self.thread.start()
        
    def stop(self):
        """Stop the debug monitor"""
        self.running = False
        if self.enabled:
            cv2.destroyAllWindows()
    
    def update_video_frame(self, frame_bytes, mime_type="image/jpeg"):
        """Update with new video frame sent to AI"""
        if not self.show_video:
            return
            
        with self.lock:
            # Convert bytes to numpy array
            nparr = np.frombuffer(frame_bytes, np.uint8)
            self.current_frame = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
            
            # Update stats
            self.frame_count += 1
            current_time = time.time()
            elapsed = current_time - self.last_frame_time
            if elapsed >= 1.0:  # Update FPS every second
                self.fps = self.frame_count / elapsed
                self.frame_count = 0
                self.last_frame_time = current_time
    
    def update_audio_level(self, audio_data, sample_rate=16000):
        """Update with audio data sent to AI"""
        if not self.show_audio:
            return
            
        with self.lock:
            # Calculate audio level (peak amplitude)
            if isinstance(audio_data, bytes):
                # Convert bytes to int16 numpy array
                audio_array = np.frombuffer(audio_data, dtype=np.int16)
            else:
                audio_array = audio_data
            
            # Calculate peak amplitude (0-32768 for int16)
            peak = np.max(np.abs(audio_array))
            normalized_peak = peak / 32768.0  # Normalize to 0-1
            
            self.audio_levels.append(normalized_peak)
            self.audio_peak = max(self.audio_levels) if self.audio_levels else 0
            
            # Update stats
            self.audio_count += 1
            current_time = time.time()
            elapsed = current_time - self.last_audio_time
            if elapsed >= 1.0:  # Update rate every second
                self.audio_rate = self.audio_count / elapsed
                self.audio_count = 0
                self.last_audio_time = current_time
    
    def report_audio_drop(self):
        """Called when an audio chunk is dropped"""
        with self.lock:
            self.audio_drops += 1

    def report_video_tokens(self, count):
        """Report estimated video tokens"""
        with self.lock:
            self.token_counts["video"] += count
            self._update_token_rates()

    def report_audio_tokens(self, count):
        """Report estimated audio tokens"""
        with self.lock:
            self.token_counts["audio"] += count
            self._update_token_rates()

    def _update_token_rates(self):
        """Update token usage rates"""
        current_time = time.time()
        elapsed = current_time - self.last_token_update
        
        if elapsed >= 1.0:
            self.token_rates["video"] = self.token_counts["video"] / elapsed
            self.token_rates["audio"] = self.token_counts["audio"] / elapsed
            
            # Reset counts
            self.token_counts["video"] = 0
            self.token_counts["audio"] = 0
            self.last_token_update = current_time

    def _display_loop(self):
        """Main display loop (runs in separate thread)"""
        while self.running:
            with self.lock:
                display_frame = self._create_display_frame()
            
            if display_frame is not None:
                cv2.imshow(self.window_name, display_frame)
            
            # Check for key press (q to quit, but don't stop the main app)
            key = cv2.waitKey(30) & 0xFF
            if key == ord('q'):
                print("[DEBUG] Debug monitor closed by user")
                self.running = False
                break
            
            time.sleep(0.03)  # ~30 FPS display
    
    def _create_display_frame(self):
        """Create the debug display frame with video and audio visualization"""
        if not self.show_video and not self.show_audio:
            return None
        
        # Start with black canvas
        if self.show_video and self.current_frame is not None:
            # Use video frame as base, but resize to reasonable display size
            display = self.current_frame.copy()
            
            # Resize to max 1280x720 while maintaining aspect ratio
            max_width = 640
            max_height = 360
            h, w = display.shape[:2]
            
            scale = min(max_width / w, max_height / h, 1.0)  # Don't upscale
            if scale < 1.0:
                new_width = int(w * scale)
                new_height = int(h * scale)
                display = cv2.resize(display, (new_width, new_height))
            
            height, width = display.shape[:2]
        else:
            # Create blank canvas
            width, height = 800, 600
            display = np.zeros((height, width, 3), dtype=np.uint8)
        
        # Add video stats overlay
        if self.show_video:
            self._draw_video_stats(display)
        
        # Add token stats overlay (Top Right)
        self._draw_token_stats(display)
        
        # Add audio visualization
        if self.show_audio:
            self._draw_audio_visualization(display)
        
        return display
    
    def _draw_token_stats(self, frame):
        """Draw estimated token usage stats"""
        h, w = frame.shape[:2]
        font = cv2.FONT_HERSHEY_SIMPLEX
        
        # Calculate total
        total_rate = self.token_rates["video"] + self.token_rates["audio"]
        
        # Position: Top Right
        start_x = w - 220
        start_y = 10
        
        # Background
        cv2.rectangle(frame, (start_x, start_y), (w - 10, start_y + 90), (0, 0, 0), -1)
        
        # Text
        cv2.putText(frame, "TOKEN USAGE (est.)", (start_x + 10, start_y + 25), font, 0.5, (0, 255, 255), 1)
        cv2.putText(frame, f"Total: {int(total_rate)} tok/s", (start_x + 10, start_y + 45), font, 0.5, (255, 255, 255), 1)
        cv2.putText(frame, f"Video: {int(self.token_rates['video'])} tok/s", (start_x + 10, start_y + 65), font, 0.5, (200, 200, 200), 1)
        cv2.putText(frame, f"Audio: {int(self.token_rates['audio'])} tok/s", (start_x + 10, start_y + 85), font, 0.5, (200, 200, 200), 1)
    
    def _draw_video_stats(self, frame):
        """Draw video statistics on frame"""
        h, w = frame.shape[:2]
        
        # Semi-transparent overlay for text
        overlay = frame.copy()
        cv2.rectangle(overlay, (10, 10), (300, 100), (0, 0, 0), -1)
        cv2.addWeighted(overlay, 0.6, frame, 0.4, 0, frame)
        
        # Draw text
        font = cv2.FONT_HERSHEY_SIMPLEX
        cv2.putText(frame, "VIDEO FEED TO AI", (20, 35), font, 0.6, (0, 255, 0), 2)
        cv2.putText(frame, f"FPS: {self.fps:.1f}", (20, 60), font, 0.5, (255, 255, 255), 1)
        cv2.putText(frame, f"Resolution: {w}x{h}", (20, 85), font, 0.5, (255, 255, 255), 1)
    
    def _draw_audio_visualization(self, frame):
        """Draw audio waveform and level meter"""
        h, w = frame.shape[:2]
        
        # Audio visualization area (bottom of frame)
        viz_height = 150
        viz_y = h - viz_height
        
        # Semi-transparent background
        overlay = frame.copy()
        cv2.rectangle(overlay, (0, viz_y), (w, h), (0, 0, 0), -1)
        cv2.addWeighted(overlay, 0.7, frame, 0.3, 0, frame)
        
        # Draw title
        font = cv2.FONT_HERSHEY_SIMPLEX
        cv2.putText(frame, "AUDIO TO AI", (20, viz_y + 25), font, 0.6, (0, 255, 255), 2)
        cv2.putText(frame, f"Rate: {self.audio_rate:.1f} chunks/s", (20, viz_y + 50), 
                   font, 0.5, (255, 255, 255), 1)
        
        # ← ADD THIS:
        drop_color = (0, 255, 0) if self.audio_drops == 0 else (0, 0, 255)
        cv2.putText(frame, f"Drops: {self.audio_drops}", (200, viz_y + 50),
                   font, 0.5, drop_color, 1)

        # Draw waveform
        if len(self.audio_levels) > 1:
            waveform_x = 20
            waveform_y = viz_y + 70
            waveform_width = w - 40
            waveform_height = 60
            
            # Draw waveform background
            cv2.rectangle(frame, (waveform_x, waveform_y), 
                         (waveform_x + waveform_width, waveform_y + waveform_height),
                         (40, 40, 40), -1)
            
            # Draw center line
            center_y = waveform_y + waveform_height // 2
            cv2.line(frame, (waveform_x, center_y), 
                    (waveform_x + waveform_width, center_y), (80, 80, 80), 1)
            
            # Draw waveform
            levels = list(self.audio_levels)
            step = waveform_width / len(levels)
            
            for i in range(len(levels) - 1):
                x1 = int(waveform_x + i * step)
                x2 = int(waveform_x + (i + 1) * step)
                
                # Amplitude (0-1 normalized)
                amp1 = levels[i]
                amp2 = levels[i + 1]
                
                y1 = int(center_y - amp1 * (waveform_height // 2))
                y2 = int(center_y - amp2 * (waveform_height // 2))
                
                # Color based on amplitude (green to yellow to red)
                if amp1 < 0.3:
                    color = (0, 255, 0)  # Green
                elif amp1 < 0.7:
                    color = (0, 255, 255)  # Yellow
                else:
                    color = (0, 0, 255)  # Red
                
                cv2.line(frame, (x1, y1), (x2, y2), color, 2)
            
            # Draw peak indicator
            peak_text = f"Peak: {self.audio_peak:.2f}"
            cv2.putText(frame, peak_text, (waveform_x + waveform_width - 120, waveform_y - 10),
                       font, 0.4, (255, 255, 255), 1)


# Global instance (singleton pattern)
_monitor = None

def get_monitor():
    """Get or create the global debug monitor instance"""
    global _monitor
    if _monitor is None:
        _monitor = DebugMonitor(show_video=True, show_audio=True)
    return _monitor

def start_monitor():
    """Start the debug monitor"""
    monitor = get_monitor()
    monitor.start()
    return monitor

def stop_monitor():
    """Stop the debug monitor"""
    global _monitor
    if _monitor is not None:
        _monitor.stop()
        _monitor = None
