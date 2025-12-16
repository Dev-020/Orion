import sys
import os

# Add Orion Root and Backends to Path
project_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '../../'))
sys.path.append(project_root)
sys.path.append(os.path.join(project_root, 'backends'))

try:
    from backends.main_utils.main_functions import browse_website, search_web
    
    print("--- Testing RAG Browse ---")
    # This page likely mentions 'Orion' or 'Ollama' or specific terms.
    # Let's search for something specific we know is in documentation.
    url = "https://docs.ollama.com/capabilities/web-search"
    query = "python example"
    
    rag_res = browse_website(url, query=query)
    print(f"RAG Result Length: {len(rag_res)} chars")
    print(rag_res[:500])
    
    if "RAG Filtered Results" in rag_res:
         print("SUCCESS: RAG Filter triggered for Browse.")
    else:
         print("FAILURE: RAG Filter NOT triggered.")

    print("\n--- Testing RAG Search ---")
    s_query = "What is the strongest block in minecraft?"
    search_res = search_web(s_query, smart_filter=True)
    print(f"Search RAG Result Length: {len(search_res)} chars")
    # print(search_res[:500])
    
    if "RAG Filtered Results" in search_res:
         print("SUCCESS: RAG Filter triggered for Search.")
         print(search_res[:500])
    else:
         print("FAILURE: RAG Filter NOT triggered for Search.")
         print(search_res[:500])

except Exception as e:
    print(f"Error: {e}")
