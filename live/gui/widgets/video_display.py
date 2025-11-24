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

    def resizeEvent(self, event):
        """Handle resize events to ensure aspect ratio is maintained."""
        # In a real implementation, we might want to re-scale the *current* pixmap here
        # For now, the next frame update will handle it.
        super().resizeEvent(event)
