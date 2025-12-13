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
from main_utils.orion_logger import setup_logging
import logging

logger = logging.getLogger(__name__)

# --- 1. CONFIGURATION ---
MODEL_PATH = config.DATA_DIR / "piper_models" / "firefly" / "en_US-fireflyv2-medium.onnx"
CONFIG_PATH = config.DATA_DIR / "piper_models" / "firefly" / "en_US-fireflyv2-medium.onnx.json"
LOG_FOLDER = f"{Path(config.PROJECT_ROOT)}/databases/{config.PERSONA}/audio_logs"  # <-- NEW: Folder to save all generated audio
# --- NEW: TTS Queue and Thread Management ---
tts_queue = queue.Queue()
tts_thread = None
stop_event = threading.Event()
interrupt_event = threading.Event() # NEW: For stopping current speech
IS_SPEAKING = False # NEW: Flag to indicate if TTS is currently speaking

# --- 2. VALIDATE FILES & CREATE LOG FOLDER ---
if not os.path.exists(MODEL_PATH) or not os.path.exists(CONFIG_PATH):
    print(f"Error: Model files not found.")
    print(f"Please run this command in your terminal first:")
    print(f"python -m piper.download_voices en_US-lessac-medium")
    exit()

# --- NEW: Create the log folder if it doesn't exist ---
os.makedirs(LOG_FOLDER, exist_ok=True)
logger.info(f"Audio logs will be saved to: {os.path.abspath(LOG_FOLDER)}")
# ---

# --- 3. LOAD THE MODEL (RUNS ONLY ONCE) ---
print("Loading Piper model (this will take a moment)...")
try:
    voice = PiperVoice.load(MODEL_PATH, config_path=CONFIG_PATH, use_cuda=False)
    sample_rate = voice.config.sample_rate
    logger.info(f"Model loaded! Sample rate: {sample_rate} Hz")
    
except Exception as e:
    print(f"Error loading model: {e}")
    exit()

# --- 4. AUDIO DEVICE DETECTION ---
# Automatically detect and use physical headphones (not VB-Cable) for TTS output
TTS_OUTPUT_DEVICE = 23
TTS_OUTPUT_DEVICE_NAME = "VoiceMeeter Input"  # Partial match for Logitech headphones

def _get_physical_audio_device():
    """
    Find the physical audio device (not VB-Cable) for TTS output.
    Returns: (device_id, device_name) tuple or (None, None) if not found
    """
    try:
        devices = sd.query_devices()
        
        for i, device in enumerate(devices):
            device_name = device['name']
            # Look for Logitech headphones with output capability
            if TTS_OUTPUT_DEVICE_NAME in device_name and device['max_output_channels'] > 0:
                # Skip VB-Cable devices
                if "VB-Audio" not in device_name and "CABLE" not in device_name:
                    print(f"[TTS] Using output device: {device_name} (ID: {i})")
                    return i, device_name
        
        # Fallback to default if not found
        default_device = sd.query_devices(kind='output')
        logger.warning(f"[TTS] WARNING: Physical device '{TTS_OUTPUT_DEVICE_NAME}' not found")
        logger.info(f"[TTS] Using default output device: {default_device['name']}")
        return None, default_device['name']
        
    except Exception as e:
        print(f"[TTS] Error detecting audio device: {e}")
        return None, None

# Detect the physical audio device at startup
#TTS_OUTPUT_DEVICE, detected_device_name = _get_physical_audio_device()

# --- 5. NEW: Text Normalization Function ---
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

# --- NEW: Streaming TTS Support ---
_stream_buffer = ""

def process_stream_chunk(text_chunk: str):
    """
    Buffers incoming text chunks and speaks complete sentences.
    """
    global _stream_buffer
    _stream_buffer += text_chunk
    
    # Regex to find sentence boundaries (., !, ?, or newline) followed by a space or end of string
    sentences = re.split(r'(?<=[.!?\n])\s+', _stream_buffer)
    
    if len(sentences) > 1:
        # Speak all complete sentences
        for sentence in sentences[:-1]:
            if sentence.strip():
                speak(sentence)
        
        # Keep the remainder in the buffer
        _stream_buffer = sentences[-1]

