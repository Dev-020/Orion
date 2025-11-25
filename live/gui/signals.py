from PyQt6.QtCore import QObject, pyqtSignal

class OrionSignals(QObject):
    """
    Defines the signals used to communicate between the backend (LiveSessionOrchestrator)
    and the frontend (PyQt6 GUI).
    """
    # Logging
    log_received = pyqtSignal(str, str) # message, category

    # Video
    video_frame_ready = pyqtSignal(bytes) # JPEG bytes

    # Chat
    chat_message_received = pyqtSignal(str, str) # sender, message

    # Status
    connection_status_changed = pyqtSignal(bool, str) # connected, status_message
    stats_updated = pyqtSignal(dict) # dictionary of stats (fps, latency, etc.)
    
    # Window Management
    window_list_updated = pyqtSignal(list) # list of window dicts

    # Stats Signals
    token_usage_updated = pyqtSignal(int, int, int) # total, input, output
    stats_updated = pyqtSignal(dict) # Generic stats dictionary
    audio_level_updated = pyqtSignal(float) # Normalized audio peak (0.0 - 1.0)
