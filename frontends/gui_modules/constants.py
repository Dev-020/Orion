import os
import customtkinter
import dotenv

dotenv.load_dotenv()

# --- Configuration & Defaults ---
WINDOW_TITLE = "Orion Core - Test Environment"
WINDOW_GEOMETRY = "600x1050"
DEFAULT_USER_ID = os.getenv("DISCORD_OWNER_ID") or "000000000000000000"
DEFAULT_USER_NAME = "Leo (GUI)"
DEFAULT_SESSION_ID = "local_gui_user"

# --- Colors ---
COLOR_TRANSPARENT = "transparent"
COLOR_BG_DARK = "#242424"       # Main window bg (default ctk)
COLOR_PANEL_BG = "#303030"      # Chat bubble / frame bg
COLOR_BUTTON_GRAY = "#505050"
COLOR_BUTTON_GRAY_HOVER = "#606060"
COLOR_BUTTON_RED = "#db524b"
COLOR_BUTTON_RED_HOVER = "#b0423d"

# Text Colors
TEXT_CYAN = "cyan"
TEXT_GRAY = "gray"
TEXT_RED = "red"
TEXT_GREEN = "#4CAF50"
TEXT_ORANGE = "#FF9800"
TEXT_LIGHT_GRAY = "#AAAAAA"

# --- Fonts ---
# Note: We can return dicts to unpack or CTkFont objects if CTk is initialized.
# Returning dicts is safer for import time.
def get_font_bold(size=12):
    return customtkinter.CTkFont(size=size, weight="bold")

def get_font_normal(size=13):
    return customtkinter.CTkFont(size=size)

def get_font_bubble(size=15):
    return customtkinter.CTkFont(size=size)

def get_font_small_italic(size=11):
    return customtkinter.CTkFont(size=size, slant="italic")

# --- Layout ---
PANE_SASH_WIDTH = 4
CHAT_PANE_MINSIZE = 300
CHAT_PANE_HEIGHT = 750
BOTTOM_PANE_MINSIZE = 300
BOTTOM_PANE_HEIGHT = 300
