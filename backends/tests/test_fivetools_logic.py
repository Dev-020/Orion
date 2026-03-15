import unittest
import json
import sys
import os
from pathlib import Path

# Add project root to sys.path to resolve imports correctly
project_root = str(Path(__file__).resolve().parent.parent.parent)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from backends.system_utils.fivetools_loader import loader
from backends.system_utils.fivetools_search import search, get_by_id, list_searchable_types
from backends.main_utils import dnd_functions

class TestFiveToolsLogic(unittest.TestCase):
    def test_loader_spells(self):
        """Verify that the loader can load spells."""
        spells = loader.get_collection("spell")
        self.assertIsInstance(spells, list)
        if spells:
            spell = spells[0]
            self.assertIn("name", spell)
            self.assertIn("source", spell)
            self.assertIn("id", spell)
            self.assertEqual(spell["type"], "spell")

    def test_loader_items(self):
        """Verify that the loader can load items."""
        items = loader.get_collection("item")
        self.assertIsInstance(items, list)
        if items:
            item = items[0]
            self.assertIn("name", item)
            self.assertEqual(item["type"], "item")

    def test_search_by_name(self):
        """Verify searching for anything by name."""
        results = search(query="Fireball", mode="summary")
        self.assertIsInstance(results, list)
        # Should find at least one Fireball related item
        names = [r["name"].lower() for r in results]
        self.assertTrue(any("fireball" in name for name in names))

    def test_search_by_type(self):
        """Verify searching with item_type filter."""
        results = search(query="Aboleth", item_type="bestiary", mode="summary")
        for r in results:
            self.assertEqual(r["type"], "bestiary")

    def test_get_by_id(self):
        """Verify full item retrieval by ID."""
        summary = search(query="Fireball", item_type="spell", mode="summary", max_results=1)
        if summary:
            item_id = summary[0]["id"]
            full_item = get_by_id(item_id)
            self.assertIsNotNone(full_item)
            self.assertEqual(full_item["id"], item_id)
            self.assertIn("entries", full_item)

    def test_list_types(self):
        """Verify that types and sources are discovered from schema."""
        discovery = list_searchable_types()
        self.assertIsInstance(discovery, dict)
        self.assertIn("item_types", discovery)
        self.assertIn("sources", discovery)
        
        types = discovery["item_types"]
        self.assertIn("spell", types)
        # Check against loader map
        for col in loader.collections_map:
            if col != "subclass": # subclass is tricky as it's often in class files
                self.assertIn(col, types)

    def test_dnd_functions_integration(self):
        """Verify that dnd_functions tool works."""
        result_json = dnd_functions.search_knowledge_base(query="Fireball", item_type="spell")
        results = json.loads(result_json)
        self.assertIsInstance(results, list)
        self.assertTrue(len(results) > 0)

if __name__ == "__main__":
    unittest.main()
