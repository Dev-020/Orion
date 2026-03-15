# 5eTools Local API — Implementation Plan

## Goal

Provide Orion’s DND persona with a **local API** that reads from the embedded 5eTools dataset (`data/5eTools/data/`) and schema (`data/5eTools/utils/schema/`), so the AI can search and retrieve D&D reference data (spells, items, bestiary, classes, feats, etc.) without depending on an external server or the legacy SQLite `knowledge_base` table.

---

## Scope

- **In scope:** (1) Refactoring `search_knowledge_base` in `dnd_functions.py` so it uses a new 5eTools data layer (loader + search) instead of SQLite. (2) A Python data layer that loads 5eTools JSON from `data/5eTools/data/`, optionally validates with the schema under `data/5eTools/utils/`, and exposes search/lookup with the same contract (summary + full by id, filter by type/source/query). (3) **Model instructions and discovery:** a DND Search Guide (glossary of item_type/source, workflow, examples) and an expanded tool docstring so the model knows what and how to search even without prior D&D knowledge; optional `list_searchable_types()` for runtime discovery.
- **Out of scope (for this plan):** Serving the 5eTools website, character-sheet integration, or a separate HTTP service; refresh/sync automation from upstream 5etools-src (can be a follow-up).

---

## Directory Layout (Current)

- **`data/5eTools/data/`** — Local copy of 5eTools JSON:
  - `spells/` (index.json + per-source files)
  - `class/`
  - `adventure/`, `bestiary/`, `book/`
  - `generated/`
  - Root files as needed: e.g. `feats.json`, `races.json`, `backgrounds.json`, `items.json`, `items-base.json`, etc., if copied.
- **`data/5eTools/utils/`** — Renamed 5etools-utils repo:
  - `schema/site/` — Primary JSON schemas for site data (spells, bestiary, class, etc.).
  - `schema/ua/`, `schema/brew/` — Optional for validation if needed.

Orion’s backend runs from `backends/`; paths to 5eTools should be resolved from the project root (e.g. `PROJECT_ROOT / "data" / "5eTools"`).

---

## Proposed Architecture

### 1. Config and paths

- **Location:** `backends/main_utils/config.py` (or a small `backends/5etools_config.py`).
- **Add:**
  - `FIVETOOLS_DATA_DIR = PROJECT_ROOT / "data" / "5eTools" / "data"`
  - `FIVETOOLS_SCHEMA_DIR = PROJECT_ROOT / "data" / "5eTools" / "utils" / "schema" / "site"`
- Optionally an env or config flag to enable/disable 5eTools local API (e.g. if the directory is missing).

### 2. Loader module

- **New module:** `backends/data_utils/5etools_loader.py` (or `backends/5etools/loader.py`).
- **Responsibilities:**
  - Discover and load JSON files from `FIVETOOLS_DATA_DIR` according to a fixed map (e.g. spells from `spells/` + index, class from `class/*.json`, bestiary from `bestiary/*.json`, etc.).
  - Normalize into a small set of “collections” (e.g. `spells`, `classes`, `feats`, `items`, `bestiary`, `adventures`, …) so the rest of the API doesn’t care about file layout.
  - Expose a simple in-memory structure (e.g. dict of list of dicts keyed by type, or a flat list with `type`/`source`/`name`/`id` for indexing).
- **Lazy vs eager:** Prefer lazy loading per collection on first use to avoid startup cost; optional “warm-up” at first DND request or at server startup.
- **Caching:** Keep loaded data in memory for the process lifetime; no DB write. Reload only on explicit refresh or server restart.

### 3. Schema validation (optional but recommended)

- **Location:** Same loader or a separate `backends/data_utils/5etools_validate.py`.
- **Approach:** Use Python `jsonschema` (or equivalent) to validate loaded JSON against the relevant schema files under `FIVETOOLS_SCHEMA_DIR` (and any `$ref` targets in `utils/schema/`).
- **When:** During load (or in a one-off “validate” script). On validation failure: log and either skip the file or fail the load, depending on policy.
- **Scope:** Start with the entity types Orion actually uses (e.g. spells, items, bestiary, class); add others as needed.

### 4. Search / lookup API (Python, in-process)

