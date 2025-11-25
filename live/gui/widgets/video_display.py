from PyQt6.QtWidgets import QLabel, QSizePolicy
from PyQt6.QtCore import Qt, pyqtSlot
from PyQt6.QtGui import QImage, QPixmap

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
            "tokens_total": 0
        }
        self.show_stats = True # Default to showing stats
        
        # Stats Label (Top Left)
        self.stats_label = QLabel(self)
        self.stats_label.setStyleSheet("""
            background-color: rgba(0, 0, 0, 150); 
            color: #FFFFFF; 
            padding: 5px; 
            border-radius: 5px;
            font-family: Consolas, monospace;
            font-size: 12px;
        """)
        self.stats_label.hide()
        
        # [NEW] Token Usage Overlay
        self.token_label = QLabel(self)
        self.token_label.setStyleSheet("""
            background-color: rgba(0, 0, 0, 150); 
            color: #00FF00; 
            padding: 5px; 
            border-radius: 5px;
            font-family: Consolas, monospace;
            font-weight: bold;
        """)
        self.token_label.setText("Tokens: 0")
        self.token_label.hide() # Hide until we have data
        
    @pyqtSlot(bytes)
    def update_frame(self, frame_bytes):
        """Update the displayed frame from JPEG bytes."""
        try:
            image = QImage.fromData(frame_bytes)
            if not image.isNull():
                # Scale to fit label while keeping aspect ratio
                pixmap = QPixmap.fromImage(image)
                scaled_pixmap = pixmap.scaled(
                    self.size(), 
                    Qt.AspectRatioMode.KeepAspectRatio, 
                    Qt.TransformationMode.SmoothTransformation
                )
                self.setPixmap(scaled_pixmap)
        except Exception as e:
            print(f"Error updating frame: {e}")

    @pyqtSlot(int, int, int)
    def update_token_display(self, total, input_tokens, output_tokens):
        """Update the token usage overlay."""
        self.token_label.setText(f"Tokens: {total:,}")
        self.token_label.adjustSize()
        self.token_label.show()
        self._position_token_label()

    def _position_token_label(self):
        """Position the label in the bottom right corner."""
        margin = 10
        x = self.width() - self.token_label.width() - margin
        y = self.height() - self.token_label.height() - margin
        self.token_label.move(x, y)

    @pyqtSlot(dict)
    def update_stats(self, new_stats):
        """Update stats dictionary and redraw label."""
        # Merge new stats
        self.stats.update(new_stats)
        
        # Update Token Label (Bottom Right) - reuse existing logic
        if "tokens_total" in new_stats:
            self.update_token_display(
                self.stats.get("tokens_total", 0),
                self.stats.get("tokens_in", 0),
                self.stats.get("tokens_out", 0)
            )

        # Update Stats Label (Top Left)
        if self.show_stats:
            text = (
                f"FPS: {self.stats['fps']:.1f}\n"
                f"Audio: {self.stats['audio_rate']:.1f} chunks/s\n"
                f"Drops: {self.stats['audio_drops']}"
            )
            self.stats_label.setText(text)
            self.stats_label.adjustSize()
            self.stats_label.move(10, 10)
            self.stats_label.show()
        else:
            self.stats_label.hide()
            
    def toggle_stats(self, checked):
        self.show_stats = checked
        if not checked:
            self.stats_label.hide()
            # Optionally hide token label too
            self.token_label.hide()
        else:
            self.stats_label.show()
            self.token_label.show()

    def resizeEvent(self, event):
        """Handle resize events to ensure aspect ratio is maintained."""
        # In a real implementation, we might want to re-scale the *current* pixmap here
        # For now, the next frame update will handle it.
        super().resizeEvent(event)
        # [NEW] Reposition token label on resize
        if hasattr(self, 'token_label'):
            self._position_token_label()
