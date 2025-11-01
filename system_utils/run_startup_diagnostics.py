"""
This module contains the functions for running the Tier 1 Heartbeat Check.
These are internal system utilities and are not intended to be called as tools by the AI.
"""

import json
import os, sys
from typing import Callable, Dict, Any
import dotenv

# Get the path of the directory containing the current script (system_utils)
current_script_dir = os.path.dirname(os.path.abspath(__file__))

# Get the path of the parent directory (the project root, Orion)
project_root = os.path.dirname(current_script_dir)

# Add the project root to Python's path
sys.path.append(project_root)

from main_utils import main_functions as functions

# This function would be imported and called by orion_core.py during its boot sequence.
# The `tools` dictionary would be passed in from the OrionCore instance to avoid circular imports.
def run_heartbeat_check(tools: Dict[str, Callable]) -> bool:
    """
    Runs a series of pre-defined, low-impact "heartbeat" checks on core tools.

    Args:
        tools (Dict[str, Callable]): A dictionary mapping tool names to their callable functions.

    Returns:
        bool: True if all tests pass, False otherwise.
    """
    dotenv.load_dotenv()
    owner_id = os.getenv("DISCORD_OWNER_ID")
    suite_path = os.path.join('instructions', 'diagnostic_suite.json')
    all_tests_passed = True

    print("--- INITIATING TIER 1 HEARTBEAT CHECK ---")

    if not os.path.exists(suite_path):
        print(f"CRITICAL ERROR: Diagnostic suite file not found at {suite_path}. Aborting checks.")
        return False

    with open(suite_path, 'r') as f:
        test_suite = json.load(f)

    for test in test_suite:
        tool_name = test.get("tool_to_test")
        description = test.get("description")
        test_cases = test.get("test_case")

        if not isinstance(test_cases, list):
            test_cases = [test_cases]

        print(f"Testing: {tool_name} - {description}...")

        if tool_name not in tools:
            print(f"  [FAIL] Tool '{tool_name}' not found in the provided toolset.")
            all_tests_passed = False
            continue

        try:
            for case in test_cases:
                tool_func = tools[case["tool_name"]]
                
                # Define which functions require a user_id
                functions_requiring_user_id = [
                    "execute_write", "execute_vdb_write", "execute_sql_write",
                    "execute_sql_ddl", "manage_character_resource", "manage_character_status",
                    "create_git_commit_proposal", "manual_sync_instructions"
                ]

                # Add user_id only if the function requires it
                if case["tool_name"] in functions_requiring_user_id:
                    if case.get("requires_owner"):
                        case["parameters"]["user_id"] = owner_id
                    elif "user_id" not in case["parameters"]:
                        case["parameters"]["user_id"] = "SYSTEM_DIAGNOSTIC_USER"

                result = tool_func(**case["parameters"])
                # We don't need to validate the result for a heartbeat, just that it didn't crash.
                # A more advanced version could check the result against an expected pattern.
            print(f"  [PASS] {tool_name} executed successfully.")

        except Exception as e:
            print(f"  [FAIL] {tool_name} failed with an exception: {e}")
            all_tests_passed = False
            
    print("--- HEARTBEAT CHECK COMPLETE ---")
    if all_tests_passed:
        print("Result: All core systems are nominal.")
    else:
        print("Result: One or more core systems failed the heartbeat check.")
        
    return all_tests_passed

def main():
    tools = [getattr(functions, func_name) for func_name in functions.__all__]
    tools_dict = {func.__name__: func for func in tools}
    run_heartbeat_check(tools_dict)

if __name__ == "__main__":
    main()