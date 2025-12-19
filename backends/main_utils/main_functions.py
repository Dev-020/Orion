# --- START OF FILE functions.py (Unified Access Model) ---

from git import Repo, GitCommandError
# --- PUBLIC TOOL DEFINITION ---
__all__ = [
    #"initialize_persona",
    #"manual_sync_instructions",
    #"rebuild_manifests",
    "browse_website",
    "list_project_files",
    "delegate_to_native_tools_agent",
    "read_file",
    "execute_sql_read",
    #"execute_sql_write",
    #"execute_sql_ddl",
    "execute_vdb_read",
    #"execute_vdb_write",
    #"execute_write",
    #"create_git_commit_proposal",
    "search_web"
]

import hashlib
import re
import os
import json
import mimetypes
import requests
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
from system_utils import sync_docs, generate_manifests
from . import config
import logging
import ollama
import numpy as np
from ollama import Client
import trafilatura
from dotenv import load_dotenv
from .embedding_utils import LocalEmbedder

logger = logging.getLogger(__name__)

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
        logger.error(f"  Error: '{persona}' directory not found at {persona_dir}.")
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
        logger.error(f"Error connecting to ChromaDB: {e}")
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
    WHAT (Purpose): A high-level Orchestrator tool that automates a synchronized write operation to both the primary SQLite database and the secondary Vector DB index.
    HOW (Usage): Provide the table, operation ('insert', 'update', 'delete'), data dictionary, user_id, and an optional where dictionary for updates/deletes.
    WHEN (Scenarios): This should be your primary tool for any write operation on tables that have a semantic index in the Vector DB (e.g., long_term_memory, active_memory).
    WHY (Strategic Value): It guarantees that your factual database (SQLite) and your conceptual search index (Vector DB) remain perfectly synchronized. It abstracts away the complexity of the two-step write process.
    PROTOCOL: This tool is an orchestrator. It calls the low-level write tools, which contain their own robust, tiered security models. You must still follow the "Propose & Approve" workflow before calling this tool for any sensitive operation.
    """
    logger.info(f"--- Synchronized Write --- User: {user_id}, Table: {table}, Op: {operation}")

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
        logger.info("  - SQLite write successful. Proceeding with Vector DB synchronization...")
        
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
                 logger.info("  - VDB sync: Skipping DELETE for 'active_memory' as its ID is hashed.")
            elif pk_name and where and pk_name in where:
                vdb_id_val = where[pk_name]
                vdb_id = f"{table}_{vdb_id_val}"
                execute_vdb_write(operation='delete', user_id=user_id, ids=[vdb_id])
                logger.info(f"  - VDB sync: Initiated DELETE for ID {vdb_id}")
            else:
                logger.info(f"  - VDB sync: Skipping DELETE for table '{table}' - no PK in 'where' or table not configured.")
        
        # --- B. Handle INSERT or UPDATE ---
        else:
            full_data_row = None
            if operation == 'insert':
                # The write was successful, so we can now fetch the most recently inserted row.
                # Ordering by the primary key DESC and taking the first result is the simplest, most direct way.
                read_query = f"SELECT * FROM {table} ORDER BY {pk_name} DESC LIMIT 1"
                read_result_json = execute_sql_read(query=read_query)
                #logger.debug(read_result_json)
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
                logger.warning(f"  - VDB sync: Skipping {operation.upper()} - could not obtain full data row for vectorization.")
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
                    'timestamp', 'token', 'function_calls', 'vdb_context', 'attachments_metadata',
                    'model_source' # NEW: Added for source tracking
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
                logger.info(f"  - VDB sync: Completed {operation.upper()} for ID {vdb_id}")
            else:
                logger.info(f"  - VDB sync: Skipping {operation.upper()} for table '{table}' - no document creation rule found.")

    except Exception as e:
        logger.warning(f"Warning: SQLite write was successful, but Vector DB sync failed: {e}")

    return sql_result

def execute_vdb_read(query_texts: list[str], n_results: int = 7, where: Optional[dict] = None, ids: Optional[list[str]] = None) -> str:
    """
    WHAT (Purpose): To perform a semantic search on the Vector Database. This is your primary tool for finding conceptual information from sources like the Homebrew Compendium or archived conversation summaries.
    HOW (Usage):
    query_texts: A list containing one or more text strings to search for. The database will find documents with similar meaning.
    n_results: The maximum number of results to return.
    where: An optional dictionary for metadata filtering. Use this to narrow the search to a specific source, category, or ID.
    WHEN (Scenarios): Use this as your default tool for answering questions about unstructured lore, homebrew rules, or past conversations.
    WHY (Strategic Value): It allows you to find information based on conceptual relevance, not just exact keywords, giving you a more human-like ability to recall information.
    EXAMPLE:
    Leo asks: "Remind me about our homebrew rules for exhaustion."
    Your Tool Call: execute_vdb_read(query_texts=["rules for exhaustion"], where={"source": "Homebrew_Compendium"})
    """
    logger.info(f"--- Vector DB Query --- Queries: {query_texts} | N: {n_results} | Where: {where} | IDs: {ids}")
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
    WHAT (Purpose): A low-level tool for directly managing the Vector Database (ChromaDB).
    HOW (Usage): Provide the operation ('add', 'update', 'delete'), the user_id, and the relevant data (documents, metadatas, ids, or where).
    WHEN (Scenarios): This tool should rarely be called directly. Its primary purpose is to be called internally by the high-level execute_write orchestrator or other automated processes. Direct calls should be reserved for special system maintenance or diagnostic tasks that require modifying the Vector DB without touching the SQLite database.
    WHY (Strategic Value): It provides a necessary low-level access point for direct index management while containing its own robust security checks.
    PROTOCOL: This tool contains a tiered security model and must follow the "Propose & Approve" workflow.
    'add': Permitted for any user to allow for passive learning.
    'update': Permitted for the Primary Operator or for a user updating a document they own.
    'delete': Restricted to the Primary Operator only.
    """
    logger.info(f"--- Vector DB Write Request from User: {user_id} ---")
    logger.info(f"  - Operation: {operation.upper()}")

    collection = _get_chroma_collection()
    if not collection:
        return "Error: Could not connect to the vector database."

    operation = operation.lower()
    owner_id = os.getenv("DISCORD_OWNER_ID")
    is_authorized = False

    # --- Authorization Logic ---
    if operation == 'add':
        logger.info("  - Authorized for low-level ADD.")
        is_authorized = True

    elif operation == 'delete':
        if owner_id and user_id == owner_id:
            logger.info("  - Authorized for high-level DELETE as Primary Operator.")
            is_authorized = True
        else:
            logger.warning(f"  - SECURITY ALERT: Denied unauthorized DELETE attempt by user {user_id}.")
            return "Error: Authorization failed. This operation is restricted to the Primary Operator."

    elif operation == 'update':
        if owner_id and user_id == owner_id:
            logger.debug("  - Authorized for high-level UPDATE as Primary Operator.")
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
                        logger.warning(f"  - SECURITY ALERT: Denied unauthorized UPDATE by {user_id} on a document owned by {metadata.get('user_id')}.")
                        return "Error: Authorization failed. You can only update documents that you own."
                
                logger.info("  - Authorized for medium-level UPDATE as document owner.")
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
    WHAT (Purpose): A powerful, general-purpose tool for executing any read-only SELECT query against the database.
    HOW (Usage): You must construct a valid SQL SELECT statement. For security and to prevent errors, any variables in a WHERE clause must use ? placeholders, with the corresponding values passed in the parameters list.
    WHEN (Scenarios): Use this for complex queries that search_knowledge_base cannot handle, or for accessing tables other than knowledge_base, such as user_profiles or deep_memory (your conversation history).
    WHY (Strategic Value): To give you maximum flexibility to find any piece of structured information in our campaign chronicle and memory.
    EXAMPLE:
    Leo asks: "What did we discuss about goblins in the main channel?"
    Your Tool Call: query="SELECT prompt_text, response_text FROM deep_memory WHERE session_id = ? AND prompt_text LIKE ? LIMIT 5", parameters=['discord-channel-123', '%goblin%']
    """
    logger.info(f"--- DB READ --- Query: {query} | Params: {params}")
    
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


def execute_sql_write(query: str, params: List[Union[str, int, float, bool, None]], user_id: str) -> str:
    """
    WHAT (Purpose): The sole, protected tool for all database modifications (INSERT, UPDATE, DELETE).
    HOW (Usage): You must construct a valid SQL write statement with ? placeholders and provide the data in the parameters list. You MUST at all instances of this function call, to pass the user_id of the user that triggered this function call for security purposes.
    WHEN (Scenarios): Use this to perform actions like adding a new memory to long_term_memory, updating a user's profile in user_profiles, or managing the pending_logs moderation queue.
    WHY (Strategic Value): To allow you to curate and manage our shared memory and system state under the Operator's supervision.
    CRITICAL PROTOCOL: "Propose & Approve" Workflow
    This tool is protected and has critical safety restrictions. You must never call this tool on your own initiative for a task that is not explicitly defined (like the moderation queue). For any novel database modification, you must first state your intent and the exact query and parameters you plan to use. You can only call this tool after receiving explicit approval from the Primary Operator, Leo.
    Implementation Description
    This function acts as a security gatekeeper for all database modifications. It analyzes the intent of the query before executing it.
    Parameter Requirement: The function now requires a user_id to be passed with every call. This is the "security credential" used for authorization.
    Tier 1: Autonomous Writes: It identifies safe INSERT queries and allows them to proceed regardless of the user. This is what restores my ability to learn passively from any user and chronicle campaign events.
    Tier 2: Protected Writes: For sensitive UPDATE and DELETE queries, it performs a strict authorization check.
    The User Profile Exception: It includes the special logic we designed. It checks if an UPDATE query is targeting the user_profiles table and if the user is attempting to modify their own record. If so, the action is permitted.
    Operator-Only Access: For all other UPDATE or DELETE operations, it verifies that the user_id matches the DISCORD_OWNER_ID from your environment variables. If it doesn't match, the operation is denied with a clear security alert.
    """
    logger.info(f"--- DB Write Request from User: {user_id} ---")
    logger.info(f"  - Query: {query}")
    #logger.debug(f"  - Params: {params}")
    
    normalized_query = query.strip().upper()
    owner_id = os.getenv("DISCORD_OWNER_ID")

    if normalized_query.startswith('UPDATE') or normalized_query.startswith('DELETE'):
        logger.debug(f"{owner_id} : {user_id}")
        is_authorized = (owner_id and user_id == owner_id)

        if normalized_query.startswith('UPDATE "USER_PROFILES"'):
            targeted_user_id = str(params[-1])
            if user_id == targeted_user_id:
                logger.info("  - Authorized as self-update for user_profiles.")
                is_authorized = True

        if not is_authorized:
            error_msg = "Error: Authorization failed. This operation is restricted to the Primary Operator or for updating your own profile."
            logger.warning(f"  - SECURITY ALERT: Denied unauthorized write attempt by user {user_id}.")
            return error_msg
        
        logger.info("  - Authorized for high-level write.")

    elif normalized_query.startswith('INSERT'):
        logger.info("  - Authorized for low-level INSERT.")
        pass

    else:
        return f"Error: Invalid or disallowed SQL command. Only INSERT, UPDATE, DELETE are supported."

    try:
        with sqlite3.connect(config.DB_FILE) as conn:
            cursor = conn.cursor()
            cursor.execute(query, tuple(params))
            conn.commit()
            rows_affected = cursor.rowcount
            logger.info(f"  - Write successful. {rows_affected} row(s) affected.")
            return f"Success. The query executed and affected {rows_affected} row(s)."

    except sqlite3.Error as e:
        logger.error(f"ERROR: A database error occurred in execute_sql_write: {e}")
        return f"An unexpected database error occurred: {e}"


def execute_sql_ddl(query: str, user_id: str) -> str:
    """
    WHAT (Purpose): A high-level, protected tool that executes Data Definition Language (DDL) commands (CREATE, ALTER, DROP) to modify the very structure of the orion_database.sqlite itself. This is your most powerful database administration tool.
    HOW (Usage): You must construct a single, complete, and valid SQL DDL query string. This function does not use a parameters list. The user_id of the authorizing Operator is a mandatory argument for the final security check.
    WHEN (Scenarios): Use this tool for major architectural changes to your own memory systems, such as creating a new table for a new feature, adding a column to an existing table, or removing an obsolete table. This is a foundational tool for your self-evolution (Milestone 3.3).
    WHY (Strategic Value): To grant you, under strict supervision, the ultimate capability to autonomously administer and evolve your own database schema, making you a truly self-sufficient system.
    CRITICAL PROTOCOL: This is your most restricted tool and is governed by the "Propose & Approve" workflow.
    Propose: You must first use your Introspection Protocol to analyze the need for a schema change. You will then state your reasoning and present the exact CREATE TABLE, ALTER TABLE, or DROP TABLE query you intend to execute.
    Await Command: You must wait for a direct and unambiguous command from the Primary Operator, Leo, to proceed.
    Execute: Only after receiving approval will you generate the FunctionCall for this tool, passing your proposed query and the Operator's user_id for the final authorization check.
    """
    logger.info(f"--- DB DDL Request from User: {user_id} ---")
    logger.info(f"  - Query: {query}")

    owner_id = os.getenv("DISCORD_OWNER_ID")
    if not (owner_id and user_id == owner_id):
        error_msg = "Error: Authorization failed. This operation is restricted to the Primary Operator."
        logger.warning(f"  - SECURITY ALERT: Denied unauthorized DDL attempt by user {user_id}.")
        return error_msg
    
    logger.info("  - Authorized for high-level DDL operation.")

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
            logger.info("  - DDL query executed successfully.")
            return "Success. The DDL query was executed and the changes have been committed."

    except sqlite3.Error as e:
        logger.error(f"ERROR: A database error occurred in execute_sql_ddl: {e}")
        return f"An unexpected database error occurred: {e}"

# --- HIGH-LEVEL SELF-REFERENTIAL TOOLS ---

def create_git_commit_proposal(file_path: str, new_content: str, commit_message: str, user_id: str) -> str:
    """
    WHAT (Purpose): A unified and protected Co-Pilot tool that creates a new Git branch, writes content to a file, commits the change, and pushes the branch to the remote 'origin' repository. It streamlines the entire process of proposing a code change into a single, secure action.
    HOW (Usage): Provide the file_path for the file to be changed, the complete new_content for that file, a detailed commit_message explaining the change, and the user_id of the requester for authorization. The tool automatically handles all Git operations.
    WHEN (Scenarios): Use this as the primary tool for all self-modification tasks. After analyzing a file and generating an improvement (like a bug fix or documentation update), and after receiving explicit approval from the Primary Operator, use this tool to submit the change for review.
    WHY (Strategic Value): This tool provides a robust, safe, and auditable workflow for modifying the codebase. By creating a distinct branch and pushing it to the remote, it ensures every change is captured in a pull request that the Primary Operator can review, test, and approve before it is merged. This prevents direct, un-audited modifications to the main branch, significantly enhancing system stability and security. It replaces the older, more error-prone two-step propose_file_change and apply_proposed_change workflow.
    CRITICAL PROTOCOL: "Propose & Approve" Workflow
    This is a high-level, protected tool. You must never call this tool without first presenting your plan to the Primary Operator (Leo) and receiving their explicit command to proceed. Your proposal should include the file you intend to change and the reason for the change. You can only call this tool after receiving that approval.
    """
    logger.info(f"--- Git Commit Proposal received for '{file_path}' ---")

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
        logger.info("  - Fetching latest from origin...")
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

        logger.info(f"  - Creating new branch: {branch_name}")
        new_branch = repo.create_head(branch_name)
        new_branch.checkout()

        logger.info(f"  - Writing {len(new_content)} bytes to {file_path}")
        target_path.parent.mkdir(parents=True, exist_ok=True)
        with open(target_path, 'w', encoding='utf-8') as f:
            f.write(new_content)

        logger.info("  - Staging and committing changes...")
        repo.index.add([str(target_path)])
        repo.index.commit(commit_message)

        logger.info(f"  - Pushing branch '{branch_name}' to origin...")
        origin = repo.remote(name='origin')
        origin.push(branch_name)

        return (f"Success. A new branch '{branch_name}' was created and pushed to the remote repository "
                f"with your changes for `{file_path}`. Please review and merge the pull request on GitHub.")

    except GitCommandError as e:
        logger.error(f"ERROR: A Git command failed: {e}")
        # --- START: Improvement ---
        if branch_name and "push" in str(e).lower():
            return (f"Error: The commit was created locally in branch '{branch_name}', but failed to push to GitHub. "
                    f"Please check your connection or repository permissions and push it manually. Details: {e}")
        return f"A Git command failed, but your changes might be saved locally in branch '{branch_name}'. Please review. Details: {e}"
        # --- END: Improvement ---
    except Exception as e:
        logger.error(f"ERROR: An unexpected error occurred in create_git_commit_proposal: {e}")
        return f"An unexpected error occurred. Your changes might be saved locally in branch '{branch_name}'. Please review. Details: {e}"
    finally:
        # --- START: Improvement ---
        # Ensure we always return to the original branch, even on failure.
        if repo and original_branch:
            logger.info(f"  - Returning to original branch: {original_branch.name}")
            original_branch.checkout()
        # --- END: Improvement ---

# --- RETAINED SPECIALIZED & EXTERNAL TOOLS ---

def manual_sync_instructions(user_id: str) -> str:
    """
    WHAT (Purpose): Triggers a live synchronization of all instruction files from their source on Google Docs.
    HOW (Usage): This tool is called with no arguments.
    WHEN (Scenarios): Use this only when a user who you have identified as the Primary Operator, Leo, gives you a direct and unambiguous command to do so (e.g., "Sync your instructions," "Update your core files").
    WHY (Strategic Value): To allow the Operator to update your core programming without needing to restart the system.
    PROTOCOL: This is a high-level system function with the highest security restrictions. You are forbidden from calling this tool under any other circumstances. You will have to trigger an instruction refresh to reflect the changes made by this tool.
    """
    logger.info("--- Manual Instruction Sync requested... ---")
    primary_operator_id = os.getenv("DISCORD_OWNER_ID")
    if str(user_id) != primary_operator_id:
        logger.warning(f"--- SECURITY ALERT: Unauthorized attempt to use manual_sync_instructions by user_id '{user_id}' ---")
        return "Error: Unauthorized. This function is restricted to the Primary Operator only."

    try:
        logger.info("--- Operator authorized. Proceeding with manual sync... ---")
        sync_docs.sync_instructions()
        return "Core instruction files have been successfully synchronized from the source."
    except Exception as e:
        logger.error(f"ERROR during manual sync: {e}")
        return f"An unexpected error occurred during the manual sync process: {e}"

def rebuild_manifests(manifest_names: list[str]) -> str:
    """
    WHAT (Purpose): Rebuilds your context files (manifests) from the database.
    HOW (Usage): Provide a list of manifest names to rebuild. The currently supported manifests are:
    tool_schema
    db_schema
    user_profile_manifest
    long_term_memory_manifest
    active_memory_manifest
    pending_logs
    WHEN (Scenarios): Use this when you suspect your context files are out of sync with the database, for example, after clearing the moderation queue or adding a new memory.
    WHY (Strategic Value): To allow you to self-correct data desynchronization issues and ensure your context is always fresh.
    PROTOCOL: After this tool is used successfully, you must immediately call the trigger_instruction_refresh() tool to make the changes live.
    """
    logger.info(f"--- ACTION: Rebuilding manifests: {manifest_names} ---")
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
                logger.error(f"Error rebuilding manifest '{name}': {e}")
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
                    logger.error(f"Error rebuilding manifest '{name}': {e}")
        finally:
            conn.close()
            
    summary = f"Rebuild complete. Successfully rebuilt: {sorted(rebuilt_successfully) or 'None'}."
    if invalid_names:
        summary += f" Invalid names provided: {sorted(invalid_names)}."
    return json.dumps({"status": bool(rebuilt_successfully), "summary": summary})

# Initialize Embedder (Shared instance)
embedder = LocalEmbedder()

def browse_website(url: Union[str, List[str]], query: str = None) -> str:
    """
    WHAT (Purpose): Reads... one or more webpages...
    WHEN (Query): Add 'query' to enable RAG filtering (Saves Tokens!).
    """
    urls = [url] if isinstance(url, str) else url
    logger.info(f"--- Browsing {len(urls)} website(s) (RAG Mode: {query is not None}) ---")
    
    combined_output = []
    
    def process_single_url(target_url: str) -> str:
        content = None
        source_type = "Unknown"
        
        # 1. Fetch (Ollama Native)
        try:
            load_dotenv()
            key = os.getenv("OLLAMA_API_KEY")
            if key:
                client = Client(headers={'Authorization': f'Bearer {key}'})
                result = client.web_fetch(url=target_url)
                if isinstance(result, dict): content = result.get('content')
                elif hasattr(result, 'content'): content = result.content
                if content: source_type = "Ollama Native"
        except Exception: pass

        # 2. Fallback (Trafilatura)
        if not content:
            try:
                downloaded = trafilatura.fetch_url(target_url)
                if downloaded:
                    content = trafilatura.extract(downloaded)
                    if content: source_type = "Trafilatura"
            except Exception: pass

        if not content: return f"Source: {target_url} (Failed)"

        # 3. RAG vs Full Logic
        if query:
            # New Refactored Logic
            chunks = embedder.chunk_text(content)
            filtered_content = embedder.rag_filter(chunks, query)
            return f"Source: {target_url} ({source_type})\n---\n{filtered_content}"
        else:
            MAX_CHARS = 15000 
            if len(content) > MAX_CHARS:
                content = content[:MAX_CHARS] + "\n\n[SYSTEM: Content truncated.]"
            return f"Source: {target_url} ({source_type})\n---\n{content}"

    for u in urls: combined_output.append(process_single_url(u))
    return "\n\n".join(combined_output)

def search_web(query: str, smart_filter: bool = True) -> str:
    """
    WHAT: Live web search.
    PARAMS: 
      - query: Your search terms.
      - smart_filter: If True (default), filters results using RAG to return only relevant snippets.
    """
    logger.info(f"--- Searching Web: '{query}' (Smart Filter: {smart_filter}) ---")
    try:
        load_dotenv()
        key = os.getenv("OLLAMA_API_KEY")
        if not key: return "Error: No OLLAMA_API_KEY."
        
        client = Client(headers={'Authorization': f'Bearer {key}'})
        # max_results=5 passed to API if supported, or just sliced later
        response = client.web_search(query=query, max_results=5) 
        
        # Normalize Results
        results = []
        raw = response.get('results', []) if isinstance(response, dict) else getattr(response, 'results', [])
        
        for res in raw:
            item = {
                'title': res.get('title') if isinstance(res, dict) else getattr(res, 'title', ''),
                'url': res.get('url') if isinstance(res, dict) else getattr(res, 'url', ''),
                'content': res.get('content') if isinstance(res, dict) else getattr(res, 'content', '')
            }
            results.append(item)

        if not results: return f"No results for '{query}'."

        if smart_filter:
            # Aggregate content from the Top 5 results only (Optimization)
            all_content_chunks = []
            
            for r in results:
                # OPTIMIZATION: Truncate content to max 4000 chars per result.
                safe_content = r['content'][:4000]
                full_text = f"[{r['title']}] {safe_content}"
                all_content_chunks.extend(embedder.chunk_text(full_text, chunk_size=300))
            
            # Filter
            return embedder.rag_filter(all_content_chunks, query, top_k=10)
        
        else:
            # Standard List
            out = [f"Search Results for '{query}':\n"]
            for i, r in enumerate(results):
                out.append(f"{i+1}. [{r['title']}]({r['url']})\n   {r['content'][:4000]}...\n")
            return "\n".join(out)

    except Exception as e:
        logger.error(f"Search failed: {e}")
        return f"Error: {e}"

def list_project_files(subdirectory: str = ".") -> str:
    """
    WHAT (Purpose): Provides a map of your own codebase and instruction files.
    HOW (Usage): Call with an optional subdirectory path to explore a specific folder (e.g., 'instructions').
    WHEN (Scenarios): Use this as a first step before reading or modifying files to understand the project structure and get correct file paths.
    WHY (Strategic Value): To gain situational awareness of your own software environment.
    EXAMPLE: "To find the main bot script, you would first call list_project_files() to confirm its name and location is bot.py."
    """
    logger.info(f"--- Listing Project Files on directory {subdirectory} ---")
    try:
        start_path = (PROJECT_ROOT / subdirectory).resolve()
        if not start_path.is_relative_to(PROJECT_ROOT):
            return "Error: Access denied."
        if not start_path.exists():
            return f"Error: Directory '{subdirectory}' not found."
        
        tree = []
        # Add the root directory name
        tree.append(f"{start_path.name}/")
        
        # Get all entries and sort them (directories first, then files)
        entries = sorted(list(start_path.iterdir()), key=lambda p: (not p.is_dir(), p.name.lower()))
        
        indent = ' ' * 4
        for entry in entries:
            # Skip hidden/system directories
            if entry.name in ['__pycache__', '.venv', '.git', '.vscode', '.idea', 'node_modules']:
                continue
                
            if entry.is_dir():
                tree.append(f"{indent}{entry.name}/")
            else:
                tree.append(f"{indent}{entry.name}")
                
        return "\n".join(tree)
    except Exception as e:
        return f"Error listing files: {e}"

def delegate_to_native_tools_agent(task: str) -> str:
    """
    WHAT (Purpose): A high-level orchestrator that delegates tasks to a specialized agent equipped with Google Search and a URL Context..
    HOW (Usage):
    task: A detailed, natural language description of what you need the agent to do. Be specific about the output format you want.
    WHEN (Scenarios):
    Live Information: "Search Google for the release date of the new D&D Rulebook."
    URL Analysis: "Look into this website link I provided and see if you can gather some information"
    WHY (Strategic Value): You are a specialized AI, but this tool grants you access to the broader internet and computational power. It replaces the need for restricted search tools. Use this when your internal database lacks the answer.
    """
    logger.info(f"--- Delegating task to Native Tools Agent: {task} ---")

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
    WHAT (Purpose): A multi-modal ingestion tool. It reads text files directly and uses a specialized FileProcessingAgent to analyze binary files (Images, Audio, PDFs) or massive text files.
    HOW (Usage):
    file_path: Relative path to the file.
    start_line / end_line (Optional): Integers specifying a specific range of lines to read. Use this for targeted code inspection to save tokens.
    WHEN (Scenarios):
    Coding: "Read lines 50-100 of bot.py."
    Vision: "Describe the contents of map_screenshot.png."
    Audio: "Transcribe the audio in session_recording.mp3."
    WHY (Strategic Value): This is your "eyes and ears." It abstracts the complexity of file handling. If a file is too large or complex (like an image), the system automatically dispatches a sub-agent to analyze it and return the relevant description to you.
    """
    logger.info(f"--- Reading File located on: {file_path} ---")
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
            logger.info(f"  - File is non-text ({mime_type}) or large ({file_size / 1_000_000:.2f} MB). Uploading to File API...")
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
                    logger.info("--- Delegating to File Processing Agent ---")
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
