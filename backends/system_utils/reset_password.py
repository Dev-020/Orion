import sys
import os
from pathlib import Path

# Add project root to path so we can import backends
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.append(str(PROJECT_ROOT))

# Adjust data path logic relative to execution
# If we run from root, DB is in databases/users.db
# AuthManager defaults to "databases/users.db" which is correct for root execution

try:
    from backends.main_utils.auth_manager import AuthManager
except ImportError:
    print("Error: Could not import AuthManager. Make sure you are running this from the project root (Orion/).")
    print("Example: python reset_password.py")
    sys.exit(1)

def main():
    print("--- Orion Admin Password Reset Tool ---")
    username = input("Enter Username to reset: ").strip()
    if not username:
        print("Username cannot be empty.")
        return

    new_password = input("Enter New Password: ").strip()
    if not new_password:
        print("Password cannot be empty.")
        return
        
    # Initialize Auth Manager
    # Explicitly point to the DB in databases/
    db_path = str(PROJECT_ROOT / "databases" / "users.db")
    auth_manager = AuthManager(db_path=db_path)
    
    confirm = input(f"Are you sure you want to reset password for '{username}'? (y/n): ")
    if confirm.lower() != 'y':
        print("Cancelled.")
        return

    if auth_manager.update_password(username, new_password):
        print(f"\n[SUCCESS] Password for '{username}' has been updated.")
    else:
        print(f"\n[FAILED] Could not update password. User '{username}' may not exist.")

if __name__ == "__main__":
    main()
