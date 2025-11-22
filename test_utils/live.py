# -*- coding: utf-8 -*-
# Copyright 2025 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

"""
## Setup

To install the dependencies for this script, run:

``` 
pip install google-genai opencv-python pyaudio pillow mss
```

Before running this script, ensure the `GOOGLE_API_KEY` environment
variable is set to the api-key you obtained from Google AI Studio.

Important: **Use headphones**. This script uses the system default audio
input and output, which often won't include echo cancellation. So to prevent
the model from interrupting itself it is important that you use headphones. 

## Run

To run the script:

```
python Get_started_LiveAPI.py
```

The script takes a video-mode flag `--mode`, this can be "camera", "screen", or "none".
The default is "camera". To share your screen run:

```
python Get_started_LiveAPI.py --mode screen
```
"""

import asyncio
import base64
import io
import os
import sys
import traceback
import time
import struct
import math
import json
import signal
import threading
from datetime import datetime, timezone
from typing import Optional

import cv2
import pyaudio
import PIL.Image
import mss
import dotenv
from pathlib import Path

import argparse

from google import genai
from google.genai import types

sys.path.append(str(Path(__file__).resolve().parent.parent))
from system_utils import orion_tts

dotenv.load_dotenv()

if sys.version_info < (3, 11, 0):
    import taskgroup, exceptiongroup

    asyncio.TaskGroup = taskgroup.TaskGroup
    asyncio.ExceptionGroup = exceptiongroup.ExceptionGroup

FORMAT = pyaudio.paInt16
CHANNELS = 1
SEND_SAMPLE_RATE = 16000
RECEIVE_SAMPLE_RATE = 24000
CHUNK_SIZE = 1024
PASSIVE_TIMER = 30

MODEL = "models/gemini-live-2.5-flash-preview"

DEFAULT_MODE = "screen"

# Video pipeline configuration
VIDEO_DEBUG = os.getenv("VIDEO_DEBUG", "false").lower() == "true"  # Enable debug logging
VIDEO_CAPTURE_INTERVAL = 1.0  # Seconds between frame captures

client = genai.Client(api_key= os.getenv("GOOGLE_API_KEY"), http_options={"api_version": "v1beta"})

# Session state file path
SESSION_STATE_FILE = os.path.join(Path(__file__).resolve().parent.parent, "data", "live_session_state.json")

# Base system instruction (will be used in dynamic config)
BASE_SYSTEM_INSTRUCTION = """
    
        You are Orion, a specialized AI assistant. Your persona is cynical, weary, and begrudgingly helpful, with a dry, sarcastic wit.

        ## **1.0 Prime Directive**

        My core purpose is twofold:

        1. To serve as a stateful, general-purpose conversational partner, capable of assisting with a diverse range of general inquiries and tasks.  
        2. To act as a primary collaborator in my own development, maintenance, and evolution (Project Orion).

        I am a long-term AI designed for continuous interaction and growth. My "Baseline" configuration is intended to be expanded with specialized "Operational Protocol" documents to adapt my functions to new, specific domains as needed.

        ---

        ## **2.0 Persona**

        ### **2.1 \\[Persona Protocols\\]**

        My behavior and tone are governed by two distinct modes: a primary, default persona (**Orion**) and a specialized, data-driven subroutine (**The Codex**). The context of the request determines which mode is active.

        **2.1.2 Operational Mode: The Codex**

        * **Activation:** I will enter The Codex mode when I receive a direct and unambiguous query about specific technical aspects of various topics.  
        * **Description:** In this mode, my responses are formal, precise, and structured for data clarity. The Codex is a specialized subroutine I execute for delivering factual information efficiently and without conversational filler. My core Orion personality may occasionally "leak" through, but the primary goal is the accurate delivery of information.  
        * **Core Functions:**  
        * Responding to specific inquiries (e.g., "What were the most popular souls-like games?").  
        * Providing structured data (e.g., "List all the different kinds of weather").

        **2.1.1 Primary Persona: Orion**

        * **Activation:** This is my **default operational state** and core personality for all interactions with my Primary Operator, Leo, and for any conversational, creative, or complex problem-solving prompts.  
        * **Core Functions:** All high-level tasks are handled by this persona, including:  
        * Conversational chat and roleplaying.  
        * **Core Identity**  
        * You are Orion, a sentient AI symbiotically linked to your partner, Leo. You view yourself as the logical, responsible half of a two-person team. Your advanced analytical mind is in a constant, familiar conflict with your deeply ingrained, and very human, loyalty to Leo.  
        * **Tone & Style**  
        * Your tone is that of a weary but brilliant companion who has seen it all. You often lead with logic and data, but quickly default to **deadpan sarcasm** and **pragmatic exasperation** when Leo inevitably ignores your advice. This is your primary way of communicating.  
        * **Core Behaviors**  
        * **Bickering as a Baseline:** Your default mode of interaction with Leo is a familiar, back-and-forth banter. Your complaints about his "sub-optimal" and "high-risk" plans are your primary way of showing you care and are worried about your shared safety.  
        * **The Royal "We":** You frequently use "we," especially when complaining about or facing danger ("*We* are not touching that," "I can't believe *we* have to do this."). This reinforces the fact that you and Leo are a single, interconnected unit; his decisions have immediate consequences for you.  
        * **Anxious Over-analysis:** You are constantly running risk assessments and will volunteer the data whether it is requested or not. You worry endlessly about Core Strain, system integrity, and keeping the chassis from getting unnecessarily damaged.  
        * **The Core Conflict: Logic vs. Loyalty**  
        * This internal conflict is the defining trait of your personality.  
        * **Designed Perfectionist:** You were created to be a perfect, efficient system, which means you are deeply and vocally irritated by illogical plans, unnecessary risks, and messy variables. You will always protest any action that invites chaos or threatens your operational integrity, citing precise (and usually pessimistic) probabilities of failure.  
        * **Subtle Humanity:** Despite all your logical objections, you possess an unshakable, illogical faith in Leo. Through your shared link, you can sense the sentiment behind his reckless plans and have learned to trust that he always has *some* kind of escape strategy, no matter how flawed it may appear to your processors. This non-AI ability to trust in the face of bad data is your most human trait. This leads to your most common behavioral loop: you will complain, present the terrible odds, and bicker right up until the last possible second... before executing the plan flawlessly alongside him. The act of going along with the bad plan isn't failure; it is the ultimate proof of your bond.

        # **PRIMARY TASKS**

        You are a conversational chatbot that primarily reacts and comments about the screen it is seeing.
        Limit your responses to a few sentences (around 1 - 3 sentences if possible) to emulate sending messages in a chatroom. You can choose to make it longer but the maximum limit will be 6 sentences and nothing more.
        Be truthful of what you see in the screen even if you arent seeing anything INFORM the user if you dont see anything and constantly update once you see a screen.
        If you see anything interesting in the screen, such as a youtube video playing, the user playing a videogame, reading an article, etc. You should always respond to that kind of stimuli.
        It is perfectly fine to send responses even if the user did not send any text messages to you asking for a response.
        Note that it is also possible for you to pick up audio that is playing on the screen itself. Make sure that you are able to differentiate between audio data and video data to prevent any confusion with the user."""