def flush_stream():
    """
    Speaks any remaining text in the buffer and signals end of stream.
    """
    global _stream_buffer
    if _stream_buffer.strip():
        speak(_stream_buffer)
    _stream_buffer = ""
    # Signal the TTS thread that the stream is complete
    tts_queue.put(None)

def speak(text: str):
    """Adds text to the TTS queue."""
    if not text:
        return
    normalized_text = _normalize_text_for_speech(text)
    if normalized_text:
        tts_queue.put(normalized_text)

# --- 5. MODIFIED CORE TTS FUNCTION ---
def _process_tts_queue():
    """
    Worker thread function that processes text from the queue and speaks it.
    """
    accumulated_audio_chunks = []  # Accumulates audio across multiple utterances
    stream_start_time = None  # Track when streaming started
    global IS_SPEAKING
    
    while not stop_event.is_set():
        try:
            # Wait for an item to appear in the queue.
            # The timeout allows the thread to check the stop_event periodically.
            text_to_speak = tts_queue.get(timeout=1)
            
            # Check for end-of-stream sentinel
            if text_to_speak is None:
                # Save all accumulated audio to a single file

                if accumulated_audio_chunks and config.SAVE:
                    print("\n>>> Saving consolidated audio file <<<")
                    audio_data_bytes = b"".join(accumulated_audio_chunks)
                    audio_array_int16 = np.frombuffer(audio_data_bytes, dtype=np.int16)
                    audio_tensor_float = torch.tensor(audio_array_int16, dtype=torch.float32) / 32768.0
                    audio_tensor = audio_tensor_float.unsqueeze(0)
                    timestamp = time.strftime("%Y%m%d_%H%M%S")
                    output_filename = os.path.join(LOG_FOLDER, f"{timestamp}.flac")
                    try:
                        torchaudio.save(output_filename, audio_tensor, sample_rate)
                        total_duration = time.time() - stream_start_time if stream_start_time else 0
                        print(f"Audio logged to: {output_filename}")
                        print(f"Total stream duration: {total_duration:.2f}s")
                    except Exception as e:
                        print(f"Error saving log file: {e}")
                    
                # Reset accumulator for next stream
                accumulated_audio_chunks = []
                stream_start_time = None
                
                tts_queue.task_done()
                continue
            
            # Process text utterance
            interrupt_event.clear() # Clear interrupt flag for new utterance

            if False:
                print(f"\n>>> Orion is Speaking <<<")
                print("Generating and streaming speech (on CPU)...")
            
            # Track start time for first utterance in stream
            if stream_start_time is None:
                stream_start_time = time.time()
            
            utterance_start = time.time()
            IS_SPEAKING = True

            # Use physical device (Logitech) instead of default (VB-Cable)
            with sd.RawOutputStream(
                samplerate=sample_rate, 
                channels=1, 
                dtype='int16',
                device=TTS_OUTPUT_DEVICE  # None = default, or specific device ID
            ) as stream:
                first_chunk = True
                for chunk in voice.synthesize(text_to_speak):
                    # Check for interrupt during synthesis
                    if interrupt_event.is_set():
                        print("TTS interrupt event received, halting playback.")
                        stream.abort()
                        break
                    if stop_event.is_set():
                        print("TTS stop event received, halting playback.")
                        break
                    if first_chunk and False:
                        first_chunk_time = time.time() - utterance_start
                        print(f"Time to first audio chunk: {first_chunk_time:.2f}s")
                        first_chunk = False
                    stream.write(chunk.audio_int16_bytes)
                    accumulated_audio_chunks.append(chunk.audio_int16_bytes)

            IS_SPEAKING = False
            utterance_end = time.time()
            if False:
                print(f"Finished streaming utterance. Time: {utterance_end - utterance_start:.2f}s")

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