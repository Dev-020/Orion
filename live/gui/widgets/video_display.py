from PyQt6.QtWidgets import QLabel, QSizePolicy
from PyQt6.QtCore import Qt, pyqtSlot, QRect
from PyQt6.QtGui import QImage, QPixmap, QPainter, QColor, QPen, QFont
from collections import deque

class VideoDisplay(QLabel):
    def __init__(self):
        super().__init__()
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setMinimumSize(640, 360)
        self.setStyleSheet("background-color: #000000; border: 1px solid #333;")
        self.setText("Waiting for Video Feed...")
        
        # Stats Data
        self.stats = {
            "fps": 0.0,
            "audio_rate": 0.0,
            "audio_drops": 0,
            "tokens_total": 0,
            "tokens_in": 0,
            "tokens_out": 0
        }
        self.show_stats = True
        
        # Audio Visualization Data
        self.audio_levels = deque(maxlen=50) # Store last 50 peak levels (0.0 - 1.0)
        self.audio_peak = 0.0
        
        # Fonts
        self.stats_font = QFont("Consolas", 10)
        self.token_font = QFont("Consolas", 10, QFont.Weight.Bold)
        
    @pyqtSlot(bytes)
    def update_frame(self, frame_bytes):
        """Update the displayed frame from JPEG bytes."""
        try:
            image = QImage.fromData(frame_bytes)
            if not image.isNull():
                # Scale to fit label while keeping aspect ratio
                pixmap = QPixmap.fromImage(image)
                # We store the pixmap but don't set it directly on the label 
                # because we want to paint over it in paintEvent
                self.current_pixmap = pixmap
                self.update() # Trigger repaint
        except Exception as e:
            print(f"Error updating frame: {e}")

    @pyqtSlot(int, int, int)
    def update_token_display(self, total, input_tokens, output_tokens):
        """Update the token usage data."""
        self.stats["tokens_total"] = total
        self.stats["tokens_in"] = input_tokens
        self.stats["tokens_out"] = output_tokens
        self.update() # Trigger repaint

    @pyqtSlot(dict)
    def update_stats(self, new_stats):
        """Update stats dictionary."""
        self.stats.update(new_stats)
        self.update() # Trigger repaint
        
    @pyqtSlot(float)
    def update_audio_level(self, level):
        """Update audio level for visualization."""
        self.audio_levels.append(level)
        self.audio_peak = level
        self.update() # Trigger repaint
            
    def toggle_stats(self, checked):
        self.show_stats = checked
        self.update() # Trigger repaint

    def paintEvent(self, event):
        """Custom paint event to draw video and overlays."""
        # Do not call super().paintEvent(event) as we are handling all painting
        
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        
        # 1. Draw Video Frame or Placeholder
        if hasattr(self, 'current_pixmap') and not self.current_pixmap.isNull():
            # Scale pixmap to fit the label
            scaled = self.current_pixmap.scaled(
                self.size(), 
                Qt.AspectRatioMode.KeepAspectRatio, 
                Qt.TransformationMode.SmoothTransformation
            )
            
            # Center the image
            x = (self.width() - scaled.width()) // 2
            y = (self.height() - scaled.height()) // 2
            painter.drawPixmap(x, y, scaled)
        else:
            # Draw placeholder text manually
            painter.setPen(QColor(255, 255, 255))
            painter.setFont(QFont("Segoe UI", 14))
            painter.drawText(self.rect(), Qt.AlignmentFlag.AlignCenter, "Waiting for Video Feed...")
            
        # If stats are disabled, stop here
        if not self.show_stats:
            return

        # 2. Draw Stats Overlay (Top Left)
        self._draw_stats_overlay(painter)
        
        # 3. Draw Token Overlay (Top Right)
        self._draw_token_overlay(painter)
        
        # 4. Draw Audio Waveform (Bottom)
        self._draw_audio_waveform(painter)

    def _draw_stats_overlay(self, painter):
        """Draw FPS, Audio Rate, Drops."""
        text = (
            f"FPS: {self.stats.get('fps', 0.0):.3f}\n"
            f"Audio: {self.stats.get('audio_rate', 0.0):.1f} chunks/s\n"
            f"Drops: {self.stats.get('audio_drops', 0)}"
        )
        
        # Background
        bg_rect = QRect(10, 10, 200, 60)
        painter.fillRect(bg_rect, QColor(0, 0, 0, 150))
        
        # Text
        painter.setPen(QColor(255, 255, 255))
        painter.setFont(self.stats_font)
        painter.drawText(bg_rect.adjusted(10, 5, -5, -5), Qt.AlignmentFlag.AlignLeft | Qt.AlignmentFlag.AlignTop, text)

    def _draw_token_overlay(self, painter):
        """Draw Token Usage."""
        total = self.stats.get('tokens_total', 0)
        text = f"Tokens: {total:,}"
        
        # Calculate width based on text
        fm = painter.fontMetrics()
        w = fm.horizontalAdvance(text) + 20
        
        # Position: Top Right
        x = self.width() - w - 10
        y = 10
        bg_rect = QRect(x, y, w, 30)
        
        # Background
        painter.fillRect(bg_rect, QColor(0, 0, 0, 150))
        
        # Text
        painter.setPen(QColor(0, 255, 0)) # Green
        painter.setFont(self.token_font)
        painter.drawText(bg_rect, Qt.AlignmentFlag.AlignCenter, text)

    def _draw_audio_waveform(self, painter):
        """Draw audio visualization at the bottom."""
        if not self.audio_levels:
            return
            
        h = self.height()
        w = self.width()
        viz_height = 60
        viz_y = h - viz_height - 10
        
        # Background for viz
        bg_rect = QRect(10, viz_y, w - 20, viz_height)
        painter.fillRect(bg_rect, QColor(0, 0, 0, 100))
        
        # Draw center line
        center_y = viz_y + (viz_height // 2)
        painter.setPen(QPen(QColor(80, 80, 80), 1))
        painter.drawLine(10, center_y, w - 10, center_y)
        
        # Draw waveform
        levels = list(self.audio_levels)
        if len(levels) < 2:
            return
            
        step = (w - 20) / (len(levels) - 1)
        
        for i in range(len(levels) - 1):
            x1 = 10 + int(i * step)
            x2 = 10 + int((i + 1) * step)
            
            amp1 = levels[i]
            amp2 = levels[i+1]
            
            # Scale amplitude to height
            y1 = int(center_y - (amp1 * (viz_height / 2) * 0.9))
            y2 = int(center_y - (amp2 * (viz_height / 2) * 0.9))
            
            # Color based on amplitude
            if amp1 < 0.3:
                color = QColor(0, 255, 0) # Green
            elif amp1 < 0.7:
                color = QColor(255, 255, 0) # Yellow
            else:
                color = QColor(255, 0, 0) # Red
                
            painter.setPen(QPen(color, 2))
            painter.drawLine(x1, y1, x2, y2)
            
            # Mirror for bottom half
            y1_b = int(center_y + (amp1 * (viz_height / 2) * 0.9))
            y2_b = int(center_y + (amp2 * (viz_height / 2) * 0.9))
            painter.drawLine(x1, y1_b, x2, y2_b)
