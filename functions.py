# --- START OF FILE functions.py (Unified Access Model) ---

from git import Repo, GitCommandError
# --- PUBLIC TOOL DEFINITION ---
__all__ = [
    "initialize_persona",
    "search_knowledge_base",
    "roll_dice",
    "manual_sync_instructions",
    "rebuild_manifests",
    "update_character_from_web",
    "search_dnd_rules",
    "browse_website",
    "lookup_character_data",
    "list_project_files",
    "read_file",
    "execute_sql_read",
    "execute_sql_write",
    "execute_sql_ddl",
    "execute_vdb_read",
    "execute_vdb_write",
    "execute_write",
    "manage_character_resource",
    "manage_character_status",
    "create_git_commit_proposal"
]
# --- END OF PUBLIC TOOL DEFINITION ---

import hashlib
import zlib
import random
import re
import os
import json
import requests
from bs4 import BeautifulSoup
from googleapiclient.discovery import build
from datetime import date
import google.auth
from datetime import datetime, timezone
from filelock import FileLock
from typing import Optional, List, Any, Union
import sqlite3
import chromadb
from chromadb.types import Metadata
from pathlib import Path
from system_utils import sync_docs, generate_manifests

# --- CONSTANTS ---
DAILY_SEARCH_QUOTA = 10000
PROJECT_ROOT = Path(__file__).parent.resolve()

# --- DATABASE CONFIGURATION ---
DB_FILE = ""
CHROMA_DB_PATH = ""
COLLECTION_NAME = ""

def get_db_paths(persona: str) -> dict:
    """Returns a dictionary of database paths based on the persona."""
    db_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'databases')
    persona_path = os.path.join(db_path, persona)
    
    # Checks if the Persona Folder exist
    if not os.path.isdir(persona_path):
        print(f"  Error: '{persona}' directory not found at {persona_path}.")
        return {}
    
    return {
        "db_file": os.path.join(persona_path, 'orion_database.sqlite'),
        "chroma_db_path": os.path.join(persona_path, "chroma_db_store"),
        "collection_name": "orion_semantic_memory"
    }

def initialize_persona(persona: str):
    """Initializes the database paths for the given persona."""
    global DB_FILE, CHROMA_DB_PATH, COLLECTION_NAME
    paths = get_db_paths(persona)
    DB_FILE = paths["db_file"]
    CHROMA_DB_PATH = paths["chroma_db_path"]
    COLLECTION_NAME = paths["collection_name"]

# --- VECTOR DATABASE ACCESS MODEL ---

def _get_chroma_collection():
    """Helper function to get the ChromaDB collection."""
    try:
        chroma_client = chromadb.PersistentClient(path=CHROMA_DB_PATH)
        collection = chroma_client.get_or_create_collection(name=COLLECTION_NAME)
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

    # --- Data Compression for vdb_context ---
    # If we are writing to deep_memory and vdb_context exists, compress it.
    if data and table == 'deep_memory' and 'vdb_context' in data and isinstance(data['vdb_context'], str):
        original_len = len(data['vdb_context'])
        # Only compress if the data is large enough to be at risk of truncation.
        if original_len > 90000:
            try:
                # Compress the string into bytes.
                compressed_data = zlib.compress(data['vdb_context'].encode('utf-8'))
                compressed_len = len(compressed_data)
                print(f"  - Compressing 'vdb_context' from {original_len} chars to {compressed_len} bytes for storage efficiency.") # noqa
                data['vdb_context'] = compressed_data

            except Exception as e:
                print(f"  - WARNING: Failed to compress vdb_context. Storing as raw text. Error: {e}")


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
                    'source_table', 'source_id', 'session_id', 'user_id', 'user_name',
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
                    function_calls_obj = None
                    for field in ['function_calls', 'vdb_context', 'attachments_metadata']:
                        if field in meta and isinstance(meta[field], str):
                            try:
                                parsed_obj = json.loads(meta[field] or "[]")
                                # We don't need to re-assign to meta here, as _sanitize_metadata will handle it later.
                                if field == 'function_calls': function_calls_obj = parsed_obj
                            except json.JSONDecodeError:
                                print(f"  - VDB sync: Could not parse '{field}' as JSON, storing as raw string.")
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

                    # 3. Create a clean, readable summary of the VDB context used.

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
        with sqlite3.connect(DB_FILE) as conn:
            conn.row_factory = sqlite3.Row
            cursor = conn.cursor()
            cursor.execute(query, tuple(params))
            rows = [dict(row) for row in cursor.fetchall()]

            # --- Data Decompression for vdb_context ---
            # After fetching, check if any row contains a 'vdb_context' field that is bytes.
            for row in rows:
                if 'vdb_context' in row and isinstance(row['vdb_context'], bytes):
                    try:
                        # Attempt to decompress the bytes back into a string.
                        decompressed_str = zlib.decompress(row['vdb_context']).decode('utf-8')
                        original_len = len(row['vdb_context'])
                        new_len = len(decompressed_str)
                        print(f"  - Decompressing 'vdb_context' from {original_len} bytes to {new_len} chars.")
                        row['vdb_context'] = decompressed_str
                    except zlib.error:
                        # This might happen if the data was not compressed (e.g., old records).
                        # We'll try to decode it as a plain string.
                        print("  - Decompression failed, attempting to decode as plain text.")
                        row['vdb_context'] = row['vdb_context'].decode('utf-8', errors='ignore')

            results = rows
            return json.dumps(results, indent=2) if results else "Query executed successfully, but returned no results."
    except sqlite3.Error as e:
        return f"Database Error: {e}"


