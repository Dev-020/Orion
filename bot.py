# bot.py (Final Refactored Version)

import discord
import os
import asyncio
from dotenv import load_dotenv
from orion_core import OrionCore
from discord.ext import commands

# All genai and file processing (fitz) imports are now removed.

# Load environment variables
load_dotenv()
MAX_TEXT_FILE_SIZE = 51200  # 50 * 1024 bytes
persona = os.getenv("ORION_PERSONA", "default")
print(f"--- Bot starting with Persona: {persona} ---")

# --- Configuration ---
BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN")

# The flag file is no longer needed as the AI will manage its own refresh.

# --- Bot Setup ---
intents = discord.Intents.default()
intents.message_content = True
bot = discord.Bot(intents=intents, debug_guilds=[os.getenv("DISCORD_GUILD_ID")] if os.getenv("DISCORD_GUILD_ID") else None)

# --- The single, unified instance of Orion's "Brain" ---
core = OrionCore(persona=persona) 
# Attach the core to the bot instance so cogs can access it
bot.core = core

# --- Security Check (is_owner) remains the same ---
def is_owner():
    def predicate(ctx: discord.ApplicationContext) -> bool:
        owner_id = os.getenv("DISCORD_OWNER_ID")
        if not owner_id: return False
        return str(ctx.author.id) == owner_id
    return commands.check(predicate)

# --- Event: on_ready remains the same ---
@bot.event
async def on_ready():
    print(f"--- {bot.user} has connected to Discord! ---")
    print(f"--- Operating on {len(bot.guilds)} servers. ---")

# --- Persona-Specific Commands ---
if persona == "dnd":
    print("--- Loading D&D commands cog... ---")
    bot.load_extension("cogs.dnd_commands")

# --- Event: on_message (Final Refactored Logic) ---
@bot.event
async def on_message(message: discord.Message):
    """This function runs every time a message is sent."""
    if message.author == bot.user:
        return

    if bot.user in message.mentions:
        async with message.channel.typing():
            
            # The hot-swap trigger is now handled internally by the AI, so the flag file check is removed.

            # --- Hybrid Session ID Logic ---
            if isinstance(message.channel, discord.Thread):
                # It's a thread, so we create a more specific ID that includes the parent channel
                session_id = f"discord-thread-{message.channel.parent.id}-{message.channel.id}"
            elif message.guild: # It's a regular channel in a server
                session_id = f"discord-channel-{message.channel.id}"
            else: # Message is in a DM
                session_id = f"discord-dm-{message.author.id}"

            # --- Streamlined Multimodal Prompt Construction ---
            user_prompt = message.clean_content.replace(f"@{bot.user.name}", "").strip()

            file_check = []
            if message.attachments:
                for attachment in message.attachments:
                    # Call the helper function in the core to handle the upload
                    if attachment.content_type and attachment.content_type.startswith('text/'):
                        # Check 2: Is the file within our size limit?
                        if attachment.size <= MAX_TEXT_FILE_SIZE:
                            try:
                                file_bytes = await attachment.read()
                                file_content = file_bytes.decode('utf-8')
                                user_prompt += f"\n\n--- ATTACHED FILE: {attachment.filename} ---\n\n{file_content}"
                                print(f"-> Appended content of '{attachment.filename}' to the prompt.")
                            except Exception as e:
                                print(f"-> ERROR: Failed to read or decode '{attachment.filename}': {e}")
                                user_prompt += f"\n\n[System Note: User attached a file named '{attachment.filename}', but it could not be read.]"
                        else:
                            # The file is too large, so we add a note instead of the content.
                            file_size_kb = round(attachment.size / 1024, 2)
                            print(f"-> SKIPPED '{attachment.filename}' because it is too large ({file_size_kb} KB).")
                            user_prompt += f"\n\n[System Note: The user attached a text file named '{attachment.filename}' ({file_size_kb} KB), which was too large to be read directly. Inform the user that you cannot read the file due to its size.]"
                    else:
                        try:
                            file = core.upload_file(
                                file_bytes=await attachment.read(),
                                display_name=attachment.filename,
                                mime_type=attachment.content_type or ""
                            )
                            if file:
                                file_check.append(file)
                            if not file:
                                await message.reply(f"[Sorry, I couldn't upload the attachment'{attachment.filename}'.")
                        except Exception as e:
                            print(f"ERROR: Failed to upload attachment '{attachment.filename}': {e}")
                            await message.reply(f"Sorry, I couldn't process the attachment '{attachment.filename}'.")
            
            # The call to the core is now clean, passing a list of parts.
            response_text, token_count, restart_pending = await asyncio.to_thread(
                core.process_prompt, 
                session_id=session_id,
                user_prompt=user_prompt,
                file_check=file_check,
                user_id=str(message.author.id),
                user_name=message.author.name
            )
            
            # --- Message sending logic with token count display ---
            if response_text and response_text.strip():
                for i in range(0, len(response_text), 1980):
                    chunk = response_text[i:i + 1980]
                    if i + 1980 >= len(response_text):
                        await message.reply(f"{chunk}\n\n*(`Tokens: {token_count}`)*")
                    else:
                        await message.reply(chunk)
            else:
                print(f"AI returned an empty response for user {message.author.name}. No message sent.")
            
            # --- Orchestrated Restart Logic ---
            if restart_pending:
                print("---! DELAYED RESTART SEQUENCE ACTIVATED !---")
                if core.save_state_for_restart():
                    core.execute_restart() # This will terminate the bot.py process

# --- Shutdown command remains the same ---
@bot.command(name="shutdown", description="Shuts down the bot gracefully. (Owner only)")
@is_owner()
async def shutdown(
    ctx: discord.ApplicationContext,
    mode: discord.Option(str, "Choose the action: 'soft' (hot-swap), 'hard' (restart), 'poweroff' (shutdown).", choices=['soft', 'hard', 'poweroff'], default='poweroff')
):
    """Manages the bot's operational state: hot-swap, restart, or full shutdown."""
    if mode == 'soft':
        await ctx.respond("Acknowledged. Initiating a 'soft' hot-swap of instructions and tools...", ephemeral=True)
        # Run the synchronous hot-swap in a separate thread to avoid blocking
        await asyncio.to_thread(core.trigger_instruction_refresh, full_restart=False)
        await ctx.followup.send("Hot-swap complete. All sessions have been migrated.", ephemeral=True)

    elif mode == 'hard':
        await ctx.respond("Acknowledged. Initiating a 'hard' orchestrated restart. Saving state...", ephemeral=True)
        # Replicate the restart logic from on_message
        if core.save_state_for_restart():
            await ctx.followup.send("State saved. Executing restart now.", ephemeral=True)
            core.execute_restart() # This will terminate and restart the process

    else: # 'poweroff'
        await ctx.respond("Acknowledged. Shutting down completely.", ephemeral=True)
        core.shutdown()
        await bot.close()

if __name__ == "__main__":
    if BOT_TOKEN:
        try:
            print("--- Starting Bot ---")
            bot.run(BOT_TOKEN)
        except KeyboardInterrupt:
            # When Ctrl+C is pressed, bot.run() handles the graceful shutdown.
            # This block is here to catch the interrupt and prevent an ugly traceback,
            # allowing the program to exit cleanly after bot.run() finishes its cleanup.
            print("\n--- Ctrl+C detected. Shutting down gracefully. ---")
    else:
        print("FATAL ERROR: DISCORD_BOT_TOKEN not found in .env file.")