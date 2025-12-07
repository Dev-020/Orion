# --- START OF FILE functions.py (Unified Access Model) ---

from git import Repo, GitCommandError
# --- PUBLIC TOOL DEFINITION ---
__all__ = [
    "initialize_persona",
    "manual_sync_instructions",
    "rebuild_manifests",
    "browse_website",
    "list_project_files",
    "delegate_to_native_tools_agent",
    "read_file",
    "execute_sql_read",
    "execute_sql_write",
    "execute_sql_ddl",
    "execute_vdb_read",
    "execute_vdb_write",
    "execute_write",
    "create_git_commit_proposal"
]

import hashlib
import re
import os
import json
import mimetypes
import requests
from bs4 import BeautifulSoup
from google.genai import types
from googleapiclient.discovery import build
from datetime import date
import google.auth
from datetime import datetime, timezone
from filelock import FileLock
from typing import Optional, List, Union
from agents.file_processing_agent import FileProcessingAgent
from agents.native_tools_agent import NativeToolsAgent
import sqlite3
import chromadb
from chromadb.types import Metadata
from pathlib import Path
from system_utils import sync_docs, generate_manifests
from . import config

# --- CONSTANTS ---
DAILY_SEARCH_QUOTA = 10000
PROJECT_ROOT = config.PROJECT_ROOT # Already a Path object

# --- PERSONA INITIALIZATION ---
def get_db_paths(persona: str) -> dict:
    """Returns a dictionary of database paths based on the persona."""
    databases_dir = PROJECT_ROOT / 'databases'
    persona_dir = databases_dir / persona
    
    # Checks if the Persona Folder exist
    if not persona_dir.is_dir():
        print(f"  Error: '{persona}' directory not found at {persona_dir}.")
        return {}
    
    return {
        "db_file": str(persona_dir / 'orion_database.sqlite'),
        "chroma_db_path": str(persona_dir / "chroma_db_store"),
        "collection_name": "orion_semantic_memory"
    }

def initialize_persona(persona: str = "default"):
    """Initializes the database paths for the given persona."""
    paths = get_db_paths(persona)
    config.DB_FILE = paths["db_file"]
    config.CHROMA_DB_PATH = paths["chroma_db_path"]
    config.COLLECTION_NAME = paths["collection_name"]

# --- VECTOR DATABASE ACCESS MODEL ---

def _get_chroma_collection():
    """Helper function to get the ChromaDB collection."""
    try:
        chroma_client = chromadb.PersistentClient(path=config.CHROMA_DB_PATH)
        collection = chroma_client.get_or_create_collection(name=config.COLLECTION_NAME)
        return collection
    except Exception as e:
        print(f"Error connecting to ChromaDB: {e}")
        return None

def _sanitize_metadata(metadata: Metadata) -> Metadata:
    """Sanitizes a metadata dictionary for ChromaDB compatibility."""
    sanitized: Metadata = {}
    for key, value in metadata.items():
        if isinstance(value, (str, int, float, bool)):
            sanitized[key] = value
        elif value is not None:
            sanitized[key] = json.dumps(value)
    return sanitized

