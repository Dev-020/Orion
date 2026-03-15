---
name: orion
description: Essential Orion tools for SQL, VDB, and D&D operations. Call activate_skill('orion') to enable database queries, multi-modal file processing, and D&D search/management tools.
---

# Orion Codebase & D&D Tools

This skill provides a bridge to Orion's native Python tools for database management, multi-modal file processing, and Dungeons & Dragons 5e reference/management.

## **Activation**
You MUST call `activate_skill('orion')` at the beginning of any session where you need to perform database queries, analyze complex files, or use D&D specific tools.

## **General Tools**

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

## **Dungeons & Dragons Tools**

### **search_knowledge_base**
Searches the D&D 5e knowledge base (local 5eTools dataset). Use this for spells, monsters, items, etc.
- **query** (string, optional): Search by item name (exact or fuzzy).
- **semantic_query** (string, optional): Concept-based search (e.g., "a spell that shoots frost").
- **item_id** (string, optional): Exact ID for 'full' mode retrieval.
- **item_type** (string, optional): filter by type (spell, bestiary, feat, class, etc.).
- **source** (string, optional): filter by source code (PHB, XGE, MM, etc.).
- **mode** (string, optional): 'summary' (default) or 'full'.
- **max_results** (integer, optional): Maximum number of results (default: 25).

### **roll_dice**
Rolls D&D dice using standard notation (e.g., '1d20', '3d6+4').
- **dice_notation** (string, required): The dice to roll.

### **manage_character_resource**
Manages a character's resource (HP, spell slots, etc.).
- **user_id** (string, required): The Discord ID of the user.
- **operation** (string, required): 'set', 'add', 'subtract', 'create', or 'view'.
- **resource_name** (string, optional): Name of the resource.
- **value** (integer, optional): Value to use for the operation.
- **max_value** (integer, optional): Max capacity for the resource.

### **manage_character_status**
Manages temporary status effects (Conditions, Spells).
- **user_id** (string, required): The Discord ID of the user.
- **operation** (string, required): 'add', 'remove', 'update', or 'view'.
- **effect_name** (string, optional): Name of the effect.
- **details** (string, optional): Details about the effect.
- **duration** (integer, optional): Duration in rounds.

### **list_searchable_types**
Discovers all searchable D&D content types and source codes available in the current installation.
