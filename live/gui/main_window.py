from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, 
    QLabel, QFrame, QSplitter
)
from PyQt6.QtCore import Qt

from live.gui.signals import OrionSignals
from live.gui.widgets.chat_panel import ChatPanel
from live.gui.widgets.video_display import VideoDisplay
from live.gui.widgets.control_panel import ControlPanel

class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.signals = OrionSignals()

        self.setWindowTitle("Orion Live Interface")
        self.resize(1280, 720)
        
        # Central Widget
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        
        # Main Layout (Horizontal Split)
        main_layout = QHBoxLayout(central_widget)
        main_layout.setContentsMargins(10, 10, 10, 10)
        main_layout.setSpacing(10)
        
        # Splitter
        splitter = QSplitter(Qt.Orientation.Horizontal)
        main_layout.addWidget(splitter)
        
        # --- Left Panel: Chat ---
        self.chat_panel = ChatPanel()
        
        # --- Right Panel: Video & Controls ---
        self.right_panel = QFrame()
        self.right_panel.setObjectName("VideoPanel")
        right_layout = QVBoxLayout(self.right_panel)
        right_layout.setContentsMargins(0, 0, 0, 0)
        
        # Video Area
        self.video_display = VideoDisplay()
        right_layout.addWidget(self.video_display, stretch=4)
        
        # Controls Area
        self.control_panel = ControlPanel()
        right_layout.addWidget(self.control_panel, stretch=1)
        
        # Add to Splitter
        splitter.addWidget(self.chat_panel)
        splitter.addWidget(self.right_panel)
        
        # Set Splitter Ratio (30% Chat, 70% Video)
        splitter.setSizes([384, 896])
        
        # Connect signals to slots (after widgets are created)
        self.signals.video_frame_ready.connect(self.video_display.update_frame)
        self.signals.chat_message_received.connect(self.chat_panel.add_message)
        self.signals.connection_status_changed.connect(self.control_panel.update_status)