def execute_write(table: str, operation: str, user_id: str, data: Optional[dict] = None, where: Optional[dict] = None) -> str:
    """
    (HIGH-LEVEL ORCHESTRATOR) Automates a synchronized write to both SQLite and the Vector DB.
    It relies on the low-level tools for all execution and security checks.
    """
    print(f"--- Synchronized Write --- User: {user_id}, Table: {table}, Op: {operation}")

    # --- OBSOLETE: The vdb_context compression logic has been removed as we now store IDs, not raw data. ---

    # --- 1. Construct and Execute SQL Query (Primary Database) ---
    try:
        operation = operation.lower()
        if operation == 'insert' and data is not None:
            columns = ', '.join(data.keys())
            placeholders = ', '.join(['?'] * len(data))
            sql_query = f"INSERT INTO {table} ({columns}) VALUES ({placeholders})"
            sql_params = list(data.values())
        elif operation == 'update' and where is not None and data is not None:
            set_clause = ', '.join([f"{key} = ?" for key in data.keys()])
            where_clause = ' AND '.join([f"{key} = ?" for key in where.keys()])
            sql_query = f"UPDATE {table} SET {set_clause} WHERE {where_clause}"
            sql_params = list(data.values()) + list(where.values())
        elif operation == 'delete' and where is not None:
            where_clause = ' AND '.join([f"{key} = ?" for key in where.keys()])
            sql_query = f"DELETE FROM {table} WHERE {where_clause}"
            sql_params = list(where.values())
        else:
            return f"Error: Invalid operation '{operation}' or missing 'where' clause for update/delete."
    except Exception as e:
        return f"Error: Failed to construct SQL query: {e}"

    sql_result = execute_sql_write(query=sql_query, params=sql_params, user_id=user_id)

    if "Success" not in sql_result:
        return f"Primary database (SQLite) write failed. Aborting sync. Error: {sql_result}"

    # --- 2. Synchronize with Vector DB (Secondary Database) ---
    try:
        print("  - SQLite write successful. Proceeding with Vector DB synchronization...")
        
        pk_map = {
            'long_term_memory': 'event_id',
            'active_memory': 'topic',
            'knowledge_base': 'id',
            'user_profiles': 'user_id',
            'deep_memory': 'id'
        }
        pk_name = pk_map.get(table)

        # --- A. Handle DELETE ---
        if operation == 'delete':
            # For active_memory, we cannot reconstruct the hash from a delete operation based on topic.
            # This is a known limitation of this design. The vector will be orphaned.
            # A more complex solution would be to read before deleting, but we accept this limitation for now.
            if table == 'active_memory':
                 print("  - VDB sync: Skipping DELETE for 'active_memory' as its ID is hashed.")
            elif pk_name and where and pk_name in where:
                vdb_id_val = where[pk_name]
                vdb_id = f"{table}_{vdb_id_val}"
                execute_vdb_write(operation='delete', user_id=user_id, ids=[vdb_id])
                print(f"  - VDB sync: Initiated DELETE for ID {vdb_id}")
            else:
                print(f"  - VDB sync: Skipping DELETE for table '{table}' - no PK in 'where' or table not configured.")
        
        # --- B. Handle INSERT or UPDATE ---
        else:
            full_data_row = None
            if operation == 'insert':
                # The write was successful, so we can now fetch the most recently inserted row.
                # Ordering by the primary key DESC and taking the first result is the simplest, most direct way.
                read_query = f"SELECT * FROM {table} ORDER BY {pk_name} DESC LIMIT 1"
                read_result_json = execute_sql_read(query=read_query)
                #print(read_result_json)
                if "returned no results" not in read_result_json:
                    read_result = json.loads(read_result_json)
                    if read_result:
                        full_data_row = read_result[0]
            elif operation == 'update':
                if pk_name and where and pk_name in where:
                    pk_value = where[pk_name]
                    read_query = f"SELECT * FROM {table} WHERE {pk_name} = ?"
                    # The result from execute_sql_read is a JSON string
                    read_result_json = execute_sql_read(query=read_query, params=[str(pk_value)])
                    # We need to handle the case where it returns no results
                    if "returned no results" not in read_result_json:
                        read_result = json.loads(read_result_json)
                        if read_result:
                            full_data_row = read_result[0]
            
            if not full_data_row:
                print(f"  - VDB sync: Skipping {operation.upper()} - could not obtain full data row for vectorization.")
                return sql_result

            # --- C. Document Factory ---
            doc, meta, vdb_id = None, None, None
            
            if table in pk_map:
                # Default behavior
                pk_val = full_data_row.get(pk_map[table])
                vdb_id = f"{table}_{pk_val}"

                # --- Selective Metadata Population ---
                # Define which fields are essential for filtering and context, excluding redundant text fields.
                essential_metadata_keys = [
                    'source_table', 'source_id', 'session_id', 'user_id', 'user_name', # 'vdb_context' is no longer needed here for the vector itself
                    'timestamp', 'token', 'function_calls', 'vdb_context', 'attachments_metadata'
                ]
                meta = {
                    'source_table': table,
                    'source_id': str(pk_val)
                }
                # Populate metadata ONLY with essential keys found in the row.
                # This prevents bloating the vector metadata with redundant text like prompt_text and response_text.
                for key in essential_metadata_keys:
                    if key in full_data_row and key not in meta:
                        meta[key] = full_data_row[key]
                
                # Specific formatting rules override the default
                if table == 'long_term_memory':
                    content = f"{full_data_row.get('description', '')} {full_data_row.get('snippet', '')}".strip()
                    doc = f"Memory Title: {full_data_row.get('title', '')}. Category: {full_data_row.get('category', '')}. Date: {full_data_row.get('date', '')}. Contents: {content}"
                
                elif table == 'deep_memory':
                    # 1. Parse JSON fields from the row data into objects for processing.
                    # This ensures we have structured data for both metadata and doc creation.
                    # The metadata is already populated with the raw strings from the DB, now we parse them.
                    # NOTE: We no longer need to parse 'vdb_context' for the document itself.
                    function_calls_obj = None
                    for field in ['function_calls', 'attachments_metadata']:
                        if field in meta and isinstance(meta[field], str):
                            try:
                                parsed_obj = json.loads(meta[field] or "[]")
                                # We don't need to re-assign to meta here, as _sanitize_metadata will handle it later.
                                if field == 'function_calls': function_calls_obj = parsed_obj
                            except json.JSONDecodeError:
                                pass
                    
                    # 2. Create a clean, readable summary of tool calls for the vector document.
                    tool_summary = ""
                    if function_calls_obj:
                        summaries = []
                        # Ensure function_calls_obj is a list before iterating
                        if isinstance(function_calls_obj, list):
                            for content_item in function_calls_obj:
                                # Ensure content_item is a dict and has 'parts'
                                if isinstance(content_item, dict) and isinstance(content_item.get('parts'), list):
                                    for part in content_item['parts']:
                                        # Ensure part is a dict before using .get()
                                        if isinstance(part, dict):
                                            if part.get('function_call'):
                                                summaries.append(f"Called function '{part['function_call'].get('name')}'")
                                            elif part.get('function_response'):
                                                summaries.append(f"Received response for '{part['function_response'].get('name')}'")
                        if summaries:
                            tool_summary = f" Actions Taken: [{'; '.join(summaries)}]."

                    # 4. Construct the final rich document for semantic search.
                    ts_iso = datetime.fromtimestamp(full_data_row.get('timestamp', 0), tz=timezone.utc).isoformat()
                    base_doc = f"Conversation from {ts_iso} with user {full_data_row.get('user_name', 'Unknown')}. User asked: '{full_data_row.get('prompt_text', '')}'. Orion responded: '{full_data_row.get('response_text', '')}'"
                    doc = base_doc + tool_summary
                
                elif table == 'active_memory':
                    unique_content = f"{full_data_row.get('topic', '')}{full_data_row.get('prompt', '')}"
                    hash_id = hashlib.sha1(unique_content.encode('utf-8')).hexdigest()
                    vdb_id = f"active_memory_{hash_id}"
                    meta['source_id'] = vdb_id # Override the source_id with the correct hash
                    doc = f"D&D Ruling for '{full_data_row.get('topic', '')}'. Question: {full_data_row.get('prompt', '')}. Ruling: {full_data_row.get('ruling', '')}"

                # Fallback document if no specific rule exists
                elif not doc:
                    # A simple JSON dump is a reasonable fallback for tables without a specific doc format.
                    doc = json.dumps(full_data_row)

            # --- D. Execute VDB Write ---
            if doc and meta and vdb_id:
                execute_vdb_write(operation='add', user_id=user_id, ids=[vdb_id], documents=[doc], metadatas=[meta])
                print(f"  - VDB sync: Completed {operation.upper()} for ID {vdb_id}")
            else:
                print(f"  - VDB sync: Skipping {operation.upper()} for table '{table}' - no document creation rule found.")

    except Exception as e:
        print(f"Warning: SQLite write was successful, but Vector DB sync failed: {e}")

    return sql_result

