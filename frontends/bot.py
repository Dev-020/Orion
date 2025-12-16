# bot.py (Refactored for Generator API & Mode Switching)

import discord
import os
import sys
import logging
from pathlib import Path

# --- PATH HACK FOR REFRACTOR PHASE 1 ---
# Add 'backends' to sys.path so we can import 'orion_core', 'main_utils', etc.
sys.path.append(str(Path(__file__).resolve().parent.parent / 'backends'))
# ---------------------------------------

import asyncio
import time
import io
import logging
from dotenv import load_dotenv  
from discord.ext import commands
import threading
from collections import deque # <--- Added for efficient buffer

# 1. Config Override (Must be before OrionCore init)
from main_utils import config
from main_utils.orion_logger import setup_logging

config.VOICE = False
config.VISION = False

# --- LOGGING SETUP ---
LOG_FILE = config.DATA_DIR / "logs" / "bot.log"
logger = setup_logging("Bot", LOG_FILE, level=logging.INFO)

# --- One "Brain" ---
# Load environment variables
load_dotenv()
persona = os.getenv("ORION_PERSONA", "default")
logger.info(f"--- Bot starting with Persona: {persona} (Voice/Vision Disabled) ---")

# --- Configuration ---
BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN")

# --- Bot Setup ---
intents = discord.Intents.default()
intents.message_content = True
bot = discord.Bot(intents=intents, debug_guilds=[os.getenv("DISCORD_GUILD_ID")] if os.getenv("DISCORD_GUILD_ID") else None)

# --- CLIENT WRAPPER ---
from orion_client import OrionClient 

logger.info("--- Initializing Orion Client ---")
# Connect to local Server
core = OrionClient(base_url="http://127.0.0.1:8000")
bot.core = core

# --- Session Preferences ---
# simple dict: session_id -> bool (True=Stream, False=Full)
streaming_preferences = {}

# --- Global Activity Buffer ---
# Map: channel_id -> deque(maxlen=config.BUFFER_SIZE) of dicts
recent_messages_buffer = {} 