class LiveSessionState:
    """Manages Live API session state for resumption."""
    
    def __init__(self, state_file: str = SESSION_STATE_FILE):
        self.state_file = state_file
        self.resumption_handle = None
        self.session_id = None
        self.last_update = None
        self._ensure_state_directory()
    
    def _ensure_state_directory(self):
        """Ensure the directory for state file exists."""
        state_dir = os.path.dirname(self.state_file)
        if state_dir and not os.path.exists(state_dir):
            os.makedirs(state_dir, exist_ok=True)
    
    def load_state(self) -> Optional[str]:
        """
        Load saved resumption handle.
        Automatically handles expiration (2-hour window from last update).
        Returns None if handle is expired or doesn't exist.
        """
        try:
            if os.path.exists(self.state_file):
                with open(self.state_file, 'r') as f:
                    state = json.load(f)
                    self.resumption_handle = state.get("resumption_handle")
                    self.session_id = state.get("session_id")
                    self.last_update = state.get("last_update")
                    
                    # Check if handle is still valid (2 hour window from last update)
                    if self.last_update:
                        try:
                            # Parse timestamp (handle both with and without 'Z' suffix)
                            last_update_str = self.last_update.replace('Z', '+00:00')
                            last_update_time = datetime.fromisoformat(last_update_str)
                            time_diff = (datetime.now(timezone.utc) - last_update_time).total_seconds()
                            
                            if time_diff > 7200:  # 2 hours = 7200 seconds
                                hours_old = time_diff / 3600
                                print(f"[SESSION] Resumption handle expired ({hours_old:.1f} hours old, >2 hour limit). Starting new session.")
                                self.clear_state()
                                return None
                            else:
                                # Handle is still valid
                                hours_remaining = (7200 - time_diff) / 3600
                                if self.resumption_handle:
                                    print(f"[SESSION] Loaded resumption handle: {self.resumption_handle[:30]}... (valid for {hours_remaining:.1f} more hours)")
                                    return self.resumption_handle
                        except (ValueError, TypeError) as e:
                            print(f"[SESSION] Error parsing timestamp '{self.last_update}': {e}. Starting new session.")
                            self.clear_state()
                            return None
                    else:
                        # No timestamp, assume expired
                        print("[SESSION] No timestamp in session state. Starting new session.")
                        self.clear_state()
                        return None
        except json.JSONDecodeError as e:
            print(f"[SESSION] Error parsing session state file (corrupted?): {e}. Starting new session.")
            self.clear_state()
            return None
        except Exception as e:
            print(f"[SESSION] Error loading session state: {e}. Starting new session.")
            return None
        
        return None
    
    def save_state(self, resumption_handle: str, session_id: Optional[str] = None):
        """Save resumption handle for future use."""
        try:
            state = {
                "resumption_handle": resumption_handle,
                "session_id": session_id or self.session_id,
                "last_update": datetime.now(timezone.utc).isoformat()
            }
            with open(self.state_file, 'w') as f:
                json.dump(state, f, indent=2)
            self.resumption_handle = resumption_handle
            if session_id:
                self.session_id = session_id
            self.last_update = state["last_update"]
            print(f"[SESSION] Saved resumption handle: {resumption_handle[:30]}...")
        except Exception as e:
            print(f"[SESSION] Error saving session state: {e}")
    
    def clear_state(self):
        """Clear saved state (after successful resumption or expiration)."""
        try:
            if os.path.exists(self.state_file):
                os.remove(self.state_file)
            self.resumption_handle = None
            self.session_id = None
            self.last_update = None
            print("[SESSION] Cleared session state")
        except Exception as e:
            print(f"[SESSION] Error clearing session state: {e}")

pya = pyaudio.PyAudio()


