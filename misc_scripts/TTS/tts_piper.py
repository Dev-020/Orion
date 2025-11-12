import time
import os
import sounddevice as sd
from piper.voice import PiperVoice
import numpy as np      # <-- Added for data conversion
import torchaudio       # <-- Added for saving .flac
import torch            # <-- Added for tensor operations

# --- 1. CONFIGURATION ---
MODEL_PATH = "piper_model/firefly/en_US-firefly-medium.onnx"
CONFIG_PATH = "piper_model/firefly/en_US-firefly-medium.onnx.json"
LOG_FOLDER = "audio_logs"  # <-- NEW: Folder to save all generated audio

# --- 2. VALIDATE FILES & CREATE LOG FOLDER ---
if not os.path.exists(MODEL_PATH) or not os.path.exists(CONFIG_PATH):
    print(f"Error: Model files not found.")
    print(f"Please run this command in your terminal first:")
    print(f"python -m piper.download_voices en_US-lessac-medium")
    exit()

# --- NEW: Create the log folder if it doesn't exist ---
os.makedirs(LOG_FOLDER, exist_ok=True)
print(f"Audio logs will be saved to: {os.path.abspath(LOG_FOLDER)}")
# ---

# --- 3. LOAD THE MODEL (RUNS ONLY ONCE) ---
print("Loading Piper model (this will take a moment)...")
try:
    voice = PiperVoice.load(MODEL_PATH, config_path=CONFIG_PATH, use_cuda=False)
    sample_rate = voice.config.sample_rate
    print(f"Model loaded! Sample rate: {sample_rate} Hz")
    
except Exception as e:
    print(f"Error loading model: {e}")
    exit()

# --- 4. CORE TTS FUNCTION ---
def speak(text_to_speak: str):
    """
    Generates audio from text, streams it to the default speaker,
    and saves a copy to the audio_logs folder.
    """
    if not text_to_speak or not text_to_speak.strip():
        print("No text provided to speak.")
        return

    print(f"\n>>> Speaking: '{text_to_speak}'")
    print("Generating and streaming speech (on CPU)...")
    start_time = time.time() # Start timer

    # --- NEW: List to collect chunks for saving ---
    audio_chunks_for_saving = []
    # ---

    with sd.RawOutputStream(samplerate=sample_rate, 
                            channels=1, 
                            dtype='int16') as stream:
        
        first_chunk = True
        
        for chunk in voice.synthesize(text_to_speak):
            
            if first_chunk:
                first_chunk_time = time.time() - start_time
                print(f"Time to first audio chunk: {first_chunk_time:.2f}s")
                first_chunk = False
            
            # 1. Stream the raw audio bytes directly to the speaker
            stream.write(chunk.audio_int16_bytes)
            
            # --- NEW: Save the chunk for logging ---
            audio_chunks_for_saving.append(chunk.audio_int16_bytes)
            # ---
    
    end_time = time.time()
    print(f"Finished streaming. Total time: {end_time - start_time:.2f}s")

    # --- NEW: Save the collected chunks to a .flac file ---
    if audio_chunks_for_saving:
        # 1. Join all byte chunks into one
        audio_data_bytes = b"".join(audio_chunks_for_saving)
        
        # 2. Convert raw bytes (int16) to a numpy array
        audio_array_int16 = np.frombuffer(audio_data_bytes, dtype=np.int16)
        
        # 3. Convert numpy array to a float tensor (required by torchaudio)
        # We normalize the audio from -32768/32767 to -1.0/1.0
        audio_tensor_float = torch.tensor(audio_array_int16, dtype=torch.float32) / 32768.0
        
        # 4. Add a channel dimension (required by torchaudio.save)
        audio_tensor = audio_tensor_float.unsqueeze(0)
        
        # 5. Create a timestamped filename
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        output_filename = os.path.join(LOG_FOLDER, f"{timestamp}.flac")
        
        # 6. Save as .flac
        try:
            torchaudio.save(output_filename, audio_tensor, sample_rate)
            print(f"Audio logged to: {output_filename}")
        except Exception as e:
            print(f"Error saving log file: {e}")

# --- 5. TEST BLOCK ---
if __name__ == '__main__':
    print("\n--- Piper TTS Ready! (Interactive Test Mode) ---")
    try:
        while True:
            text_to_speak = input("\nEnter text to speak (or 'q' to quit): ")
            if text_to_speak.lower() == 'q':
                break
            speak(text_to_speak)

    except KeyboardInterrupt:
        print("\nExiting...")

    print("Script finished.")