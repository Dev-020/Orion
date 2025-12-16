import os
import ollama
from dotenv import load_dotenv

# Load key from .env
load_dotenv()

key = os.getenv("OLLAMA_API_KEY")
if key:
    print(f"Key found: {key[:4]}...{key[-4:]}")
else:
    print("Key NOT found in environment.")


# Attempt to use the new beta capabilities
try:
    print("--- Testing Ollama Web Search (Beta) ---")
    
    # Try Explicit Client
    from ollama import Client
    print("Initializing Explicit Client with Headers...")
    client = Client(headers={'Authorization': f'Bearer {key}'})
    
    response = client.web_search(query="What is the latest Dungeons and Dragons movie?")
    
    # Inspect structure
    print(f"Response Type: {type(response)}") 
    print(f"Response: {response}")

    print("\n--- Testing Ollama Web Fetch (Beta) ---")
    # Taking a safe URL to test fetch
    test_url = "https://www.google.com"
    if isinstance(response, dict) and response.get('results'):
        test_url = response['results'][0]['url']
        
    print(f"Fetching: {test_url}")
    fetch_res = client.web_fetch(url=test_url)
    print(f"Fetch Result type: {type(fetch_res)}")
    print(f"Fetch Result: {fetch_res}")

except AttributeError:
    print("Error: 'ollama' module/Client does not have 'web_search' or 'web_fetch'.")
except Exception as e:
    print(f"Error: {e}")
