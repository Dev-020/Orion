# cli.py (V2.7 - Multimodal Compatible)
from orion_core import OrionCore
from dotenv import load_dotenv
import json
import os
from vertexai.generative_models import Part # <-- NEW, IMPORTANT IMPORT

# Load environment variables from .env file for the core to use
load_dotenv()

def run_cli():
    """Initializes the Orion Core and runs the command-line interface."""
    
    # --- 1. Create the "Brain" ---
    core = OrionCore()

    # --- 2. Run the User Interface Loop ---
    print("\n=================================================================")
    print("Orion CLI is active. Type 'quit' to exit.")
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
        # The old `structured_prompt` is gone.
        # We now create a list of Parts, which for the CLI is just the user's text.

        # We call the new process_prompt with the correct arguments.
        response_text = core.process_prompt(
            user_prompt=user_input,
            session_id=cli_session_id,
            file_check=[],
            user_id=cli_user_id,
            user_name=cli_user_name
        )
        # --- END OF MODIFICATION ---
        
        print(f"\nOrion: {response_text}\n")

if __name__ == "__main__":
    run_cli()