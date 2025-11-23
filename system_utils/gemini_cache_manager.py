# system_utils/gemini_cache_manager.py
"""
Gemini Context Cache Manager - Standalone Reusable Module

Manages Gemini API context cache lifecycle with:
- Multi-persona support (each persona maintains independent cache)
- Persistent cache storage across script restarts
- Rolling heartbeat TTL updates (30-minute expiry)
- Automatic instruction hash validation
- Graceful 404 handling for expired caches

Cost optimization: Break-even at < 1 request per cache.
"""

import hashlib
import sqlite3
from datetime import datetime, timezone
from typing import Optional
from google import genai
from google.genai import types


class GeminiCacheManager:
    """
    Manages context caching for Gemini API with persistent storage.
    
    Each persona/model combination maintains one active cache that persists
    across script restarts and automatically invalidates when system instructions change.
    """
    
    def __init__(
        self,
        client: genai.Client,
        db_file: str,
        model_name: str,
        system_instructions: str,
        persona: str = "default"
    ):
        """
        Initialize cache manager.
        
        Args:
            client: Initialized genai.Client instance
            db_file: Path to SQLite database for cache metadata persistence
            model_name: Gemini model name (e.g., "gemini-3-pro-preview")
            system_instructions: Full system instruction text to cache
            persona: Persona identifier for multi-persona support
        """
        self.client = client
        self.db_file = db_file
        self.model_name = model_name
        self.system_instructions = system_instructions
        self.persona = persona
        
        # Ensure cache metadata table exists
        self._ensure_cache_table()
        
        print(f"[Cache Manager] Initialized for persona '{persona}', model '{model_name}'")

    
    def _ensure_cache_table(self):
        """Creates cache_metadata table if it doesn't exist."""
        try:
            with sqlite3.connect(self.db_file) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS cache_metadata (
                        persona TEXT NOT NULL,
                        model_name TEXT NOT NULL,
                        cache_name TEXT NOT NULL,
                        instruction_hash TEXT NOT NULL,
                        created_at TEXT NOT NULL,
                        last_updated TEXT NOT NULL,
                        ttl_seconds INTEGER DEFAULT 1800,
                        PRIMARY KEY (persona, model_name)
                    )
                """)
                conn.commit()
                print("[Cache Manager] Database table verified/created")
        except Exception as e:
            print(f"[Cache Manager] ERROR creating table: {e}")
    
    def _compute_instruction_hash(self) -> str:
        """Calculates SHA256 hash of current system instructions."""
        return hashlib.sha256(self.system_instructions.encode('utf-8')).hexdigest()
    
    def _load_cache_from_db(self) -> Optional[tuple[str, str]]:
        """
        Loads cache metadata from database for current persona/model.
        
        Returns:
            Tuple of (cache_name, instruction_hash) if found, None otherwise
        """
        try:
            with sqlite3.connect(self.db_file) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT cache_name, instruction_hash 
                    FROM cache_metadata 
                    WHERE persona = ? AND model_name = ?
                """, (self.persona, self.model_name))
                result = cursor.fetchone()
                return result if result else None
        except Exception as e:
            print(f"[Cache Manager] ERROR loading from DB: {e}")
            return None
    
    def _save_cache_to_db(self, cache_name: str, instruction_hash: str):
        """
        Saves/updates cache metadata in database.
        
        Args:
            cache_name: Gemini cache resource name (e.g., "cachedContents/abc123")
            instruction_hash: SHA256 hash of system instructions
        """
        try:
            timestamp = datetime.now(timezone.utc).isoformat()
            with sqlite3.connect(self.db_file) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT OR REPLACE INTO cache_metadata 
                    (persona, model_name, cache_name, instruction_hash, created_at, last_updated, ttl_seconds)
                    VALUES (?, ?, ?, ?, ?, ?, 1800)
                """, (self.persona, self.model_name, cache_name, instruction_hash, timestamp, timestamp))
                conn.commit()
                print(f"[Cache Manager] Saved cache metadata to DB: {cache_name[:50]}...")
        except Exception as e:
            print(f"[Cache Manager] ERROR saving to DB: {e}")
    
    def _validate_cache(self, cache_name: str) -> bool:
        """
        Validates that cache still exists via Gemini API.
        
        Args:
            cache_name: Cache resource name to validate
            
        Returns:
            True if cache exists, False if 404/expired
        """
        try:
            self.client.caches.get(name=cache_name)
            return True
        except Exception as e:
            error_str = str(e).lower()
            if "404" in error_str or "not found" in error_str:
                print(f"[Cache Manager] Cache expired/not found: {cache_name}")
                return False
            # Re-raise unexpected errors
            print(f"[Cache Manager] Unexpected error validating cache: {e}")
            raise
    
    def _validate_instruction_hash(self, stored_hash: str) -> bool:
        """
        Compares stored instruction hash with current instructions.
        
        Args:
            stored_hash: SHA256 hash from database
            
        Returns:
            True if hashes match, False if instructions changed
        """
        current_hash = self._compute_instruction_hash()
        if stored_hash != current_hash:
            print(f"[Cache Manager] Instruction hash mismatch - instructions changed")
            print(f"  Stored:  {stored_hash[:16]}...")
            print(f"  Current: {current_hash[:16]}...")
            return False
        return True
    
    def _create_new_cache(self) -> types.CachedContent:
        """
        Creates a new cache with 30-minute TTL.
        
        Returns:
            CachedContent object from Gemini API
        """
        print(f"[Cache Manager] Creating new cache for persona '{self.persona}'...")
        
        try:
            cache = self.client.caches.create(
                model=self.model_name,
                config=types.CreateCachedContentConfig(
                    display_name=f"orion_{self.persona}_{self.model_name}",
                    system_instruction=self.system_instructions,
                    # NO TOOLS - they break function calling when cached
                    ttl="1800s"  # 30 minutes
                )
            )
            
            print(f"[Cache Manager] ✓ Cache created: {cache.name}")
            print(f"[Cache Manager] NOTE: Tools excluded from cache (dual-mode architecture)")
            
            # Save to database with current instruction hash
            instruction_hash = self._compute_instruction_hash()
            self._save_cache_to_db(cache.name, instruction_hash)
            
            return cache
            
        except Exception as e:
            print(f"[Cache Manager] ERROR creating cache: {e}")
            raise
    
    def get_or_create_cache(self) -> types.CachedContent:
        """
        Retrieves existing cache or creates new one (Check/Validate/Create pattern).
        
        Performs:
        1. Load cache metadata from database
        2. Validate instruction hash (auto-invalidate if changed)
        3. Validate cache exists via API (handle 404)
        4. Create new cache if validation fails
        
        Returns:
            CachedContent object ready for use in GenerateContentConfig
        """
        # Step 1: Try to load existing cache from database
        cache_data = self._load_cache_from_db()
        
        if cache_data:
            cache_name, stored_hash = cache_data
            print(f"[Cache Manager] Found cached entry: {cache_name[:50]}...")
            
            # Step 2: Validate instruction hash
            if not self._validate_instruction_hash(stored_hash):
                print("[Cache Manager] → Invalidating cache (instructions changed)")
                return self._create_new_cache()
            
            # Step 3: Validate cache still exists via API
            if not self._validate_cache(cache_name):
                print("[Cache Manager] → Recreating cache (expired/404)")
                return self._create_new_cache()
            
            # Cache is valid, retrieve and return it
            print("[Cache Manager] ✓ Reusing existing cache")
            return self.client.caches.get(name=cache_name)
        
        # Step 4: No cache found, create new one
        print("[Cache Manager] No existing cache found")
        return self._create_new_cache()
    
    def update_cache_ttl(self, cache_name: str) -> bool:
        """
        Updates cache TTL to 30 minutes (rolling heartbeat).
        
        Should be called after each successful generation to keep cache alive
        during active usage periods.
        
        Args:
            cache_name: Cache resource name to update
            
        Returns:
            True if successful, False otherwise
        """
        try:
            self.client.caches.update(
                name=cache_name,
                config=types.UpdateCachedContentConfig(ttl="1800s")
            )
            
            # Update last_updated timestamp in database
            timestamp = datetime.now(timezone.utc).isoformat()
            with sqlite3.connect(self.db_file) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    UPDATE cache_metadata 
                    SET last_updated = ? 
                    WHERE persona = ? AND model_name = ?
                """, (timestamp, self.persona, self.model_name))
                conn.commit()
            
            print(f"[Cache Manager] ✓ TTL reset to 30 minutes")
            return True
            
        except Exception as e:
            print(f"[Cache Manager] WARNING: Failed to update TTL: {e}")
            return False
    
    def invalidate_and_recreate(self) -> types.CachedContent:
        """
        Invalidates current cache and creates a new one.
        
        Used when system instructions are hot-swapped via trigger_instruction_refresh().
        
        Returns:
            New CachedContent object
        """
        print("[Cache Manager] Invalidating current cache and recreating...")
        return self._create_new_cache()