- **New module:** `backends/data_utils/5etools_search.py` (or `backends/5etools/search.py`).
- **Public interface (conceptually):**
  - **`search(query=None, item_type=None, source=None, mode='summary', max_results=25)`**  
    - `query`: optional substring match on `name` (and optionally other fields).
    - `item_type`: filter by type (e.g. `spell`, `item`, `monster`, `class`, `feat`).
    - `source`: filter by source (e.g. `PHB`, `XGE`).
    - `mode`: `summary` → list of `{ id, name, type, source }`; `full` not used without `id`.
  - **`get_by_id(id)`**  
    - Returns full document for a single id (for “full” mode).
- **Implementation (v1):**
  - Use the loader’s in-memory collections; iterate and filter by `name` (substring), `type`, `source`.
  - Assign or use existing stable `id` per entity (e.g. slug from name+source, or 5eTools’ own id if present).
  - Return JSON-serializable dicts/lists so the caller can `json.dumps` as today.
- **Implementation (later):** Add full-text search over `entries` or key fields (e.g. whoosh, or a simple inverted index) if needed for “search anything” quality.

### 5. Refactor `search_knowledge_base` as the local API

- **Current behavior:** `backends/main_utils/dnd_functions.py` defines `search_knowledge_base(query, id, item_type, source, data_query, mode, max_results)` and uses the SQLite `knowledge_base` table (currently empty for DND).
- **Target behavior:** **Fully refactor** the implementation of `search_knowledge_base` in `dnd_functions.py` so that it:
  - Calls the new 5eTools loader/search layer (from `data_utils/5etools_loader.py` and `5etools_search.py`) when the 5eTools data directory is present.
  - Keeps the **same public signature and return shape**: summary = list of `{ id, name, type, source }`; full = single full document by `id`. No new function name; existing callers (Discord `/lookup`, core, GEMINI.md instructions) remain unchanged.
- **Fallback:** If the 5eTools data directory is missing or the loader fails, return a clear error (e.g. “5eTools data not configured. Ensure data/5eTools/data/ is populated.”) rather than falling back to SQLite. The SQLite `knowledge_base` table is deprecated for DND; no dual-path routing.

### 6. ID and type mapping

- 5eTools files use varying structures (e.g. spells in `spell` array with `name`, `source`; bestiary by file; class by file). The loader must:
  - Define a **unified id** (e.g. `f"{type}_{name}_{source}"` or use existing `id` field when present).
  - Map **item_type** from caller (e.g. `spell`, `feat`, `monster`) to the right collection and, if needed, to 5eTools file roles (e.g. optionalfeatures vs feats).
- Document the supported `item_type` and `source` values (and optionally expose a small “list types / list sources” helper for the AI or UI).

---

## 7. How Orion (the model) knows what and how to search

The model powering Orion may have little or no built-in knowledge of D&D 5e: it may not know that “Fireball” is a spell, what “fluff” means, or that `item_type` can be `bestiary` vs `spell` vs `feat`. To make search effective, Orion must receive **explicit instructions and a discoverable vocabulary** for the D&D dataset.

### 7.1 Problem

- Without guidance, the model might call `search_knowledge_base(query='fireball')` and get results, but not know to add `item_type='spell'` to narrow results or to use `source='PHB'` when the user asks for “the PHB version.”
- It may not know that “monsters” are under `item_type='bestiary'`, that “subclasses” are a type, or that “fluff” refers to descriptive/lore text (often in separate fluff entries) rather than rules.
- So: **we must teach the model the vocabulary and workflow** via system instructions and, optionally, a discovery tool.

### 7.2 D&D search glossary (injected into model context)

When the DND persona is active, the model must have access to a **D&D search glossary** that defines:

- **Valid `item_type` values** and what they mean, e.g.:
  - `spell` — Spells (level, school, casting time, etc.). Use for “Fireball,” “Counterspell,” etc.
  - `feat` — Feats and character options (e.g. Ability Score Improvement, War Caster).
  - `optionalfeature` — Optional class features (e.g. Fighting Styles, Metamagic, Invocations).
  - `class` — Classes (e.g. Wizard, Fighter). Use for class features and progression.
  - `subclass` — Subclasses (e.g. Evoker, Champion). Often nested under class.
  - `race` — Races and lineage.
  - `background` — Backgrounds (e.g. Sage, Soldier).
  - `item` — Magic items and equipment.
  - `bestiary` — Monsters and creatures. Use for “Aboleth,” “Mind Flayer,” etc.
  - `adventure` — Adventure modules and encounters.
  - `book` — Sourcebooks and reference books.
  - `fluff` — Descriptive or lore-only content (no rules). Use when the user asks for flavor text or “what’s the lore of X.”
