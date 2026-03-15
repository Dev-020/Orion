# Persona Support & DND Knowledge Base

## Current Persona Support

### How it works today

- **Persona is process-wide.** The active persona is set once at startup, not per request or per session.
- **Backend:** `config.PERSONA` is set when the core initializes. `initialize_persona(persona)` in `main_utils.main_functions` switches database paths to `databases/<persona>/` (SQLite + Chroma).
- **Launcher:** The TUI exposes a `PERSONA` field; saving config writes to the env/config file and restart is required for the server to pick it up.
- **Bots:** Discord and Telegram read `ORION_PERSONA` from the environment (default `"default"`). To run the DND persona on Discord/Telegram, you must start the bot with `ORION_PERSONA=dnd`.
- **Web frontend:** There is **no persona selector**. All web users talk to whichever persona the server was started with.
- **API:** `POST /process_prompt` does **not** accept a `persona` field. Session ID is used for conversation continuity only; the same core (and thus persona) serves all requests.

### Summary: is it “sufficient”?

| Use case | Supported? |
|----------|------------|
| Run “Default” for general use | Yes — set `PERSONA=default` and start server/launcher. |
| Run “DND” for D&D/roleplay | Yes — set `PERSONA=dnd` and start server/launcher (or `ORION_PERSONA=dnd` for bots). |
| Switch persona without restart | No — persona is fixed for the process. |
| Different personas for different users/sessions in one server | No — would require per-request persona and core switching (not implemented). |
| Web UI to choose persona | No — would require API + frontend changes. |

So you **can** run Default and DND as separate setups (e.g. two launcher configs or two processes with different env), but you **cannot** switch between them at runtime on a single server or from the web UI.

---

## DND Persona & Knowledge Base

### Current state

- **`databases/dnd/`** exists and has:
  - `orion_database.sqlite` (~229 MB) with the expected DND tables.
  - Table **`knowledge_base`** exists with columns: `id`, `type`, `name`, `source`, `data` (JSON).
  - **Row count: 0** — the table is empty. The Knowledge Base is not populated.
- **Default persona** (`databases/default/`) does **not** have a `knowledge_base` table (and doesn’t need one for general use).
- **DND tools** in `main_utils.dnd_functions` are already wired for the Knowledge Base:
  - `search_knowledge_base(query, id, item_type, source, data_query, mode, max_results)` — summary (id, name, type, source) or full (data) by `id`.
  - Discord cog `/lookup` calls it; the full/core flow expects data in this table.

### Archived data (restoration source)

Under **`_old_files/_knowledge_base_ARCHIVE/`** you have the original D&D content used to feed the Knowledge Base:

| Category   | Path (under archive) | Description |
|-----------|----------------------|-------------|
| Adventure | `adventure/*.json`   | Many official adventures (LMOP, SKT, etc.) — nested `data[]` with sections. |
| Bestiary  | `bestiary/*.json`   | Monster/bestiary entries. |
| Book      | `book/*.json`       | Book-level reference. |
| Class     | `class/*.json`      | Classes/subclasses. |
| Spells    | `spells/*.json`     | Spell lists (e.g. fluff-spells-*, index). |
| Misc      | `misc/*.json`       | Other reference. |
| Generated | `generated/`        | Generated/derived content. |

Archive JSON shape (e.g. adventure): top-level `data` array; items have `type`, `name`, `id`, `entries`, etc. The DB row shape is: `id`, `type`, `name`, `source`, `data` (full JSON for the item).

---

## Bringing Back the Knowledge Base

### Goal

Repopulate **`databases/dnd/orion_database.sqlite`** table **`knowledge_base`** from `_old_files/_knowledge_base_ARCHIVE/`` so that:

- Orion (with `PERSONA=dnd`) can answer using spells, books, classes, subclasses, monsters, adventures, etc.
- `search_knowledge_base` and `/lookup` return useful results.

### Steps (high level)

1. **Ingestion script** (new or under `backends/system_utils/` or `backends/test_utils/`):
   - Walk `_old_files/_knowledge_base_ARCHIVE/` (adventure, bestiary, book, class, spells, misc; optionally `generated`).
   - For each JSON file:
     - Parse and map to one or more rows: `(id, type, name, source, data)`.
     - `type`: from folder name (e.g. `adventure`, `spells`, `bestiary`, `class`, `book`, `misc`).
     - `source`: from filename or content (e.g. `PHB`, `XGE`, `LMOP`, `MM`).
     - `name`: from first section/filename or content.
     - `id`: stable ID (e.g. slug from path + index, or existing `id` in content).
     - `data`: full JSON for the logical “item” (one row per top-level section or per file, depending on desired granularity).
   - Use `initialize_persona("dnd")` so `config.DB_FILE` points to `databases/dnd/orion_database.sqlite`.
   - Insert rows into `knowledge_base` (batch or one-by-one; consider transactions for speed).
   - Optionally: run Chroma sync for `knowledge_base` (if you use VDB for semantic search on this table) so embeddings stay in sync.

2. **Manifest generation** (already partially there):
   - `generate_manifests.py` has `generate_knowledge_base_manifest(conn, output_dir)` but it is **not** in the `db_generators` list, so it never runs. When running manifests for the **dnd** persona, add this generator so that `knowledge_base_manifest.json` is produced (and any tooling that depends on it works). For **default** persona, skip it if the `knowledge_base` table does not exist (see below).

3. **Optional: VDB sync**
   - If the app expects Chroma entries for `knowledge_base` (e.g. semantic search), run the existing sync/embed flow for the dnd DB after ingestion so the vector store matches the new rows.

4. **Run with DND persona**
   - Start server (or launcher) with `PERSONA=dnd` so the process uses `databases/dnd/` and the repopulated `knowledge_base`. Use `/lookup` and chat to verify.

### Making manifest generation safe for both personas

- In `generate_manifests.main()`, only call `generate_knowledge_base_manifest` if the current DB has a `knowledge_base` table (e.g. check `sqlite_master`). That way:
  - **default** (no table): skip without error.
  - **dnd** (table present): run and produce `knowledge_base_manifest.json`.

---

## Summary

- **Persona switching:** Implemented only at process level (config/env + restart). No per-request or per-session persona; no web UI for it.
- **DND persona:** DB and schema are in place; `search_knowledge_base` and Discord `/lookup` are ready.
- **Knowledge Base:** Table exists for DND but is **empty**. Restore by ingesting from `_old_files/_knowledge_base_ARCHIVE/` into `knowledge_base`, then optionally run manifest generation and VDB sync for the dnd persona.
