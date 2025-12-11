# bot.py (Refactored for Generator API & Mode Switching)

import discord
import os
import asyncio
import time
import io
from dotenv import load_dotenv  
from discord.ext import commands
import threading

# 1. Config Override (Must be before OrionCore init)
from main_utils import config
config.VOICE = False
config.VISION = False

# --- One "Brain" ---
# Load environment variables
load_dotenv()
MAX_TEXT_FILE_SIZE = 15360  # 15 * 1024 bytes (approx 3-4k tokens)
persona = os.getenv("ORION_PERSONA", "default")
print(f"--- Bot starting with Persona: {persona} (Voice/Vision Disabled) ---")

# --- Configuration ---
BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN")

# --- Bot Setup ---
intents = discord.Intents.default()
intents.message_content = True
bot = discord.Bot(intents=intents, debug_guilds=[os.getenv("DISCORD_GUILD_ID")] if os.getenv("DISCORD_GUILD_ID") else None)

# Selector Logic: Use Lite Core for Gemma/Ollama, Pro Core for everything else
if "gemma" in config.AI_MODEL.lower() or getattr(config, 'BACKEND', 'api') == 'ollama':
    try:
        from orion_core_lite import OrionLiteCore as OrionCore
        print(f"--- Loaded Orion Lite Core (Backend: {getattr(config, 'BACKEND', 'api')}) ---")
    except Exception as e:
        print(f"CRITICAL ERROR loading Lite Core: {e}")
        from orion_core import OrionCore
        print("--- Fallback to Orion Pro Core ---")
else:
    from orion_core import OrionCore
    print("--- Loaded Orion Pro Core ---")

core = OrionCore(persona=persona) 
bot.core = core

# --- Session Preferences ---
# simple dict: session_id -> bool (True=Stream, False=Full)
streaming_preferences = {}

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
        # fix: iterate asynchronously if the generator is async, 
        # BUT OrionCore currently returns a synchronous generator in a thread usually?
        # Actually core.process_prompt is a standard generator, so we iterate synchronously 
        # but we might be running this in a thread. 
        # However, we are in an async function here. 
        # To keep the bot responsive, we should probably iterate direct if it's a generator,
        # but since core blocks, we really should have run the whole process_prompt in a thread.
        # Let's adjust: process_prompt is a generator. We need to iterate it. 
        # If we iterate it in the main loop, it blocks.
        # So we need to wrap the *iteration* in a thread or use an async wrapper.
        # Since core is sync, we'll do the "run_in_executor" dance for each Step? No, that's inefficient.
        # Better: run the Consumer in a thread, but the consumer needs to await bot.edit. 
        # This is tricky mixing sync generator with async discord calls.
        
        # SOLUTION: We will not use 'async for' because core is sync.
        # We will use a dedicated thread to consume the generator, push updates to a queue,
        # and a local async loop to read the queue and update Discord.
        
        queue = asyncio.Queue()
        
        def generator_producer():
            try:
                for item in generator:
                    asyncio.run_coroutine_threadsafe(queue.put(item), bot.loop)
                asyncio.run_coroutine_threadsafe(queue.put("DONE"), bot.loop)
            except Exception as e:
                asyncio.run_coroutine_threadsafe(queue.put({"type": "error", "content": str(e)}), bot.loop)

        # Start producer thread
        producer_thread = threading.Thread(target=generator_producer)
        producer_thread.start()
        
    # Consumer loop (Async)
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
        
        while True:
            item = await queue.get()
            if item == "DONE":
                break
                
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
                            print(f"Failed to attach thought file: {e}")
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
            
            queue.task_done()
        
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
        print(f"Error in consumer: {e}")
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
    filepath = os.path.join("data", filename)
    
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

@bot.command(name="shutdown", description="Owner only shutdown/restart.")
async def shutdown(ctx, mode: str = 'poweroff'):
    if str(ctx.author.id) != os.getenv("DISCORD_OWNER_ID"): return
    if mode == 'soft':
        await ctx.respond("Soft refreshing instructions...")
        await asyncio.to_thread(core.trigger_instruction_refresh, full_restart=False)
        await ctx.send("Refresh complete.")
    elif mode == 'hard':
        await ctx.respond("Hard restart sequence engaged...")
        if core.save_state_for_restart():
            core.execute_restart()
    else:
        await ctx.respond("Shutting down.")
        await bot.close()

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
    
    if bot.user in message.mentions or isinstance(message.channel, discord.DMChannel):
        session_id = get_session_id(message)
        
        # 1. Mode Check (Default Stream = True)
        use_stream = streaming_preferences.get(session_id, True)
        
        # 2. Prepare Prompt
        user_prompt = message.clean_content.replace(f"@{bot.user.name}", "").strip()
        
        # File Handling
        file_check = []
        if message.attachments:
            for attachment in message.attachments:
                ctype = attachment.content_type or ""
                
                # A. Text Files (Inject Content + Metadata)
                is_text = ctype.startswith('text/') or ctype in ['application/json', 'application/xml']
                is_text_ext = attachment.filename.lower().endswith(config.TEXT_FILE_EXTENSIONS)
                
                if is_text or is_text_ext:
                     if attachment.size <= MAX_TEXT_FILE_SIZE:
                         try:
                             content = (await attachment.read()).decode('utf-8')
                             user_prompt += f"\n\n--- FILE: {attachment.filename} ---\n{content}"
                             
                             # Create Metadata Object for DB tracking
                             from types import SimpleNamespace
                             text_file_obj = SimpleNamespace(
                                 display_name=attachment.filename,
                                 mime_type=ctype,
                                 size_bytes=attachment.size,
                                 uri="text://injected" # Marker for Core to NOT upload
                             )
                             file_check.append(text_file_obj)
                         except: 
                             user_prompt += f"\n[System: Could not read text file '{attachment.filename}']"
                
                # B. Supported Media (Upload to File API)
                elif ctype.startswith(('image/', 'audio/', 'video/', 'application/pdf')):
                    try: 
                        f = core.upload_file(await attachment.read(), attachment.filename, ctype)
                        if f: file_check.append(f)
                    except: pass
                
                # C. Unsupported (Notify AI)
                else:
                    user_prompt += f"\n[System: User attached unsupported file '{attachment.filename}' (Type: {ctype}). File was discarded.]"

        # 3. Initial "Thinking" Message
        response_msg = await message.reply("*[Orion is thinking...]*")
        
        # 4. Call Core (Generator)
        def blocking_get_gen():
            return core.process_prompt(
                session_id=session_id,
                user_prompt=user_prompt,
                file_check=file_check,
                user_id=str(message.author.id),
                user_name=message.author.name,
                stream=use_stream
            )
        
        generator = await asyncio.to_thread(blocking_get_gen)
        
        # 5. Consume (Streams updates to response_msg)
        should_restart = await consume_generator_async(generator, response_msg)
        
        # 6. Restart if needed
        if should_restart:
             print("--- RESTART TRIGGERED BY CHAT ---")
             if core.save_state_for_restart():
                 core.execute_restart()

if __name__ == "__main__":
    if BOT_TOKEN:
        bot.run(BOT_TOKEN)
    else:
        print("ERROR: NO TOKEN")