# --- Helper: Async Generator Consumer ---
async def consume_generator_async(generator, message_to_edit):
    """
    Consumes the OrionCore generator updates and edits the Discord message.
    Handles both streaming (token accumulation) and full responses.
    Implements:
      - 1.5s throttling for edits.
      - 2000 char pagination (overflow to new message).
      - Status updates.
    """
    full_text_buffer = ""
    current_message = message_to_edit
    
    last_edit_time = 0
    edit_interval = config.EDIT_TIME  # Seconds between edits to respect rate limits
    
    # Track pagination
    # We only care about the *current* chunk we are streaming into
    
    try:
        should_restart = False
        message_chain = [message_to_edit] # Track all messages in response
        thought_buffer = ""
        is_thinking = True # simplistic state tracking

        def get_display_text(is_thought_phase=True):
            """Helper to format text based on phase."""
            text = ""
            if is_thought_phase:
                 # In thought phase: Show thoughts (Quote) + Response so far (empty usually)
                if thought_buffer:
                    encoded_thoughts = thought_buffer.strip().replace(chr(10), chr(10) + '> ')
                    text += f"> **Thinking Process:**\n> {encoded_thoughts}\n\n"
                text += full_text_buffer
            else:
                # In response phase: Show ONLY Response (Thoughts are handled via file)
                text += full_text_buffer
            return text

        # NATIVE ASYNC LOOP - No Threading/Encoding needed
        async for item in generator:
            if isinstance(item, dict):
                msg_type = item.get("type")
                content = item.get("content")
                
                if msg_type == "status":
                    pass 
                
                elif msg_type == "thought":
                    thought_buffer += content
                    # We are in thinking phase
                    
                    # Throttle edits
                    now = time.time()
                    if now - last_edit_time > edit_interval:
                        display_text = get_display_text(is_thought_phase=True)
                        # We use message_to_edit directly here or message_chain[0]
                        # Since we haven't split yet, chain[0] is the main msg
                        await update_message_chain(message_to_edit.channel, message_chain, display_text)
                        last_edit_time = now

                elif msg_type == "token":
                    # FIRST TOKEN TRANSITION DETECT
                    if is_thinking and thought_buffer:
                        is_thinking = False
                        # 1. Convert thoughts to file
                        try:
                            thought_file = discord.File(
                                io.BytesIO(thought_buffer.encode('utf-8')), 
                                filename="thought_process.md"
                            )
                            
                            # CLEANUP OVERFLOW: Delete extra messages if thoughts spilled over
                            if len(message_chain) > 1:
                                for overflow_msg in message_chain[1:]:
                                    try:
                                        await overflow_msg.delete()
                                    except:
                                        pass # Best effort
                                message_chain = [message_chain[0]]

                            # 2. Update ORIGINAL message: Clear text, Attach file
                            # Note: We must be careful not to lose the "Response so far" if any (unlikely if strictly sequential)
                            await message_to_edit.edit(content="", file=thought_file)
                            
                            # 3. Start NEW message chain for the response
                            # We send a placeholder or the first token to start it
                            new_msg = await message_to_edit.channel.send(content) # Send first token
                            message_chain = [new_msg] # Reset chain to this new message
                            full_text_buffer = content # Start buffer with this token
                            
                            last_edit_time = time.time()
                            continue # Skip standard processing this loop
                            
                        except Exception as e:
                            logger.error(f"Failed to attach thought file: {e}")
                            # Fallback: Just keep printing text
                            pass
                    
                    full_text_buffer += content
                    
                    # Throttle edits
                    now = time.time()
                    if now - last_edit_time > edit_interval:
                        display_text = get_display_text(is_thought_phase=False)
                        message_chain = await update_message_chain(message_to_edit.channel, message_chain, display_text)
                        last_edit_time = now
                        
                elif msg_type == "full_response":
                    # Overwrite buffer with final clean text
                    full_text_buffer = item.get("text", "")
                    should_restart = item.get("restart_pending", False)
                    pass

                elif msg_type == "error":
                    full_text_buffer += f"\n\n[System Error: {content}]"
                    display_text = get_display_text(is_thought_phase=is_thinking)
                    message_chain = await update_message_chain(message_to_edit.channel, message_chain, display_text)
            
        
        # Final flush
        # Check if we never transitioned (e.g. only thoughts, no tokens?) unlikely but solvable
        if is_thinking and thought_buffer:
             # Case: thoughts finished but no tokens? Or just done.
             # Convert to file regardless
            try:
                thought_file = discord.File(
                    io.BytesIO(thought_buffer.encode('utf-8')), 
                    filename="thought_process.md"
                )
                await message_to_edit.edit(content="", file=thought_file)
                # If there's text buffer, send it in new msg
                if full_text_buffer:
                    new_msg = await message_to_edit.channel.send(full_text_buffer)
                    message_chain = [new_msg]
            except:
                pass
        else:
            # Normal flush of response
            display_text = get_display_text(is_thought_phase=False)
            message_chain = await update_message_chain(message_to_edit.channel, message_chain, display_text)
        
        return should_restart

    except Exception as e:
        logger.error(f"Error in consumer: {e}")
        await current_message.edit(content=f"{full_text_buffer}\n\n[Bot Error: {e}]")

    return False # No restart by default

async def update_message_chain(channel, chain, full_text):
    """
    Updates a chain of messages to reflect the full_text.
    Splits text into chunks (1900 chars) and distributes across the chain.
    Expands the chain if necessary.
    """
    CHUNK_SIZE = 1900
    text_chunks = [full_text[i:i+CHUNK_SIZE] for i in range(0, len(full_text), CHUNK_SIZE)]
    if not text_chunks: text_chunks = [""] # Handle empty case

    for i, chunk in enumerate(text_chunks):
        if i < len(chain):
            # Update existing message if content differs
            if chain[i].content != chunk:
                try:
                    await chain[i].edit(content=chunk)
                except discord.errors.HTTPException:
                    # Rare race condition or sizing issue
                    pass 
        else:
            # Create new message for overflow
            new_msg = await channel.send(chunk)
            chain.append(new_msg)
            
    return chain

