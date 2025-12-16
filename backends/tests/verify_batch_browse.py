import sys
import os

PROJECT_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../'))
sys.path.append(PROJECT_ROOT)
sys.path.append(os.path.join(PROJECT_ROOT, 'backends'))

try:
    from backends.main_utils.main_functions import browse_website
    
    print("--- Testing Single URL ---")
    single_res = browse_website("https://docs.ollama.com/capabilities/web-search")
    print(f"Single Result: {len(single_res)} chars")
    
    print("\n--- Testing Batch URLs ---")
    urls = ["https://docs.ollama.com/capabilities/web-search", "https://google.com"]
    batch_res = browse_website(urls)
    print(f"Batch Result Length: {len(batch_res)} chars")
    print("--- Preview ---")
    print(batch_res[:300])
    
    if "https://docs.ollama.com/capabilities/web-search" in batch_res and "https://google.com" in batch_res:
         print("\nSUCCESS: Both URLs found in output.")
    else:
         print("\nFAILURE: Missing content.")

except Exception as e:
    print(f"Error: {e}")
