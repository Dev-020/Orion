import torch
from TTS.api import TTS
import os
import time
import glob
import subprocess
import re  # For splitting sentences
import threading
import queue
import torchaudio

# --- 1. CONFIGURATION ---
VOICE_FOLDER = "audio_samples/audio"
TEMP_FILE_PREFIX = "_temp_audio"

# --- 2. SETUP QUEUES ---
# Queue for text sentences to be generated
text_queue = queue.Queue()
# Queue for audio filenames to be played
audio_queue = queue.Queue()

# --- 3. AUDIO PLAYER (Modified to be BLOCKING) ---
def play_audio_ffmpeg_blocking(filename):
    """
    Plays an audio file using ffplay.
    This version is BLOCKING and will wait for the audio to finish.
    """
    if not os.path.exists(filename):
        print(f"Error: Audio file not found: {filename}")
        return
    try:
        # Use subprocess.run() to make the call blocking
        subprocess.run(
            ["ffplay", "-nodisp", "-autoexit", "-hide_banner", filename],
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
    except FileNotFoundError:
        print("Error: 'ffplay' command not found.")
    except Exception as e:
        print(f"Error playing audio: {e}")

# --- 4. WORKER THREAD FUNCTIONS ---

def generator_thread(tts_object, voice_samples_list):
    """
    THE "CHEF" THREAD
    Waits for a sentence from the text_queue, generates audio,
    and puts the filename into the audio_queue.
    """
    file_counter = 0
    while True:
        sentence = text_queue.get()
        if sentence is None:
            break
            
        print(f"[Generator] Cooking sentence: '{sentence}'...")
        start_time = time.time()
        
        output_filename = f"{TEMP_FILE_PREFIX}_{file_counter}.wav"
        file_counter += 1

        try:
            # --- THIS IS THE CORRECTED CODE ---
            # Use the high-level tts_to_file method.
            # It will automatically cache the speaker latents after the first run.
            tts_object.tts_to_file(
                text=sentence,
                file_path=output_filename,
                speaker_wav=voice_samples_list, # Pass the full list
                language="en",
                split_sentences=True
            )
            # --- END OF CORRECTION ---

            end_time = time.time()
            print(f"[Generator] Finished in {end_time - start_time:.2f}s. Adding to play queue.")
            
            audio_queue.put(output_filename)

        except Exception as e:
            print(f"[Generator] ERROR: {e}")
        
        finally:
            # Make sure to signal that the task is done
            text_queue.task_done()

def player_thread():
    """
    THE "WAITER" THREAD
    Waits for a filename from the audio_queue, plays it, and deletes it.
    """
    while True:
        # Get a filename from the queue (blocks until a file is available)
        filename = audio_queue.get()
        
        # Check for the 'None' signal to quit
        if filename is None:
            break
            
        print(f"[Player] Playing audio: {filename}")
        play_audio_ffmpeg_blocking(filename)
        
        # Clean up the temp file after playing
        try:
            os.remove(filename)
        except Exception as e:
            print(f"Error deleting temp file: {e}")

# --- 5. INITIALIZATION ---
def get_voice_samples(folder):
    print(f"Scanning for voice samples in: ./{folder}/")
    all_samples = glob.glob(os.path.join(folder, "*.[mM][pP]3")) + \
                  glob.glob(os.path.join(folder, "*.[wW][aA][vV]")) + \
                  glob.glob(os.path.join(folder, "*.[fF][lL][aA][cC]"))
    return all_samples

voice_samples_list = get_voice_samples(VOICE_FOLDER)
if not voice_samples_list:
    print(f"Error: No audio files found in '{VOICE_FOLDER}'.")
    exit()

print("Found voice samples:")
for sample in voice_samples_list:
    print(f"  - {sample}")

device = "cuda" if torch.cuda.is_available() else "cpu"
print(f"\nUsing device: {device}")
if device == "cpu":
    print("WARNING: Running on CPU. This will be very slow, but the Jukebox will help!")

print("Loading XTTS-v2 model (this will take a moment)...")
tts = TTS("tts_models/multilingual/multi-dataset/xtts_v2").to(device)

print("\nPre-computing speaker latents...")
low_level_model = tts.synthesizer.tts_model
gpt_cond_latent, speaker_embedding = low_level_model.get_conditioning_latents(
    audio_path=voice_samples_list
)
print("Speaker latents computed and cached.")

# --- 6. START WORKER THREADS ---
print("\nStarting Generator and Player threads...")
# Start the "Chef" thread
threading.Thread(
    target=generator_thread, 
    # --- THIS IS THE CORRECTION ---
    # Pass the main 'tts' object and the 'voice_samples_list'
    args=(tts, voice_samples_list), 
    # ---
    daemon=True
).start()

# Start the "Waiter" thread
threading.Thread(target=player_thread, daemon=True).start()

# --- 7. MAIN LOOP (The "Order Taker") ---
print("\n--- Jukebox Ready! ---")
try:
    while True:
        text_to_speak = input("\nEnter text to speak (or 'q' to quit): ")
        if text_to_speak.lower() == 'q':
            break
        
        # Split the input text into sentences
        # This regex splits by '.', '?', '!', and '...'
        sentences = re.split(r'[.!?]+| \.\.\. ', text_to_speak)
        sentences = [s.strip() for s in sentences if s.strip()]

        if not sentences:
            print("No text entered, please try again.")
            continue
            
        print(f"Queuing {len(sentences)} sentences for generation...")
        # Put each sentence into the text_queue for the "chef"
        for sentence in sentences:
            text_queue.put(sentence)

except KeyboardInterrupt:
    print("\nExiting...")

finally:
    # Send 'None' to the queues to signal the threads to stop
    text_queue.put(None)
    audio_queue.put(None)
    print("Script finished. Cleaning up...")
    # Clean up any leftover temp files
    for temp_file in glob.glob(f"{TEMP_FILE_PREFIX}_*.wav"):
        os.remove(temp_file)