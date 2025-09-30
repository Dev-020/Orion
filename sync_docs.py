# --- START OF FILE sync_docs.py (Unified Auth Version) ---
import os
import json
import google.auth
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# --- PATH CONFIGURATION ---
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
MANIFEST_FILE = os.path.join(SCRIPT_DIR, 'docs_manifest.json')
INSTRUCTIONS_DIR = os.path.join(SCRIPT_DIR, 'instructions')

def get_authenticated_service(service_name, version):
    """Gets a Google API service object with Application Default Credentials."""
    credentials, _ = google.auth.default()
    service = build(service_name, version, credentials=credentials, static_discovery=False)
    return service

def read_structural_elements(elements):
    """(Helper) Reads text from a list of structural elements."""
    text = ''
    if not elements: return ''
    for value in elements:
        if 'paragraph' in value:
            para_elements = value.get('paragraph').get('elements')
            for elem in para_elements:
                text += elem.get('textRun', {}).get('content', '')
        elif 'table' in value:
            table = value.get('table')
            for row in table.get('tableRows'):
                for cell in row.get('tableCells'):
                    text += read_structural_elements(cell.get('content'))
    return text

def get_doc_content(service, doc_id):
    """Downloads a Google Doc as plain text, handling the tab structure."""
    try:
        document = service.documents().get(documentId=doc_id, includeTabsContent=True).execute()
        all_text_parts = []
        tabs = document.get('tabs', [])
        for tab in tabs:
            documentTab = tab.get('documentTab')
            if documentTab:
                body = documentTab.get('body')
                if body:
                    content = body.get('content')
                    if content:
                        all_text_parts.append(read_structural_elements(content))
        return "".join(all_text_parts)
    except HttpError as err:
        print(f"An error occurred while getting doc content: {err}")
        return None

def sync_instructions():
    """Main function to check for updates and sync documents."""
    try:
        drive_service = get_authenticated_service('drive', 'v3')
        docs_service = get_authenticated_service('docs', 'v1')
    except Exception as e:
        print(f"Authentication failed for Google Drive/Docs. Ensure you have run 'gcloud auth application-default login'. Error: {e}")
        return

    if not os.path.exists(INSTRUCTIONS_DIR):
        os.makedirs(INSTRUCTIONS_DIR)

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
                    print(f"  -> Change detected! Downloading latest version...")
                    content = get_doc_content(docs_service, doc_id)
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