def execute_sql_write(query: str, params: List[Union[str, int, float, None]], user_id: str) -> str:
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
        with sqlite3.connect(DB_FILE) as conn:
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
        with sqlite3.connect(DB_FILE) as conn:
            cursor = conn.cursor()
            cursor.executescript(query)
            conn.commit()
            print("  - DDL query executed successfully.")
            return "Success. The DDL query was executed and the changes have been committed."

    except sqlite3.Error as e:
        print(f"ERROR: A database error occurred in execute_sql_ddl: {e}")
        return f"An unexpected database error occurred: {e}"

def manage_character_resource(user_id: str, operation: str, resource_name: Optional[str] = None, value: Optional[int] = None, max_value: Optional[int] = None) -> str:
    """
    Manages a character's resource. Operations: 'set', 'add', 'subtract', 'create', 'view'.
    'create' is used to add a new resource, requires a 'value', and can optionally take a 'max_value'.
    'set' overwrites the current value and can optionally update the max_value.
    'add'/'subtract' modifies the current_value (using 'value') and/or the max_value (using 'max_value').
    'view' returns the current and max value of a specific resource, or all resources if no name is provided.
    """
    print(f"--- RESOURCE MGMT --- User: {user_id}, Resource: {resource_name or 'ALL'}, Op: {operation}, Val: {value}, Max: {max_value}")

    # --- Input Validation ---
    valid_ops = ['set', 'add', 'subtract', 'create', 'view']
    if operation.lower() not in valid_ops:
        return f"Error: Invalid operation '{operation}'. Must be one of {valid_ops}."

    timestamp = datetime.now(timezone.utc).isoformat()

    try:
        with sqlite3.connect(DB_FILE) as conn:
            conn.row_factory = sqlite3.Row  # Set the row factory on the connection
            cursor = conn.cursor()

            # --- Fetch current state ---
            row = None
            if resource_name:
                cursor.execute("SELECT current_value, max_value FROM character_resources WHERE user_id = ? AND resource_name = ?", (user_id, resource_name)) # noqa
                row = cursor.fetchone()

            # --- Handle 'view' operation ---
            if operation == 'view':
                if resource_name:
                    cursor.execute("SELECT resource_name, current_value, max_value FROM character_resources WHERE user_id = ? AND resource_name = ?", (user_id, resource_name)) # noqa
                else:
                    cursor.execute("SELECT resource_name, current_value, max_value FROM character_resources WHERE user_id = ?", (user_id,))
                rows = cursor.fetchall()
                results = [dict(row) for row in rows]
                return json.dumps(results, indent=2) if results else "Info: You have no active resources."

            # --- Handle 'create' operation ---
            if operation == 'create' and value is not None and resource_name:
                if row:
                    return f"Error: Resource '{resource_name}' already exists for user {user_id}. Use 'set' or 'add' to modify."
                query = "INSERT INTO character_resources (user_id, resource_name, current_value, max_value, last_updated) VALUES (?, ?, ?, ?, ?)" # noqa
                params = (user_id, resource_name, value, max_value, timestamp)
                cursor.execute(query, params)
                conn.commit()
                return f"Success: Created resource '{resource_name}' for user {user_id} with value {value}."

            # --- Pre-modification checks ---
            if not row and resource_name:
                return f"Error: Resource '{resource_name}' not found for user {user_id}. Use 'create' operation first."

            current_val, current_max = (row[0], row[1]) if row else (None, None)
            set_clauses, params = [], []

            # --- Handle 'set', 'add', 'subtract' operations ---
            if operation == 'set':
                if value is not None:
                    set_clauses.append("current_value = ?")
                    params.append(value)
                if max_value is not None:
                    set_clauses.append("max_value = ?")
                    params.append(max_value)

            elif operation in ['add', 'subtract']:
                op_multiplier = 1 if operation == 'add' else -1
                if value is not None:
                    if current_val is None: return f"Error: Cannot modify current_value for '{resource_name}' as it is not set."
                    set_clauses.append("current_value = ?")
                    params.append(current_val + (value * op_multiplier))
                if max_value is not None:
                    if current_max is None: return f"Error: Cannot modify max_value for '{resource_name}' as it is not set."
                    set_clauses.append("max_value = ?")
                    params.append(current_max + (max_value * op_multiplier))

            if set_clauses:
                set_clauses.append("last_updated = ?")
                params.append(timestamp)
                query = f"UPDATE character_resources SET {', '.join(set_clauses)} WHERE user_id = ? AND resource_name = ?"
                params.extend([user_id, resource_name])
                cursor.execute(query, tuple(params))
                conn.commit()
                return f"Success: Updated '{resource_name}' for user {user_id}."
            else:
                return "Info: Operation did not result in any changes."

    except sqlite3.Error as e:
        print(f"ERROR: A database error occurred in manage_character_resource: {e}")
        return f"An unexpected database error occurred: {e}"

