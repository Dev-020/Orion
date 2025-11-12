import os
import glob
import shutil
import torchaudio
import re

# --- CONFIGURATION ---
INPUT_AUDIO_DIR = "audio_samples/audio"
INPUT_TRANSCRIPT_DIR = "audio_samples/transcripts"
OUTPUT_DIR = "converted_dataset"

# ---

def relabel_and_convert():
    """
    Scans audio and transcript directories, converts audio to WAV,
    and re-labels both into a new, clean, numbered dataset.
    """
    # 1. Setup output directories
    output_audio_dir = os.path.join(OUTPUT_DIR, "wavs")
    output_transcript_dir = os.path.join(OUTPUT_DIR, "transcripts")

    if os.path.exists(OUTPUT_DIR):
        print(f"WARNING: Output directory '{OUTPUT_DIR}' already exists.")
        overwrite = input("Do you want to overwrite it? This will delete all its contents. (y/n): ").lower()
        if overwrite == 'y':
            print("Deleting existing directory...")
            shutil.rmtree(OUTPUT_DIR)
        else:
            print("Operation cancelled.")
            return

    print(f"Creating new dataset directory at '{OUTPUT_DIR}'...")
    os.makedirs(output_audio_dir)
    os.makedirs(output_transcript_dir)

    # 2. Find all audio files
    print(f"Scanning for audio files in '{INPUT_AUDIO_DIR}'...")
    audio_files = glob.glob(os.path.join(INPUT_AUDIO_DIR, "*.flac"))
    audio_files.extend(glob.glob(os.path.join(INPUT_AUDIO_DIR, "*.wav")))
    audio_files.extend(glob.glob(os.path.join(INPUT_AUDIO_DIR, "*.mp3")))

    if not audio_files:
        print(f"Error: No .flac, .wav, or .mp3 audio files found in '{INPUT_AUDIO_DIR}'.")
        shutil.rmtree(OUTPUT_DIR) # Clean up empty directories
        return

    print(f"Found {len(audio_files)} audio files. Starting processing...")
    
    file_counter = 1
    processed_count = 0

    # 3. Process each file
    for audio_path in sorted(audio_files):
        base_name = os.path.splitext(os.path.basename(audio_path))[0]
        transcript_path = os.path.join(INPUT_TRANSCRIPT_DIR, base_name + ".txt")

        if not os.path.exists(transcript_path):
            print(f"  - ❌ WARNING: Transcript not found for '{os.path.basename(audio_path)}'. Skipping.")
            continue

        try:
            # 4. Read and clean transcript
            with open(transcript_path, 'r', encoding='utf-8') as f:
                transcript_text = f.read().strip()
                # Remove any leading text in brackets, like [Music] or [Sound]
                transcript_text = re.sub(r'\[.*?\]\s*', '', transcript_text).strip()

            # 5. Load audio and convert to WAV
            waveform, sample_rate = torchaudio.load(audio_path)

            # 6. Define new numbered filenames
            new_audio_filename = f"{file_counter}.wav"
            new_transcript_filename = f"{file_counter}.txt"
            
            new_audio_path = os.path.join(output_audio_dir, new_audio_filename)
            new_transcript_path = os.path.join(output_transcript_dir, new_transcript_filename)

            # 7. Save the new files
            torchaudio.save(new_audio_path, waveform, sample_rate)
            with open(new_transcript_path, 'w', encoding='utf-8') as f:
                f.write(transcript_text)

            file_counter += 1
            processed_count += 1
        except Exception as e:
            print(f"  - ❌ ERROR processing '{os.path.basename(audio_path)}': {e}. Skipping.")

    print(f"\n✨ Successfully processed and relabeled {processed_count} audio/transcript pairs.")
    print(f"New dataset created in '{os.path.abspath(OUTPUT_DIR)}'.")

if __name__ == "__main__":
    relabel_and_convert()