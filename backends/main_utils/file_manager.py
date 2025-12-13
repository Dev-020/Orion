
import os
import io
import time
import base64
from . import config
from types import SimpleNamespace
from google.genai import types
import logging

logger = logging.getLogger(__name__)

# Define supported text extensions for injection

class UploadFile:
    """
    Centralized file ingestion class.
    Handles file type detection, text extraction, and backend-specific uploading.
    """
    def __init__(self, core_backend: str, client: object = None, file_processing_agent = None):
        """
        Args:
            core_backend: "api" (Google GenAI) or "ollama" (Local).
            client: The GenAI client instance (only needed if backend="api").
            file_processing_agent: Optional agent for pre-processing (VertexAI specific).
        """
        self.backend = core_backend
        self.client = client
        self.file_processing_agent = file_processing_agent

    def process_file(self, file_bytes: bytes, display_name: str, mime_type: str):
        """
        Ingests a file and returns a standardized object for the AI prompt.
        
        Returns:
            - Text Object (SimpleNamespace) for injected text.
            - API File Object (types.File) for GenAI uploads.
            - Local File Object (SimpleNamespace) for Ollama/Local usage.
            - None on failure.
        """
        logger.info(f"--- [FileManager] Processing '{display_name}' ({mime_type}) for backend '{self.backend}' ---")

        # 1. Text Injection Check
        if self._is_text_file(display_name, mime_type):
            return self._handle_text_injection(file_bytes, display_name, mime_type)

        # 2. Media Handling
        if self.backend == "api":
            return self._handle_api_upload(file_bytes, display_name, mime_type)
        elif self.backend == "ollama":
            return self._handle_local_ingest(file_bytes, display_name, mime_type)
        else:
             logger.error(f"ERROR: Unknown backend '{self.backend}'")
             return None

    def _is_text_file(self, filename: str, mime_type: str) -> bool:
        is_text_mime = mime_type.startswith('text/') or mime_type in ['application/json', 'application/xml', 'application/javascript']
        is_text_ext = filename.lower().endswith(config.TEXT_FILE_EXTENSIONS)
        return is_text_mime or is_text_ext

    def _handle_text_injection(self, file_bytes: bytes, display_name: str, mime_type: str):
        try:
            # Decode bytes to string
            text_content = file_bytes.decode('utf-8')
            logger.info(f"  - Detected Text File. Injecting content ({len(text_content)} chars).")
            
            return SimpleNamespace(
                uri="text://injected",
                display_name=display_name,
                mime_type=mime_type,
                size_bytes=len(file_bytes),
                text_content=text_content # The actual content to inject
            )
        except UnicodeDecodeError:
            logger.warning(f"  - Warning: Could not decode '{display_name}' as UTF-8. Treating as binary.")
            # Fallback to binary handling
            if self.backend == "api":
                return self._handle_api_upload(file_bytes, display_name, mime_type)
            else:
                return self._handle_local_ingest(file_bytes, display_name, mime_type)

    def _handle_api_upload(self, file_bytes: bytes, display_name: str, mime_type: str):
        # VertexAI Delegation (If agent is present, we are in Vertex mode)
        if self.file_processing_agent:
             try:
                 logger.info(f"  - [FileManager] Delegating '{display_name}' to FileProcessingAgent (VertexAI) for analysis...")
                 # The agent handles the upload internally (or we could upload here and pass handle, but likely agent needs raw bytes or handle)
                 # Checking `agents/file_processing_agent.py`: `upload_file` returns a File Handle.
                 # But we need ANALYSIS for Vertex. 
                 # Wait, implementation plan says: "call agent.upload_file (or run logic)".
                 # If we call `upload_file`, we get a File Handle. We can't attach that to Vertex prompt.
                 # We need to RUN the agent.
                 
                 # 1. Upload to API first (Agent needs a handle to analyze)
                 # Re-use the standard upload logic below?
                 # Actually, `FileProcessingAgent.run` expects a LIST of file handles.
                 pass # Fallthrough to upload first
             except Exception as e:
                 logger.error(f"  - [FileManager] Agent check failed: {e}. Falling back to standard upload.")

        # Standard API Upload
        try:
            logger.debug(f"  - [FileManager] Uploading to Google File API...")
            file_handle = self.client.files.upload(
                file=io.BytesIO(file_bytes),
                config=types.UploadFileConfig(
                    mime_type=mime_type,
                    display_name=display_name
                )
            )
            
            # Polling
            while file_handle.state.name == "PROCESSING":
                time.sleep(0.5)
                file_handle = self.client.files.get(name=file_handle.name)

            if file_handle.state.name == "FAILED":
                logger.error(f"  - [FileManager] Upload FAILED.")
                try: self.client.files.delete(name=file_handle.name)
                except: pass
                return None
            
            logger.info(f"  - [FileManager] Upload Active: {file_handle.uri}")
            
            # Post-Upload: VertexAI Analysis Step
            if self.file_processing_agent:
                try:
                    logger.info(f"  - [FileManager] Invoking FileProcessingAgent for analysis...")
                    # The agent.run command takes a LIST of handles
                    # We create a temporary context for the agent if needed, or just pass empty
                    analysis_text = self.file_processing_agent.run([file_handle])
                    
                    logger.info(f"  - [FileManager] Analysis complete ({len(analysis_text)} chars). Returning as Text Object.")
                    
                    # Return as Text Object (Analysis) but KEEP ORIGINAL MIME TYPE
                    return SimpleNamespace(
                        uri="text://analysis",
                        display_name=display_name,
                        mime_type=mime_type, # Preserve original type: e.g. "image/png"
                        size_bytes=len(file_bytes),
                        text_content=analysis_text,
                        is_analysis=True # Marker
                    )
                except Exception as e:
                    logger.error(f"  - [FileManager] Analysis failed: {e}. Returning raw file handle as fallback.")
                    return file_handle

            return file_handle

        except Exception as e:
            logger.error(f"  - [FileManager] API Upload Error: {e}")
            return None

    def _handle_local_ingest(self, file_bytes: bytes, display_name: str, mime_type: str):
        """
        Handles local ingestion for Ollama (or other local backends).
        """
        # A. Images -> Base64 for Vision Models
        if mime_type.startswith("image/"):
            logger.info(f"  - [FileManager] Processing Image for Local Vision Model...")
            b64_data = base64.b64encode(file_bytes).decode('utf-8')
            
            base64_obj = SimpleNamespace(
                uri="data://base64",
                display_name=display_name,
                mime_type=mime_type,
                size_bytes=len(file_bytes),
                base64_data=b64_data
            )

            # VLM Delegation (If agent is present, use it for analysis)
            if self.file_processing_agent:
                try:
                    logger.info(f"  - [FileManager] Delegating '{display_name}' to FileProcessingAgent (Local VLM) for analysis...")
                    # The agent expects a list of file handles. We pass our base64 object.
                    analysis_text = self.file_processing_agent.run([base64_obj])
                    
                    logger.debug(f"  - [FileManager] Analysis complete ({len(analysis_text)} chars). Returning as Text Object.")
                    
                    return SimpleNamespace(
                        uri="text://analysis",
                        display_name=display_name,
                        mime_type=mime_type, # Preserve original type
                        size_bytes=len(file_bytes),
                        text_content=analysis_text,
                        is_analysis=True
                    )
                except Exception as e:
                    logger.error(f"  - [FileManager] Analysis failed: {e}. Falling back to raw image.")
            
            return base64_obj
        
        # B. PDFs/Docs -> Save to temp for potential RAG/Tool usage
        # (Ollama can't natively "read" PDFs without a tool)
        logger.info(f"  - Staging Local File '{display_name}'...")
        # Use data/ directory for temp storage
        temp_dir = os.path.join(os.getcwd(), "data", "temp_uploads")
        os.makedirs(temp_dir, exist_ok=True)
        
        file_path = os.path.join(temp_dir, display_name)
        with open(file_path, "wb") as f:
            f.write(file_bytes)
            
        logger.info(f"  - Saved to: {file_path}")
        return SimpleNamespace(
            uri=f"file://{file_path}",
            display_name=display_name,
            mime_type=mime_type,
            size_bytes=len(file_bytes),
            local_path=file_path
        )