# Old function removed


# --- Commands ---

@bot.slash_command(name="mode", description="Switch session mode.")
async def switch_mode(ctx: discord.ApplicationContext, mode: discord.Option(str, choices=["cache", "function"])):
    session_id = get_session_id(ctx)
    result = core.set_session_mode(session_id, mode)
    await ctx.respond(result, ephemeral=True)

@bot.slash_command(name="stream", description="Toggle streaming implementation.")
async def toggle_stream(
    ctx: discord.ApplicationContext, 
    setting: discord.Option(str, choices=["on", "off"], description="Enable or disable real-time streaming")
):
    session_id = get_session_id(ctx)
    is_streaming = (setting == "on")
    streaming_preferences[session_id] = is_streaming
    await ctx.respond(f"Streaming set to **{setting.upper()}** for this session.", ephemeral=True)

import io

@bot.slash_command(name="history", description="Download chat history for this channel.")
async def history(ctx: discord.ApplicationContext):
    session_id = get_session_id(ctx)
    history_list = core.chat.get_session(session_id)
    
    if not history_list:
        await ctx.respond(f"No history found for session `{session_id}`.", ephemeral=True)
        return

    # Formatter
    lines = [f"Chat History for Session: {session_id}", "="*40, ""]
    for i, exchange in enumerate(history_list):
        lines.append(f"--- Exchange {i+1} ---")
        
        # Helper to extract text from Content object or Dict
        def get_text(content_obj):
            text = ""
            try:
                # Case A: Object with parts
                if hasattr(content_obj, "parts"):
                    for part in content_obj.parts:
                        if hasattr(part, "text") and part.text:
                            text += part.text
                # Case B: Dict (if persisted/loaded as dict)
                elif isinstance(content_obj, dict):
                     # Check 'parts' list
                     if "parts" in content_obj:
                         for part in content_obj["parts"]:
                             # part could be dict or obj
                             if isinstance(part, dict):
                                 text += part.get("text", "")
                             elif hasattr(part, "text"):
                                 text += part.text
            except Exception: 
                text = "[Error extracting content]"
            return text.strip()

        user_text = get_text(exchange.get("user_content"))
        model_text = get_text(exchange.get("model_content"))
        
        lines.append(f"User: {user_text}")
        lines.append(f"Orion: {model_text}")
        lines.append("-" * 20 + "\n")

    full_output = "\n".join(lines)
    
    # Save to data directory
    filename = f"history_{session_id}.txt"
    filename = f"history_{session_id}.txt"
    # Data is now in backends/data
    data_dir = Path(__file__).resolve().parent.parent / "backends" / "data"
    data_dir.mkdir(exist_ok=True, parents=True) # Ensure it exists
    filepath = data_dir / filename
    
    try:
        # Write to local file
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(full_output)
            
        # Send the file
        file_to_send = discord.File(filepath, filename=filename)
        await ctx.respond(
            content=f"History saved to `{filepath}` and attached below.",
            file=file_to_send,
            ephemeral=True
        )
    except Exception as e:
        await ctx.respond(f"Error saving/sending history file: {e}", ephemeral=True)

import sys # Added for sys.exit

