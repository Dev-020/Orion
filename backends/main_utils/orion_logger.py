import logging
import sys
from pathlib import Path
import os

# ANSI Color Codes
RESET = "\033[0m"
GREY = "\033[90m"
CYAN = "\033[96m"
YELLOW = "\033[93m"
RED = "\033[91m"
BOLD_RED = "\033[1;91m"

class ColorFormatter(logging.Formatter):
    """
    Formatter for Console Output. 
    Adds color based on log level.
    """
    
    FORMATS = {
        logging.DEBUG:    GREY + "%(asctime)s - [%(name)s] - %(levelname)s - %(message)s" + RESET,
        logging.INFO:     CYAN + "%(asctime)s - [%(name)s] - %(levelname)s - %(message)s" + RESET,
        logging.WARNING:  YELLOW + "%(asctime)s -   [%(name)s] - %(levelname)s - %(message)s" + RESET,
        logging.ERROR:    RED + "%(asctime)s - [%(name)s] - %(levelname)s - %(message)s" + RESET,
        logging.CRITICAL: BOLD_RED + "%(asctime)s - [%(name)s] - %(levelname)s - %(message)s" + RESET
    }

    def format(self, record):
        log_fmt = self.FORMATS.get(record.levelno, self.FORMATS[logging.INFO])
        formatter = logging.Formatter(log_fmt, datefmt="%Y-%m-%d %H:%M:%S")
        return formatter.format(record)

class PlainFormatter(logging.Formatter):
    """
    Formatter for File Output.
    Clean text, no colors.
    """
    def __init__(self):
        super().__init__("%(asctime)s - [%(name)s] - %(levelname)s - %(message)s", datefmt="%Y-%m-%d %H:%M:%S")

def setup_logging(logger_name: str, log_file_path: Path = None, level=logging.INFO, console_output=True):
    """
    Sets up the logger with:
    1. StreamHandler (Console) - Colorized
    2. FileHandler (File) - Plain Text (if log_file_path provided)
    
    Returns the configured logger.
    """
    # Get the ROOT logger to capture logs from all modules (OrionCore, Utils, etc.)
    # This acts as the "Umbrella" for the entire process.
    root_logger = logging.getLogger()
    root_logger.setLevel(logging.DEBUG) 
    
    # Remove existing handlers to avoid duplicates on restart/reload
    if root_logger.hasHandlers():
        root_logger.handlers.clear()

    # 1. Console Handler
    # If running managed (by launcher), suppress console output to avoid duplicates
    # because launcher redirects stdout to the log file already.
    if console_output and os.environ.get("ORION_MANAGED_PROCESS") != "true":
        c_handler = logging.StreamHandler(sys.stdout)
        c_handler.setLevel(level)
        c_handler.setFormatter(ColorFormatter())
        root_logger.addHandler(c_handler)

    # 2. File Handler
    if log_file_path:
        # Ensure directory exists
        log_file_path.parent.mkdir(parents=True, exist_ok=True)
        
        f_handler = logging.FileHandler(log_file_path, encoding='utf-8')
        f_handler.setLevel(logging.DEBUG) # Always log everything to file for debugging
        f_handler.setFormatter(PlainFormatter()) # Revert to Plain for clean files
        root_logger.addHandler(f_handler)
        
    # 3. Crash Handling (Sys Excepthook)
    # This ensures that unhandled exceptions (crashes) are logged to the file
    # 3. Crash Handling (Sys Excepthook)
    def handle_exception(exc_type, exc_value, exc_traceback):
        if issubclass(exc_type, KeyboardInterrupt):
            sys.__excepthook__(exc_type, exc_value, exc_traceback)
            return
        root_logger.critical("Uncaught Exception:", exc_info=(exc_type, exc_value, exc_traceback))

    sys.excepthook = handle_exception
    
    # 4. Suppress Noisy Third-Party Loggers
    # We set these to WARNING so they don't spam INFO/DEBUG logs to our Root Logger
    noisy_libraries = [
        "httpcore", 
        "httpx", 
        "discord", 
        "websockets", 
        "uvicorn.access", # Suppress access logs (GET /health 200 OK etc)
        "chromadb",
        "watchfiles"
    ]
    for lib in noisy_libraries:
         logging.getLogger(lib).setLevel(logging.WARNING)
        
    return logging.getLogger(logger_name)

def get_orion_logger(name: str):
    """
    Helper to get a logger for a module.
    Assumes setup_logging has been called by the main process entry point.
    """
    return logging.getLogger(name)

if __name__ == "__main__":
    # Test
    log = setup_logging("TestLogger", Path("test.log"))
    log.info("This is Info (Cyan)")
    log.warning("This is Warning (Yellow)")
    log.error("This is Error (Red)")
    log.debug("This is Debug (Grey)")
    print("Check test.log for plain text.")
