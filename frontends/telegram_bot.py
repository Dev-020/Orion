# telegram_bot.py (Refactored for Orion Client-Server Architecture)

import os
import sys
import asyncio
import logging
import io
import time
from pathlib import Path
from dotenv import load_dotenv
from collections import deque

# --- PATH HACK ---
# Add 'backends' to sys.path so we can import 'orion_client', 'main_utils', etc.
sys.path.append(str(Path(__file__).resolve().parent.parent / 'backends'))

from telegram import Update, constants
from telegram.ext import ApplicationBuilder, ContextTypes, CommandHandler, MessageHandler, filters
from telegram.error import RetryAfter, TelegramError

from orion_client import OrionClient
from main_utils import config
from main_utils.orion_logger import setup_logging

# 1. Config Override
config.VOICE = False
config.VISION = False

# --- LOGGING SETUP ---
LOG_FILE = config.DATA_DIR / "logs" / "telegram.log"
logger = setup_logging("TelegramBot", LOG_FILE, level=logging.INFO)

# --- Load Environment ---
load_dotenv()
BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
ALLOWED_USERS = os.getenv("TELEGRAM_ALLOWED_USERS", "").split(",")
ALLOWED_USERS = [u.strip() for u in ALLOWED_USERS if u.strip()]

if not BOT_TOKEN:
    logger.critical("ERROR: TELEGRAM_BOT_TOKEN not found in .env")
    sys.exit(1)

persona = os.getenv("ORION_PERSONA", "default")
logger.info(f"--- Telegram Bot starting with Persona: {persona} (Voice/Vision Disabled) ---")

# --- Initializing Orion Client ---
core = OrionClient(base_url="http://127.0.0.1:8000")

# --- Global Activity Buffer & Preferences ---
streaming_preferences = {} # session_id -> bool
# Map: chat_id -> deque of dicts
recent_messages_buffer = {} 
# Note: In Telegram, we only buffer what we see. 
# If bot is admin or privacy mode is off, it sees everything.

# --- Helper: Get Session ID ---
def get_session_id(update: Update):
    if update.effective_chat.type == constants.ChatType.PRIVATE:
        return f"telegram-dm-{update.effective_user.id}"
    return f"telegram-group-{update.effective_chat.id}"

# --- Security Decorator ---
def restricted(func):
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user_id = str(update.effective_user.id)
        if ALLOWED_USERS and user_id not in ALLOWED_USERS:
            logger.warning(f"Unauthorized access attempt from user ID: {user_id}")
            await update.message.reply_text("You are not authorized to use this bot.")
            return
        return await func(update, context)
    return wrapper

# --- Message Chain Helper (mirrors Discord's update_message_chain) ---
# --- Message Chain Helper ---
async def update_message_chain_tg(chat, chain, full_text, parse_mode=constants.ParseMode.HTML):
    """
    Telegram equivalent of Discord's update_message_chain.
    Splits text into chunks, ensures each chunk is valid HTML/Markdown,
    and updates the message chain.
    """
    CHUNK_SIZE = 4000 
    
    # If using HTML, we must ensure each chunk is valid on its own
    if parse_mode == constants.ParseMode.HTML:
        # We split the raw HTML-converted text first
        text_chunks = [full_text[i:i+CHUNK_SIZE] for i in range(0, len(full_text), CHUNK_SIZE)]
        # Then we fix each chunk
        text_chunks = [ensure_valid_html(chunk) for chunk in text_chunks]
    else:
        text_chunks = [full_text[i:i+CHUNK_SIZE] for i in range(0, len(full_text), CHUNK_SIZE)]

    if not text_chunks:
        text_chunks = [""]

    for i, chunk in enumerate(text_chunks):
        if i < len(chain):
            try:
                # Content diff check to reduce API calls
                # Note: Telegram Message objects don't reliably store .text if it was HTML
                # so we just try to edit.
                await chain[i].edit_text(chunk, parse_mode=parse_mode)
            except RetryAfter as e:
                await asyncio.sleep(e.retry_after)
                try: await chain[i].edit_text(chunk, parse_mode=parse_mode)
                except: pass
            except TelegramError as e:
                if "Message is not modified" not in str(e):
                    logger.debug(f"[Chain Edit] {e}")
        else:
            try:
                new_msg = await chat.send_message(chunk, parse_mode=parse_mode)
                chain.append(new_msg)
            except RetryAfter as e:
                await asyncio.sleep(e.retry_after)
                new_msg = await chat.send_message(chunk, parse_mode=parse_mode)
                chain.append(new_msg)
            except TelegramError as e:
                logger.error(f"[Chain Overflow] {e}")

    return chain


import html
import re

