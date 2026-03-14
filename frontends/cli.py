# cli.py (V2.7 - Multimodal Compatible)
import sys
from pathlib import Path

# --- PATH HACK FOR REFRACTOR PHASE 1 ---
# Add 'backends' to sys.path so we can import 'orion_core'
sys.path.append(str(Path(__file__).resolve().parent.parent / 'backends'))
# ---------------------------------------

from orion_core import OrionCore
from main_utils import config
from dotenv import load_dotenv
import json
import os
from vertexai.generative_models import Part # <-- NEW, IMPORTANT IMPORT

# Load environment variables from .env file for the core to use
load_dotenv()

def run_cli():
    """Initializes the Orion Core and runs the command-line interface."""
    
    # --- 1. Create the "Brain" ---
    if config.BACKEND == "cli":
        from orion_core_geminicli import OrionCoreGeminiCLI
        core = OrionCoreGeminiCLI()
    elif config.BACKEND == "ollama":
        from orion_core_lite import OrionLiteCore
        core = OrionLiteCore()
    else:
        from orion_core import OrionCore
        core = OrionCore()

    # --- 2. Run the User Interface Loop ---
    print("\n=================================================================")
    print(f"Orion CLI is active ({config.BACKEND} backend). Type 'quit' to exit.")
    print("=================================================================\n")

    cli_session_id = "local_cli_user"
    cli_user_id = os.getenv("DISCORD_OWNER_ID") or "000000000000000000" # The CLI user may NOT always be the owner
    cli_user_name = "Leo (CLI)"

    while True:
        user_input = input("You: ")
        if user_input.lower() == 'quit':
            # --- ADDITION: Ensure shutdown is called for the CLI ---
            print("Archiving session memory and shutting down...")
            core.shutdown()
            # --- END OF ADDITION ---
            break
        if not user_input.strip():
            continue

        # --- MODIFICATION HERE ---
        # Handle the generator returned by process_prompt
        print("\nOrion: ", end="", flush=True)
        
        response_text = ""
        token_count = 0
        restart_pending = False
        
        for chunk in core.process_prompt(
            user_prompt=user_input,
            session_id=cli_session_id,
            file_check=[],
            user_id=cli_user_id,
            user_name=cli_user_name,
            stream=True
        ):
            if chunk["type"] == "token":
                print(chunk["content"], end="", flush=True)
                response_text += chunk["content"]
            elif chunk["type"] == "status":
                # Optional: print status in a subtle way
                # print(f"[{chunk['content']}] ", end="", flush=True)
                pass
            elif chunk["type"] == "full_response":
                response_text = chunk.get("text", response_text)
                token_count = chunk.get("token_count", token_count)
                restart_pending = chunk.get("restart_pending", restart_pending)
            elif chunk["type"] == "usage":
                token_count = chunk.get("token_count", token_count)
                restart_pending = chunk.get("restart_pending", restart_pending)
        
        if token_count > 0:
            print(f"\n\n*(`Tokens: {token_count}`)*\n")
        else:
            print("\n")

        # --- Orchestrated Restart Logic for CLI ---
        if restart_pending:
            print("---! DELAYED RESTART SEQUENCE ACTIVATED !---")
            if core.save_state_for_restart():
                # The restart call will terminate this script and start a new one.
                core.execute_restart()
        # --- END OF MODIFICATION ---

if __name__ == "__main__":
    run_cli()