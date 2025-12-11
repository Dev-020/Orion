import os
import sys
import json
import time
import shutil
import hashlib
import sqlite3
import argparse
import datetime
import google.auth
from pathlib import Path
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from googleapiclient.errors import HttpError

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.append(str(PROJECT_ROOT))

# Configuration
DATABASES_DIR = PROJECT_ROOT / 'databases'
BACKUP_STATE_FILE = PROJECT_ROOT / 'data' / 'backup_state.json'
DRIVE_FOLDER_NAME = 'Orion'
BACKUP_ROOT_FOLDER = 'db_backups'

def get_authenticated_service():
    """Gets a Google Drive API service object."""
    creds, _ = google.auth.default()
    return build('drive', 'v3', credentials=creds)

def find_or_create_folder(service, folder_name, parent_id=None):
    """Finds a folder by name within a parent, or creates it."""
    query = f"mimeType='application/vnd.google-apps.folder' and name='{folder_name}' and trashed=false"
    if parent_id:
        query += f" and '{parent_id}' in parents"
    
    results = service.files().list(q=query, fields="files(id, name)").execute()
    files = results.get('files', [])

    if files:
        return files[0]['id']
    else:
        file_metadata = {
            'name': folder_name,
            'mimeType': 'application/vnd.google-apps.folder'
        }
        if parent_id:
            file_metadata['parents'] = [parent_id]
        
        folder = service.files().create(body=file_metadata, fields='id').execute()
        return folder['id']

def calculate_file_hash(filepath):
    """Calculates SHA256 hash of a file."""
    sha256_hash = hashlib.sha256()
    with open(filepath, "rb") as f:
        # Read and update hash string value in blocks of 4K
        for byte_block in iter(lambda: f.read(4096), b""):
            sha256_hash.update(byte_block)
    return sha256_hash.hexdigest()

def load_backup_state():
    """Loads the backup state from JSON."""
    if BACKUP_STATE_FILE.exists():
        with open(BACKUP_STATE_FILE, 'r') as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                return {}
    return {}

def save_backup_state(state):
    """Saves the backup state to JSON."""
    BACKUP_STATE_FILE.parent.mkdir(exist_ok=True, parents=True)
    with open(BACKUP_STATE_FILE, 'w') as f:
        json.dump(state, f, indent=4)

def perform_hot_backup(src_db_path, dest_backup_path):
    """
    Performs a hot backup of a SQLite database using the SQLite Backup API.
    This ensures data consistency even if the DB is being written to.
    """
    try:
        # Open the source database
        src_conn = sqlite3.connect(src_db_path)
        
        # Open the destination database (will be created)
        dest_conn = sqlite3.connect(dest_backup_path)
        
        # Copy data from source to destination
        src_conn.backup(dest_conn)
        
        # Close connections
        dest_conn.close()
        src_conn.close()
        return True
    except Exception as e:
        print(f"Error during hot backup of {src_db_path}: {e}")
        return False

def upload_file(service, filepath, parent_id):
    """Uploads a file to Google Drive."""
    file_metadata = {
        'name': filepath.name,
        'parents': [parent_id]
    }
    media = MediaFileUpload(str(filepath), resumable=True)
    try:
        file = service.files().create(body=file_metadata, media_body=media, fields='id').execute()
        print(f"File ID: {file.get('id')} uploaded.")
        return file.get('id')
    except HttpError as error:
        print(f"An error occurred: {error}")
        return None

def main():
    parser = argparse.ArgumentParser(description='Backup Orion Databases to Google Drive.')
    parser.add_argument('--type', choices=['auto', 'manual'], default='manual', help='Type of backup (auto or manual)')
    args = parser.parse_args()

    print(f"--- Starting {args.type.upper()} Backup ---")
    
    # 1. Authenticate
    try:
        service = get_authenticated_service()
    except Exception as e:
        print(f"Authentication failed: {e}")
        return

    # 2. Setup Drive Structure
    try:
        drive_orion_id = find_or_create_folder(service, DRIVE_FOLDER_NAME)
        backup_root_id = find_or_create_folder(service, BACKUP_ROOT_FOLDER, drive_orion_id)
        type_folder_id = find_or_create_folder(service, args.type, backup_root_id)
        
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        
        # Initialize variable for folder ID (only create if we actually have files to upload)
        current_backup_folder_id = None
        
    except Exception as e:
        print(f"Failed to setup Drive folder structure: {e}")
        return

    # 3. Discovery & Backup Loop
    backup_state = load_backup_state()
    files_uploaded = 0
    files_to_upload = []

    if not DATABASES_DIR.exists():
        print(f"Database directory not found: {DATABASES_DIR}")
        return

    # First pass: Check what needs to be uploaded
    for persona_dir in DATABASES_DIR.iterdir():
        if persona_dir.is_dir():
            persona_name = persona_dir.name
            db_file = persona_dir / 'orion_database.sqlite'
            
            if db_file.exists():
                print(f"Checking persona: {persona_name}...")
                
                # Smart Change Detection (Auto Only)
                current_hash = calculate_file_hash(db_file)
                last_hash = backup_state.get(persona_name, {}).get('last_hash')
                
                if args.type == 'auto' and current_hash == last_hash:
                    print(f"  -> Skipped (No changes detected since last backup).")
                    continue
                
                files_to_upload.append((persona_name, db_file, current_hash))

    # Second pass: Perform backups if pending files exist
    if files_to_upload:
        # Create timestamp folder only now
        current_backup_folder_id = find_or_create_folder(service, timestamp, type_folder_id)
        print(f"Drive Destination: {DRIVE_FOLDER_NAME}/{BACKUP_ROOT_FOLDER}/{args.type}/{timestamp}/")

        for persona_name, db_file, current_hash in files_to_upload:
             # Perform Hot Backup to Temp File
            temp_filename = f"orion_database_{persona_name}_{timestamp}.sqlite"
            temp_filepath = PROJECT_ROOT / 'data' / temp_filename
            
            print(f"  -> Creating Hot Snapshot for {persona_name}...")
            if perform_hot_backup(db_file, temp_filepath):
                # Upload
                print(f"  -> Uploading to Drive...")
                if upload_file(service, temp_filepath, current_backup_folder_id):
                    files_uploaded += 1
                    # Update State
                    backup_state[persona_name] = {
                        'last_hash': current_hash,
                        'last_backup_time': timestamp
                    }
                
                # Cleanup
                if temp_filepath.exists():
                    os.remove(temp_filepath)
            else:
                print(f"  -> Hot Backup Failed!")
    
    # Save state
    save_backup_state(backup_state)
    
    if files_uploaded > 0:
        print(f"--- Backup Complete. {files_uploaded} files uploaded. ---")
    elif args.type == 'auto':
        print("--- Backup Complete. No changes detected. ---")
    else:
        print("--- No files found to backup. ---")

if __name__ == '__main__':
    main()
