import os
from dotenv import load_dotenv
from google import genai

# Load environment variables
load_dotenv()

def list_available_models():
    """Lists available models from the Google GenAI API."""
    print("--- Listing Available Models ---")
    
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        print("Error: GOOGLE_API_KEY not found in environment.")
        return

    try:
        client = genai.Client(api_key=api_key)
        # Verify the list method signature or return type based on observation
        # usage: client.models.list()
        
        # Pager object, iterate to get models
        for model in client.models.list():
            # filter for gemma or just print all to be safe, but focus on gemma
            if "gemma" in model.name.lower() or "gemini" in model.name.lower():
                print(f"Model: {model.name}")
                print(f"  - Display Name: {model.display_name}")
                # print(f"  - Supported Methods: {model.supported_generation_methods}")
                print("-" * 20)
                
    except Exception as e:
        print(f"An error occurred: {e}")

if __name__ == "__main__":
    list_available_models()
