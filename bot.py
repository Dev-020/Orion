# bot.py (Final Refactored Version)

import discord
import os
import asyncio
from dotenv import load_dotenv
from orion_core import OrionCore
from discord.ext import commands
import functions

# All genai and file processing (fitz) imports are now removed.

# Load environment variables
load_dotenv()
MAX_TEXT_FILE_SIZE = 51200  # 50 * 1024 bytes

# --- Configuration ---
BOT_TOKEN = os.getenv("DISCORD_BOT_TOKEN")

# The flag file is no longer needed as the AI will manage its own refresh.

# --- Bot Setup ---
intents = discord.Intents.default()
intents.message_content = True
bot = discord.Bot(intents=intents)

# --- The single, unified instance of Orion's "Brain" ---
core = OrionCore()

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

# --- Command: /lookup (New) ---
@bot.command(name="lookup", description="Performs a targeted search of Orion's knowledge base.")
async def lookup(
    ctx: discord.ApplicationContext,
    query: discord.Option(str, "A general search term for a summary list (e.g., 'fireball', 'eldritch blast', 'divine smite').", required=False, default=None),
    id: discord.Option(str, "The specific ID of an item to get its full details.", required=False, default=None),
    item_type: discord.Option(str, "Filter by a specific type (valid types: 'spells', 'misc', 'bestiary', 'adventure', 'book').", required=False, default=None),
    source: discord.Option(str, "Filter by a specific source (e.g., 'PHB', 'DMG', 'XGE', 'XPHB').", required=False, default=None),
    max_results: discord.Option(int, "The maximum number of results to return. (default is 25)", default=25)
):
    """
    Executes a knowledge base search, then passes the result to Orion for formatting.
    """
    await ctx.defer()

    if not query and not id:
        await ctx.respond("Please provide either a `query` for a summary search or an `id` for a detailed lookup.", ephemeral=True)
        return

    # 1. Directly execute the search using the trusted function
    search_result = None
    fallback_notification = ""
    if id:
        # An 'id' was provided, so we perform a 'full' lookup
        id_search_result = functions.search_knowledge_base(id=id, mode='full')
        # Check if the 'full' lookup failed. A successful result will be a JSON string.
        # A failed lookup returns a plain text error/info message.
        is_json = id_search_result.strip().startswith('{') or id_search_result.strip().startswith('[')
        if not is_json and query:
            # The ID lookup failed, but a query was also provided. Fall back to it.
            print(f"-> ID '{id}' not found. Falling back to query: '{query}'")
            fallback_notification = f"[System Note: The initial lookup for id='{id}' failed. The system has fallen back to a summary search for the query='{query}'. Inform the user about this fallback before presenting the results.]\n\n"
        else:
            search_result = id_search_result

    if query and search_result is None:
        # A 'query' was provided and either no 'id' was given or the 'id' fallback was triggered.
        search_result = functions.search_knowledge_base(
            query=query, item_type=item_type, source=source, mode='summary', max_results=max_results
        )

    # 2. Construct the prompt for Orion
    prompt_for_orion = f"{fallback_notification}A user performed a direct knowledge base lookup.\nThe raw JSON result is: {search_result}\n\nPlease present this information to the user in a clear, well-formatted, and easy-to-read manner. If it's a list of search results, make it scannable and include the `id` for each item. If it's a single detailed entry, structure it logically with headers."

    # 3. Get the session ID
    if isinstance(ctx.channel, discord.Thread):
        session_id = f"discord-thread-{ctx.channel.parent.id}-{ctx.channel.id}"
    elif ctx.guild:
        session_id = f"discord-channel-{ctx.channel.id}"
    else: # DM
        session_id = f"discord-dm-{ctx.author.id}"

    # 4. Process the prompt through the core
    response_text, token_count, _ = await asyncio.to_thread(
        core.process_prompt, session_id=session_id, user_prompt=prompt_for_orion, file_check=[],
        user_id=str(ctx.author.id), user_name=ctx.author.name
    )
    await ctx.respond(f"{response_text}\n\n*(`Tokens: {token_count}`)*")

