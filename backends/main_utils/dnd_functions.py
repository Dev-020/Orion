# --- START OF FILE functions.py (Unified Access Model) ---

# --- PUBLIC TOOL DEFINITION ---
__all__ = [
    "search_knowledge_base",
    "roll_dice",
    "update_character_from_web",
    "search_dnd_rules",
    "browse_website",
    "lookup_character_data",
    "manage_character_resource",
    "manage_character_status",
]
# --- END OF PUBLIC TOOL DEFINITION ---

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
from typing import Optional, List, Any
import sqlite3
from pathlib import Path
from . import config
import logging

logger = logging.getLogger(__name__)

# --- CONSTANTS ---
DAILY_SEARCH_QUOTA = 10000
PROJECT_ROOT = Path(__file__).parent.parent.resolve()

def manage_character_resource(user_id: str, operation: str, resource_name: Optional[str] = None, value: Optional[int] = None, max_value: Optional[int] = None) -> str:
    """
    Manages a character's resource. Operations: 'set', 'add', 'subtract', 'create', 'view'.
    'create' is used to add a new resource, requires a 'value', and can optionally take a 'max_value'.
    'set' overwrites the current value and can optionally update the max_value.
    'add'/'subtract' modifies the current_value (using 'value') and/or the max_value (using 'max_value').
    'view' returns the current and max value of a specific resource, or all resources if no name is provided.
    """
    logger.info(f"--- RESOURCE MGMT --- User: {user_id}, Resource: {resource_name or 'ALL'}, Op: {operation}, Val: {value}, Max: {max_value}")

    # --- Input Validation ---
    valid_ops = ['set', 'add', 'subtract', 'create', 'view']
    if operation.lower() not in valid_ops:
        return f"Error: Invalid operation '{operation}'. Must be one of {valid_ops}."

    timestamp = datetime.now(timezone.utc).isoformat()

    try:
        with sqlite3.connect(config.DB_FILE) as conn:
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
    logger.info(f"--- STATUS MGMT --- User: {user_id}, Effect: {effect_name or 'ALL'}, Op: {operation}")

    valid_ops = ['add', 'remove', 'update', 'view']
    if operation.lower() not in valid_ops:
        return f"Error: Invalid operation '{operation}'. Must be one of {valid_ops}."

    timestamp = datetime.now(timezone.utc).isoformat()
    return_message = ""
    
    try:
        with sqlite3.connect(config.DB_FILE) as conn:
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
        logger.error(f"ERROR: A database error occurred in manage_character_status: {e}")
        return f"An unexpected database error occurred: {e}"

def roll_dice(dice_notation: str) -> str:
    """
    Rolls one or more dice based on standard D&D notation (e.g., '1d20', '3d6+4, 1d8', '2d8-1 and 1d4').
    Returns a JSON object with a list of individual roll results and a grand total.
    """
    logger.info(f"--- Rolling Dice: {dice_notation} ---")
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
    logger.info(f"--- DB Knowledge Search. Mode: {mode.upper()}. Query: '{query or id}' ---")

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

    from .main_functions import execute_sql_read
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
            logger.error(f"ERROR: Failed to parse full data in search_knowledge_base: {e}")
            return "Error: Could not parse or find the full data entry. The record may be malformed."
    
    return result_json

def update_character_from_web() -> str:
    """
    Downloads the character sheet JSON from D&D Beyond and generates its schema.
    """
    logger.info("--- ACTION: Updating character sheet from D&D Beyond ---")
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
        logger.info(f"--- Performing web search for URLs about: '{query}' (Query {tracker.get('count', 0) + 1}/{DAILY_SEARCH_QUOTA}) ---")
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
    logger.info(f"--- Browsing website: {url} ---")
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
    logger.info(f"--- ACTION: Looking up character data with query: '{query}' ---")
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
