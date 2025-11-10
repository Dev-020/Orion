import torch
from TTS.api import TTS
import os
import glob
import time

# --- 1. CONFIGURATION ---
# The folder to scan for voice samples
VOICE_FOLDER = "orion_voice"

# The output file name
OUTPUT_FILE = "cloned_output.wav"
# ---

import subprocess
import os

def play_audio_ffmpeg(filename):
    """
    Plays an audio file using ffplay (from ffmpeg) in a non-blocking way.
    """
    # Check if the file exists before trying to play it
    if not os.path.exists(filename):
        print(f"Error: Audio file not found: {filename}")
        return

    print("Playing audio with ffplay...")
    try:
        # We use subprocess.Popen for a non-blocking call.
        # This starts ffplay and your Python script continues.
        #
        # Key flags:
        # -nodisp : Hides the ffplay pop-up window.
        # -autoexit : Closes ffplay when the audio is done.
        # -hide_banner : Suppresses the startup text.
        subprocess.Popen(
            ["ffplay", "-nodisp", "-autoexit", "-hide_banner", filename],
            stdout=subprocess.DEVNULL, # Hides console output
            stderr=subprocess.DEVNULL  # Hides console errors
        )
    except FileNotFoundError:
        print("Error: 'ffplay' command not found.")
        print("Please ensure ffmpeg is installed and in your system's PATH.")
    except Exception as e:
        print(f"Error playing audio with ffplay: {e}")

def get_voice_samples(folder):
    """
    Finds all .mp3 and .wav files in a folder and returns a list.
    """
    print(f"Scanning for voice samples in: ./{folder}/")
    
    # Use glob to find files. The * matches any name.
    # We use glob for both .mp3 and .wav, and add them together.
    # [wW] handles both .wav and .WAV (case-insensitive)
    mp3_files = glob.glob(os.path.join(folder, "*.[mM][pP]3"))
    wav_files = glob.glob(os.path.join(folder, "*.[wW][aA][vV]"))
    
    all_samples = mp3_files + wav_files
    
    return all_samples

# --- 2. INITIALIZATION ---

# Check if the folder exists
if not os.path.isdir(VOICE_FOLDER):
    print(f"Error: Folder '{VOICE_FOLDER}' not found.")
    print("Please create the folder and add your .mp3 or .wav samples.")
    exit()

# Get the list of all voice samples
voice_samples_list = get_voice_samples(VOICE_FOLDER)

if not voice_samples_list:
    print(f"Error: No .mp3 or .wav files found in '{VOICE_FOLDER}'.")
    print("Please add audio samples to the folder.")
    exit()

print("Found voice samples:")
for sample in voice_samples_list:
    print(f"  - {sample}")

# 3. Get device
device = "cuda" if torch.cuda.is_available() else "cpu"
print(f"\nUsing device: {device}")
if device == "cpu":
    print("WARNING: Running on CPU. This will be very slow.")

# --- 4. LOAD THE MODEL (RUNS ONLY ONCE) ---
print("Loading XTTS-v2 model (this will take a moment)...")
try:
    tts = TTS("tts_models/multilingual/multi-dataset/xtts_v2").to(device)
    print("Model loaded! Ready to generate speech.")
except Exception as e:
    print(f"Error loading TTS model: {e}")
    print("This can be due to network issues or a corrupted model.")
    print("Try deleting the model folder in your home directory to force a re-download.")
    exit()

# --- 5. RUN THE "SERVER" LOOP ---
try:
    while True:
        # Get text input from the user
        text_to_speak = input("\nEnter text to speak (or 'q' to quit): ")

        # Check if the user wants to quit
        if text_to_speak.lower() == 'q':
            break
            
        if not text_to_speak.strip():
            print("No text entered, please try again.")
            continue

        # --- This is the FAST part ---
        print("Generating speech using voice samples...")
        start_time = time.time() # Start timer

        try:
            tts.tts_to_file(
                text=text_to_speak,
                file_path=OUTPUT_FILE,
                
                # --- THIS IS THE DYNAMIC PART ---
                # We are using the list of files we found earlier
                speaker_wav=voice_samples_list,
                # ---
                
                language="en",
                split_sentences=True
            )
            
            end_time = time.time() # End timer
            print(f"Speech saved to {OUTPUT_FILE} (Time taken: {end_time - start_time:.2f}s)")
            
            # --- NEW: Play the generated audio file ---
            play_audio_ffmpeg(OUTPUT_FILE)
            # ---
            
        except Exception as e:
            print(f"Error during audio generation: {e}")
            print("This can sometimes happen with very short text.")

except KeyboardInterrupt:
    # This allows you to press Ctrl+C to quit gracefully
    print("\nExiting...")

print("Script finished.")