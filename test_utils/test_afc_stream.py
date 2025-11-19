import os
import asyncio
from google import genai
from google.genai import types
from dotenv import load_dotenv

load_dotenv()

def test_tool():
    """A simple tool to list files."""
    print("--- [TOOL] test_tool executed! ---")
    return "file1.txt, file2.txt"

tools = [test_tool]

client = genai.Client(vertexai=True, project=os.getenv("GEMINI_PROJECT_ID"), location="global")

def run_stream_test(enable_afc: bool):
    print(f"\n\n=== Testing with automatic_function_calling={enable_afc} ===")

    # We need to construct the config object carefully
    # If automatic_function_calling is not a valid kwarg for GenerateContentConfig constructor in this version,
    # we might need to set it differently.
    # Let's try passing it as a dict if the object rejects it, but inspection showed 'automatic_function_calling' field.
    
    try:

        content_list = ["Call the test_tool function.", "Say 1 - 5 slowly."]
        # Test the stream
        for content in content_list:
            response_stream = client.models.generate_content_stream(
                model="gemini-3-pro-preview",
                contents=content,
                config=types.GenerateContentConfig(
                    tools=tools
                ),
            )

            print("--- Stream Start ---")
            last_chunk = None
            for chunk in response_stream:
                # Print what we receive
                last_chunk = chunk
                if chunk.candidates:
                    for part in chunk.candidates[0].content.parts:
                        if part.function_call:
                            print(f"CHUNK: Function Call -> {part.function_call.name}")
                        if part.text:
                            print(f"CHUNK: Text -> {part.text.strip()}")
                else:
                    print(f"CHUNK: No candidates (Usage/Other) -> {chunk}")
            print("--- Stream End ---")
            print(last_chunk.automatic_function_calling_history)

    except Exception as e:
        print(f"ERROR: {e}")

if __name__ == "__main__":
    print("Running reproduction tests...")
    # Test 1: AFC Enabled (Default behavior)
    run_stream_test(enable_afc=True)
    
    # Test 2: AFC Disabled
    #run_stream_test(enable_afc=False)