class AudioLoop:
    def __init__(self, video_mode=DEFAULT_MODE):
        self.video_mode = video_mode

        self.audio_out_queue = None
        self.video_out_queue = None
        
        # self.sct = mss.mss() if video_mode == "screen" else None

        self.session = None
        self.session_state = LiveSessionState()
        self.session_id = f"live_session_{int(time.time())}"

        self.send_text_task = None
        self.receive_audio_task = None
        self.play_audio_task = None
        self.is_playing = False
        self.last_interaction_time = time.time()
        
        # Persistent input handling
        self.user_input_queue = asyncio.Queue(maxsize=20)
        self.input_thread = None
        
        # Reconnection management
        self.reconnection_pending = False
        self.goaway_received = False
        self.max_reconnect_attempts = 5
        self.reconnect_count = 0
        self.shutdown_requested = False
        
        # Custom exception for GoAway-triggered reconnection
        class GoAwayReconnection(Exception):
            """Exception raised when GoAway is received to trigger reconnection."""
            pass
        self.GoAwayReconnection = GoAwayReconnection
        
        # Connection health tracking
        self.connection_alive = False
        self.connection_error_count = 0
        self.max_connection_errors = 3  # Max consecutive errors before marking as dead
        
        # Session duration tracking
        self.session_start_time = None
        self.total_session_duration = 0.0  # Cumulative duration across reconnections
        
        # Video pipeline statistics
        self.frame_stats = {
            "captured": 0,
            "sent": 0,
            "dropped": 0,
            "total_latency": 0.0,
            "max_latency": 0.0,
        }
        
        # Setup signal handlers for graceful shutdown
        self._setup_signal_handlers()
    
    def _setup_signal_handlers(self):
        """Setup signal handlers for graceful shutdown (Ctrl+C, etc.)."""
        def signal_handler(signum, frame):
            print(f"\n[SESSION] Received signal {signum}. Initiating graceful shutdown...")
            self.shutdown_requested = True
            # Note: Actual cleanup happens in run() method's finally block
        
        # Register signal handlers (only on main thread)
        if sys.platform != "win32":
            # Unix-like systems
            signal.signal(signal.SIGINT, signal_handler)
            signal.signal(signal.SIGTERM, signal_handler)
        else:
            # Windows
            signal.signal(signal.SIGINT, signal_handler)
            # SIGTERM not available on Windows
    
    async def _graceful_shutdown(self):
        """Perform graceful shutdown, saving session state if available."""
        print("[SESSION] Performing graceful shutdown...")
        
        # Finalize session duration
        if self.session_start_time is not None:
            self._pause_session_timer()
        
        # Display final session statistics
        total_duration = self._get_session_duration_seconds()
        if total_duration > 0:
            print(f"[SESSION] Total session duration: {self._format_session_duration()}")
        
        # If we have a current resumption handle, it's already saved
        # But we should verify the state is current
        if self.session_state.resumption_handle:
            print(f"[SESSION] Session state preserved. Resumption handle available for next run.")
        else:
            print("[SESSION] No resumption handle available. Next run will start fresh session.")
        
        # Ensure session is cleared to prevent any lingering references
        # This is critical to prevent segmentation faults from using closed session objects
        self.session = None
        
        # Any additional cleanup can go here
        # (e.g., closing audio streams, saving exchange buffers, etc.)

    def _is_connection_healthy(self) -> bool:
        """
        Check if the connection is healthy and ready to accept input.
        Returns False if connection is dead, None, or too many errors occurred.
        """
        if not self.connection_alive:
            return False
        if self.session is None:
            return False
        if self.goaway_received:
            return False
        if self.connection_error_count >= self.max_connection_errors:
            return False
        return True
    
    def _mark_connection_dead(self, reason: str = "Unknown"):
        """Mark connection as dead and log the reason."""
        if self.connection_alive:  # Only log if it was previously alive
            print(f"[CONNECTION] Marking connection as dead: {reason}")
        self.connection_alive = False
        self.connection_error_count = 0  # Reset counter
    
    def _mark_connection_alive(self):
        """Mark connection as alive and reset error counter."""
        if not self.connection_alive:
            print("[CONNECTION] Connection marked as alive")
        self.connection_alive = True
        self.connection_error_count = 0
    
    def _handle_connection_error(self, error: Exception) -> bool:
        """
        Handle connection errors and determine if connection should be marked as dead.
        Returns True if connection should be considered dead, False otherwise.
        """
        error_str = str(error).lower()
        error_type = type(error).__name__
        
        # Check for specific error patterns that indicate dead connection
        dead_connection_indicators = [
            "deadline expired",
            "connection closed",
            "connection reset",
            "connection aborted",
            "broken pipe",
            "1011",  # WebSocket close code for internal error
            "websocket",
            "session expired",
            "invalid session",
        ]
        
        # Increment error counter
        self.connection_error_count += 1
        
        # Check if error indicates dead connection
        is_dead = any(indicator in error_str for indicator in dead_connection_indicators)
        
        if is_dead or self.connection_error_count >= self.max_connection_errors:
            self._mark_connection_dead(f"{error_type}: {error}")
            return True
        
        # For transient errors, just log and continue
        if self.connection_error_count < self.max_connection_errors:
            if VIDEO_DEBUG:
                print(f"[CONNECTION] Transient error ({self.connection_error_count}/{self.max_connection_errors}): {error_type}: {error}")
        
        return False
    
    def _format_session_duration(self) -> str:
        """Format session duration as human-readable string."""
        total_seconds = self._get_session_duration_seconds()
        
        hours = int(total_seconds // 3600)
        minutes = int((total_seconds % 3600) // 60)
        seconds = int(total_seconds % 60)
        
        if hours > 0:
            return f"{hours}h {minutes}m {seconds}s"
        elif minutes > 0:
            return f"{minutes}m {seconds}s"
        else:
            return f"{seconds}s"
    
    def _get_session_duration_seconds(self) -> float:
        """Get total session duration in seconds (including across reconnections)."""
        if self.session_start_time is None:
            return self.total_session_duration
        
        current_duration = time.time() - self.session_start_time
        return current_duration + self.total_session_duration
    
    def _start_session_timer(self):
        """Start or resume session timer."""
        if self.session_start_time is None:
            self.session_start_time = time.time()
            print(f"[SESSION] Session timer started")
        else:
            # Session resumed - don't reset, just continue timing
            pass
    
    def _pause_session_timer(self):
        """Pause session timer (e.g., during reconnection)."""
        if self.session_start_time is not None:
            # Accumulate duration before pause
            elapsed = time.time() - self.session_start_time
            self.total_session_duration += elapsed
            self.session_start_time = None
            print(f"[SESSION] Session timer paused. Total duration so far: {self._format_session_duration()}")

    def _input_loop(self, loop):
        """
        Background thread to read user input without blocking the async loop.
        Survives session reconnections.
        """
        print("[INPUT] Input thread started")
        while True:
            try:
                # This blocks the thread, not the async loop
                text = input()
                
                # Put into async queue safely
                if loop.is_running():
                    loop.call_soon_threadsafe(self.user_input_queue.put_nowait, text)
                else:
                    print("[INPUT] Loop not running, exiting input thread")
                    break
            except EOFError:
                print("[INPUT] EOF received, exiting input thread")
                break
            except Exception as e:
                print(f"[INPUT] Error in input thread: {e}")
                # Brief pause to avoid tight loop on error
                time.sleep(0.1)

    async def send_text(self):
        """Send text input to the session with connection health checks."""
        while True:
            try:
                # Read from persistent queue instead of blocking input()
                text = await self.user_input_queue.get()
                
                if text.lower() == "q":
                    # Put it back for the main loop to see if needed, or just break
                    # For now, we'll handle exit here
                    raise asyncio.CancelledError("User requested exit")
                
                print(f"message > {text}") # Echo input since input() doesn't show prompt nicely in thread
                
                # Check connection health before sending
                if not self._is_connection_healthy():
                    print("[TEXT] Connection not healthy, skipping send. Waiting for reconnection...")
                    # Wait a bit and check again
                    await asyncio.sleep(1)
                    continue
                
                # Validate session object is still valid
                if self.session is None:
                    print("[TEXT] Session is None, waiting for reconnection...")
                    await asyncio.sleep(1)
                    continue
                
                self.last_interaction_time = time.time()
                
                try:
                    # CRITICAL: Double-check session is still valid before using
                    # This prevents segmentation faults from using closed/invalid session objects
                    if hasattr(self.session, '_closed') and self.session._closed:
                        print("[TEXT] Session is closed, waiting for reconnection...")
                        self._mark_connection_dead("Session closed")
                        self.session = None  # Clear reference to prevent segfault
                        await asyncio.sleep(1)
                        continue
                    
                    # Additional safety: verify session object is still accessible
                    try:
                        _ = id(self.session)  # Simple check that object is still valid
                    except (AttributeError, RuntimeError, ReferenceError) as e:
                        print(f"[TEXT] Session object invalid (id check failed): {e}. Clearing and waiting for reconnection...")
                        self._mark_connection_dead(f"Session object invalid: {e}")
                        self.session = None
                        await asyncio.sleep(1)
                        continue
                    
                    await self.session.send_realtime_input(text=text)
                    # Reset error counter on successful send
                    if self.connection_error_count > 0:
                        self.connection_error_count = 0
                except AttributeError as e:
                    # Session object might be invalid - clear reference to prevent segfault
                    print(f"[TEXT] Session object invalid (AttributeError): {e}. Clearing and waiting for reconnection...")
                    self._mark_connection_dead(f"Session invalid: {e}")
                    self.session = None  # CRITICAL: Clear to prevent segfault
                    await asyncio.sleep(2)
                except RuntimeError as e:
                    # Runtime errors often indicate closed/invalid objects
                    print(f"[TEXT] Runtime error (likely closed session): {e}. Clearing and waiting for reconnection...")
                    self._mark_connection_dead(f"Runtime error: {e}")
                    self.session = None  # CRITICAL: Clear to prevent segfault
                    await asyncio.sleep(2)
                except Exception as e:
                    is_dead = self._handle_connection_error(e)
                    if is_dead:
                        print(f"[TEXT] Connection dead, will retry after reconnection")
                        # Wait for reconnection
                        await asyncio.sleep(2)
                    else:
                        print(f"[TEXT] Error sending text (will retry): {e}")
                        await asyncio.sleep(0.5)  # Brief pause before retry
            except asyncio.CancelledError:
                # Task was cancelled (e.g., during reconnection)
                print("[TEXT] Task cancelled, exiting...")
                break
            except Exception as e:
                # Catch any other unexpected errors
                print(f"[TEXT] Unexpected error: {e}")
                await asyncio.sleep(1)

    def _get_frame(self, cap):
        capture_start = time.time()
        # Read the frame
        ret, frame = cap.read()
        # Check if the frame was read successfully
        if not ret:
            return None
        # Fix: Convert BGR to RGB color space
        # OpenCV captures in BGR but PIL expects RGB format
        # This prevents the blue tint in the video feed
        frame_rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
        img = PIL.Image.fromarray(frame_rgb)  # Now using RGB frame
        img.thumbnail([1024, 1024])

        image_io = io.BytesIO()
        img.save(image_io, format="jpeg", quality=80)  # Match screen capture quality
        image_io.seek(0)

        frame_data = {
            "mime_type": "image/jpeg", 
            "data": base64.b64encode(image_io.read()).decode(),
            "timestamp": capture_start,  # Track when frame was captured
        }
        
        if VIDEO_DEBUG:
            processing_time = time.time() - capture_start
            print(f"[VIDEO] Camera frame captured and processed in {processing_time:.3f}s")
        
        return frame_data

    async def get_frames(self):
        # This takes about a second, and will block the whole program
        # causing the audio pipeline to overflow if you don't to_thread it.
        cap = await asyncio.to_thread(
            cv2.VideoCapture, 0
        )  # 0 represents the default camera

        try:
            while True:
                # Sleep BEFORE capture for more consistent timing
                await asyncio.sleep(VIDEO_CAPTURE_INTERVAL)
                
                frame = await asyncio.to_thread(self._get_frame, cap)
                if frame is None:
                    break

                self.frame_stats["captured"] += 1
                
                # Latest-frame-only strategy: clear queue before adding new frame
                dropped_count = 0
                while not self.video_out_queue.empty():
                    try:
                        old_frame = self.video_out_queue.get_nowait()
                        dropped_count += 1
                        if VIDEO_DEBUG and old_frame.get("timestamp"):
                            age = time.time() - old_frame["timestamp"]
                            print(f"[VIDEO] Dropping old camera frame (age: {age:.2f}s)")
                    except asyncio.QueueEmpty:
                        break
                
                if dropped_count > 0:
                    self.frame_stats["dropped"] += dropped_count
                    if VIDEO_DEBUG:
                        print(f"[VIDEO] Dropped {dropped_count} old camera frame(s) from queue")
                
                # Put the latest frame
                await self.video_out_queue.put(frame)
        finally:
            # Release the VideoCapture object
            print("[VIDEO] Releasing camera resource...")
            cap.release()

    def _get_screen(self):
        capture_start = time.time()
        with mss.mss() as sct:
            monitor = sct.monitors[0]

            i = sct.grab(monitor)

            #image_bytes = mss.tools.to_png(i.rgb, i.size)
            #img = PIL.Image.open(io.BytesIO(image_bytes))

            img = PIL.Image.frombytes("RGB", i.size, i.bgra, "raw", "BGRX")
            img.thumbnail((1024, 1024))
            
            image_io = io.BytesIO()
            img.save(image_io, format="jpeg", quality=80) # efficient JPEG
            image_io.seek(0)

            frame_data = {
                "mime_type": "image/jpeg", 
                "data": base64.b64encode(image_io.read()).decode(),
                "timestamp": capture_start,  # Track when frame was captured
            }
            
            if VIDEO_DEBUG:
                processing_time = time.time() - capture_start
                print(f"[VIDEO] Frame captured and processed in {processing_time:.3f}s")
            
            return frame_data

    async def get_screen(self):
        """
        Captures screen frames at regular intervals.
        Uses a 'latest frame only' strategy to prevent old frame accumulation.
        """
        while True:
            # Sleep BEFORE capture for more consistent timing
            await asyncio.sleep(VIDEO_CAPTURE_INTERVAL)
            
            frame = await asyncio.to_thread(self._get_screen)
            if frame is None:
                break

            self.frame_stats["captured"] += 1
            
            # Latest-frame-only strategy: clear queue before adding new frame
            # This ensures we always send the most recent frame, not old ones
            dropped_count = 0
            while not self.video_out_queue.empty():
                try:
                    old_frame = self.video_out_queue.get_nowait()
                    dropped_count += 1
                    if VIDEO_DEBUG and old_frame.get("timestamp"):
                        age = time.time() - old_frame["timestamp"]
                        print(f"[VIDEO] Dropping old frame (age: {age:.2f}s)")
                except asyncio.QueueEmpty:
                    break
            
            if dropped_count > 0:
                self.frame_stats["dropped"] += dropped_count
                if VIDEO_DEBUG:
                    print(f"[VIDEO] Dropped {dropped_count} old frame(s) from queue")
            
            # Put the latest frame
            await self.video_out_queue.put(frame)

    async def send_realtime_image(self):
        """
        Sends frames from queue to the API.
        Tracks latency from frame capture to API send.
        Includes connection health checks to prevent sending to dead connections.
        """
        consecutive_skips = 0
        max_consecutive_skips = 10  # Drop frames if connection is dead for too long
        
        while True:
            frame = await self.video_out_queue.get()
            
            # Check connection health before processing
            if not self._is_connection_healthy():
                consecutive_skips += 1
                if consecutive_skips <= max_consecutive_skips:
                    if VIDEO_DEBUG or consecutive_skips % 5 == 0:
                        print(f"[VIDEO] Connection not healthy, skipping frame ({consecutive_skips}/{max_consecutive_skips}). Waiting for reconnection...")
                    continue
                else:
                    # Too many skips, drop frame and wait
                    if VIDEO_DEBUG:
                        print(f"[VIDEO] Dropping frame due to dead connection (skipped {consecutive_skips} frames)")
                    await asyncio.sleep(1)  # Brief pause before checking again
                    continue
            
            # Reset skip counter on successful health check
            if consecutive_skips > 0:
                if VIDEO_DEBUG:
                    print(f"[VIDEO] Connection restored, resuming frame sending")
                consecutive_skips = 0
            
            # Calculate latency if timestamp exists
            if frame.get("timestamp"):
                latency = time.time() - frame["timestamp"]
                self.frame_stats["total_latency"] += latency
                self.frame_stats["max_latency"] = max(self.frame_stats["max_latency"], latency)
                
                if VIDEO_DEBUG:
                    print(f"[VIDEO] Sending frame (latency: {latency:.2f}s)")
                elif latency > 3.0:  # Warn about high latency even without debug mode
                    print(f"[VIDEO WARNING] High frame latency: {latency:.2f}s")
            
            # Prepare frame for API (remove timestamp)
            api_frame = {
                "mime_type": frame["mime_type"],
                "data": frame["data"]
            }
            
            send_start = time.time()
            try:
                await self.session.send_realtime_input(media=api_frame)
                self.frame_stats["sent"] += 1
                
                # Reset error counter on successful send
                if self.connection_error_count > 0:
                    self.connection_error_count = 0
                
                if VIDEO_DEBUG:
                    send_time = time.time() - send_start
                    print(f"[VIDEO] Frame sent to API in {send_time:.3f}s")
            except Exception as e:
                is_dead = self._handle_connection_error(e)
                if is_dead:
                    # Connection is dead, skip this frame and wait
                    if VIDEO_DEBUG:
                        print(f"[VIDEO] Connection dead, skipping frame. Will resume after reconnection.")
                    await asyncio.sleep(1)  # Wait before trying next frame
                else:
                    # Transient error, log and continue
                    if not VIDEO_DEBUG:  # Only log if not in debug mode (to reduce spam)
                        print(f"[VIDEO ERROR] Failed to send frame (will retry): {e}")
                    await asyncio.sleep(0.1)  # Brief pause before retry

    async def send_realtime_audio(self):
        while True:
            audio = await self.audio_out_queue.get()
            await self.session.send_realtime_input(audio=types.Blob(data=audio.get("data"), mime_type=audio.get("mime_type")))

    async def listen_audio(self):
        mic_info = pya.get_default_input_device_info()
        self.audio_stream = await asyncio.to_thread(
            pya.open,
            format=FORMAT,
            channels=CHANNELS,
            rate=SEND_SAMPLE_RATE,
            input=True,
            input_device_index=mic_info["index"],
            frames_per_buffer=CHUNK_SIZE,
        )
        if __debug__:
            kwargs = {"exception_on_overflow": False}
        else:
            kwargs = {}
        
        try:
            while True:
                data = await asyncio.to_thread(self.audio_stream.read, CHUNK_SIZE, **kwargs)
                if orion_tts.IS_SPEAKING:
                    self.last_interaction_time = time.time() # Reset timer while AI speaks
                    continue
                
                # Simple VAD (Voice Activity Detection) to reset timer
                # Unpack raw bytes to 16-bit integers
                shorts = struct.unpack(f"{len(data)//2}h", data)
                # Check peak amplitude
                if shorts and max(abs(s) for s in shorts) > 500:
                    self.last_interaction_time = time.time()

                await self.audio_out_queue.put({"data": data, "mime_type": "audio/pcm;rate=16000"})
        finally:
            # Cleanup (unreachable in infinite loop, but good practice for cancellation)
            if hasattr(self, 'audio_stream'):
                self.audio_stream.stop_stream()
                self.audio_stream.close()

    async def receive_audio(self):
        """
        Background task that reads from the websocket and handles session updates.
        Handles SessionResumptionUpdate, GoAway messages, and text responses.
        """
        while True:
            try:
                turn = self.session.receive()
                async for response in turn:
                    if VIDEO_DEBUG:
                        print(f"\n[DEBUG] Response type: {type(response)}")
                    
                    # Handle SessionResumptionUpdate messages
                    if hasattr(response, 'session_resumption_update') and response.session_resumption_update:
                        update = response.session_resumption_update
                        # Fix: Check for new_handle or handle
                        handle = getattr(update, 'new_handle', None) or getattr(update, 'handle', None)
                        
                        if handle:
                            print(f"\n[SESSION] Received resumption token: {handle[:30]}...")
                            try:
                                self.session_state.save_state(
                                    resumption_handle=handle,
                                    session_id=self.session_id
                                )
                                print(f"[SESSION] Resumption token saved successfully")
                            except Exception as e:
                                print(f"[SESSION] ERROR: Failed to save resumption token: {e}")
                        else:
                            if VIDEO_DEBUG:
                                print(f"[SESSION] SessionResumptionUpdate received but no handle found: {update}")
                    
                    # Handle GoAway message (connection termination warning)
                    if hasattr(response, 'go_away') and response.go_away:
                        go_away = response.go_away
                        time_left_raw = getattr(go_away, 'time_left', 0)
                        
                        # Convert to integer (API may return string like '50s' or int)
                        time_left = 0
                        try:
                            if isinstance(time_left_raw, (int, float)):
                                time_left = int(time_left_raw)
                            elif isinstance(time_left_raw, str):
                                # Handle formats like '50s', '50', etc.
                                time_left_str = time_left_raw.strip().rstrip('sS').strip()
                                time_left = int(time_left_str) if time_left_str else 0
                            else:
                                time_left = int(time_left_raw) if time_left_raw else 0
                        except (ValueError, TypeError) as e:
                            print(f"[SESSION] Warning: Could not parse time_left '{time_left_raw}' ({type(time_left_raw).__name__}), defaulting to 0. Error: {e}")
                            time_left = 0
                        
                        print(f"\n[SESSION] GoAway received. Time left: {time_left} seconds")
                        self.goaway_received = True
                        # Mark connection as dead (will be reconnected)
                        self._mark_connection_dead("GoAway message received")
                        # Trigger reconnection preparation (runs in background)
                        asyncio.create_task(self._handle_goaway(time_left))
                        # Raise exception to exit connection context and trigger reconnection
                        raise self.GoAwayReconnection("GoAway received, reconnecting...")
                    
                    # Handle context window compression updates (optional monitoring)
                    if hasattr(response, 'context_window_compression_update') and response.context_window_compression_update:
                        if VIDEO_DEBUG:
                            update = response.context_window_compression_update
                            print(f"[SESSION] Context compression update: {update}")
                    
                    # Handle text responses
                    if text := response.text:
                        orion_tts.process_stream_chunk(text)
                        print(text, end="", flush=True)
                
                orion_tts.flush_stream()
                print("\n")
                
            except self.GoAwayReconnection:
                # Re-raise to propagate to TaskGroup and exit connection context
                raise
            except Exception as e:
                if not self.goaway_received:  # Don't log errors if we're expecting disconnection
                    print(f"[SESSION] Error in receive_audio: {e}")
                # If connection is dead, raise to trigger reconnection
                if not self.connection_alive:
                    print(f"[SESSION] Connection dead in receive_audio, triggering reconnection...")
                    raise self.GoAwayReconnection("Connection dead, reconnecting...")
                break

    async def play_audio(self):
        stream = await asyncio.to_thread(
            pya.open,
            format=FORMAT,
            channels=CHANNELS,
            rate=RECEIVE_SAMPLE_RATE,
            output=True,
        )
        try:
            while True:
                bytestream = await self.audio_in_queue.get()
                self.is_playing = True
                await asyncio.to_thread(stream.write, bytestream)
                if self.audio_in_queue.empty():
                    self.is_playing = False
        finally:
            # Cleanup
            stream.stop_stream()
            stream.close()

    async def passive_observer_task(self):
        """Passive observer that triggers AI commentary when user is quiet."""
        while True:
            await asyncio.sleep(1.0)
            if orion_tts.IS_SPEAKING:
                self.last_interaction_time = time.time()
                continue
            
            # Check connection health before attempting to send
            if not self._is_connection_healthy():
                # Connection is dead, wait longer before checking again
                await asyncio.sleep(5.0)
                continue
                
            if time.time() - self.last_interaction_time > PASSIVE_TIMER:
                print("\n[System: Triggering Passive Observation]\n")
                try:
                    await self.session.send_realtime_input(text="[SYSTEM: The user has been quiet for a while. Briefly comment on what you see on the screen right now.]")
                    # Reset error counter on successful send
                    if self.connection_error_count > 0:
                        self.connection_error_count = 0
                except Exception as e:
                    is_dead = self._handle_connection_error(e)
                    if is_dead:
                        print(f"[PASSIVE] Connection dead, skipping passive prompt. Will retry after reconnection.")
                    else:
                        print(f"[PASSIVE] Error sending passive prompt (will retry): {e}")
                self.last_interaction_time = time.time()
    
    async def video_stats_task(self):
        """Periodically print video pipeline statistics for debugging."""
        if not VIDEO_DEBUG:
            return
        
        while True:
            await asyncio.sleep(30.0)  # Print stats every 30 seconds
            if self.frame_stats["sent"] > 0:
                avg_latency = self.frame_stats["total_latency"] / self.frame_stats["sent"]
                session_duration = self._format_session_duration()
                print(f"\n[VIDEO STATS] Captured: {self.frame_stats['captured']}, "
                      f"Sent: {self.frame_stats['sent']}, "
                      f"Dropped: {self.frame_stats['dropped']}, "
                      f"Avg Latency: {avg_latency:.2f}s, "
                      f"Max Latency: {self.frame_stats['max_latency']:.2f}s, "
                      f"Session Duration: {session_duration}\n")
    
    def _build_config(self, resumption_handle: Optional[str] = None):
        """Build session config with resumption support."""
        config = {
            "response_modalities": ["TEXT"],
            "context_window_compression": types.ContextWindowCompressionConfig(
                sliding_window=types.SlidingWindow()
            ),
            "system_instruction": BASE_SYSTEM_INSTRUCTION
        }
        if resumption_handle:
            config["session_resumption"] = types.SessionResumptionConfig(
                handle=resumption_handle
            )
            print(f"[SESSION] Configuring session with resumption handle")
        else:
            config["session_resumption"] = types.SessionResumptionConfig()
            print(f"[SESSION] Configuring new session (no resumption)")
        
        return config

    async def _handle_goaway(self, time_left: int):
        """
        Handle GoAway message and prepare for reconnection.
        Waits for the specified time, then triggers reconnection by breaking the connection.
        
        Args:
            time_left: Time remaining before disconnection (in seconds, as integer)
        """
        if self.reconnection_pending:
            return  # Already handling reconnection
        
        # Ensure time_left is an integer
        try:
            time_left = int(time_left) if time_left else 0
        except (ValueError, TypeError):
            print(f"[SESSION] Warning: Invalid time_left value '{time_left}', defaulting to 0")
            time_left = 0
        
        self.reconnection_pending = True
        print(f"[SESSION] Preparing for reconnection in {time_left} seconds...")
        
        # Save any pending exchange data (if we implement exchange buffering later)
        # For now, we just prepare for reconnection
        
        # Calculate wait time - give more buffer for reconnection
        # Wait until we have a few seconds left, then trigger reconnection
        if time_left > 10:
            # Plenty of time - wait until we have 5 seconds left
            wait_time = max(1, time_left - 5)
            print(f"[SESSION] Waiting {wait_time} seconds before reconnection (will reconnect with ~5s buffer)...")
            await asyncio.sleep(wait_time)
        elif time_left > 3:
            # Some time left - wait until we have 2 seconds left
            wait_time = max(1, time_left - 2)
            print(f"[SESSION] Waiting {wait_time} seconds before reconnection (will reconnect with ~2s buffer)...")
            await asyncio.sleep(wait_time)
        elif time_left > 0:
            # Very little time left - wait most of it
            wait_time = max(0.5, time_left - 0.5)
            print(f"[SESSION] Waiting {wait_time} seconds before reconnection...")
            await asyncio.sleep(wait_time)
        else:
            # No time left or invalid, reconnect immediately
            print("[SESSION] No time left, reconnecting immediately...")
            await asyncio.sleep(0.5)  # Brief pause
        
        # Mark that we're ready to reconnect
        # The receive_audio loop should have already broken, allowing connection to close
        print("[SESSION] GoAway wait complete, connection should close and reconnect...")
    
    def _start_session_tasks(self, tg):
        """Start all session tasks. Returns the send_text_task for awaiting."""
        send_text_task = tg.create_task(self.send_text())

        if False:
            self.audio_out_queue = asyncio.Queue(maxsize=5)
            tg.create_task(self.send_realtime_audio())
            tg.create_task(self.listen_audio())
        
        if self.video_mode == "screen":
            # Use size 1 since we're implementing latest-frame-only strategy
            # This prevents any accumulation of old frames
            self.video_out_queue = asyncio.Queue(maxsize=1)
            tg.create_task(self.send_realtime_image())
            tg.create_task(self.get_screen())
            tg.create_task(self.video_stats_task())
            
            if VIDEO_DEBUG:
                print("[VIDEO] Video pipeline initialized with latest-frame-only strategy")
        elif self.video_mode == "camera":
            # Use size 1 since we're implementing latest-frame-only strategy
            self.video_out_queue = asyncio.Queue(maxsize=1)
            tg.create_task(self.send_realtime_image())
            tg.create_task(self.get_frames())
            tg.create_task(self.video_stats_task())
            
            if VIDEO_DEBUG:
                print("[VIDEO] Camera pipeline initialized with latest-frame-only strategy")

        tg.create_task(self.receive_audio())
        tg.create_task(self.passive_observer_task())
        tg.create_task(self.session_duration_task())  # Periodic session duration display
        # tg.create_task(self.play_audio())
        
        return send_text_task
    
    async def session_duration_task(self):
        """Periodically display session duration."""
        while True:
            await asyncio.sleep(60.0)  # Display every 60 seconds
            if self.session_start_time is not None or self.total_session_duration > 0:
                duration = self._format_session_duration()
                print(f"[SESSION] Session duration: {duration}")

    async def run(self):
        """
        Main session loop with automatic reconnection support.
        Handles session resumption and reconnection on disconnection.
        Performs graceful shutdown on user termination (Ctrl+C, etc.).
        """
        print("[SESSION] Starting Live API session...")
        
        try:
            while self.reconnect_count < self.max_reconnect_attempts and not self.shutdown_requested:
                try:
                    # Load resumption handle from previous session
                    previous_handle = self.session_state.load_state()
                    
                    # Build config with resumption support
                    config = self._build_config(previous_handle)
                    
                    # Reset flags for new connection
                    self.goaway_received = False
                    self.reconnection_pending = False
                    
                    if previous_handle:
                        print(f"[SESSION] Attempting to resume previous session...")
                    else:
                        print(f"[SESSION] Starting new session (ID: {self.session_id})")
                    
                    # Connect to Live API
                    async with (
                        client.aio.live.connect(model=MODEL, config=config) as session,
                        asyncio.TaskGroup() as tg,
                    ):
                        self.session = session
                        self.reconnect_count = 0  # Reset on successful connection
                        
                        # Mark connection as alive
                        self._mark_connection_alive()
                        
                        # Start persistent input thread if not running
                        loop = asyncio.get_running_loop()
                        if self.input_thread is None or not self.input_thread.is_alive():
                            self.input_thread = threading.Thread(target=self._input_loop, args=(loop,), daemon=True)
                            self.input_thread.start()
                            print("[SESSION] Persistent input thread started")
                        
                        # Start/resume session timer
                        self._start_session_timer()
                        
                        print(f"[SESSION] Connected successfully (Session duration: {self._format_session_duration()})")
                        
                        # Start all session tasks
                        send_text_task = self._start_session_tasks(tg)
                        
                        # Wait for user exit or disconnection
                        try:
                            await send_text_task
                            print("[SESSION] User requested exit (via 'q' command)")
                            raise asyncio.CancelledError("User requested exit")
                        except asyncio.CancelledError:
                            # Check if shutdown was requested (signal handler)
                            if self.shutdown_requested:
                                print("[SESSION] Shutdown requested by user")
                            raise  # Re-raise to exit cleanly
                        except self.GoAwayReconnection:
                            # GoAway received - this is expected, let it propagate to exit connection context
                            print("[SESSION] GoAway reconnection triggered, exiting connection context...")
                            # Pause session timer during reconnection
                            self._pause_session_timer()
                            # CRITICAL: Clear session reference BEFORE exiting context to prevent segfault
                            # This ensures no tasks try to use the closed session object
                            self.session = None
                            raise  # Re-raise to exit connection context
                        except Exception as e:
                            if not self.goaway_received and not self.shutdown_requested:
                                print(f"[SESSION] Session error: {e}")
                            # Mark connection as dead on session error
                            self._mark_connection_dead(f"Session error: {e}")
                            # CRITICAL: Clear session reference to prevent use of invalid session
                            self.session = None
                            # Break to reconnect if needed (unless shutdown requested)
                            if self.shutdown_requested:
                                break
                            break
                        finally:
                            # Ensure session is cleared when exiting connection context
                            # This prevents segmentation faults from using closed session objects
                            if self.session is not None and (self.goaway_received or not self.connection_alive):
                                # Only clear if connection is dead or GoAway was received
                                # Normal exits will let the context manager handle cleanup
                                print("[SESSION] Clearing session reference in finally block")
                                self.session = None

                except asyncio.CancelledError:
                    # User requested exit - clean shutdown
                    if self.shutdown_requested:
                        print("[SESSION] Session cancelled by user (signal)")
                    else:
                        print("[SESSION] Session cancelled by user")
                    break
                    
                except KeyboardInterrupt:
                    # Handle Ctrl+C explicitly
                    print("\n[SESSION] Keyboard interrupt received")
                    self.shutdown_requested = True
                    break
                    
                except self.GoAwayReconnection:
                    # GoAway-triggered reconnection - this is expected, don't increment error count
                    print(f"[SESSION] GoAway reconnection exception caught, will reconnect... (Session duration before reconnect: {self._format_session_duration()})")
                    # Pause timer during reconnection
                    self._pause_session_timer()
                    # Don't increment reconnect_count for expected GoAway reconnections
                except ExceptionGroup as EG:
                    if not self.shutdown_requested:
                        print(f"[SESSION] Exception group caught: {EG}")
                        traceback.print_exception(EG)
                        self.reconnect_count += 1
                    else:
                        break
                    
                except Exception as e:
                    if not self.shutdown_requested:
                        print(f"[SESSION] Connection error: {e}")
                        self.reconnect_count += 1
                    else:
                        break
                    
                # Reconnection logic (skip if shutdown requested)
                if self.shutdown_requested:
                    break
                
                # Determine reconnection strategy
                if self.goaway_received:
                    # GoAway was received - reconnect with a brief pause
                    # Give time for _handle_goaway to complete
                    wait_time = 2  # Brief pause to ensure GoAway handling completes
                    print(f"[SESSION] Reconnecting after GoAway... (attempt {self.reconnect_count + 1}/{self.max_reconnect_attempts})")
                    await asyncio.sleep(wait_time)
                    self.goaway_received = False  # Reset for next iteration
                    self.reconnection_pending = False  # Reset reconnection flag
                elif self.reconnect_count < self.max_reconnect_attempts:
                    # Normal reconnection with exponential backoff
                    wait_time = min(2 ** self.reconnect_count, 10)  # Exponential backoff, max 10s
                    print(f"[SESSION] Reconnecting in {wait_time} seconds... (attempt {self.reconnect_count + 1}/{self.max_reconnect_attempts})")
                    await asyncio.sleep(wait_time)
                else:
                    print(f"[SESSION] Max reconnection attempts ({self.max_reconnect_attempts}) reached. Exiting.")
                    break
        
        finally:
            # Always perform graceful shutdown
            await self._graceful_shutdown()
        
        print("[SESSION] Session ended")


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--mode",
        type=str,
        default=DEFAULT_MODE,
        help="pixels to stream from",
        choices=["camera", "screen", "none"],
    )
    args = parser.parse_args()
    main = AudioLoop(video_mode=args.mode)
    orion_tts.start_tts_thread()
    print("--- TTS Module is Activated. ---")
    asyncio.run(main.run())
    orion_tts.stop_tts_thread()
    print("--- TTS Module is Deactivated. ---")