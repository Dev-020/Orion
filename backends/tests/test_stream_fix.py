from typing import Generator
import time

# Mocking the generator logic from orion_core_lite
def mock_stream_generator() -> Generator:
    # Simulate first pass: Tool Call (normally handled)
    # ... skipped for this test ...
    
    # Simulate second pass: Model thinks the answer but puts it in thought block
    thought_content = "The answer is T1 won the 2025 Worlds."
    
    print(f"--- Simulating Model Stream ---")
    # Yield thought
    yield {"type": "thought", "content": thought_content}
    
    # Yield NO content tokens
    # ...
    
    yield {"type": "done"}

def consume_stream():
    full_response_text = ""
    for chunk in mock_stream_generator():
        print(f"Received: {chunk}")
        if chunk["type"] == "token":
            full_response_text += chunk["content"]
            
    print(f"\nFinal Content Text: '{full_response_text}'")
    if not full_response_text:
        print("FAIL: No content text extracted.")
    else:
        print("SUCCESS: Content text extracted.")

if __name__ == "__main__":
    consume_stream()
