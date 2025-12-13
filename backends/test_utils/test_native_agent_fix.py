import os
from google import genai
from agents.native_tools_agent import NativeToolsAgent
from dotenv import load_dotenv

load_dotenv()

class MockCore:
    def __init__(self):
        self.client = genai.Client(vertexai=True, project=os.getenv("GOOGLE_CLOUD_PROJECT_ID"), location="global")

def test_agent():
    print("--- Testing NativeToolsAgent Fix ---")
    try:
        core = MockCore()
        agent = NativeToolsAgent(core)
        # We'll use a task that requires a search to trigger the citation protocol.
        response = agent.run("What is the latest stable version of Python? Please provide the source link.")
        print("\nSuccess! Agent ran without 'unexpected keyword argument' error.")
        
        if "http" in response:
            print("VERIFICATION PASSED: Response contains a URL.")
        else:
            print("VERIFICATION WARNING: Response does not contain a URL. Check if the model followed instructions.")
            
    except TypeError as e:
        if "unexpected keyword argument 'tools'" in str(e):
            print("\nFAILURE: The 'tools' argument error persists.")
        else:
            print(f"\nError (possibly unrelated): {e}")
    except Exception as e:
        print(f"\nAn error occurred: {e}")

if __name__ == "__main__":
    test_agent()