def execute_vdb_read(query_texts: list[str], n_results: int = 7, where: Optional[dict] = None, ids: Optional[list[str]] = None) -> str:
    """
    Queries the vector database for similar documents. Can be filtered by metadata (`where`) or a specific list of `ids`.
    """
    print(f"--- Vector DB Query --- Queries: {query_texts} | N: {n_results} | Where: {where} | IDs: {ids}")
    collection = _get_chroma_collection()
    if not collection:
        return "Error: Could not connect to the vector database."

    try:
        # Pass the `ids` parameter directly to the ChromaDB query method.
        results = collection.query(
            query_texts=query_texts,
            n_results=n_results,
            where=where,
            ids=ids
        )
        return json.dumps(results, indent=2)
    except Exception as e:
        return f"Error querying vector database: {e}"

def execute_vdb_write(operation: str, user_id: str, documents: Optional[list[str]] = None, metadatas: Optional[List[Metadata]] = None, ids: Optional[list[str]] = None, where: Optional[dict] = None) -> str:
    """
    Manages the vector database using a tiered security model.
    - 'add': Low-level access, anyone can use.
    - 'update': Medium-level, restricted to the data's owner or the Primary Operator.
    - 'delete': High-level, restricted to the Primary Operator only.
    """
    print(f"--- Vector DB Write Request from User: {user_id} ---")
    print(f"  - Operation: {operation.upper()}")

    collection = _get_chroma_collection()
    if not collection:
        return "Error: Could not connect to the vector database."

    operation = operation.lower()
    owner_id = os.getenv("DISCORD_OWNER_ID")
    is_authorized = False

    # --- Authorization Logic ---
    if operation == 'add':
        print("  - Authorized for low-level ADD.")
        is_authorized = True

    elif operation == 'delete':
        if owner_id and user_id == owner_id:
            print("  - Authorized for high-level DELETE as Primary Operator.")
            is_authorized = True
        else:
            print(f"  - SECURITY ALERT: Denied unauthorized DELETE attempt by user {user_id}.")
            return "Error: Authorization failed. This operation is restricted to the Primary Operator."

    elif operation == 'update':
        if owner_id and user_id == owner_id:
            print("  - Authorized for high-level UPDATE as Primary Operator.")
            is_authorized = True
        else:
            # For non-owners, we must verify they own all documents they are trying to update.
            if not ids:
                return "Error: 'update' operation requires 'ids' for non-owner users to verify ownership."
            try:
                existing_docs = collection.get(ids=ids)
                # --- THIS IS THE CORRECTED LOGIC ---
                # Safely get the 'metadatas' list using .get()
                metadatas_list = existing_docs.get('metadatas')

                # Now, check if the list is missing or empty
                if not metadatas_list:
                    return "Error: Could not find one or more documents to update."

                # If we have the list, it's now safe to iterate
                for metadata in metadatas_list:
                    if metadata.get('user_id') != user_id:
                        print(f"  - SECURITY ALERT: Denied unauthorized UPDATE by {user_id} on a document owned by {metadata.get('user_id')}.")
                        return "Error: Authorization failed. You can only update documents that you own."
                
                print("  - Authorized for medium-level UPDATE as document owner.")
                is_authorized = True
                # --- END OF CORRECTED LOGIC ---
            except Exception as e:
                return f"Error during ownership verification: {e}"

    if not is_authorized:
        return f"Error: Invalid operation '{operation}' or initial authorization failed."

    # --- Execution Logic ---
    try:
        if operation in ['add', 'update']:
            if not (documents and metadatas and ids):
                return f"Error: '{operation}' operation requires documents, metadatas, and ids."
            
            # Sanitize metadata before writing
            sanitized_metadatas = [_sanitize_metadata(m) for m in metadatas]

            collection.upsert(documents=documents, metadatas=sanitized_metadatas, ids=ids)
            return f"Successfully upserted {len(documents)} documents."

        elif operation == 'delete':
            if not ids and not where:
                return "Error: 'delete' operation requires either ids or a where clause."
            collection.delete(ids=ids, where=where)
            return "Successfully initiated delete operation."
        else:
            return f"Error: Invalid operation '{operation}'. Must be one of 'add', 'update', 'delete'."
    except Exception as e:
        return f"Error managing vector database: {e}"

