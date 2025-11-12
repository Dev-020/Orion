import time
import os
import sounddevice as sd
import numpy as np
import torchaudio
import torch
import sys
import threading
import re
import queue
from piper.voice import PiperVoice
from pathlib import Path

sys.path.append(str(Path(__file__).resolve().parent.parent))
from main_utils import config

# --- 1. CONFIGURATION ---
MODEL_PATH = Path(config.PROJECT_ROOT) / "data" / "piper_models" / "firefly" / "en_US-firefly-medium.onnx"
CONFIG_PATH = Path(config.PROJECT_ROOT) / "data" / "piper_models" / "firefly" / "en_US-firefly-medium.onnx.json"
LOG_FOLDER = f"{Path(config.PROJECT_ROOT)}/databases/{config.PERSONA}/audio_logs"  # <-- NEW: Folder to save all generated audio
# --- NEW: TTS Queue and Thread Management ---
tts_queue = queue.Queue()
tts_thread = None
stop_event = threading.Event()
interrupt_event = threading.Event() # NEW: For stopping current speech
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

# --- 4. NEW: Text Normalization Function ---
def _normalize_text_for_speech(text: str) -> str:
    """
    Cleans and normalizes text to make it more suitable for TTS.
    - Removes markdown formatting (*, _, #, etc.).
    - Strips out system messages in square brackets.
    - Collapses whitespace.
    """
    if not text:
        return ""

    # 1. Remove markdown emphasis (asterisks, underscores)
    text = re.sub(r'(\*|_){1,3}', '', text)

    # 2. Remove markdown headings (e.g., #, ##)
    text = re.sub(r'^\s*#+\s*', '', text, flags=re.MULTILINE)

    # 3. Remove system-generated metadata in square brackets (e.g., [System Note: ...])
    text = re.sub(r'\[.*?\]', '', text)

    # 4. Collapse multiple spaces and newlines into a single space
    text = re.sub(r'\s+', ' ', text).strip()

    return text

# --- 5. MODIFIED CORE TTS FUNCTION ---
def speak(text: str):
    """
    Public function to add text to the TTS queue.
    This is what other modules will call.
    """
    # --- MODIFICATION: Normalize the text before queueing ---
    normalized_text = _normalize_text_for_speech(text)
    if normalized_text:
        tts_queue.put(normalized_text)

def _process_tts_queue():
    """
    Generates audio from text, streams it to the default speaker,
    and saves a copy to the audio_logs folder.
    """
    while not stop_event.is_set():
        try:
            # Wait for an item to appear in the queue.
            # The timeout allows the thread to check the stop_event periodically.
            text_to_speak = tts_queue.get(timeout=1)
            interrupt_event.clear() # NEW: Clear interrupt flag for new utterance

            print(f"\n>>> Speaking: '{text_to_speak}'")
            print("Generating and streaming speech (on CPU)...")
            start_time = time.time()

            audio_chunks_for_saving = []

            with sd.RawOutputStream(samplerate=sample_rate, channels=1, dtype='int16') as stream:
                first_chunk = True
                for chunk in voice.synthesize(text_to_speak):
                    # NEW: Check for interrupt during synthesis
                    if interrupt_event.is_set():
                        print("TTS interrupt event received, halting playback.")
                        stream.abort()
                        break
                    if stop_event.is_set():
                        print("TTS stop event received, halting playback.")
                        break
                    if first_chunk:
                        first_chunk_time = time.time() - start_time
                        print(f"Time to first audio chunk: {first_chunk_time:.2f}s")
                        first_chunk = False
                    stream.write(chunk.audio_int16_bytes)
                    audio_chunks_for_saving.append(chunk.audio_int16_bytes)

            end_time = time.time() # This line might not be reached if interrupted
            print(f"Finished streaming. Total time: {end_time - start_time:.2f}s")

            # --- Save the collected chunks to a .flac file ---
            if audio_chunks_for_saving and not stop_event.is_set():
                audio_data_bytes = b"".join(audio_chunks_for_saving)
                audio_array_int16 = np.frombuffer(audio_data_bytes, dtype=np.int16)
                audio_tensor_float = torch.tensor(audio_array_int16, dtype=torch.float32) / 32768.0
                audio_tensor = audio_tensor_float.unsqueeze(0)
                timestamp = time.strftime("%Y%m%d_%H%M%S")
                output_filename = os.path.join(LOG_FOLDER, f"{timestamp}.flac")
                try:
                    torchaudio.save(output_filename, audio_tensor, sample_rate)
                    print(f"Audio logged to: {output_filename}")
                except Exception as e:
                    print(f"Error saving log file: {e}")

            tts_queue.task_done()

        except queue.Empty:
            # This is expected when the queue is empty and timeout is reached.
            # It allows the loop to check stop_event.
            continue

# --- 6. NEW: Thread Start/Stop Functions ---
def start_tts_thread():
    """Starts the TTS processing thread."""
    global tts_thread
    if tts_thread is None or not tts_thread.is_alive():
        stop_event.clear()
        tts_thread = threading.Thread(target=_process_tts_queue, daemon=True)
        tts_thread.start()
        print("--- TTS processing thread started. ---")

def stop_speech():
    """
    NEW: Stops the currently playing speech and clears the queue.
    """
    print("--- Interrupting TTS and clearing queue... ---")
    # 1. Set the interrupt event to stop the current utterance
    interrupt_event.set()

    # 2. Clear any pending items in the queue
    with tts_queue.mutex:
        tts_queue.queue.clear()

    print("--- TTS interrupt complete. ---")

def stop_tts_thread():
    """Stops the TTS processing thread gracefully."""
    global tts_thread
    if tts_thread and tts_thread.is_alive():
        print("--- Stopping TTS processing thread... ---")
        stop_event.set()
        # Clear the queue to prevent the thread from blocking on shutdown
        while not tts_queue.empty():
            try:
                tts_queue.get_nowait()
            except queue.Empty:
                continue
        tts_thread.join(timeout=2) # Wait for the thread to finish
        tts_thread = None
        print("--- TTS processing thread stopped. ---")

# --- 7. TEST BLOCK ---
if __name__ == '__main__':
    start_tts_thread() # Start the consumer thread
    print("\n--- Piper TTS Ready! (Interactive Test Mode) ---")
    try:
        while True:
            text_to_speak = input("\nEnter text to speak (or 'q' to quit): ")
            if text_to_speak.lower() == 'q':
                break
            speak(text_to_speak) # Add text to the queue

    except KeyboardInterrupt:
        print("\nExiting...")
    finally:
        stop_tts_thread() # Stop the consumer thread
    print("Script finished.")