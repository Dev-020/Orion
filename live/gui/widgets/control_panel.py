from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QHBoxLayout, QComboBox, 
    QPushButton, QCheckBox, QLabel, QFrame
)
from PyQt6.QtCore import pyqtSignal, Qt

class ControlPanel(QFrame):
    # Signals
    window_changed = pyqtSignal(int) # HWND
    screen_share_toggled = pyqtSignal(bool)
    mute_toggled = pyqtSignal(bool)
    stop_session = pyqtSignal()
    refresh_windows = pyqtSignal()

    def __init__(self):
        super().__init__()
        self.setObjectName("ControlPanel")
        self.layout = QVBoxLayout(self)
        
        # Header
        self.layout.addWidget(QLabel("CONTROLS", objectName="HeaderLabel"))
        
        # Window Selection
        win_layout = QHBoxLayout()
        self.window_combo = QComboBox()
        self.window_combo.setPlaceholderText("Select Window...")
        # We'll populate this dynamically
        self.window_combo.currentIndexChanged.connect(self._on_window_selected)
        
        refresh_btn = QPushButton("↻")
        refresh_btn.setFixedWidth(30)
        refresh_btn.setToolTip("Refresh Window List")
        refresh_btn.clicked.connect(self.refresh_windows.emit)
        
        win_layout.addWidget(self.window_combo)
        win_layout.addWidget(refresh_btn)
        self.layout.addLayout(win_layout)
        
        # Toggles
        toggles_layout = QHBoxLayout()
        
        self.screen_check = QCheckBox("Full Screen")
        self.screen_check.toggled.connect(self.screen_share_toggled.emit)
        
        self.mute_btn = QPushButton("Mute Mic")
        self.mute_btn.setCheckable(True)
        self.mute_btn.toggled.connect(self._on_mute_toggled)
        
        toggles_layout.addWidget(self.screen_check)
        toggles_layout.addWidget(self.mute_btn)
        self.layout.addLayout(toggles_layout)
        
        # Stop Button
        self.stop_btn = QPushButton("Stop Session")
        self.stop_btn.setObjectName("DestructiveButton")
        self.stop_btn.clicked.connect(self.stop_session.emit)
        self.layout.addWidget(self.stop_btn)
        
        # Store window data map {index: hwnd}
        self.window_map = {}

    def update_window_list(self, windows: list):
        """
        Update the combobox with list of windows.
        windows: List of dicts {'hwnd': int, 'title': str, ...}
        """
        self.window_combo.blockSignals(True)
        self.window_combo.clear()
        self.window_map = {}
        
        for i, win in enumerate(windows):
            title = win.get('title', 'Unknown')
            hwnd = win.get('hwnd')
            self.window_combo.addItem(title)
            self.window_map[i] = hwnd
            
        self.window_combo.blockSignals(False)

    def _on_window_selected(self, index):
        if index in self.window_map:
            hwnd = self.window_map[index]
            self.window_changed.emit(hwnd)
            # Uncheck screen share if window selected
            self.screen_check.blockSignals(True)
            self.screen_check.setChecked(False)
            self.screen_check.blockSignals(False)

    def _on_mute_toggled(self, checked):
        self.mute_btn.setText("Unmute Mic" if checked else "Mute Mic")
        self.mute_toggled.emit(checked)
