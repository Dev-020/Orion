from PyQt6.QtWidgets import (
    QWidget, QVBoxLayout, QTextEdit, QLineEdit, 
    QPushButton, QHBoxLayout, QLabel
)
from PyQt6.QtCore import pyqtSignal, Qt

class ChatPanel(QWidget):
    # Signal emitted when user sends a message
    message_sent = pyqtSignal(str)

    def __init__(self):
        super().__init__()
        self.layout = QVBoxLayout(self)
        self.layout.setContentsMargins(0, 0, 0, 0)
        
        # Header
        self.header = QLabel("CHAT")
        self.header.setObjectName("HeaderLabel")
        self.layout.addWidget(self.header)
        
        # Chat History (Read-only)
        self.history = QTextEdit()
        self.history.setReadOnly(True)
        self.history.setObjectName("ChatHistory")
        self.layout.addWidget(self.history)
        
        # Input Area
        input_layout = QHBoxLayout()
        self.input_field = QLineEdit()
        self.input_field.setPlaceholderText("Type a message...")
        self.input_field.returnPressed.connect(self.send_message)
        
        self.send_btn = QPushButton("Send")
        self.send_btn.setObjectName("PrimaryButton")
        self.send_btn.clicked.connect(self.send_message)
        
        input_layout.addWidget(self.input_field)
        input_layout.addWidget(self.send_btn)
        
        self.layout.addLayout(input_layout)

    def send_message(self):
        text = self.input_field.text().strip()
        if text:
            self.message_sent.emit(text)
            self.append_message("You", text)
            self.input_field.clear()

    def append_message(self, sender: str, text: str):
        """Append a message to the chat history."""
        # Simple HTML formatting for colors
        if sender == "You":
            color = "#00D9FF" # Cyan
            align = "right"
        elif sender == "Orion":
            color = "#00B4D8" # Blue
            align = "left"
        else:
            color = "#888888" # Gray (System)
            align = "center"
            
        formatted = f'<div style="color: {color}; text-align: {align};"><b>{sender}:</b> {text}</div><br>'
        self.history.append(formatted)
        
        # Auto-scroll to bottom
        scrollbar = self.history.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())

    def add_message(self, sender: str, message: str):
        """Add a message to the chat display"""
        self.append_message(sender, message)