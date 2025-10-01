"""
This module contains the functions for running the Tier 1 Heartbeat Check.
These are internal system utilities and are not intended to be called as tools by the AI.
"""

import json
import os
from typing import Callable, Dict, Any

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
                # Special handling for user_id which is required for some tools
                if "user_id" not in case["parameters"] and case["tool_name"] in ["execute_sql_write"]:
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

