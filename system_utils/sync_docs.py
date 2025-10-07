# --- START OF FILE sync_docs.py (Drive API Markdown Export Version) ---
import os
import json
import io
import google.auth
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaIoBaseDownload
from pathlib import Path

# --- PATH CONFIGURATION ---
# Determine the project root directory (which is the parent of 'system_utils')
PROJECT_ROOT = Path(__file__).resolve().parent.parent

MANIFEST_FILE = Path(__file__).resolve().parent / 'docs_manifest.json'
INSTRUCTIONS_DIR = PROJECT_ROOT / 'instructions'

def get_authenticated_service(service_name, version):
    """Gets a Google API service object with Application Default Credentials."""
    credentials, _ = google.auth.default()
    service = build(service_name, version, credentials=credentials, static_discovery=False)
    return service

def get_doc_as_markdown(service, doc_id):
    """Downloads a Google Doc directly as a Markdown file using the Drive API."""
    try:
        mime_type = 'text/markdown'
        request = service.files().export(fileId=doc_id, mimeType=mime_type)
        
        fh = io.BytesIO()
        downloader = MediaIoBaseDownload(fh, request)
        
        done = False
        while not done:
            status, done = downloader.next_chunk()
            print(f"  -> Download progress: {int(status.progress() * 100)}%")
            
        # Decode the downloaded bytes into a string
        fh.seek(0)
        markdown_content = fh.read().decode('utf-8')
        return markdown_content
        
    except HttpError as err:
        print(f"An error occurred while downloading the document: {err}")
        # Add more specific error handling if needed, e.g., for 404 Not Found
        return None

def sync_instructions():
    """Main function to check for updates and sync documents as Markdown."""
    try:
        drive_service = get_authenticated_service('drive', 'v3')
    except Exception as e:
        print(f"Authentication failed for Google Drive. Ensure you have run 'gcloud auth application-default login'. Error: {e}")
        return

    # Ensure the output directory exists.
    INSTRUCTIONS_DIR.mkdir(exist_ok=True)

    with open(MANIFEST_FILE, 'r+') as f:
        manifest_data = json.load(f)
        for doc_info in manifest_data['instructions']:
            doc_id = doc_info['google_doc_id']
            local_filename = doc_info['name']
            local_filepath = os.path.join(INSTRUCTIONS_DIR, local_filename)
            last_known_mod_time = doc_info['last_modified_time']
            
            print(f"Checking '{local_filename}'...")
            try:
                metadata = drive_service.files().get(fileId=doc_id, fields='modifiedTime').execute()
                current_mod_time = metadata['modifiedTime']
                
                if current_mod_time != last_known_mod_time or not os.path.exists(local_filepath):
                    print(f"  -> Change detected! Downloading latest version as Markdown...")
                    content = get_doc_as_markdown(drive_service, doc_id)
                    
                    if content is not None:
                        with open(local_filepath, 'w', encoding='utf-8') as out_file:
                            out_file.write(content)
                        doc_info['last_modified_time'] = current_mod_time
                        print(f"  -> Successfully updated '{local_filename}'.")
                else:
                    print("  -> No changes. File is up to date.")
            
            except HttpError as err:
                print(f"An error occurred with doc ID {doc_id}: {err}")
                
        f.seek(0)
        json.dump(manifest_data, f, indent=2)
        f.truncate()

if __name__ == '__main__':
    sync_instructions()