def manage_character_status(user_id: str, operation: str, effect_name: Optional[str] = None, details: Optional[str] = None, duration: Optional[int] = None) -> str:
    """
    Manages a character's temporary status effects. Operations: 'add', 'remove', 'update', 'view'.
    'add' applies a new status effect. 'details' and 'duration' are optional.
    'remove' deletes a status effect from the table based on its name.
    'update' modifies the details or duration of an existing status effect.
    'view' returns the details of a specific effect, or all effects if no name is provided.
    """ 
    print(f"--- STATUS MGMT --- User: {user_id}, Effect: {effect_name or 'ALL'}, Op: {operation}")

    valid_ops = ['add', 'remove', 'update', 'view']
    if operation.lower() not in valid_ops:
        return f"Error: Invalid operation '{operation}'. Must be one of {valid_ops}."

    timestamp = datetime.now(timezone.utc).isoformat()
    return_message = ""
    
    try:
        with sqlite3.connect(DB_FILE) as conn:
            conn.row_factory = sqlite3.Row  # Set the row factory on the connection
            cursor = conn.cursor()
            
            if operation == 'view':
                if effect_name:
                    cursor.execute("SELECT effect_name, effect_details, duration_in_rounds, timestamp FROM character_status WHERE user_id = ? AND effect_name = ?", (user_id, effect_name)) # noqa
                else:
                    cursor.execute("SELECT effect_name, effect_details, duration_in_rounds, timestamp FROM character_status WHERE user_id = ?", (user_id,)) # noqa
                rows = cursor.fetchall()
                results = [dict(row) for row in rows]
                return json.dumps(results, indent=2) if results else "Info: You have no active status effects."
            
            if operation == 'add' and effect_name:
                query = "INSERT INTO character_status (user_id, effect_name, effect_details, duration_in_rounds, timestamp) VALUES (?, ?, ?, ?, ?)"
                params = (user_id, effect_name, details, duration, timestamp)
                cursor.execute(query, params)
                return_message = f"Success: Applied status '{effect_name}' to user {user_id}."

            elif operation == 'remove' and effect_name:
                query = "DELETE FROM character_status WHERE user_id = ? AND effect_name = ?"
                params = (user_id, effect_name)
                cursor.execute(query, params)
                rows_affected = cursor.rowcount
                if rows_affected > 0:
                    return_message = f"Success: Removed {rows_affected} instance(s) of status '{effect_name}' for user {user_id}."
                else:
                    return_message = f"Info: No active status named '{effect_name}' found for user {user_id} to remove."
            
            elif operation == 'update' and effect_name:
                cursor.execute("SELECT status_id FROM character_status WHERE user_id = ? AND effect_name = ?", (user_id, effect_name))
                row = cursor.fetchone()
                if not row:
                    return f"Error: Status '{effect_name}' not found for user {user_id}. Use 'add' operation first."

                set_clauses = ["timestamp = ?"]
                update_params = [timestamp]
                if details is not None:
                    set_clauses.append("effect_details = ?")
                    update_params.append(details)
                if duration is not None:
                    set_clauses.append("duration_in_rounds = ?")
                    update_params.append(str(duration))
                
                query = f"UPDATE character_status SET {', '.join(set_clauses)} WHERE user_id = ? AND effect_name = ?"
                update_params.extend([user_id, effect_name])
                
                cursor.execute(query, tuple(update_params))
                return_message = f"Success: Updated status '{effect_name}' for user {user_id}."

            conn.commit()
        print(return_message)
        return return_message

    except sqlite3.Error as e:
        print(f"ERROR: A database error occurred in manage_character_status: {e}")
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

    try:
        repo = Repo(PROJECT_ROOT)
        target_path = (PROJECT_ROOT / file_path).resolve()
        if not target_path.is_relative_to(PROJECT_ROOT):
            return "Error: Access denied. Cannot access files outside the project directory."

        timestamp = datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')
        sanitized_message = re.sub(r'[^a-zA-Z0-9\-]', '-', commit_message.splitlines()[0]).strip('-')
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

        repo.heads.master.checkout()

        return (f"Success. A new branch '{branch_name}' was created and pushed to the remote repository "
                f"with your changes for `{file_path}`. Please review and merge the pull request on GitHub.")

    except GitCommandError as e:
        print(f"ERROR: A Git command failed: {e}")
        return f"An error occurred during a Git operation: {e}"
    except Exception as e:
        print(f"ERROR: An unexpected error occurred in create_git_commit_proposal: {e}")
        return f"An unexpected error occurred: {e}"

