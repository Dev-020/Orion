# --- START OF FILE sync_docs.py (Drive API Markdown Export Version with Image Stripping) ---
import os
import json
import io
import re
import sys
import google.auth
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaIoBaseDownload
from pathlib import Path
from .embed_document import run_embedding_sync

# Add project root to be able to import main_utils
sys.path.append(str(Path(__file__).resolve().parent.parent))
from main_utils import config

# --- PATH CONFIGURATION ---
INSTRUCTIONS_DIR = Path(config.OUTPUT_DIR)
MANIFEST_FILE = Path(config.PROJECT_ROOT) / 'data' / f'docs_{config.PERSONA}.json'

def get_authenticated_service(service_name, version):
    """Gets a Google API service object with Application Default Credentials."""
    credentials, _ = google.auth.default()
    service = build(service_name, version, credentials=credentials, static_discovery=False)
    return service

def strip_base64_images(markdown_content):
    """Removes base64 encoded images from a Markdown string."""
    # Google Docs export places image data definitions at the end.
    # We find the first occurrence of a markdown image data block start
    # and truncate the rest of the file. This is more reliable than regex.
    try:
        cutoff_index = markdown_content.index('[image1]: <data:image')
        return markdown_content[:cutoff_index].strip()
    except ValueError:
        # If the marker isn't found, return the original content.
        return markdown_content

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
        return None

def sync_instructions():
    """Main function to check for updates and sync documents as Markdown."""
    try:
        drive_service = get_authenticated_service('drive', 'v3')
    except Exception as e:
        print(f"Authentication failed for Google Drive. Ensure you have run 'gcloud auth application-default login'. Error: {e}")
        return

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
                    print(f"  -> Change detected! Downloading and cleaning Markdown...")
                    content = get_doc_as_markdown(drive_service, doc_id)
                    
                    if content is not None:
                        # Strip embedded image data before writing to file
                        cleaned_content = strip_base64_images(content)
                        
                        with open(local_filepath, 'w', encoding='utf-8') as out_file:
                            out_file.write(cleaned_content)
                            
                        doc_info['last_modified_time'] = current_mod_time
                        print(f"  -> Successfully updated '{local_filename}'.")
                        
                    # Trigger vector database embedding
                    if local_filename == "Homebrew_Compendium.md" or local_filename == "Operational_Protocols.md":
                        print(f"  -> Starting vector embedding for '{local_filename}'...")
                        run_embedding_sync(os.path.join(INSTRUCTIONS_DIR, local_filename))
                else:
                    print("  -> No changes. File is up to date.")
            
            except HttpError as err:
                print(f"An error occurred with doc ID {doc_id}: {err}")
                
        f.seek(0)
        json.dump(manifest_data, f, indent=2)
        f.truncate()
    
if __name__ == '__main__':
    sync_instructions()