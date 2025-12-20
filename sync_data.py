import os
import sys
import shutil
import argparse
import time
import io
from pathlib import Path
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload, MediaIoBaseUpload
import google.auth
from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow

# --- CONFIGURATION ---
PROJECT_ROOT = Path(__file__).resolve().parent
DATABASES_DIR = PROJECT_ROOT / "databases"
DATA_DIR = PROJECT_ROOT / "backends" / "data"
SYNC_FILENAME = "orion_sync_state.zip"
DRIVE_FOLDER_NAME = "Orion"
SCOPES = ['https://www.googleapis.com/auth/drive.file']

def get_authenticated_service():
    """Authenticates with Google Drive."""
    creds = None
    # We look for token.json in standard expected locations or relative to script
    # This logic mimics standard Google Auth flow but looks in PROJECT_ROOT
    token_path = PROJECT_ROOT / "token.json" # Assuming token.json might be at root or passed
    
    # Try generic default auth first (useful if potential environment defaults)
    try:
        creds, _ = google.auth.default(scopes=SCOPES)
    except:
        pass

    # If no valid generic creds, use typical client_secret flow if we were interactive
    # For now, let's assume the user has a setup similar to backup_db.py which relies on google.auth.default()
    # or specific .env vars.
    # backup_db.py uses `google.auth.default()`. We will stick to that.
    if not creds or not creds.valid:
        creds, _ = google.auth.default()
    
    return build('drive', 'v3', credentials=creds)

def find_file_in_folder(service, filename, folder_id):
    """Finds a specific file ID within a folder."""
    query = f"name='{filename}' and '{folder_id}' in parents and trashed=false"
    results = service.files().list(q=query, fields="files(id, name)").execute()
    files = results.get('files', [])
    return files[0]['id'] if files else None

def find_or_create_folder(service, folder_name, parent_id=None):
    """Finds or creates a folder."""
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

def zip_folders(zip_path):
    """Zips the databases and data directories."""
    print(f"Archiving data to {zip_path}...")
    
    # We want to zip 'databases' and 'backends/data'.
    # shutil.make_archive creates a zip of a SINGLE root_dir.
    # To include multiple specific distinct folders, we need to create a temporary staging area
    # or use zipfile module directly. Direct zipfile is cleaner to avoid copying gigabytes of data.
    
    import zipfile
    
    with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zipf:
        # Add databases
        for root, dirs, files in os.walk(DATABASES_DIR):
            for file in files:
                file_path = Path(root) / file
                # Archive name should be relative to PROJECT_ROOT e.g. "databases/users.db"
                arcname = file_path.relative_to(PROJECT_ROOT)
                zipf.write(file_path, arcname)
                
        # Add backends/data
        for root, dirs, files in os.walk(DATA_DIR):
            for file in files:
                file_path = Path(root) / file
                arcname = file_path.relative_to(PROJECT_ROOT)
                zipf.write(file_path, arcname)
                
    print(f"Archive created. Size: {os.path.getsize(zip_path) / (1024*1024):.2f} MB")

def push_sync(service):
    """Zips local data and uploads to Drive."""
    print("--- STARTING PUSH SYNC ---")
    
    # 1. Zip
    temp_zip = PROJECT_ROOT / "temp_sync.zip"
    try:
        zip_folders(temp_zip)
        
        # 2. Upload
        root_folder_id = find_or_create_folder(service, DRIVE_FOLDER_NAME)
        # Search for existing sync file
        existing_file_id = find_file_in_folder(service, SYNC_FILENAME, root_folder_id)
        
        if existing_file_id:
            print(f"Updating existing cloud archive (ID: {existing_file_id})...")
            # Use 'with open' to ensure file handle is closed immediately after usage
            with open(temp_zip, 'rb') as f:
                media = MediaIoBaseUpload(f, mimetype='application/zip', resumable=True)
                service.files().update(
                    fileId=existing_file_id,
                    media_body=media
                ).execute()
        else:
            print("Creating new cloud archive...")
            file_metadata = {
                'name': SYNC_FILENAME,
                'parents': [root_folder_id]
            }
            with open(temp_zip, 'rb') as f:
                media = MediaIoBaseUpload(f, mimetype='application/zip', resumable=True)
                service.files().create(
                    body=file_metadata,
                    media_body=media,
                    fields='id'
                ).execute()
            
        print("Push complete!")
        
    finally:
        if temp_zip.exists():
            os.remove(temp_zip)

def pull_sync(service):
    """Downloads from Drive and overwrites local data."""
    print("--- STARTING PULL SYNC ---")
    
    # 1. Find File
    root_folder_id = find_or_create_folder(service, DRIVE_FOLDER_NAME)
    file_id = find_file_in_folder(service, SYNC_FILENAME, root_folder_id)
    
    if not file_id:
        print("No sync archive found in cloud! (Did you 'push' from the source device?)")
        return

    # 2. Download
    print(f"Downloading archive (ID: {file_id})...")
    temp_zip = PROJECT_ROOT / "temp_pull.zip"
    request = service.files().get_media(fileId=file_id)
    fh = io.FileIO(temp_zip, 'wb')
    downloader = MediaIoBaseDownload(fh, request)
    done = False
    while done is False:
        status, done = downloader.next_chunk()
        print(f"Download {int(status.progress() * 100)}%.", end='\r')
    print("\nDownload complete.")
    fh.close()
    
    # 3. Validation & Extraction
    print("Validating archive integrity...")
    try:
        import zipfile
        
        # Verify zip structure and CRCs before touching any local files
        with zipfile.ZipFile(temp_zip, 'r') as zipf:
            first_bad_file = zipf.testzip()
            if first_bad_file:
                raise zipfile.BadZipFile(f"CRC-32 error detected in file: {first_bad_file}")
            
            # If we get here, the zip is good. NOW we can safely replace local data.
            print("Archive is valid. replacing local data...")
            
            # Helper to nuke folders before extracting to ensure no stale files
            print("Clearing local state folders...")
            if DATABASES_DIR.exists(): shutil.rmtree(DATABASES_DIR)
            if DATA_DIR.exists(): shutil.rmtree(DATA_DIR)
            
            print(f"Extracting to {PROJECT_ROOT}...")
            zipf.extractall(PROJECT_ROOT)
            
        print("Pull complete! Local state is now identical to cloud.")
        
    except zipfile.BadZipFile as e:
        print("\n[ERROR] The downloaded archive is corrupted!")
        print(f"Details: {e}")
        print("Use the 'push' command on the SOURCE device to create a fresh archive.")
        print("Your local data has NOT been modified.")
        
    finally:
        if temp_zip.exists():
            os.remove(temp_zip)

def main():
    parser = argparse.ArgumentParser(description="Orion Data Sync")
    parser.add_argument("action", choices=["push", "pull"], help="Sync direction (push=upload, pull=download)")
    args = parser.parse_args()
    
    try:
        service = get_authenticated_service()
        if args.action == "push":
            push_sync(service)
        else:
            pull_sync(service)
    except Exception as e:
        print(f"Sync failed: {e}")

if __name__ == "__main__":
    main()