# --- RETAINED SPECIALIZED & EXTERNAL TOOLS ---

def roll_dice(dice_notation: str) -> str:
    """
    Rolls one or more dice based on standard D&D notation (e.g., '1d20', '3d6+4, 1d8', '2d8-1 and 1d4').
    Returns a JSON object with a list of individual roll results and a grand total.
    """
    print(f"--- Rolling Dice: {dice_notation} ---")
    # This pattern finds all instances of 'XdY' with an optional modifier like '+Z' or '-Z'
    pattern = re.compile(r'(\d+)d(\d+)([+\-]\d+)?')
    matches = pattern.findall(dice_notation.lower().strip())

    if not matches:
        return f"Error: No valid dice notation found in '{dice_notation}'. Please use a format like '1d20' or '3d6+4'."

    all_results = []
    grand_total = 0

    for match in matches:
        num_dice = int(match[0])
        die_sides = int(match[1])
        modifier_str = match[2]

        if num_dice <= 0 or die_sides <= 0:
            # Skip invalid entries like '0d6'
            continue

        rolls = [random.randint(1, die_sides) for _ in range(num_dice)]
        sub_total = sum(rolls)
        modifier = 0

        if modifier_str:
            modifier = int(modifier_str)
            sub_total += modifier

        roll_result = {
            "notation": f"{num_dice}d{die_sides}{modifier_str if modifier_str else ''}",
            "rolls": rolls,
            "modifier": modifier,
            "total": sub_total
        }
        all_results.append(roll_result)
        grand_total += sub_total

    return json.dumps({
        "results": all_results,
        "grand_total": grand_total
    }, indent=2)

