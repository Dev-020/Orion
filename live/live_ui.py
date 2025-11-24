"""
Live API UI Module - Rich-based Terminal Output Handlers
Provides three visual output sections:
- Conversation: User input and AI responses 
- System Logs: Compact status notifications
- Debug: Detailed technical output (VIDEO_DEBUG only)
"""

import os
import time
from rich.console import Console
from rich.text import Text
from rich.panel import Panel
from rich.style import Style

# Initialize console
console = Console()

# Check if debug mode is enabled
VIDEO_DEBUG = os.getenv("VIDEO_DEBUG", "false").lower() == "true"

# Color scheme (dark mode friendly)
COLORS = {
    # Conversation colors
    "user": "#00D9FF",  # Cyan
    "ai": "#00B4D8",    # Blue
    
    # System log colors
    "session": "#4ADE80",  # Green
    "video": "#60A5FA",    # Blue
    "connection": "#4ADE80",  # Green (healthy)
    "connection_error": "#EF4444",  # Red (error)
    "input": "#22D3EE",  # Cyan
    "passive": "#FBBF24",  # Yellow
    "text": "#22D3EE",  # Cyan (for INPUT category)
    
    # Debug colors
    "debug": "#A78BFA",  # Purple
    
    # Separator color
    "separator": "#6B7280",  # Dim Gray
}

# Emoji mapping for categories
CATEGORY_ICONS = {
    "SESSION": "🟢",
    "VIDEO": "📡",
    "CONNECTION": "🔗",
    "INPUT": "⌨️",
    "PASSIVE": "👁️",
    "TEXT": "⌨️",
}


def print_separator(title: str):
    """Print a section separator with title."""
    separator = "━" * (console.width - len(title) - 4)
    text = Text()
    text.append("━━ ", style=COLORS["separator"])
    text.append(title, style="bold " + COLORS["separator"])
    text.append(f" {separator}", style=COLORS["separator"])
    console.print(text)


def get_relative_time(seconds: float) -> str:
    """Convert seconds to relative time string (e.g., '5m 23s')."""
    if seconds < 60:
        return f"{int(seconds)}s"
    elif seconds < 3600:
        minutes = int(seconds // 60)
        secs = int(seconds % 60)
        return f"{minutes}m {secs}s"
    else:
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        secs = int(seconds % 60)
        return f"{hours}h {minutes}m {secs}s"


class ConversationHandler:
    """Handles conversation display (user input and AI responses)."""
    
    def __init__(self):
        self.ai_buffer = []  # Buffer for streaming AI responses
        self.section_printed = False
    
    def _print_conversation_separator(self):
        """Print conversation separator line."""
        console.print()  # Blank line
        separator = "─" * console.width
        console.print(separator, style=COLORS["separator"])
    
    def user_input(self, text: str):
        """Display user input."""
        # Print separator before conversation
        if self.section_printed:  # Not the first time
            self._print_conversation_separator()
        else:
            console.print()  # Just blank line for first time
            self.section_printed = True
        
        user_text = Text()
        user_text.append("You", style=f"bold {COLORS['user']}")
        user_text.append(" > ", style=COLORS['user'])
        user_text.append(text, style=COLORS['user'])  # Apply color to text
        console.print(user_text)
        console.print()  # Blank line after user input
    
    def stream_ai(self, text: str):
        """Stream AI response text (no newline)."""
        # If this is the first chunk, print AI prefix
        if not self.ai_buffer:
            ai_prefix = Text()
            ai_prefix.append("Orion", style=f"bold {COLORS['ai']}")
            ai_prefix.append(" > ", style=COLORS['ai'])
            console.print(ai_prefix, end="")
        
        # Print the chunk with AI color styling
        styled_text = Text(text, style=COLORS['ai'])
        console.print(styled_text, end="")
        self.ai_buffer.append(text)
    
    def flush_ai(self):
        """Complete AI message with newline."""
        if self.ai_buffer:
            console.print()  # Newline to complete message
            console.print()  # Blank line after AI response
            self.ai_buffer = []


class SystemLogHandler:
    """Handles system notification logs."""
    
    def __init__(self):
        self.section_printed = False
        self.start_time = time.time()
    
    def _ensure_section_header(self):
        """Print section header once."""
        if not self.section_printed:
            console.print()  # Blank line
            print_separator("⚙️  SYSTEM LOGS")
            self.section_printed = True
    
    def info(self, message: str, category: str = "SESSION", duration: float = None):
        """
        Log system information.
        
        Args:
            message: Log message
            category: Category (SESSION, VIDEO, CONNECTION, INPUT, PASSIVE, TEXT)
            duration: Optional duration in seconds (for relative time display)
        """
        self._ensure_section_header()
        
        # Get emoji icon
        icon = CATEGORY_ICONS.get(category.upper(), "ℹ️")
        
        # Get color for category
        color_key = category.lower()
        if color_key == "connection" and "error" in message.lower():
            color = COLORS["connection_error"]
        else:
            color = COLORS.get(color_key, COLORS["session"])
        
        # Build log line
        log_line = Text()
        log_line.append(f"{icon} ", style=color)
        log_line.append(category.upper().ljust(12), style=f"bold {color}")
        log_line.append(message, style=color)
        
        # Add relative time if provided
        if duration is not None:
            relative = get_relative_time(duration)
            log_line.append(f" ({relative})", style=f"dim {color}")
        
        console.print(log_line)


class DebugHandler:
    """Handles debug output (only when VIDEO_DEBUG=True)."""
    
    def __init__(self):
        self.enabled = VIDEO_DEBUG
        self.section_printed = False
    
    def _ensure_section_header(self):
        """Print section header once."""
        if not self.section_printed and self.enabled:
            console.print()  # Blank line
            print_separator("🐛 DEBUG")
            self.section_printed = True
    
    def debug(self, message: str, category: str = "VIDEO"):
        """
        Log debug information (only if VIDEO_DEBUG=True).
        
        Args:
            message: Debug message
            category: Category for context
        """
        if not self.enabled:
            return
        
        self._ensure_section_header()
        
        # Build debug line
        debug_line = Text()
        debug_line.append("🐛 ", style=COLORS["debug"])
        debug_line.append(f"[{category}] ", style=f"dim {COLORS['debug']}")
        debug_line.append(message, style=COLORS["debug"])
        
        console.print(debug_line)


# Global instances
conversation = ConversationHandler()
system_log = SystemLogHandler()
debug_log = DebugHandler()


# Expose functions for convenience
__all__ = [
    "conversation",
    "system_log", 
    "debug_log",
    "print_separator",
    "get_relative_time",
]