- **Common `source` codes** (so the model can narrow by book when useful): e.g. `PHB`, `XGE`, `TCE`, `MM`, `DMG`, `VGM`, etc. Optionally list these in the glossary or expose via a helper.
- **Spell-specific hints:** For spells, the model can use `query` for the spell name; adding `item_type='spell'` improves precision. Level or school can be mentioned in the glossary if the search API supports filtering by them later.

This glossary should live in a **single reference document** (e.g. a DND-specific instruction file or a dedicated “DND Search Guide” section) that is included in the system prompt or loaded context when the DND persona is active (e.g. via GEMINI.md, Primary_Directive, or a DND_Handout that is already referenced in the project).

### 7.3 Workflow instructions for the model

- **When the user asks about something by name (e.g. “Do you have anything on Fireball?”):**
  - Prefer a **targeted search**: if the user’s intent is clearly a spell, use `item_type='spell'`; if a monster, use `item_type='bestiary'`; if a feat, use `item_type='feat'`. Use `query` for the name (e.g. `query='Fireball'`).
  - If the intent is ambiguous, start with a **broader search** (e.g. `query='Fireball'` without `item_type`) to see what types match, then refine (e.g. call again with `item_type='spell'` for the spell entry).
- **Two-step workflow:** First call in `mode='summary'` to get a list of matching ids/names/types/sources; then call with `id='...'` and `mode='full'` to retrieve the full document for the chosen entry.
- **Examples** to include in the instructions:
  - “User asks about the Fireball spell” → `search_knowledge_base(query='Fireball', item_type='spell', mode='summary')`, then get full by `id`.
  - “User asks about the Mind Flayer” → `search_knowledge_base(query='Mind Flayer', item_type='bestiary', mode='summary')`, then get full by `id`.
  - “User asks what fluff exists for elves” → `search_knowledge_base(query='elf', item_type='fluff', mode='summary')` (or equivalent if fluff is a separate type).

### 7.4 Rich tool description (docstring and schema)

- The **Python docstring** for `search_knowledge_base` in `dnd_functions.py` should be expanded so that the **tool schema** (e.g. generated for the model’s function-calling API) includes:
  - A short summary of the tool’s purpose (search the local D&D 5e dataset).
  - The meaning of each parameter: `query` (substring on name/title), `id` (exact id for full retrieval), `item_type` (see glossary: spell, feat, bestiary, class, …), `source` (sourcebook code), `mode` (summary vs full), `max_results`.
  - A one-line pointer: “For valid item_type and source values, see the DND Search Guide in your instructions.”
- This ensures that even if the model only sees the tool signature and description, it still gets the minimal vocabulary (parameter meanings) and a pointer to the full glossary.

### 7.5 Optional: discovery tool

- **`list_searchable_types()`** (or **`list_5etools_types()`**): A small tool that returns the list of **valid `item_type`** values and, optionally, a short description for each (e.g. “spell: Spells from sourcebooks”; “bestiary: Monsters and creatures”). Optionally also return **valid `source`** codes if we want the model to discover them at runtime.
- **When to use:** The model can call this when the user’s request is vague (e.g. “What D&D content do you have?”) or when it is unsure which `item_type` to use. It is not required for every search; the glossary in the instructions should be enough for most queries (e.g. “Fireball” → spell, “Mind Flayer” → bestiary).
- **Implementation:** The tool can read from a small static JSON or Python dict (derived from the loader’s known collections) so it stays in sync with what the search API actually supports.

### 7.6 Where to put the glossary and workflow