# --- UNIFIED DATABASE ACCESS MODEL ---

def execute_sql_read(query: str, params: List[str] = []) -> str:
    """
    (Pillar 1) Executes a read-only SQL query (SELECT) against the database.
    Returns results as a JSON string.
    """
    print(f"--- DB READ --- Query: {query} | Params: {params}")
    
    if not query.strip().upper().startswith("SELECT"):  
        return "Error: This tool is for read-only (SELECT) queries."

    try:
        with sqlite3.connect(config.DB_FILE) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(query, tuple(params))
            rows = [dict(row) for row in cursor.fetchall()] # Decompression logic is no longer needed here.

            results = rows
            return json.dumps(results, indent=2) if results else "Query executed successfully, but returned no results."
    except sqlite3.Error as e:
        return f"Database Error: {e}"


def execute_sql_write(query: str, params: list, user_id: str) -> str:
    """
    Executes a write query (INSERT, UPDATE, DELETE) on the database using a
    tiered security model.
    """
    print(f"--- DB Write Request from User: {user_id} ---")
    print(f"  - Query: {query}")
    #print(f"  - Params: {params}")
    
    normalized_query = query.strip().upper()
    owner_id = os.getenv("DISCORD_OWNER_ID")

    if normalized_query.startswith('UPDATE') or normalized_query.startswith('DELETE'):
        print(f"{owner_id} : {user_id}")
        is_authorized = (owner_id and user_id == owner_id)

        if normalized_query.startswith('UPDATE "USER_PROFILES"'):
            targeted_user_id = str(params[-1])
            if user_id == targeted_user_id:
                print("  - Authorized as self-update for user_profiles.")
                is_authorized = True

        if not is_authorized:
            error_msg = "Error: Authorization failed. This operation is restricted to the Primary Operator or for updating your own profile."
            print(f"  - SECURITY ALERT: Denied unauthorized write attempt by user {user_id}.")
            return error_msg
        
        print("  - Authorized for high-level write.")

    elif normalized_query.startswith('INSERT'):
        print("  - Authorized for low-level INSERT.")
        pass

    else:
        return f"Error: Invalid or disallowed SQL command. Only INSERT, UPDATE, DELETE are supported."

    try:
        with sqlite3.connect(config.DB_FILE) as conn:
            cursor = conn.cursor()
            cursor.execute(query, tuple(params))
            conn.commit()
            rows_affected = cursor.rowcount
            print(f"  - Write successful. {rows_affected} row(s) affected.")
            return f"Success. The query executed and affected {rows_affected} row(s)."

    except sqlite3.Error as e:
        print(f"ERROR: A database error occurred in execute_sql_write: {e}")
        return f"An unexpected database error occurred: {e}"


