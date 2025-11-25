import asyncio
import time
import numpy as np
import sounddevice as sd
from pathlib import Path
from google.genai import types

# Import system_log and debug monitor
import sys
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

from live.live_ui import system_log
from live.debug_monitor import get_monitor
try:
    from system_utils import orion_tts
except ImportError:
    print(f"Warning: {ImportError}")
    orion_tts = None

# Audio configuration
CHANNELS = 1
SEND_SAMPLE_RATE = 16000
CHUNK_SIZE = 1024
AI_INPUT_DEVICE = 6  # or whatever ID has "Aux" or "Output" in VoiceMeeter devices

class AudioPipeline:
    def __init__(self, connection_manager, signals=None):
        self.connection_manager = connection_manager
        self.audio_out_queue = asyncio.Queue(maxsize=60)
        self.debug_monitor = get_monitor()
        self.last_interaction_time = time.time()
        self.signals = signals
        
        # Stats
        self.audio_count = 0
        self.audio_drops = 0
        self.last_stats_time = time.time()

    async def send_realtime_audio(self):
        while True:
            audio = await self.audio_out_queue.get()
            try:
                await self.connection_manager.session.send_realtime_input(audio=types.Blob(data=audio.get("data"), mime_type=audio.get("mime_type")))
                
                # Track stats
                self.audio_count += 1
                
                current_time = time.time()
                if current_time - self.last_stats_time >= 1.0:
                    rate = self.audio_count / (current_time - self.last_stats_time)
                    self.audio_count = 0
                    self.last_stats_time = current_time
                    
                    if self.signals:
                        self.signals.stats_updated.emit({
                            "audio_rate": rate,
                            "audio_drops": self.audio_drops,
                            "type": "audio"
                        })

                # Feed to debug monitor
                if self.debug_monitor:
                    self.debug_monitor.update_audio_level(audio.get("data"))
                    
                    # Calculate estimated tokens (32 tokens/sec)
                    # len(data) is bytes (int16 = 2 bytes). 
                    # Duration = (len / 2) / 16000. Tokens = Duration * 32.
                    # Simplifies to len(data) / 1000
                    chunk_tokens = len(audio.get("data")) / 1000.0
                    self.debug_monitor.report_audio_tokens(chunk_tokens)
            except Exception as e:
                self.audio_drops += 1
                if self.debug_monitor:
                    self.debug_monitor.report_audio_drop()
                system_log.info(f"Error sending audio: {e}", category="AUDIO")

    async def listen_audio(self):
        """
        Capture system audio from the default input device (Virtual Cable) using sounddevice.
        """
        # Use the default input device (which should be CABLE Output)
        retry_count = 0
        while retry_count < 5:
            try:
                device_info = sd.query_devices(device=AI_INPUT_DEVICE)
                system_log.info(f"Opening audio stream on device: {device_info['name']}", category="AUDIO")
                break  # EXIT loop on success!
            except Exception as e:
                retry_count += 1
                wait_time = min(2 ** retry_count, 10)  # Exponential backoff
                system_log.info(f"Error querying audio devices (attempt {retry_count}/5): {e}", category="AUDIO")
            
                if retry_count >= 5:
                    system_log.info(f"Failed to initialize audio after 5 attempts. Audio disabled.", category="AUDIO")
                    return
                
                system_log.info(f"Retrying in {wait_time} seconds...", category="AUDIO")
                await asyncio.sleep(wait_time)
        
        # Create a queue for audio blocks
        q = asyncio.Queue()
        
        def callback(indata, frames, time_info, status):
            """Callback for sounddevice input stream."""
            if status:
                system_log.info(f"Audio status: {status}", category="AUDIO")
            # Make a copy of the data to ensure it's safe to pass to another thread/loop
            q.put_nowait(indata.copy())

        try:
            # Open the stream
            with sd.InputStream(samplerate=SEND_SAMPLE_RATE,
                                channels=CHANNELS,
                                dtype='int16',
                                callback=callback,
                                blocksize=CHUNK_SIZE,
                                device=AI_INPUT_DEVICE):
                
                system_log.info("Audio stream started", category="AUDIO")
                
                while True:
                    # Get audio data from the queue
                    indata = await q.get()
                    
                    # Check if AI is speaking (to avoid feedback loop if not using separate channels)
                    if orion_tts.IS_SPEAKING:
                        # Optional: mute system audio capture while AI is speaking to prevent echo
                        # self.last_interaction_time = time.time() 
                        #continue
                        pass

                    # Simple VAD to keep session alive
                    # indata is numpy array of int16
                    peak = np.max(np.abs(indata))
                    if peak > 500:
                        self.last_interaction_time = time.time()
                    
                    # Convert to bytes
                    data = indata.tobytes()
                    
                    await self.audio_out_queue.put({"data": data, "mime_type": "audio/pcm;rate=16000"})
                    
        except Exception as e:
            system_log.info(f"Error in listen_audio: {e}", category="AUDIO")
            # Wait a bit before retrying (outer loop might handle restart)
            await asyncio.sleep(1)