# --- Command: /resource (New) ---
@bot.command(name="resource", description="Manage one of your character's resources (e.g., HP, spell slots).")
async def resource(
    ctx: discord.ApplicationContext,
    operation: discord.Option(str, "Choose the operation to perform.", choices=['set', 'add', 'subtract', 'create', 'view']),
    resource_name: discord.Option(str, "The name of the resource (e.g., 'HP'). Not needed to view all.", required=False, default=None),
    value: discord.Option(int, "The value to apply to the resource's current value.", required=False, default=None),
    max_value: discord.Option(int, "The value to apply to the resource's maximum value.", required=False, default=None)
):
    """
    Directly manages a character's resource and asks Orion to format the result.
    """
    await ctx.defer()

    if operation != 'view' and not resource_name:
        await ctx.respond(f"A `resource_name` is required for the '{operation}' operation.", ephemeral=True)
        return

    if operation == 'create' and value is None:
        await ctx.respond(f"A `value` is required for the 'create' operation.", ephemeral=True)
        return

    # 1. Execute the resource management function directly
    result = functions.manage_character_resource(
        user_id=str(ctx.author.id),
        operation=operation,
        resource_name=resource_name,
        value=value,
        max_value=max_value
    )

    # 2. Construct the prompt for Orion
    prompt_for_orion = f"A user just managed their character resource using the command `/resource`.\nThe raw result is: '{result}'\n\nPlease present this result to the user in a clear and concise confirmation message. Add narrative flair where appropriate (e.g., for taking damage or healing)."

    # 3. Get the session ID
    if isinstance(ctx.channel, discord.Thread):
        session_id = f"discord-thread-{ctx.channel.parent.id}-{ctx.channel.id}"
    elif ctx.guild:
        session_id = f"discord-channel-{ctx.channel.id}"
    else: # DM
        session_id = f"discord-dm-{ctx.author.id}"

    # 4. Process the prompt through the core
    response_text, token_count, _ = await asyncio.to_thread(
        core.process_prompt, session_id=session_id, user_prompt=prompt_for_orion, file_check=[],
        user_id=str(ctx.author.id), user_name=ctx.author.name
    )
    await ctx.respond(f"{response_text}\n\n*(`Tokens: {token_count}`)*")

# --- Command: /status (New) ---
@bot.command(name="status", description="Manage a temporary status effect on your character.")
async def status(
    ctx: discord.ApplicationContext,
    operation: discord.Option(str, "Choose whether to add, remove, update, or view an effect.", choices=['add', 'remove', 'update', 'view']),
    effect_name: discord.Option(str, "The name of the status effect. Not needed to view all.", required=False, default=None),
    details: discord.Option(str, "Add descriptive details for the status effect.", required=False, default=None),
    duration: discord.Option(int, "Set a duration in rounds for the effect.", required=False, default=None)
):
    """
    Directly manages a character's status effect and asks Orion to format the result.
    """
    await ctx.defer()

    if operation != 'view' and not effect_name:
        await ctx.respond(f"An `effect_name` is required for the '{operation}' operation.", ephemeral=True)
        return

    # 1. Execute the status management function directly
    result = functions.manage_character_status(
        user_id=str(ctx.author.id),
        operation=operation,
        effect_name=effect_name,
        details=details,
        duration=duration
    )

    # 2. Construct the prompt for Orion
    prompt_for_orion = f"A user just managed their character status using the command `/status`.\nThe raw result is: '{result}'\n\nPlease present this result to the user as a clear and concise confirmation message."

    # 3. Process the prompt through the core (session ID is not strictly needed but good for consistency)
    session_id = f"discord-dm-{ctx.author.id}" # Status effects are personal, so a DM session is a safe default
    response_text, token_count, _ = await asyncio.to_thread(
        core.process_prompt, session_id=session_id, user_prompt=prompt_for_orion, file_check=[],
        user_id=str(ctx.author.id), user_name=ctx.author.name
    )
    await ctx.respond(f"{response_text}\n\n*(`Tokens: {token_count}`)*")

# --- Command: /dice_roll (New) ---
@bot.command(name="dice_roll", description="Rolls dice and asks Orion to interpret the result.")
async def roll(
    ctx: discord.ApplicationContext,
    dice: str,
    reason: discord.Option(str, "The reason for this roll (e.g., 'to hit an goblin')", required=False, default=None)
):
    """
    Executes a dice roll, then passes the structured result to Orion for formatting.
    """
    await ctx.defer() # Acknowledge the command immediately

    # 1. Execute the dice roll using the trusted function
    roll_result = functions.roll_dice(dice)

    # 2. Construct the prompt for Orion
    prompt_for_orion = f"A user just performed a direct dice roll with the command `/dice_roll {dice}`."
    if reason:
        prompt_for_orion += f" The stated reason for the roll was: '{reason}'."
    prompt_for_orion += f"\n\nThe raw result of the roll is this JSON object: {roll_result}\n\nPlease present this result to the user in a clear and engaging D&D-style format. If the roll was a critical success or failure on a d20, add appropriate narrative flair."

    # 3. Get the session ID to maintain context
    if isinstance(ctx.channel, discord.Thread):
        session_id = f"discord-thread-{ctx.channel.parent.id}-{ctx.channel.id}"
    elif ctx.guild:
        session_id = f"discord-channel-{ctx.channel.id}"
    else: # DM
        session_id = f"discord-dm-{ctx.author.id}"

    # 4. Process the prompt through the core
    response_text, token_count, _ = await asyncio.to_thread(
        core.process_prompt,
        session_id=session_id,
        user_prompt=prompt_for_orion,
        file_check=[],
        user_id=str(ctx.author.id),
        user_name=ctx.author.name
    )
    await ctx.respond(f"{response_text}\n\n*(`Tokens: {token_count}`)*")

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
        bot.run(BOT_TOKEN)
    else:
        print("FATAL ERROR: DISCORD_BOT_TOKEN not found in .env file.")