def execute_sql_ddl(query: str, user_id: str) -> str:
    """
    (Pillar 2) Executes a Data Definition Language (DDL) query against the database.
    This is a high-level, protected tool restricted to the Primary Operator.
    """
    print(f"--- DB DDL Request from User: {user_id} ---")
    print(f"  - Query: {query}")

    owner_id = os.getenv("DISCORD_OWNER_ID")
    if not (owner_id and user_id == owner_id):
        error_msg = "Error: Authorization failed. This operation is restricted to the Primary Operator."
        print(f"  - SECURITY ALERT: Denied unauthorized DDL attempt by user {user_id}.")
        return error_msg
    
    print("  - Authorized for high-level DDL operation.")

    normalized_query = query.strip().upper()
    if not (
        normalized_query.startswith("CREATE TABLE")
        or normalized_query.startswith("ALTER TABLE")
        or normalized_query.startswith("DROP TABLE")
        or normalized_query.startswith("BEGIN TRANSACTION")
    ):
        return "Error: Invalid or disallowed SQL command. Only CREATE TABLE, ALTER TABLE, and DROP TABLE are supported."

    try:
        with sqlite3.connect(config.DB_FILE) as conn:
            cursor = conn.cursor()
            cursor.executescript(query)
            conn.commit()
            print("  - DDL query executed successfully.")
            return "Success. The DDL query was executed and the changes have been committed."

    except sqlite3.Error as e:
        print(f"ERROR: A database error occurred in execute_sql_ddl: {e}")
        return f"An unexpected database error occurred: {e}"

# --- HIGH-LEVEL SELF-REFERENTIAL TOOLS ---

