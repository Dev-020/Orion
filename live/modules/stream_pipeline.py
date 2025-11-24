import asyncio
import subprocess
import shlex
import re
from pathlib import Path
from google.genai import types

# Import system_log
import sys
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.append(str(PROJECT_ROOT))

from live.live_ui import system_log

class StreamPipeline:
    def __init__(self, connection_manager):
        self.connection_manager = connection_manager
        self.process = None
        self.audio_device = "CABLE Output (VB-Audio Virtual Cable)" # Default, can be configured
        self.running = False
        self.debug_monitor = None
        
    async def _get_audio_devices(self):
        """List available dshow audio devices."""
        cmd = "ffmpeg -list_devices true -f dshow -i dummy"
        try:
            # Run ffmpeg to list devices (output goes to stderr)
            process = await asyncio.create_subprocess_shell(
                cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            _, stderr = await process.communicate()
            output = stderr.decode('utf-8', errors='ignore')
            
            devices = []
            # Parse output for audio devices
            # Example: [dshow @ ...]  "Microphone (Realtek Audio)"
            #          [dshow @ ...]     Alternative name "@device_cm_{...}"
            lines = output.split('\n')
            in_audio_section = False
            for line in lines:
                if "DirectShow audio devices" in line:
                    in_audio_section = True
                    continue
                if "DirectShow video devices" in line:
                    in_audio_section = False
                    continue
                    
                if in_audio_section and '"' in line:
                    match = re.search(r'"([^"]+)"', line)
                    if match:
                        devices.append(match.group(1))
            return devices
        except Exception as e:
            system_log.info(f"Error listing audio devices: {e}", category="STREAM")
            return []

    async def start_stream(self):
        """Start the ffmpeg streaming process."""
        if self.running:
            return

        # 1. Verify Audio Device
        devices = await self._get_audio_devices()
        if self.audio_device not in devices:
            system_log.info(f"Warning: Configured audio device '{self.audio_device}' not found.", category="STREAM")
            if devices:
                system_log.info(f"Available devices: {devices}", category="STREAM")
                # Fallback to first available device if possible, or keep default and hope
                # self.audio_device = devices[0] 
            else:
                system_log.info("No audio devices found via ffmpeg dshow.", category="STREAM")

        # 2. Build FFmpeg Command
        # Inputs: Screen (gdigrab) + Audio (dshow)
        # Output: Fragmented MP4 stream to stdout
        # Tuning: ultrafast, zerolatency for real-time performance
        
        # Note: -rtbufsize is important to prevent buffer overflows
        # -movflags frag_keyframe+empty_moov is CRITICAL for streaming MP4
        cmd = (
            f'ffmpeg -f gdigrab -framerate 30 -video_size 1920x1080 -i desktop '
            f'-f dshow -i audio="{self.audio_device}" '
            f'-c:v libx264 -preset ultrafast -tune zerolatency -pix_fmt yuv420p '
            f'-c:a aac -b:a 128k -ar 44100 '
            f'-f mp4 -movflags frag_keyframe+empty_moov -'
        )
        
        system_log.info(f"Starting FFmpeg stream: {cmd}", category="STREAM")
        
        try:
            self.process = await asyncio.create_subprocess_shell(
                cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE, # Capture stderr for logging
                stdin=asyncio.subprocess.DEVNULL
            )
            self.running = True
            
            # Start tasks to read stdout (data) and stderr (logs)
            asyncio.create_task(self._stream_loop())
            asyncio.create_task(self._log_loop())
            
        except Exception as e:
            system_log.info(f"Failed to start FFmpeg: {e}", category="STREAM")
            self.running = False

    async def _stream_loop(self):
        """Read chunks from ffmpeg stdout and send to Gemini."""
        chunk_size = 1024 * 64 # 64KB chunks
        
        while self.running and self.process:
            try:
                if self.process.stdout.at_eof():
                    break
                    
                data = await self.process.stdout.read(chunk_size)
                if not data:
                    break
                
                # Send to Gemini
                if self.connection_manager.is_healthy():
                    await self.connection_manager.session.send_realtime_input(
                        media=types.Blob(data=data, mime_type="video/mp4")
                    )
                
            except Exception as e:
                system_log.info(f"Error sending stream chunk: {e}", category="STREAM")
                await asyncio.sleep(0.1)

        system_log.info("Stream loop ended", category="STREAM")
        self.running = False

    async def _log_loop(self):
        """Read ffmpeg stderr logs."""
        while self.running and self.process:
            try:
                if self.process.stderr.at_eof():
                    break
                line = await self.process.stderr.readline()
                if line:
                    # Filter logs to avoid spam, or log only errors
                    log_msg = line.decode('utf-8', errors='ignore').strip()
                    if "Error" in log_msg or "frame=" in log_msg: # Log errors and progress
                         # Only log progress occasionally or it's too spammy
                         pass 
            except Exception:
                break

    def stop(self):
        """Stop the streaming process."""
        self.running = False
        if self.process:
            try:
                self.process.terminate()
            except ProcessLookupError:
                pass
            self.process = None
