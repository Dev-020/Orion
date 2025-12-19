
import subprocess
import time
import threading
import ollama

def run_generation():
    print("Starting generation...")
    try:
        ollama.generate(model='qwen2.5-coder:7b', prompt='Write a very long story about a space adventure to ensure the GPU is active for a while.')
    except Exception as e:
        print(f"Generation error: {e}")

def check_gpu_status():
    print("Checking 'ollama ps'...")
    # Give it a second to start
    time.sleep(2)
    try:
        result = subprocess.run(['ollama', 'ps'], capture_output=True, text=True)
        print("\n--- OLLAMA PS OUTPUT ---")
        print(result.stdout)
        print("------------------------")
        
        if "100% GPU" in result.stdout or "GPU" in result.stdout:
            print("SUCCESS: GPU usage detected.")
        else:
            print("WARNING: GPU usage NOT explicitly detected (check output above).")
            
    except Exception as e:
        print(f"Error running ollama ps: {e}")

if __name__ == "__main__":
    # Start generation in background
    t = threading.Thread(target=run_generation)
    t.start()
    
    # Check status
    check_gpu_status()
    
    # Wait for thread (optional, or just exit)
    t.join(timeout=5)
    print("Test complete.")
