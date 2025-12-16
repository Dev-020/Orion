import sys
import os

# Adjust path to import backends
PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../'))
sys.path.append(PROJECT_ROOT)
sys.path.append(os.path.join(PROJECT_ROOT, 'backends'))

try:
    from backends.main_utils.main_functions import search_web, browse_website
    
    print("--- Testing search_web ---")
    search_res = search_web("What is the lore of God of War game?", smart_filter=False)
    print(len(search_res))
    
    print("\n--- Testing browse_website (Ollama/Trafilatura) ---")
    # Use a solid URL
    browse_res = browse_website("https://www.example.com")
    print(browse_res[:500]) # Print first 500 chars
    
except ImportError as e:
    print(f"Import Error: {e}")
    print(f"Sys Path: {sys.path}")
except Exception as e:
    print(f"Runtime Error: {e}")