def search_knowledge_base(query: Optional[str] = None, id: Optional[str] = None, item_type: Optional[str] = None, source: Optional[str] = None, data_query: Optional[dict] = None, mode: str = 'summary', max_results: int = 25) -> str:
    """
    Searches the knowledge base using a structured query and the low-level SQL execution function.
    This tool has two modes: 'summary' (default) and 'full'.
    - 'summary' mode returns a list of matching items with basic info (id, name, type, source).
    - 'full' mode requires a specific 'id' and returns the complete data for that single item.
    - 'data_query' can be a dictionary (e.g., {'metadata.is_official': True}) to filter results based on the content of the 'data' JSON column.
    """
    print(f"--- DB Knowledge Search. Mode: {mode.upper()}. Query: '{query or id}' ---")

    if mode == 'full' and not id:
        return "Error: 'full' mode requires a specific 'id'. Please perform a 'summary' search first to get the ID."
    
    if not any([query, id, data_query]):
        return "Error: You must provide at least one search criterion: 'query', 'id', or 'data_query'."

    select_columns = "id, name, type, source" if mode == 'summary' else "data"
    
    where_clauses = []
    params: List[Any] = []

    if id:
        where_clauses.append("id = ?")
        params.append(id)
    else:
        if query:
            where_clauses.append("name LIKE ?")
            params.append(f"%{query}%")
        if item_type:
            where_clauses.append("type = ?")
            params.append(item_type.lower())
        if source:
            where_clauses.append("source = ?")
            params.append(source.upper())
        if data_query:
            for key, value in data_query.items():
                path = f"$.{key}"
                where_clauses.append("json_extract(data, ?) = ?")
                params.append(path)
                if isinstance(value, bool):
                    params.append(1 if value else 0)
                else:
                    params.append(value)

    if not where_clauses:
         return "Error: You must provide at least one search criterion."

    sql_query = f"SELECT {select_columns} FROM knowledge_base WHERE {' AND '.join(where_clauses)} LIMIT ?"
    params.append(max_results)

    result_json = execute_sql_read(sql_query, [str(p) for p in params])

    if "returned no results" in result_json:
        return f"Source: Local Database\n---\nNo entries found matching your criteria."

    if mode == 'full':
        try:
            data = json.loads(result_json)
            if data and 'data' in data[0]:
                return json.dumps(json.loads(data[0]['data']), indent=2)
            else:
                return f"Source: Local Database\n---\nNo full data entry found for the given id."
        except (json.JSONDecodeError, IndexError, KeyError) as e:
            print(f"ERROR: Failed to parse full data in search_knowledge_base: {e}")
            return "Error: Could not parse or find the full data entry. The record may be malformed."
    
    return result_json

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
    Rebuilds specified manifest JSON files.
    """
    print(f"--- ACTION: Rebuilding manifests: {manifest_names} ---")
    base_path = Path(__file__).parent.resolve()
    db_path = base_path / generate_manifests.DB_FILE
    output_path = base_path / generate_manifests.OUTPUT_DIR
    
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
                db_not_required_map[name](output_path)
                rebuilt_successfully.append(name)
            except Exception as e:
                print(f"Error rebuilding manifest '{name}': {e}")
        elif name in db_required_map:
            db_manifests_to_run.append(name)
        else:
            invalid_names.append(name)

    if db_manifests_to_run:
        conn = generate_manifests.get_db_connection(db_path)
        if not conn:
            return "Error: Could not connect to the database to rebuild manifests."
        try:
            for name in db_manifests_to_run:
                try:
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


def update_character_from_web() -> str:
    """
    Downloads the character sheet JSON from D&D Beyond and generates its schema.
    """
    print("--- ACTION: Updating character sheet from D&D Beyond ---")
    character_url = "https://character-service.dndbeyond.com/character/v5/character/151586987?includeCustomItems=true"
    base_dir = os.path.dirname(os.path.abspath(__file__))
    character_dir, instructions_dir = os.path.join(base_dir, 'character'), os.path.join(base_dir, 'instructions')
    raw_file_path, schema_file_path = os.path.join(character_dir, 'character_sheet_raw.json'), os.path.join(instructions_dir, 'character_schema.json')
    os.makedirs(character_dir, exist_ok=True)
    
    try:
        response = requests.get(character_url, timeout=15)
        response.raise_for_status()
        raw_data = response.json()
        with open(raw_file_path, 'w', encoding='utf-8') as f: json.dump(raw_data, f, indent=2)
        
        def _generate_json_structure(data):
            if isinstance(data, dict): return {k: _generate_json_structure(v) for k, v in data.items()}
            elif isinstance(data, list): return [_generate_json_structure(data[0])] if data else []
            elif isinstance(data, (int, float)): return "number"
            elif isinstance(data, bool): return "boolean"
            else: return "string"
        
        with open(schema_file_path, 'w', encoding='utf-8') as f: json.dump(_generate_json_structure(raw_data), f, indent=2)
        return f"Successfully downloaded character data for '{raw_data.get('data', {}).get('name', 'Unknown')}' and generated the data schema."
    except requests.exceptions.RequestException as e:
        return f"Error: A network error occurred while fetching the character sheet: {e}"
    except Exception as e:
        return f"An unexpected error occurred: {e}"

def search_dnd_rules(query: str, num_results: int = 5) -> str:
    """Performs a web search using Google's Custom Search API."""
    quota_file = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'quota_tracker.json')
    lock_file = quota_file + ".lock"
    with FileLock(lock_file, timeout=5):
        today = str(date.today())
        try:
            with open(quota_file, 'r') as f: tracker = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            tracker = {"date": today, "count": 0}
        if tracker.get("date") != today: tracker = {"date": today, "count": 0}
        if tracker.get("count", 0) >= DAILY_SEARCH_QUOTA:
            return "Error: Daily search quota has been reached."
        print(f"--- Performing web search for URLs about: '{query}' (Query {tracker.get('count', 0) + 1}/{DAILY_SEARCH_QUOTA}) ---")
        try:
            search_engine_id = os.getenv("SEARCH_ENGINE_ID")
            credentials, _ = google.auth.default()
            service = build("customsearch", "v1", credentials=credentials, static_discovery=False)
            res = service.cse().list(q=query, cx=search_engine_id, num=num_results).execute()
            tracker["count"] += 1
            with open(quota_file, 'w') as f: json.dump(tracker, f)
            if 'items' in res and len(res['items']) > 0:
                return "\n\n".join([f"Title: {i.get('title')}\nURL: {i.get('link')}" for i in res['items']])
            else:
                return "No relevant URLs found."
        except Exception as e:
            return f"An error occurred during web search: {e}"

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