- **Option A (recommended):** Add or extend a **DND-specific instruction file** that is loaded when the DND persona is active (e.g. `backends/instructions/DND_Search_Guide.md` or a section in `DND_Handout.md` if it exists). That file contains the glossary (item_type, source), workflow (summary → full, when to add item_type), and examples. Ensure this file is included in the context that builds the system prompt for the DND persona (e.g. via the same mechanism that loads GEMINI.md or Primary_Directive).
- **Option B:** Extend **GEMINI.md** (or the equivalent “Project Overview” that the model sees) so that the existing “3.1 [Knowledge Base]” and the tool block for `search_knowledge_base` are updated with the full glossary and examples. That keeps everything in one place but may make GEMINI.md long; a dedicated DND Search Guide is easier to maintain.
- **Option C:** Both: a short reminder and one example in the main instructions, plus a dedicated DND Search Guide that is injected only for the DND persona.

---

## File and Module Summary

| Item | Path / location |
|------|------------------|
| Config | `config.py`: `FIVETOOLS_DATA_DIR`, `FIVETOOLS_SCHEMA_DIR` (and optional feature flag). |
| Loader | `backends/data_utils/5etools_loader.py` — load and normalize 5eTools JSON from `data/5eTools/data/`. |
| Validation | `backends/data_utils/5etools_validate.py` or inside loader — validate with `data/5eTools/utils/schema/`. |
| Search | `backends/data_utils/5etools_search.py` — search/lookup API using loader output. |
| Integration | `backends/main_utils/dnd_functions.py` — **refactor** `search_knowledge_base` so its implementation calls the 5eTools search layer; same signature and return shape. |
| Glossary / instructions | DND Search Guide (e.g. `backends/instructions/DND_Search_Guide.md` or section in `DND_Handout.md`) — item_type and source glossary, workflow, examples. Injected when DND persona is active. |
| Tool docstring | `dnd_functions.search_knowledge_base` — expanded docstring for tool schema (parameter meanings, pointer to DND Search Guide). |
| Optional discovery | `dnd_functions.list_searchable_types()` — returns valid item_type (and optionally source) for runtime discovery. |
| Package | Ensure `backends/data_utils/` (or `backends/5etools/`) is a package and importable from `main_utils`. |

---

## Dependencies

- **Python:** Use only stdlib + existing Orion deps where possible. For schema validation add **`jsonschema`** (or keep validation optional and skip if not installed).
- No new HTTP server or external service; all runs inside the Orion backend process.

---

## Verification

1. **Unit tests:** Load from `data/5eTools/data/` with a few sample files; run search by name/type/source and get_by_id; assert summary and full shapes.
2. **Integration:** With DND persona and 5eTools data present, trigger a lookup (e.g. Discord `/lookup` or equivalent) and confirm results come from 5eTools data.
3. **Missing data:** If `data/5eTools/data/` is missing or empty, return a clear “5eTools data not configured” (or similar) message from `search_knowledge_base`.
4. **Model instructions:** Confirm that when DND persona is active, the DND Search Guide (or equivalent) is included in the context so the model receives the glossary and examples; optionally verify that a prompt like “Do you have anything on Fireball?” leads to a call with `item_type='spell'` (or a follow-up refinement).

---

## Future Work

- **Refresh script:** Script or doc to update `data/5eTools/data/` (and optionally `utils/`) from upstream 5etools-src (and 5etools-utils).
- **Full-text / universal search:** Improve search over `entries` and other long text (e.g. whoosh or minimal in-memory index) so “search anything” feels like Omnisearch.
- **Optional HTTP:** Expose the same search/lookup as FastAPI routes under the existing server (e.g. `/dnd/5etools/search`) for debugging or future reuse.

---

## Summary

1. **Refactor:** `search_knowledge_base` in `dnd_functions.py` is **refactored in place** to use a new 5eTools data layer (loader + search) reading from `data/5eTools/data/`. Same function name, signature, and return shape; no new tool or routing. SQLite `knowledge_base` is not used for DND.
2. **Local API:** Loader and search modules under `backends/data_utils/` (or `backends/5etools/`) load and index 5eTools JSON, with optional schema validation via `data/5eTools/utils/schema/`. No separate server or repo.
3. **Model instructions:** Because the AI may not know D&D terminology (spells, bestiary, feats, fluff, source codes), a **DND Search Guide** (glossary of `item_type` and `source`, workflow, and examples) is added to the instructions loaded when the DND persona is active. The `search_knowledge_base` docstring is expanded for the tool schema, and an optional **list_searchable_types()** tool can expose valid types/sources at runtime. This ensures Orion knows **what** to search and **how** to form effective queries (e.g. Fireball → `query='Fireball', item_type='spell'`).
