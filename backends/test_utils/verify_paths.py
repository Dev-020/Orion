import sys
from pathlib import Path

# Add project root to sys.path
sys.path.append("c:\\GitBash\\Orion")

from main_utils import config, main_functions

def verify():
    print("--- Verifying Phase 1 (Pathlib Standardization) ---")
    
    # Check 1: PROJECT_ROOT type
    if isinstance(config.PROJECT_ROOT, Path):
        print(f"[PASS] config.PROJECT_ROOT is a Path object: {config.PROJECT_ROOT}")
    else:
        print(f"[FAIL] config.PROJECT_ROOT is NOT a Path object. Type: {type(config.PROJECT_ROOT)}")
        
    # Check 2: Existence
    if config.PROJECT_ROOT.exists():
        print(f"[PASS] config.PROJECT_ROOT exists on disk.")
    else:
        print(f"[FAIL] config.PROJECT_ROOT path not found!")

    # Check 3: OUTPUT_DIR logic
    if isinstance(config.OUTPUT_DIR, Path):
         print(f"[PASS] config.OUTPUT_DIR is a Path object: {config.OUTPUT_DIR}")
    else:
         print(f"[FAIL] config.OUTPUT_DIR is NOT a Path object.")

    # Check 4: get_db_paths resolution (simulating config.PERSONA='default')
    paths = main_functions.get_db_paths("default")
    print("\n--- DB Paths Resolution ---")
    for key, val in paths.items():
        print(f"{key}: {val}")
        if isinstance(val, str):
             print(f"  -> [PASS] {key} returned as string (Compatibility Mode)")
        else:
             print(f"  -> [WARN] {key} is {type(val)} (Expected str)")

    print("\n--- System Utils Import Check ---")
    try:
        from system_utils import sync_docs, generate_manifests, embed_document
        print("[PASS] Successfully imported sync_docs, generate_manifests, and embed_document.")
    except ImportError as e:
        print(f"[FAIL] Failed to import system_utils modules: {e}")
    except Exception as e:
        print(f"[FAIL] Unexpected error importing system_utils: {e}")

    print("\n[SUCCESS] Phase 1 Verification Complete.")

if __name__ == "__main__":
    verify()