@bot.command(name="shutdown", description="Owner only shutdown/restart.")
async def shutdown(ctx):
    if str(ctx.author.id) != os.getenv("DISCORD_OWNER_ID"):
        await ctx.respond("You are not authorized to shutdown the bot.", ephemeral=True)
        return

    await ctx.defer()
    
    # Check if we should restart or just stop
    # In Client-Server, "shutdown" usually means stop. 
    # But if user wants restart, we can add a flag or separate command.
    # For now, let's assume this command toggles a restart if we use a specific arg?
    # Actually, legacy behavior was toggleable. 
    # Let's make this command just STOP, and rely on !restart for restart?
    # Or just use exit code 5 for restart, code 0 for stop.
    
    # Simple Toggle:
    # If used as !shutdown -> Stop (Code 0)
    # If used as !restart -> Restart (Code 5)
    
    # Since slash command name is fixed to "shutdown", let's just make it a STOP.
    # User can restart via TUI.
    
    # WAIT: User wants !restart capability.
    # Let's change this to a restart command or add keys.
    # Legacy: "Hard restart sequence engaged..." -> This implies restart.
    
    await ctx.respond("♻️ **Bot Restart Sequence Engaged** (Supervisor Pattern)")
    # We exit with Code 5. Launcher will restart us.
    await bot.close()
    sys.exit(5)

# --- Helpers ---
def get_session_id(ctx_or_msg):
    # Ensure we are looking at the channel, not the message/context itself
    if hasattr(ctx_or_msg, 'channel'):
        obj = ctx_or_msg.channel
    else:
        obj = ctx_or_msg
        
    # Basic mapping based on Channel Type
    if isinstance(obj, discord.Thread):  
        return f"discord-thread-{obj.parent.id}-{obj.id}"
    elif isinstance(obj, discord.DMChannel):
        return f"discord-dm-{obj.id}"
    elif hasattr(obj, 'id'): # TextChannel, VoiceChannel, etc.
        return f"discord-channel-{obj.id}"
    
    return f"discord-unknown-{id(obj)}" # Fallback

