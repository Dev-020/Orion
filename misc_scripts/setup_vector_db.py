import chromadb
import os

# Define the path for the persistent ChromaDB database.
# This will create a directory named 'chroma_db_store' in the project's root directory.
db_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "chroma_db_store")

print(f"Initializing ChromaDB at: {db_path}")

# Create a persistent client. This will save the database to the specified directory.
# If the directory doesn't exist, it will be created.
client = chromadb.PersistentClient(path=db_path)

# Define the name of the collection.
collection_name = "orion_semantic_memory"

try:
    # Create the collection. This is where the vectors and metadata will be stored.
    # The get_or_create_collection method is idempotent:
    # - If the collection doesn't exist, it will be created.
    # - If the collection already exists, it will be retrieved.
    collection = client.get_or_create_collection(name=collection_name)
    
    print(f"Successfully created or retrieved collection: '{collection_name}'")
    print("Vector database setup is complete.")
    
except Exception as e:
    print(f"An error occurred during ChromaDB setup: {e}")

