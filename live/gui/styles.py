"""
Orion GUI Styles (Dark Theme)
"""

DARK_THEME = """
QMainWindow {
    background-color: #1E1E1E;
    color: #FFFFFF;
}

QWidget {
    background-color: #1E1E1E;
    color: #FFFFFF;
    font-family: 'Segoe UI', sans-serif;
    font-size: 14px;
}

/* --- Panels --- */
QFrame#ChatPanel, QFrame#VideoPanel, QFrame#ControlPanel {
    background-color: #252526;
    border: 1px solid #333333;
    border-radius: 8px;
}

/* --- Buttons --- */
QPushButton {
    background-color: #3C3C3C;
    border: 1px solid #555555;
    border-radius: 4px;
    padding: 6px 12px;
    color: #FFFFFF;
}

QPushButton:hover {
    background-color: #505050;
    border-color: #007ACC;
}

QPushButton:pressed {
    background-color: #007ACC;
    border-color: #007ACC;
}

QPushButton#PrimaryButton {
    background-color: #007ACC;
    border: 1px solid #007ACC;
}

QPushButton#PrimaryButton:hover {
    background-color: #0098FF;
}

QPushButton#DestructiveButton {
    background-color: #3C3C3C;
    border: 1px solid #AA0000;
    color: #FFAAAA;
}

QPushButton#DestructiveButton:hover {
    background-color: #AA0000;
    color: #FFFFFF;
}

/* --- Input Fields --- */
QLineEdit, QTextEdit {
    background-color: #1E1E1E;
    border: 1px solid #333333;
    border-radius: 4px;
    padding: 4px;
    color: #E0E0E0;
}

QLineEdit:focus, QTextEdit:focus {
    border: 1px solid #007ACC;
}

/* --- Chat Area --- */
QTextEdit#ChatHistory {
    background-color: #1E1E1E;
    border: none;
}

/* --- Scrollbars --- */
QScrollBar:vertical {
    border: none;
    background: #1E1E1E;
    width: 10px;
    margin: 0px 0px 0px 0px;
}

QScrollBar::handle:vertical {
    background: #424242;
    min-height: 20px;
    border-radius: 5px;
}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
    border: none;
    background: none;
}

/* --- Labels --- */
QLabel#HeaderLabel {
    font-size: 16px;
    font-weight: bold;
    color: #00D9FF;
}

QLabel#StatsLabel {
    font-family: 'Consolas', monospace;
    font-size: 12px;
    color: #888888;
}
"""