# --- Event: on_message ---
@bot.event
async def on_message(message: discord.Message):
    if message.author == bot.user: return
    
    # --- BUFFER LOGIC START ---
    try:
        # We buffer ALL messages from other users
        # Filter: Skip if it mentions the bot (it will be processed as a prompt anyway)
        # Note: Users might want context of "What did I just say to you?" but 
        # normally recent history contains the answer. 
        # The prompt says "ignore discord messages that specifically mentions the AI model".
        # So filtering mentions is correct.
        
        is_mentioning_bot = bot.user in message.mentions or isinstance(message.channel, discord.DMChannel)
        
        if not is_mentioning_bot:
            channel_id = message.channel.id
            if channel_id not in recent_messages_buffer:
                recent_messages_buffer[channel_id] = deque(maxlen=config.BUFFER_SIZE)
            
            # Metadata Extraction
            atts_meta = []
            if message.attachments:
                for a in message.attachments:
                    atts_meta.append({
                        "filename": a.filename,
                        "content_type": a.content_type or "unknown",
                        "size": f"{a.size // 1024}KB"
                    })
            
            msg_data = {
                "timestamp": message.created_at, # Datetime
                "author_name": message.author.display_name,
                "author_id": str(message.author.id),
                "content": message.clean_content,
                "attachments": atts_meta
            }
            
            recent_messages_buffer[channel_id].append(msg_data)
            logger.debug(f"[\033[96mBuffer Debug\033[0m] Channel {channel_id}: Appended message from {msg_data['author_name']}")
            
    except Exception as e:
        logger.error(f"Error in buffering message: {e}")
    # --- BUFFER LOGIC END ---
    
    if bot.user in message.mentions or isinstance(message.channel, discord.DMChannel):
        session_id = get_session_id(message)
        
        # 1. Mode Check (Default Stream = True)
        use_stream = streaming_preferences.get(session_id, True)
        
        # 2. Prepare Prompt
        user_prompt = message.clean_content.replace(f"@{bot.user.name}", "").strip()
        
        # --- Context Buffer Retrieval ---
        recent_context = ""
        channel_id = message.channel.id
        if channel_id in recent_messages_buffer:
            # Get the deque
            buffer = recent_messages_buffer[channel_id]
            
            # Format the context
            context_lines = [f"[Recent Channel Activity (Last {getattr(config, 'BUFFER_SIZE', 30)} Messages)]"]
            for msg_data in buffer:
                # msg_data = {timestamp, author_name, author_id, content, attachments[]}
                ts = msg_data['timestamp'].strftime("%H:%M:%S")
                meta = f"[{ts}] {msg_data['author_name']} (ID: {msg_data['author_id']}):"
                content = msg_data['content']
                
                # Attachments
                if msg_data['attachments']:
                    att_str = " ".join([f"[Attachment: {a['filename']} | Type: {a['content_type']} | Size: {a['size']}]" for a in msg_data['attachments']])
                    content += f" {att_str}"
                
                context_lines.append(f"{meta} {content}")
            
            if len(context_lines) > 1: # Only if we have history
                recent_context = "\n".join(context_lines) + "\n\n[Current Message]"
                
            # CLEAR BUFFER (As requested to prevent duplication)
            recent_messages_buffer[channel_id].clear()
            logger.debug(f"[\033[93mBuffer Debug\033[0m] Channel {channel_id}: Buffer cleared after context retrieval.")
        
        # File Handling
        file_check = []
        if message.attachments:
            for attachment in message.attachments:
                ctype = attachment.content_type or ""
                
                # Unified File Handling via Core (ASYNC)
                try: 
                    # 1. Download bytes
                    file_bytes = await attachment.read()
                    
                    # 2. Upload directly (ASYNC)
                    logger.info(f"Uploading {attachment.filename} ({len(file_bytes)} bytes)...")
                    
                    # DIRECT AWAIT - No run_in_executor needed for async methods
                    f = await core.async_upload_file(
                        mime_type=ctype, 
                        file_obj=file_bytes, 
                        display_name=attachment.filename
                    )

                    if f: 
                        file_check.append(f)
                        logger.info(f"Successfully uploaded: {attachment.filename}")
                    else:
                        logger.error(f"[\033[91mUpload Error\033[0m] Failed to upload {attachment.filename}")
                        user_prompt += f"\n[System: User attached file '{attachment.filename}' but it failed to process.]"
                except Exception as e:
                    logger.error(f"[\033[91mUpload Exception\033[0m] {e}")
                    user_prompt += f"\n[System: Error reading attachment '{attachment.filename}': {e}]"

        if recent_context:
             # Prepend context to the prompt
             user_prompt = f"{recent_context}\n\n{user_prompt}"

        # 3. Initial "Thinking" Message
        response_msg = await message.reply("*[Orion is thinking...]*")
        
        # 4. Call Core (Async Generator) - DIRECT
        # No blocking_get_gen, no to_thread. Just call the async generator method.
        generator = core.async_process_prompt(
            session_id=session_id,
            user_prompt=user_prompt,
            file_check=file_check,
            user_id=str(message.author.id),
            user_name=message.author.name,
            stream=use_stream
        )
        
        # 5. Consume (Streams updates to response_msg)
        # We await the consumer, which iterates the generator.
        should_restart = await consume_generator_async(generator, response_msg)
        
        # 6. Restart if needed
        if should_restart:
             logger.info("--- RESTART TRIGGERED BY CHAT ---")
             if core.save_state_for_restart():
                 core.execute_restart()

if __name__ == "__main__":
    if BOT_TOKEN:
        logger.info("--- Starting Discord Bot Client ---")
        
        # --- LOAD COGS ---
        cogs_dir = Path(__file__).resolve().parent / "cogs"
        if cogs_dir.exists():
            for filename in os.listdir(cogs_dir):
                if filename.endswith(".py"):
                    try:
                        bot.load_extension(f"cogs.{filename[:-3]}")
                        logger.info(f"Loaded Cog: {filename}")
                    except Exception as e:
                        logger.error(f"Failed to load cog {filename}: {e}")

        try:
            bot.run(BOT_TOKEN)
        except Exception as e:
            logger.critical(f"Bot Crashed: {e}")
    else:
        logger.critical("ERROR: NO TOKEN")