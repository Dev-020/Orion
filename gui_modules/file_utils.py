import os
import mimetypes
from pathlib import Path
from typing import List, Tuple, Callable, Any

def guess_mime_type(file_path: str) -> str:
    mime_type, _ = mimetypes.guess_type(file_path)
    if mime_type is None:
        mime_type = "application/octet-stream"
    return mime_type

def upload_files_process(
    core: Any, 
    file_paths: Tuple[str], 
    on_success_callback: Callable[[List[Any]], None],
    on_error_callback: Callable[[str], None]
):
    """
    Process to be run in a thread. Uploads files to the core.
    """
    new_handles = []
    display_name = None
    
    for file_path in file_paths:
        try:
            display_name = Path(file_path).name
            mime_type = guess_mime_type(file_path)
            
            with open(file_path, "rb") as f:
                file_bytes = f.read()
                
            file_handle = core.upload_file(
                file_bytes=file_bytes,
                display_name=display_name,
                mime_type=mime_type
            )
            
            if file_handle:
                new_handles.append(file_handle)
                
        except Exception as e:
            error_msg = f"Failed to upload {display_name}: {e}"
            print(f"ERROR: {error_msg}")
            if on_error_callback:
                on_error_callback(error_msg)
                
    if on_success_callback:
        on_success_callback(new_handles)