def markdown_to_html(text):
    """
    Markdown to HTML converter for Telegram HTML parse_mode.
    Does NOT include auto-closing (handled by ensure_valid_html).
    """
    # 1. Escape HTML first
    text = html.escape(text)
    
    # 2. Convert Bold: **text** -> <b>text</b>
    text = re.sub(r'\*\*(.*?)\*\*', r'<b>\1</b>', text)
    
    # 3. Convert Code: `text` -> <code>text</code>
    text = re.sub(r'`(.*?)`', r'<code>\1</code>', text)
    
    # 4. Convert Links: [text](url) -> <a href="\2">\1</a>
    text = re.sub(r'\[(.*?)\]\((.*?)\)', r'<a href="\2">\1</a>', text)

    return text

def ensure_valid_html(text):
    """
    Ghost Tag (Auto-Closer) strategy using a stack to ensure 
    nested tags are closed in the correct order for a single message.
    """
    # Handle raw Markdown mid-stream artifacts first
    if text.count("**") % 2 != 0:
        last_idx = text.rfind("**")
        if last_idx != -1:
            text = text[:last_idx] + "<b>" + text[last_idx+2:]
    
    if text.count("`") % 2 != 0:
        last_idx = text.rfind("`")
        if last_idx != -1:
            text = text[:last_idx] + "<code>" + text[last_idx+1:]

    # Stack-based HTML tag closer
    # Detects <b>, <i>, <code>, <u>, <s>, <a>, <blockquote>
    tags = re.findall(r'<(/?)([a-z1-6]+)(?: [^>]*)?>', text, re.IGNORECASE)
    stack = []
    for is_closing, tag_name in tags:
        tag_name = tag_name.lower()
        if is_closing:
            if stack and stack[-1] == tag_name:
                stack.pop()
        else:
            stack.append(tag_name)
    
    # Close any remaining tags in the stack in reverse order
    for tag_name in reversed(stack):
        text += f"</{tag_name}>"

    return text

# --- Async Generator Consumer ---
# --- Async Generator Consumer ---
async def consume_generator_async(generator, initial_message):
    """
    Generic Orion protocol consumer for Telegram.
    Handles 'thought' and 'token' events, providing real-time feedback and clean transitions.
    """
    full_text_buffer = ""
    last_edit_time = 0
    edit_interval = config.EDIT_TIME
    
    # Track pagination & chain
    message_chain = [initial_message]
    chat = initial_message.chat
    thought_buffer = ""
    is_thinking = True 

    def get_display_text(is_thought_phase=True):
        """Helper to format text based on phase."""
        text = ""
        if is_thought_phase:
            if thought_buffer:
                formatted_thoughts = markdown_to_html(thought_buffer.strip())
                text += f"<b>Thinking Process:</b>\n<blockquote>{formatted_thoughts}</blockquote>\n\n"
            text += markdown_to_html(full_text_buffer)
        else:
            text += markdown_to_html(full_text_buffer)
        return text

    try:
        should_restart = False
        
        async for item in generator:
            if not isinstance(item, dict): continue
            
            msg_type = item.get("type")
            content = item.get("content")
            
            if msg_type == "thought":
                thought_buffer += content
                now = time.time()
                if now - last_edit_time > edit_interval:
                    display_text = get_display_text(is_thought_phase=True)
                    message_chain = await update_message_chain_tg(chat, message_chain, display_text)
                    last_edit_time = now

            elif msg_type == "token":
                # TRANSITION DETECT
                if is_thinking and thought_buffer:
                    is_thinking = False
                    logger.info(f"[Transition] Thought→Response. Thought length: {len(thought_buffer)}")
                    
                    # 1. Solidification Deduplication: 
                    # If the backend yielded thoughts and then "promoted" them to a token,
                    # we must strip that token from the end of the thought buffer.
                    clean_thoughts = thought_buffer.strip()
                    clean_token = content.strip()
                    if clean_thoughts.endswith(clean_token):
                        # Strip redundant answer from thoughts
                        thought_buffer = clean_thoughts[:-len(clean_token)].strip()
                        logger.debug("[Transition] Stripped redundant answer from thought process.")

                    # 2. Convert Thoughts to File (if non-empty)
                    if thought_buffer:
                        try:
                            thought_file = io.BytesIO(thought_buffer.encode('utf-8'))
                            await initial_message.reply_document(
                                document=thought_file,
                                filename="thought_process.md",
                                caption="<b>Thinking Process</b>",
                                parse_mode=constants.ParseMode.HTML
                            )
                        except Exception as e:
                            logger.error(f"Failed to send thought file: {e}")
                    
                    # 3. Cleanup: Delete the Thinking Chain
                    for msg in message_chain:
                        try: await msg.delete()
                        except: pass

                    # 4. Start Response in NEW Chain
                    new_msg = await chat.send_message(markdown_to_html(content), parse_mode=constants.ParseMode.HTML)
                    message_chain = [new_msg]
                    full_text_buffer = content
                    
                    last_edit_time = time.time()
                    continue 

                is_thinking = False # Out of thinking mode
                full_text_buffer += content
                
                # Throttled Edit
                now = time.time()
                if now - last_edit_time > edit_interval:
                    display_text = get_display_text(is_thought_phase=False)
                    message_chain = await update_message_chain_tg(chat, message_chain, display_text)
                    last_edit_time = now

            elif msg_type == "full_response":
                full_text_buffer = item.get("text", "")
                should_restart = item.get("restart_pending", False)

            elif msg_type == "usage":
                should_restart = item.get("restart_pending", False)

            elif msg_type == "error":
                full_text_buffer += f"\n\n[System Error: {content}]"
                display_text = get_display_text(is_thought_phase=is_thinking)
                await update_message_chain_tg(chat, message_chain, display_text)

        # Final Flush
        if is_thinking and thought_buffer:
            # Case: Only thoughts (no tokens arrived before stream closed)
            try:
                # Same Deduplication for the final flush
                if full_text_buffer and thought_buffer.strip().endswith(full_text_buffer.strip()):
                    thought_buffer = thought_buffer.strip()[:-len(full_text_buffer.strip())].strip()

                if thought_buffer:
                    thought_file = io.BytesIO(thought_buffer.encode('utf-8'))
                    await initial_message.reply_document(
                        document=thought_file, 
                        filename="thought_process.md",
                        caption="<b>Thinking Process (Final)</b>",
                        parse_mode=constants.ParseMode.HTML
                    )
                
                for msg in message_chain:
                    try: await msg.delete()
                    except: pass
                
                if full_text_buffer:
                     await chat.send_message(markdown_to_html(full_text_buffer), parse_mode=constants.ParseMode.HTML)
                else:
                     await chat.send_message("<b>Done Thinking.</b>", parse_mode=constants.ParseMode.HTML)
            except: pass
        else:
            await update_message_chain_tg(chat, message_chain, get_display_text(is_thought_phase=False))

        return should_restart

    except Exception as e:
        logger.error(f"[Consumer Error] {e}")
        try:
            await update_message_chain_tg(chat, message_chain, f"{full_text_buffer}\n\n[Error: {e}]")
        except: pass
    
    return False

