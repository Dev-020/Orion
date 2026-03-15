# 5eTools Local API

Orion's D&D persona now utilizes a **local API** that reads from an embedded 5eTools dataset. This replaces the legacy SQLite-based knowledge base for D&D reference data.

## Features

- **Local Data**: Reads JSON from `data/5eTools/data/`.
- **Cached Loader**: Collections (spells, monsters, items, etc.) are lazy-loaded and cached in memory.
- **Search & Retrieval**: Supports summary searches by name/type/source and full retrieval by unique IDs.
- **Dynamic Discovery**: Automatically discovers searchable types and source books by scanning the 5eTools schema.

## Components

### Backend Implementation (`backends/system_utils/`)
-   **`fivetools_loader.py`**: Normalizes and caches 5eTools JSON files.
-   **`fivetools_search.py`**: Core search logic and schema-driven discovery.

### DND Functions (`backends/main_utils/dnd_functions.py`)
-   **`search_knowledge_base`**: Refactored to act as a proxy for the 5eTools local API.
-   **`list_searchable_types`**: Returns available categories and sources at runtime.

## AI Persona Integration
Orion uses the [DND Search Guide](file:///c:/GitBash/Orion/backends/instructions/DND_Search_Guide.md) to understand the dataset's vocabulary and search workflow.

## Verification
Unit and integration tests are available in `backends/tests/test_fivetools_logic.py`.
```bash
python -m unittest backends/tests/test_fivetools_logic.py
```
