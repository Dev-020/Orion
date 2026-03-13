import os
import sys
import json
import logging
import time

# Ensure backends is in path for imports
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from orion_core_geminicli import OrionCoreGeminiCLI
from main_utils import config
from main_utils.orion_logger import setup_logging

def run_test():
    # Setup clean logging
    setup_logging("TestCLI", level=logging.INFO)
    logger = logging.getLogger("TestCLI")
    
    logger.info("=== Gemini CLI Core Integration Test ===")
    
    # Disable components not needed for a quick text test
    config.VOICE = False
    config.VISION = False
    config.PAST_MEMORY = False
    
    # Initialize the Core
    try:
        core = OrionCoreGeminiCLI()
        logger.info("Core Initialized.")
    except Exception as e:
        logger.error(f"Failed to initialize core: {e}")
        return

    # Use a fresh session for isolation
    test_session_id = f"test-direct-{int(time.time())}"
    test_prompt = "Hello! Can you list out the current directory you are in right now? Then brieflt introduce yourself. Also perform a simple tool call to determine that your functionalities are working."
    
    logger.info(f"Sending Prompt: '{test_prompt}'")
    
    try:
        generator = core.process_prompt(
            session_id=test_session_id,
            user_prompt=test_prompt,
            user_id="test-user",
            user_name="Tester",
            stream=True
        )
        
        print("\n--- Assistant Response ---")
        for chunk in generator:
            if chunk["type"] == "token":
                print(chunk["content"], end="", flush=True)
            elif chunk["type"] == "status":
                # Print status updates on a new line to avoid interfering with tokens
                print(f"\n[Status]: {chunk['content']}")
        print("\n--------------------------\n")

    except Exception as e:
        logger.error(f"Error during prompt processing: {e}")
    finally:
        logger.info("Shutting down core...")
        core.shutdown()
        logger.info("Test complete.")

if __name__ == "__main__":
    run_test()
