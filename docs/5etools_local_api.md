# 5eTools Local API

Orion's D&D persona now utilizes a **local API** that reads from an embedded 5eTools dataset. This replaces the legacy SQLite-based knowledge base for D&D reference data.

## Features

- **Local Data**: Reads JSON from `data/5eTools/data/`.
- **Cached Loader**: Collections (spells, monsters, items, etc.) are lazy-loaded and cached in memory.
- **Search & Retrieval**: Supports summary searches by name/type/source and full retrieval by unique IDs.
- **Fuzzy Search**: Automatically handles typos using `difflib` when exact substring matches fail (e.g., "Firball" -> "Fireball").
- **Semantic Search**: Concept-based search via Orion's Vector DB (ChromaDB). Allows querying by effect or lore (e.g., "a spell that shoots frost").
- **Dynamic Discovery**: Automatically discovers searchable types and source books by scanning the 5eTools schema.
- **Gemini CLI Integration**: D&D tools are exposed as part of the `orion` skill, enabling native tool use for the CLI persona.

## Components

### Backend Implementation (`backends/system_utils/`)
-   **`fivetools_loader.py`**: Normalizes and caches 5eTools JSON files.
-   **`fivetools_search.py`**: Core search logic (exact + fuzzy) and schema-driven discovery.
-   **`embed_5etools.py`**: Manual ingestion script to populate the Vector DB with 5eTools data.
-   **`initialize_database.py`**: Unified tool to create/wipe persona databases with robust schemas.
-   **`refresh_semantic_memory.py`**: Surgical refresh utility to sync conversation/profile data between SQLite and ChromaDB.

### DND Functions (`backends/main_utils/dnd_functions.py`)
-   **`search_knowledge_base`**: Refactored to act as a proxy for the 5eTools local API, routing between direct and semantic searches.
-   **`list_searchable_types`**: Returns available categories and sources at runtime.

## AI Persona Integration
Orion uses the [DND Search Guide](file:///c:/GitBash/Orion/backends/instructions/DND_Search_Guide.md) to understand the dataset's vocabulary and search workflow. The `orion` skill provides the following D&D tools:
- `search_knowledge_base`
- `roll_dice`
- `manage_character_resource`
- `manage_character_status`
- `list_searchable_types`

## Verification
Unit and integration tests are available in `backends/tests/test_fivetools_logic.py`.
```bash
python backends/tests/test_fivetools_logic.py
```

An interactive CLI for testing search is also available:
```bash
python backends/test_utils/dnd_search_cli.py
```
