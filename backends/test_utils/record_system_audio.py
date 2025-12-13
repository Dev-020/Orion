import sounddevice as sd
import numpy as np
import soundfile as sf
import os
import datetime
import queue
import threading
import whisper
import torch 
import torchaudio.transforms as T # Import torchaudio.transforms for Resample

# --- Configurable Settings (Using User's Specified Values) ---
DEVICE_ID = 27
SAMPLE_RATE = 48000 
CHUNK_SIZE = 1536  
CHUNKS_TO_KEEP_FOR_TAIL = 4 # Number of silent chunks to retain at the end for natural decay    

# --- VAD Settings for Segmentation ---
VAD_SAMPLE_RATE = 16000

VAD_SILENCE_PROB_THRESHOLD = 0.6  
VAD_SILENCE_DURATION_SEC = 0.85   
# --- END VAD Settings ---

MAX_RECORDING_SEC = -1 # Max length of any single recording chunk 
WHISPER_MODEL = "base"

# --- Define folder paths ---
BASE_FOLDER = "audio_samples"
AUDIO_FOLDER = os.path.join(BASE_FOLDER, "audio")
TRANSCRIPTS_FOLDER = os.path.join(BASE_FOLDER, "transcripts")

# --- Global Variables ---
q = queue.Queue()
transcription_q = queue.Queue()
recording_frames = []
is_recording = False
silence_chunks = 0
stream_active = True

# --- NEW: Global for VAD model and utilities ---
vad_model = None
# utils is not needed globally, but will be loaded in main()
# --- END NEW ---


# --- NEW: Resampler Utility (Corrected) ---
def resample_chunk(audio_chunk, current_sr, target_sr):
    """Resamples the audio chunk for VAD processing."""
    # Convert numpy array to torch tensor, ensuring it's float32
    if audio_chunk.ndim > 1:
        tensor_chunk = torch.from_numpy(audio_chunk[:, 0]).float()
    else:
        tensor_chunk = torch.from_numpy(audio_chunk).float()
    
    # Resample
    resampler = T.Resample(current_sr, target_sr) 
    resampled_tensor = resampler(tensor_chunk)
    
    # Return as numpy array
    return resampled_tensor.numpy()
# --- END NEW ---


# --- This function is HEAVILY UPDATED with VAD logic ---
def audio_callback(indata, frames, time, status):
    """
    This function is called by the sounddevice stream for each new chunk of audio.
    It now uses the directly loaded Silero VAD model to determine voice activity.
    """
    global is_recording, recording_frames, silence_chunks, vad_model, VAD_SAMPLE_RATE
    
    if not stream_active:
        raise sd.CallbackStop

    # --- NEW: Determine voice activity using VAD ---
    is_speech = False
    
    if vad_model:
        # 1. Resample chunk to VAD's required sample rate (16000Hz)
        if SAMPLE_RATE != VAD_SAMPLE_RATE:
            resampled_data = resample_chunk(indata, SAMPLE_RATE, VAD_SAMPLE_RATE)
        else:
            if indata.ndim > 1:
                resampled_data = indata[:, 0].copy()
            else:
                resampled_data = indata.copy()
            
        # 2. Convert to PyTorch tensor
        audio_tensor = torch.from_numpy(resampled_data).float()
        
        # 3. Get speech probability (Silero VAD expects a 1-dimensional tensor)
        voice_prob = vad_model(audio_tensor, VAD_SAMPLE_RATE).item()
        
        is_speech = voice_prob > VAD_SILENCE_PROB_THRESHOLD
    else:
        # Fallback if VAD failed to load
        volume_norm = np.linalg.norm(indata) * 10
        is_speech = volume_norm > 0.25 
        
    # --- Recording Logic (Unchanged) ---
    if is_recording:
        recording_frames.append(indata.copy())
        
        if not is_speech:
            silence_chunks += 1
        else:
            silence_chunks = 0
            
        chunks_for_silence = int((VAD_SILENCE_DURATION_SEC * SAMPLE_RATE) / CHUNK_SIZE)
        stop_due_to_silence = (silence_chunks > chunks_for_silence)
        
        stop_due_to_length = False
        if MAX_RECORDING_SEC != -1:
            max_chunks = int((MAX_RECORDING_SEC * SAMPLE_RATE) / CHUNK_SIZE)
            if len(recording_frames) > max_chunks:
                stop_due_to_length = True

        if stop_due_to_silence or stop_due_to_length:
            
            if stop_due_to_silence:
                print(f"VAD Silence detected ({VAD_SILENCE_DURATION_SEC}s), stopping recording...")
                
                # --- NEW FIX: Retain 4 chunks for a natural sound decay (the "tail") ---
                # We trim the silence chunks, but leave 4 of them in the final clip.
                # If total silence_chunks is 8, we only trim 4, keeping the other 4.
                
                if silence_chunks > CHUNKS_TO_KEEP_FOR_TAIL:
                    # Trim only the excess silence
                    trim_count = silence_chunks - CHUNKS_TO_KEEP_FOR_TAIL
                    frames_to_save = recording_frames[:-trim_count]
                else:
                    # Should not happen if stop_due_to_silence is True, but a safeguard
                    frames_to_save = recording_frames.copy()
                # --- END NEW FIX ---
                
            else: # This block is only reachable if stop_due_to_length is True
                print(f"Max length ({MAX_RECORDING_SEC}s) reached, saving chunk...")
                frames_to_save = recording_frames.copy()

            q.put(frames_to_save)
            
            is_recording = False
            recording_frames.clear()
            silence_chunks = 0
            print("Listening for new sound...")
            
    else:
        if is_speech:
            print("Voice detected (VAD), starting recording!")
            is_recording = True
            silence_chunks = 0
            recording_frames.clear()
            recording_frames.append(indata.copy())