def lookup_character_data(query: str) -> str:
    """
    Retrieves a specific piece of data from the local character sheet file.
    """
    print(f"--- ACTION: Looking up character data with query: '{query}' ---")
    raw_file_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'character', 'character_sheet_raw.json')
    try:
        with open(raw_file_path, 'r', encoding='utf-8') as f: data = json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return "Error: 'character_sheet_raw.json' not found. Run `update_character_from_web`."
    try:
        keys, current_level = query.split('.'), data
        for key in keys:
            match = re.match(r"(\w+)\[(\d+)\]", key)
            if match:
                base_key, index = match.groups()
                current_level = current_level[base_key][int(index)]
            else:
                current_level = current_level[key]
        return json.dumps(current_level, indent=2)
    except (KeyError, IndexError, TypeError):
        return f"Error: Query '{query}' is invalid. Check `character_schema.json` for the correct path."
    except Exception as e:
        return f"An unexpected error occurred: {e}"

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
            tree.append(f"{indent}{os.path.basename(root)}/")
            sub_indent = ' ' * 4 * (level + 1)
            for f in files:
                tree.append(f"{sub_indent}{f}")
        return "\n".join(tree)
    except Exception as e:
        return f"Error listing files: {e}"

def read_file(file_path: str) -> str:
    """
    Reads the contents of a specific file within the project.
    """
    print(f"--- Reading File located on: {file_path} ---")
    try:
        target_path = (PROJECT_ROOT / file_path).resolve()
        if not target_path.is_relative_to(PROJECT_ROOT):
            return "Error: Access denied."
        if not target_path.is_file():
            return f"Error: File not found at '{file_path}'."
        with open(target_path, 'r', encoding='utf-8') as f:
            return f"[System Note: The following are the contents inside the file found in the filepath: {file_path}]{f.read()}"
    except UnicodeDecodeError:
        return f"Error: Could not decode the file at '{file_path}'. It may not be a text file."
    except Exception as e:
        return f"Error reading file: {e}"
