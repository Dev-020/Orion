import sys
import time
import logging
from pathlib import Path

# Add project root to sys.path to ensure imports work
project_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(project_root))

from backends.main_utils.orion_logger import setup_logging

def demo_logging():
    # 1. Setup Logger
    log_file = project_root / "backends" / "data" / "logs" / "demo_test.log"
    setup_logging("DemoLogger", log_file, level=logging.INFO, console_output=True)
    logger = logging.getLogger("DemoLogger")

    print("\n--- STARTING LOGGING DEMO ---\n")

    # 2. Standard Logs
    logger.info("This is a standard INFO message. It should be green/white in console.")
    logger.warning("This is a WARNING message. It should be yellow in console.")
    logger.error("This is an ERROR message. It should be red in console.")

    # 3. Hybrid Thinking Strategy Demo
    print("\n--- SIMULATING AI THOUGHT PROCESS ---\n")
    
    # In the code (orion_core_lite.py), we log a summary for the file
    logger.info("[Thinking Process Started...]")
    
    # And stream simulated thoughts directly to stdout (console only)
    thought_text = "Thinking... Analyzing request... Formulating response..."
    # ANSI Grey for thoughts
    sys.stdout.write("\033[90m") 
    for char in thought_text:
        sys.stdout.write(char)
        sys.stdout.flush()
        time.sleep(0.05) # Simulate streaming speed
    sys.stdout.write("\033[0m\n") # Reset color
    
    # Log completion summary to file
    logger.info("[Thinking Process Complete]")

    print("\n--- DEMO COMPLETE ---\n")
    print(f"File logs written to: {log_file}")

if __name__ == "__main__":
    demo_logging()