# --- Telegram Handlers ---

@restricted
async def start_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    logger.info(f"[\033[96mCommand\033[0m] /start from {update.effective_user.first_name}")
    await update.message.reply_text("Hello! I am Orion. How can I help you today?")

@restricted
async def mode_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    args = context.args
    user_name = update.effective_user.first_name
    if not args:
        await update.message.reply_text("Usage: /mode <cache|function>")
        return
    mode = args[0].lower()
    session_id = get_session_id(update)
    logger.info(f"[\033[96mCommand\033[0m] /mode {mode} from {user_name} (Session: {session_id})")
    try:
        result = core.set_session_mode(session_id, mode)
        await update.message.reply_text(f"Session mode set to: **{mode}**")
    except Exception as e:
        logger.error(f"[\033[91mCommand Error\033[0m] Failed to set mode: {e}")
        await update.message.reply_text(f"Error setting mode: {e}")

@restricted
async def history_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    session_id = get_session_id(update)
    user_name = update.effective_user.first_name
    logger.info(f"[\033[96mCommand\033[0m] /history from {user_name} (Session: {session_id})")
    
    try:
        # Note: server.py /get_history endpoint handles sanitization
        # but OrionClient.sessions[id] is the legacy-ish property way used in bot.py
        # Let's use the explicit way if possible or emulate bot.py
        history_list = core.chat.get_session(session_id) 
        
        if not history_list:
            await update.message.reply_text(f"No history found for session `{session_id}`.")
            return

        # Formatter
        lines = [f"Chat History for Session: {session_id}", "="*40, ""]
        for i, exchange in enumerate(history_list):
            lines.append(f"--- Exchange {i+1} ---")
            
            def get_text(content_obj):
                text = ""
                try:
                    if hasattr(content_obj, "parts"):
                        for part in content_obj.parts:
                            if hasattr(part, "text") and part.text:
                                text += part.text
                    elif isinstance(content_obj, dict):
                         if "parts" in content_obj:
                             for part in content_obj["parts"]:
                                 if isinstance(part, dict): text += part.get("text", "")
                                 elif hasattr(part, "text"): text += part.text
                except Exception: text = "[Error extracting content]"
                return text.strip()

            user_text = get_text(exchange.get("user_content"))
            model_text = get_text(exchange.get("model_content"))
            
            lines.append(f"User: {user_text}")
            lines.append(f"Orion: {model_text}")
            lines.append("-" * 20 + "\n")

        full_output = "\n".join(lines)
        
        # Save to data directory
        filename = f"history_{session_id}.txt"
        data_dir = config.DATA_DIR / "history"
        data_dir.mkdir(exist_ok=True, parents=True)
        filepath = data_dir / filename
        
        with open(filepath, "w", encoding="utf-8") as f:
            f.write(full_output)
            
        # Send the file
        with open(filepath, "rb") as f:
            await update.message.reply_document(
                document=f,
                filename=filename,
                caption=f"Chat history for session `{session_id}`"
            )
            
    except Exception as e:
        logger.error(f"[\033[91mCommand Error\033[0m] Failed to handle /history: {e}")
        await update.message.reply_text(f"Error retrieving history: {e}")