def create_git_commit_proposal(file_path: str, new_content: str, commit_message: str, user_id: str) -> str:
    """
    (Pillar 3 & 4 Unified) Creates a new Git branch, writes content to a file,
    commits the change, and pushes the branch to the remote 'origin'.
    """
    print(f"--- Git Commit Proposal received for '{file_path}' ---")

    owner_id = os.getenv("DISCORD_OWNER_ID")
    if str(user_id) != owner_id:
        return "Error: Authorization failed. This tool is restricted to the Primary Operator."

    repo = None
    original_branch = None
    branch_name = None
    try:
        # Initialize repo and get the actual, case-correct path for the repo's working directory
        repo = Repo(str(PROJECT_ROOT), search_parent_directories=True)
        original_branch = repo.active_branch

        # --- START: Improvement ---
        # Ensure the repository is not in a detached HEAD state and the working tree is clean.
        if repo.is_dirty(untracked_files=True):
            return "Error: The repository has uncommitted changes or untracked files. Please resolve this manually before proceeding."
        
        # Fetch latest changes from origin and ensure the local main branch is up-to-date.
        origin = repo.remote(name='origin')
        print("  - Fetching latest from origin...")
        origin.fetch()
        repo.heads.master.checkout(force=True) # Use master or main as appropriate
        repo.git.reset('--hard', 'origin/master')
        # --- END: Improvement ---

        repo_root = Path(repo.working_dir)

        # Construct the target path using the case-correct repo root
        target_path = (repo_root / file_path).resolve()

        # Security check: Ensure the resolved path is within the repository
        if not target_path.is_relative_to(repo_root):
            return f"Error: Access denied. Path '{file_path}' is outside the project directory."

        timestamp = datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')
        sanitized_message = re.sub(r'[^a-zA-Z0-9\-]', '-', commit_message.splitlines()[0]).strip('-')
        # --- FIX: Restore branch_name assignment ---
        branch_name = f"orion-changes/{timestamp}-{sanitized_message[:50]}"

        print(f"  - Creating new branch: {branch_name}")
        new_branch = repo.create_head(branch_name)
        new_branch.checkout()

        print(f"  - Writing {len(new_content)} bytes to {file_path}")
        target_path.parent.mkdir(parents=True, exist_ok=True)
        with open(target_path, 'w', encoding='utf-8') as f:
            f.write(new_content)

        print("  - Staging and committing changes...")
        repo.index.add([str(target_path)])
        repo.index.commit(commit_message)

        print(f"  - Pushing branch '{branch_name}' to origin...")
        origin = repo.remote(name='origin')
        origin.push(branch_name)

        return (f"Success. A new branch '{branch_name}' was created and pushed to the remote repository "
                f"with your changes for `{file_path}`. Please review and merge the pull request on GitHub.")

    except GitCommandError as e:
        print(f"ERROR: A Git command failed: {e}")
        # --- START: Improvement ---
        if branch_name and "push" in str(e).lower():
            return (f"Error: The commit was created locally in branch '{branch_name}', but failed to push to GitHub. "
                    f"Please check your connection or repository permissions and push it manually. Details: {e}")
        return f"A Git command failed, but your changes might be saved locally in branch '{branch_name}'. Please review. Details: {e}"
        # --- END: Improvement ---
    except Exception as e:
        print(f"ERROR: An unexpected error occurred in create_git_commit_proposal: {e}")
        return f"An unexpected error occurred. Your changes might be saved locally in branch '{branch_name}'. Please review. Details: {e}"
    finally:
        # --- START: Improvement ---
        # Ensure we always return to the original branch, even on failure.
        if repo and original_branch:
            print(f"  - Returning to original branch: {original_branch.name}")
            original_branch.checkout()
        # --- END: Improvement ---

# --- RETAINED SPECIALIZED & EXTERNAL TOOLS ---

def manual_sync_instructions(user_id: str) -> str:
    """
    Triggers a manual synchronization of the AI's core instruction files.
    SECURITY: This is a restricted tool.
    """
    print("--- Manual Instruction Sync requested... ---")
    primary_operator_id = os.getenv("DISCORD_OWNER_ID")
    if str(user_id) != primary_operator_id:
        print(f"--- SECURITY ALERT: Unauthorized attempt to use manual_sync_instructions by user_id '{user_id}' ---")
        return "Error: Unauthorized. This function is restricted to the Primary Operator only."

    try:
        print("--- Operator authorized. Proceeding with manual sync... ---")
        sync_docs.sync_instructions()
        return "Core instruction files have been successfully synchronized from the source."
    except Exception as e:
        print(f"ERROR during manual sync: {e}")
        return f"An unexpected error occurred during the manual sync process: {e}"

