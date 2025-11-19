import os
import sys
from unittest.mock import MagicMock
from dotenv import load_dotenv

# Add project root to path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

# Mock diagnostics BEFORE importing orion_core
# We need to mock the module 'system_utils.run_startup_diagnostics'
# But since orion_core imports it, we need to make sure it's mocked in sys.modules
mock_diagnostics = MagicMock()
mock_diagnostics.run_heartbeat_check.return_value = True
sys.modules['system_utils.run_startup_diagnostics'] = mock_diagnostics

from orion_core import OrionCore

def verify_streaming_tools():
    print("--- Starting Streaming Tool Verification (Diagnostics Skipped) ---")
    core = OrionCore()
    
    # Prompt that should trigger 'list_project_files'
    prompt = "You MUST use the 'list_project_files' tool to list the files in the current directory. Do not answer from memory. Execute the tool now."
    session_id = "test_stream_tool_session"
    user_id = os.getenv("DISCORD_OWNER_ID")
    user_name = "Owner"
    
    print(f"--- Sending Prompt: '{prompt}' ---")
    
    try:
        response_generator = core.process_prompt(
            session_id=session_id,
            user_prompt=prompt,
            file_check=[],
            user_id=user_id,
            user_name=user_name,
            stream=True
        )
        
        full_text = ""
        print("--- Stream Output Start ---")
        for chunk in response_generator:
            if isinstance(chunk, dict):
                print(f"\n--- Metadata Chunk: {chunk} ---")
            else:
                print(f"CHUNK: {repr(chunk)}")
                full_text += chunk
                
        print("\n--- Stream Output End ---")
        print(f"FULL TEXT CAPTURED:\n{full_text}\n-------------------")
        
        if "Executing tool:" in full_text:
            print("SUCCESS: Tool execution message detected.")
        elif "verify_streaming_tools.py" in full_text:
             print("PARTIAL SUCCESS: File list returned, but execution message missing?")
        else:
            print("FAILURE: Tool execution not detected and file list not found.")

    except Exception as e:
        print(f"\nCRITICAL ERROR: {e}")

if __name__ == "__main__":
    verify_streaming_tools()