@restricted
async def handle_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    message = update.message
    if not message: return
    
    session_id = get_session_id(update)
    user_name = message.from_user.first_name
    chat_id = update.effective_chat.id
    
    # --- BUFFER LOGIC (Mirroring bot.py) ---
    if chat_id not in recent_messages_buffer:
        recent_messages_buffer[chat_id] = deque(maxlen=config.BUFFER_SIZE)
    
    msg_data = {
        "timestamp": message.date,
        "author_name": user_name,
        "author_id": str(message.from_user.id),
        "content": message.text or message.caption or "",
        "attachments": [] # Simplified for now
    }
    recent_messages_buffer[chat_id].append(msg_data)
    logger.debug(f"[\033[96mBuffer Debug\033[0m] Chat {chat_id}: Appended message from {user_name}")
    # --- END BUFFER LOGIC ---

    logger.info(f"[\033[96mMessage\033[0m] Received from {user_name} (ID: {message.from_user.id}) in {session_id}")
    
    user_prompt = message.text or message.caption or ""
    
    # 1. Handle Attachments
    file_check = []
    if message.document or message.photo:
        # Use first photo in list (highest resolution)
        tg_file = message.document if message.document else message.photo[-1]
        
        # Download
        mime_type = getattr(tg_file, 'mime_type', 'image/jpeg' if message.photo else 'application/octet-stream')
        filename = getattr(tg_file, 'file_name', f"tg_file_{tg_file.file_id[:8]}")
        
        try:
            logger.info(f"[\033[96mUpload\033[0m] Processing attachment: {filename} ({mime_type})")
            status_msg = await message.reply_text(f"Processing attachment: {filename}...")
            file_info = await context.bot.get_file(tg_file.file_id)
            file_bytes = await file_info.download_as_bytearray()
            
            # Upload to Orion Server
            logger.info(f"[\033[96mUpload\033[0m] Sending {filename} to Orion Server...")
            uploaded_file = await core.async_upload_file(
                file_obj=bytes(file_bytes),
                mime_type=mime_type,
                display_name=filename
            )
            
            if uploaded_file:
                logger.info(f"[\033[92mUpload Success\033[0m] {filename} uploaded successfully.")
                file_check.append(uploaded_file)
                await status_msg.delete()
            else:
                logger.error(f"[\033[91mUpload Error\033[0m] Server refused upload for {filename}")
                await status_msg.edit_text(f"Failed to process {filename} on server.")
        except Exception as e:
            logger.error(f"[\033[91mUpload Exception\033[0m] {e}")
            user_prompt += f"\n[System: Error processing attachment: {e}]"

    # 2. Call Orion
    # Clear buffer after context is retrieved (if we were to send context)
    # For now, we mirror the 'cleared' log if we use it.
    # recent_messages_buffer[chat_id].clear()
    # logger.debug(f"[\033[93mBuffer Debug\033[0m] Chat {chat_id}: Buffer cleared after context retrieval.")

    wait_msg = await message.reply_text("<i>[Orion is thinking...]</i>", parse_mode=constants.ParseMode.HTML)
    
    use_stream = streaming_preferences.get(session_id, True)
    
    generator = core.async_process_prompt(
        session_id=session_id,
        user_prompt=user_prompt,
        file_check=file_check,
        user_id=str(message.from_user.id),
        user_name=message.from_user.first_name,
        stream=use_stream
    )
    
    should_restart = await consume_generator_async(generator, wait_msg)
    
    if should_restart:
        logger.info("--- RESTART TRIGGERED BY CHAT ---")
        # Launcher handles restart if we exit with 5
        sys.exit(5)

if __name__ == "__main__":
    logger.info("--- Starting Telegram Bot ---")
    application = ApplicationBuilder().token(BOT_TOKEN).build()
    
    # Handlers
    application.add_handler(CommandHandler("start", start_command))
    application.add_handler(CommandHandler("mode", mode_command))
    application.add_handler(CommandHandler("history", history_command))
    
    # Message handler (Text & Files)
    application.add_handler(MessageHandler(filters.TEXT | filters.ATTACHMENT, handle_message))
    
    application.run_polling()