def rebuild_manifests(manifest_names: list[str]) -> str:
    """
    Rebuilds specified manifest JSON files using the central config.
    """
    print(f"--- ACTION: Rebuilding manifests: {manifest_names} ---")
    # Use the centrally managed config for paths
    db_path = Path(config.DB_FILE)
    output_path = Path(config.OUTPUT_DIR)
    
    db_required_map = {
        "db_schema": generate_manifests.generate_db_schema_json,
        "user_profile_manifest": generate_manifests.generate_user_profile_manifest,
        "long_term_memory_manifest": generate_manifests.generate_long_term_memory_manifest,
        "active_memory_manifest": generate_manifests.generate_active_memory_manifest,
        "pending_logs": generate_manifests.generate_pending_logs_json
    }
    db_not_required_map = {
        "tool_schema": generate_manifests.generate_tool_schema_json
    }
    
    rebuilt_successfully, invalid_names, db_manifests_to_run = [], [], []

    for name in manifest_names:
        name = name.lower().strip()
        if name in db_not_required_map:
            try:
                # Pass the output path to the generator function
                db_not_required_map[name](output_path)
                rebuilt_successfully.append(name)
            except Exception as e:
                print(f"Error rebuilding manifest '{name}': {e}")
        elif name in db_required_map:
            db_manifests_to_run.append(name)
        else:
            invalid_names.append(name)

    if db_manifests_to_run:
        # Pass the db path to the connection function
        conn = generate_manifests.get_db_connection(db_path)
        if not conn:
            return "Error: Could not connect to the database to rebuild manifests."
        try:
            for name in db_manifests_to_run:
                try:
                    # Pass both connection and output path to the generator
                    db_required_map[name](conn, output_path)
                    rebuilt_successfully.append(name)
                except Exception as e:
                    print(f"Error rebuilding manifest '{name}': {e}")
        finally:
            conn.close()
            
    summary = f"Rebuild complete. Successfully rebuilt: {sorted(rebuilt_successfully) or 'None'}."
    if invalid_names:
        summary += f" Invalid names provided: {sorted(invalid_names)}."
    return json.dumps({"status": bool(rebuilt_successfully), "summary": summary})

def browse_website(url: str) -> str:
    """Reads the text content of a single webpage."""
    print(f"--- Browsing website: {url} ---")
    try:
        headers = {'User-Agent': 'Mozilla/5.0'}
        response = requests.get(url, headers=headers, timeout=10)
        soup = BeautifulSoup(response.text, 'html.parser')
        content = "\n".join([p.get_text() for p in soup.find_all('p')])
        if not content: return f"Source: Live Web Browse ({url})\n---\nCould not extract text."
        return f"Source: Live Web Browse ({url})\n---\n{content}"
    except Exception as e:
        return f"Source: Live Web Browse\n---\nAn error occurred: {e}"

def list_project_files(subdirectory: str = ".") -> str:
    """
    Lists all files and directories within the project.
    """
    print(f"--- Listing Project Files on directory {subdirectory} ---")
    try:
        start_path = (PROJECT_ROOT / subdirectory).resolve()
        if not start_path.is_relative_to(PROJECT_ROOT):
            return "Error: Access denied."
        if not start_path.exists():
            return f"Error: Directory '{subdirectory}' not found."
        tree = []
        for root, dirs, files in os.walk(start_path):
            dirs[:] = [d for d in dirs if d not in ['__pycache__', '.venv', '.git', '.vscode']]
            level = root.replace(str(start_path), '').count(os.sep)
            indent = ' ' * 4 * level
            tree.append(f"{indent}{Path(root).name}/")
            sub_indent = ' ' * 4 * (level + 1)
            for f in files:
                tree.append(f"{sub_indent}{f}")
        return "\n".join(tree)
    except Exception as e:
        return f"Error listing files: {e}"

def delegate_to_native_tools_agent(task: str) -> str:
    """
    (HIGH-LEVEL ORCHESTRATOR) Delegates a complex task that requires native tool use (like Google Search or Code Execution) to a specialized agent.
    This tool should be used when a user's query cannot be answered directly and requires external information or computation.
    The 'task' parameter should be a detailed description of what the agent needs to accomplish.
    """
    print(f"--- Delegating task to Native Tools Agent: {task} ---")

    core = config.ORION_CORE_INSTANCE
    if not core:
        return "Error: Orion Core instance not available for agent delegation."

    # 1. Instantiate the agent. The agent's __init__ method is responsible for its own setup.
    agent = NativeToolsAgent(orion_core=core)

    # 2. Run the agent with the specified task.
    agent_response = agent.run(task=task)

    return agent_response