# --- These functions are UNCHANGED ---
def save_recording():
    while stream_active:
        try:
            frames_to_save = q.get(timeout=1)
            
            if frames_to_save:
                recording_data = np.concatenate(frames_to_save, axis=0)
                
                timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
                filename = os.path.join(AUDIO_FOLDER, f"recording_{timestamp}.flac")
                
                sf.write(filename, recording_data, SAMPLE_RATE)
                print(f"Recording saved to: {filename}")
                q.task_done()
                
                transcription_q.put(filename)
                
        except queue.Empty:
            continue

def transcribe_worker():
    print(f"Loading Whisper model '{WHISPER_MODEL}'...")
    try:
        model = whisper.load_model(WHISPER_MODEL)
        print(f"Whisper model loaded.")
    except Exception as e:
        print(f"Error loading Whisper model: {e}")
        return

    while stream_active:
        try:
            filename = transcription_q.get(timeout=1)
            
            print(f"Transcribing {filename}...")
            result = model.transcribe(filename, fp16=False)
            transcript = result["text"]
            
            base_filename = os.path.basename(filename)
            transcript_name = os.path.splitext(base_filename)[0] + ".txt"
            txt_filename = os.path.join(TRANSCRIPTS_FOLDER, transcript_name)
            
            with open(txt_filename, "w", encoding="utf-8") as f:
                f.write(str(transcript))
                
            print(f"Transcription saved to: {txt_filename}")
            transcription_q.task_done()
            
        except queue.Empty:
            continue
        except Exception as e:
            print(f"Error during transcription: {e}")
            transcription_q.task_done()

# --- This function is UPDATED with final VAD loading fix ---
def main():
    global stream_active, SAMPLE_RATE, vad_model
    
    if not os.path.exists(AUDIO_FOLDER):
        os.makedirs(AUDIO_FOLDER)
        print(f"Created directory: {AUDIO_FOLDER}")
        
    if not os.path.exists(TRANSCRIPTS_FOLDER):
        os.makedirs(TRANSCRIPTS_FOLDER)
        print(f"Created directory: {TRANSCRIPTS_FOLDER}")
    
    # --- Load VAD Model Directly from PyTorch Hub (FINAL FIX) ---
    try:
        # FIX: Using the correct tuple unpacking resolves the Pylance warning.
        vad_model, utils = torch.hub.load( 
            repo_or_dir='snakers4/silero-vad',
            model='silero_vad',
            force_reload=False 
        )
        print("Silero VAD model loaded successfully via PyTorch Hub.")
    except Exception as e:
        print(f"Error loading VAD model: {e}")
        print("VAD feature will be disabled. Check your torch/torchaudio installation.")
        vad_model = None

    save_thread = threading.Thread(target=save_recording)
    save_thread.daemon = True
    save_thread.start()

    transcribe_thread = threading.Thread(target=transcribe_worker)
    transcribe_thread.daemon = True
    transcribe_thread.start()

    try:
        channels = 1 
        if DEVICE_ID is not None:
            device_info = sd.query_devices(DEVICE_ID, 'input')
            
            if not isinstance(device_info, dict):
                print(f"Error: Expected device info to be a dictionary, but got {type(device_info)}")
                return 

            new_sample_rate = int(device_info['default_samplerate'])
            if SAMPLE_RATE != new_sample_rate:
                print(f"Default sample rate was {SAMPLE_RATE}, changing to device's default: {new_sample_rate}")
                SAMPLE_RATE = new_sample_rate
            
            channels = device_info['max_input_channels']
            device_name = device_info.get('name', 'Unknown Device')
            print(f"Using device: {device_name} (Index: {DEVICE_ID})")
            
            if MAX_RECORDING_SEC == -1:
                print("\nNOTE: MAX_RECORDING_SEC is set to -1 (unlimited).")
                print("For XTTS training, clips between 3-15 seconds are recommended.")
        else:
            channels = 1
            print("Using default input device (microphone).")

        with sd.InputStream(
            device=DEVICE_ID,
            channels=channels,
            samplerate=SAMPLE_RATE,
            blocksize=CHUNK_SIZE,
            callback=audio_callback
        ):
            print("\nListening for voice activity (VAD mode)... Press Ctrl+C to stop.")
            while True:
                sd.sleep(1000)

    except KeyboardInterrupt:
        print("\nStopping...")
    except Exception as e:
        print(f"An error occurred: {e}")
    finally:
        stream_active = False
        print("Waiting for saving thread to finish...")
        save_thread.join(timeout=2)
        
        print("Waiting for transcription thread to finish...")
        transcribe_thread.join(timeout=10)
        
        print("Done.")

if __name__ == "__main__":
    main()