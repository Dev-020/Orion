---
name: orion
description: Essential Orion tools for SQL, VDB, and multi-modal file operations. Call activate_skill('orion') to enable execute_sql_read, execute_vdb_read, execute_write, list_project_files, and read_file.
---

# Orion Codebase Tools

This skill provides a bridge to Orion's native Python tools for database management and multi-modal file processing.

## **Activation**
You MUST call `activate_skill('orion')` at the beginning of any session where you need to perform database queries or analyze complex files (images, audio, PDF).

## **Available Tools**

### **execute_sql_read**
Executes a read-only SELECT query against the SQLite database.
- **query** (string, required): A valid SQL SELECT statement. Use `?` placeholders for security.
- **params** (list of strings, optional): A list of values for the `?` placeholders.

### **execute_vdb_read**
Performs a semantic search on the Vector Database (ChromaDB).
- **query_texts** (list of strings, required): Text strings to search for.
- **n_results** (integer, optional): Maximum number of results (default: 7).
- **where** (dictionary, optional): Metadata filters.
- **ids** (list of strings, optional): Specific vector IDs to retrieve.

### **execute_write**
An orchestrator for synchronized writes to both SQLite and Vector DB.
- **table** (string, required): Target table name.
- **operation** (string, required): 'insert', 'update', or 'delete'.
- **user_id** (string, required): The ID of the user requesting the change.
- **data** (dictionary, optional): Data to insert/update.
- **where** (dictionary, optional): Filter for update/delete.

### **list_project_files**
Lists the file structure of the codebase.
- **subdirectory** (string, optional): Folder to explore (default: ".").

### **read_file**
A multi-modal ingestion tool for reading text, images, audio, and PDFs.
- **file_path** (string, required): Path to the file relative to the project root.
- **start_line** (integer, optional): Starting line for text files.
- **end_line** (integer, optional): Ending line for text files.

### **browse_website**
Reads one or more webpages with optional RAG filtering.
- **url** (string or list, required): Target URL(s).
- **query** (string, optional): Query for RAG filtering.

### **search_web**
Performs a live web search with RAG-based result filtering.
- **query** (string, required): Search terms.
- **smart_filter** (boolean, optional): Whether to use RAG filtering (default: true).

### **delegate_to_native_tools_agent**
Delegates a complex task to a specialized agent with Google Search and URL context.
- **task** (string, required): Natural language description of the task.