def read_file(file_path: str, start_line: Optional[int] = None, end_line: Optional[int] = None) -> Union[str, list]:
    """
    Reads a file from the project directory. For text files, it returns the content as a string,
    optionally within a specified line range. For binary files (images, PDFs, audio, etc.)
    or very large text files, it uploads the file and returns a file object for the LLM to process.
    """
    print(f"--- Reading File located on: {file_path} ---")
    try:
        target_path = (PROJECT_ROOT / file_path).resolve()

        if not target_path.is_relative_to(PROJECT_ROOT):
            return "Error: Access denied. File is outside the project directory."
        if not target_path.is_file():
            return f"Error: File not found at '{file_path}'."

        # --- 1. Identify file type ---
        mime_type, _ = mimetypes.guess_type(target_path)
        is_text = False
        if mime_type:
            # Treat common script/data formats as text, in addition to 'text/*'
            if mime_type.startswith('text/') or mime_type in ['application/json', 'application/javascript', 'application/xml']:
                is_text = True
        
        # --- 2. Handle Large or Non-Text Files via Upload ---
        file_size = target_path.stat().st_size
        # Use upload for non-text files OR for text files larger than ~200k tokens (800KB)
        if not is_text or file_size > 800_000:
            print(f"  - File is non-text ({mime_type}) or large ({file_size / 1_000_000:.2f} MB). Uploading to File API...")
            if not config.ORION_CORE_INSTANCE:
                return "Error: Orion Core instance not available for file upload."
            
            try:
                with open(target_path, 'rb') as f:
                    file_bytes = f.read()
                
                display_name = target_path.name
                # Use detected mime_type or a default if none was found
                upload_mime_type = mime_type if mime_type else 'application/octet-stream'

                # Call the upload_file method from the OrionCore instance
                file_handle = config.ORION_CORE_INSTANCE.upload_file(file_bytes, display_name, upload_mime_type)

                # --- AGENTIC WORKFLOW INITIATION ---
                if file_handle:
                    print("--- Delegating to File Processing Agent ---")
                    core = config.ORION_CORE_INSTANCE
                    if not core:
                        return "Error: Orion Core instance not available for agent delegation."

                    # 1. Instantiate the agent. The agent's __init__ method is now responsible
                    # for its own setup by taking the core instance.
                    agent = FileProcessingAgent(orion_core=core)
                    
                    # 2. Run the agent. Its job is to focus solely on the file and the user's immediate request.
                    # The main model will integrate the agent's response into the broader conversation. 
                    return agent.run(file_handles=[file_handle])
                else:
                    return f"Error: File upload failed for '{file_path}'."
            except Exception as upload_e:
                return f"Error during file upload process: {upload_e}"

        # --- 3. Handle Text Files Directly ---
        # This 'else' block handles the case where the file is a text file and is NOT large.
        # This makes the control flow exhaustive and guarantees a return value.
        else:
            try:
                with open(target_path, 'r', encoding='utf-8') as f:
                    if start_line is not None and end_line is not None:
                        if start_line <= 0 or end_line < start_line:
                            return "Error: Invalid line range. 'start_line' must be > 0 and 'end_line' must be >= 'start_line'."
                        lines = f.readlines()
                        total_lines = len(lines)
                        start_idx = start_line - 1
                        end_idx = min(end_line, total_lines)

                        if start_idx >= total_lines:
                             return f"Error: 'start_line' ({start_line}) is beyond the end of the file ({total_lines} lines)."

                        content = "".join(lines[start_idx:end_idx])
                        return f"[System Note: The following are the contents of lines {start_line}-{end_idx} from the text file '{file_path}']\n---\n{content}"
                    else:
                        content = f.read()
                        return f"[System Note: The following are the contents of the text file '{file_path}']\n---\n{content}"
            except UnicodeDecodeError:
                return f"Error: Could not decode the file '{file_path}' with UTF-8. It may be a binary file misidentified as text."
        
    except Exception as e:
        return f"An unexpected error occurred while reading file: {e}"
