import os
import glob
import re

# --- CONFIGURATION (Paths are relative to where you run this script) ---
# Folder containing your .flac (or .wav) audio files
AUDIO_DIR = "converted_dataset/wavs" 
# Folder containing your .txt transcripts
TRANSCRIPT_DIR = "converted_dataset/transcripts"
# The final output file
OUTPUT_METADATA_FILE = "metadata.csv"
# ---

def create_metadata_file():
    """
    Scans the audio directory, finds matching transcripts, and generates a metadata.csv file.
    """
    if not os.path.isdir(AUDIO_DIR) or not os.path.isdir(TRANSCRIPT_DIR):
        print(f"Error: Required folders '{AUDIO_DIR}' or '{TRANSCRIPT_DIR}' not found.")
        print("Please create both folders and place your files inside.")
        return

    # Find all audio files (handling both .flac and .wav)
    audio_files = glob.glob(os.path.join(AUDIO_DIR, "*.flac"))
    audio_files.extend(glob.glob(os.path.join(AUDIO_DIR, "*.wav")))
    
    if not audio_files:
        print(f"Error: No .flac or .wav audio files found in '{AUDIO_DIR}'.")
        return

    metadata_lines = []
    print(f"Processing {len(audio_files)} audio files...")

    for audio_path in audio_files:
        # Get the full filename (e.g., recording_2025-11-11_21-41-32.flac)
        filename = os.path.basename(audio_path)
        # Get the base name without extension (e.g., recording_2025-11-11_21-41-32)
        base_name = os.path.splitext(filename)[0]

        # Construct the expected transcript path
        transcript_path = os.path.join(TRANSCRIPT_DIR, base_name + ".txt")

        if os.path.exists(transcript_path):
            with open(transcript_path, 'r', encoding='utf-8') as f:
                # Read the transcript and clean up potential tags
                transcript = f.read().strip()
                
                # Remove any leading text enclosed in square brackets (like )
                transcript = re.sub(r'\[.*?\]\s*', '', transcript).strip()
                
                # Format the line for the TTS trainer: wavs/filename|transcript
                # We use the 'wavs/' prefix as a standard convention for TTS training
                metadata_line = f"wavs/{filename}|{transcript}"
                metadata_lines.append(metadata_line)
                
        else:
            print(f"  ❌ WARNING: Transcript file not found for {filename}. Skipping.")
    
    # Write all lines to the final CSV file
    with open(OUTPUT_METADATA_FILE, 'w', encoding='utf-8') as f:
        f.write('\n'.join(metadata_lines))
        
    print(f"\n✨ Successfully created metadata file with {len(metadata_lines)} entries.")
    print(f"File saved as: {os.path.abspath(OUTPUT_METADATA_FILE)}")

if __name__ == "__main__":
    create_metadata_file()