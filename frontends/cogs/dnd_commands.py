# cogs/dnd_commands.py

import discord
from discord.ext import commands
from main_utils import dnd_functions
import asyncio

class DndCommands(commands.Cog):
    """A cog for all D&D persona specific slash commands."""

    def __init__(self, bot: discord.Bot):
        self.bot = bot
        # We need a reference to the core, which is attached to the bot instance
        self.core = bot.core 

    # --- Command: /lookup ---
    @commands.slash_command(name="lookup", description="Performs a targeted search of Orion's knowledge base.")
    async def lookup(
        self,
        ctx: discord.ApplicationContext,
        query: discord.Option(str, "A general search term for a summary list (e.g., 'fireball', 'eldritch blast', 'divine smite').", required=False, default=None),
        id: discord.Option(str, "The specific ID of an item to get its full details.", required=False, default=None),
        item_type: discord.Option(str, "Filter by a specific type (valid types: 'spells', 'misc', 'bestiary', 'adventure', 'book').", required=False, default=None),
        source: discord.Option(str, "Filter by a specific source (e.g., 'PHB', 'DMG', 'XGE', 'XPHB').", required=False, default=None),
        max_results: discord.Option(int, "The maximum number of results to return. (default is 25)", default=25)
    ):
        await ctx.defer()

        if not query and not id:
            await ctx.respond("Please provide either a `query` for a summary search or an `id` for a detailed lookup.", ephemeral=True)
            return

        search_result = None
        fallback_notification = ""
        if id:
            id_search_result = dnd_functions.search_knowledge_base(id=id, mode='full')
            is_json = id_search_result.strip().startswith('{') or id_search_result.strip().startswith('[')
            if not is_json and query:
                print(f"-> ID '{id}' not found. Falling back to query: '{query}'")
                fallback_notification = f"[System Note: The initial lookup for id='{id}' failed. The system has fallen back to a summary search for the query='{query}'. Inform the user about this fallback before presenting the results.]\n\n"
            else:
                search_result = id_search_result

        if query and search_result is None:
            search_result = dnd_functions.search_knowledge_base(
                query=query, item_type=item_type, source=source, mode='summary', max_results=max_results
            )

        prompt_for_orion = f"{fallback_notification}A user performed a direct knowledge base lookup.\nThe raw JSON result is: {search_result}\n\nPlease present this information to the user in a clear, well-formatted, and easy-to-read manner. If it's a list of search results, make it scannable and include the `id` for each item. If it's a single detailed entry, structure it logically with headers."

        if isinstance(ctx.channel, discord.Thread):
            session_id = f"discord-thread-{ctx.channel.parent.id}-{ctx.channel.id}"
        elif ctx.guild:
            session_id = f"discord-channel-{ctx.channel.id}"
        else:
            session_id = f"discord-dm-{ctx.author.id}"

        response_text, token_count, _ = await asyncio.to_thread(
            self.core.process_prompt, session_id=session_id, user_prompt=prompt_for_orion, file_check=[],
            user_id=str(ctx.author.id), user_name=ctx.author.name
        )
        await ctx.respond(f"{response_text}\n\n*(`Tokens: {token_count}`)*")

    # --- Command: /resource ---
    @commands.slash_command(name="resource", description="Manage one of your character's resources (e.g., HP, spell slots).")
    async def resource(
        self,
        ctx: discord.ApplicationContext,
        operation: discord.Option(str, "Choose the operation to perform.", choices=['set', 'add', 'subtract', 'create', 'view']),
        resource_name: discord.Option(str, "The name of the resource (e.g., 'HP'). Not needed to view all.", required=False, default=None),
        value: discord.Option(int, "The value to apply to the resource's current value.", required=False, default=None),
        max_value: discord.Option(int, "The value to apply to the resource's maximum value.", required=False, default=None)
    ):
        await ctx.defer()

        if operation != 'view' and not resource_name:
            await ctx.respond(f"A `resource_name` is required for the '{operation}' operation.", ephemeral=True)
            return

        if operation == 'create' and value is None:
            await ctx.respond(f"A `value` is required for the 'create' operation.", ephemeral=True)
            return

        result = dnd_functions.manage_character_resource(
            user_id=str(ctx.author.id), operation=operation, resource_name=resource_name, value=value, max_value=max_value
        )

        prompt_for_orion = f"A user just managed their character resource using the command `/resource`.\nThe raw result is: '{result}'\n\nPlease present this result to the user in a clear and concise confirmation message. Add narrative flair where appropriate (e.g., for taking damage or healing)."

        if isinstance(ctx.channel, discord.Thread):
            session_id = f"discord-thread-{ctx.channel.parent.id}-{ctx.channel.id}"
        elif ctx.guild:
            session_id = f"discord-channel-{ctx.channel.id}"
        else:
            session_id = f"discord-dm-{ctx.author.id}"

        response_text, token_count, _ = await asyncio.to_thread(
            self.core.process_prompt, session_id=session_id, user_prompt=prompt_for_orion, file_check=[],
            user_id=str(ctx.author.id), user_name=ctx.author.name
        )
        await ctx.respond(f"{response_text}\n\n*(`Tokens: {token_count}`)*")

    # --- Command: /status ---
    @commands.slash_command(name="status", description="Manage a temporary status effect on your character.")
    async def status(
        self,
        ctx: discord.ApplicationContext,
        operation: discord.Option(str, "Choose whether to add, remove, update, or view an effect.", choices=['add', 'remove', 'update', 'view']),
        effect_name: discord.Option(str, "The name of the status effect. Not needed to view all.", required=False, default=None),
        details: discord.Option(str, "Add descriptive details for the status effect.", required=False, default=None),
        duration: discord.Option(int, "Set a duration in rounds for the effect.", required=False, default=None)
    ):
        await ctx.defer()

        if operation != 'view' and not effect_name:
            await ctx.respond(f"An `effect_name` is required for the '{operation}' operation.", ephemeral=True)
            return

        result = dnd_functions.manage_character_status(
            user_id=str(ctx.author.id), operation=operation, effect_name=effect_name, details=details, duration=duration
        )

        prompt_for_orion = f"A user just managed their character status using the command `/status`.\nThe raw result is: '{result}'\n\nPlease present this result to the user as a clear and concise confirmation message."

        session_id = f"discord-dm-{ctx.author.id}"
        response_text, token_count, _ = await asyncio.to_thread(
            self.core.process_prompt, session_id=session_id, user_prompt=prompt_for_orion, file_check=[],
            user_id=str(ctx.author.id), user_name=ctx.author.name
        )
        await ctx.respond(f"{response_text}\n\n*(`Tokens: {token_count}`)*")

    # --- Command: /dice_roll ---
    @commands.slash_command(name="dice_roll", description="Rolls dice and asks Orion to interpret the result.")
    async def roll(
        self,
        ctx: discord.ApplicationContext,
        dice: str,
        reason: discord.Option(str, "The reason for this roll (e.g., 'to hit an goblin')", required=False, default=None)
    ):
        await ctx.defer()

        roll_result = dnd_functions.roll_dice(dice)

        prompt_for_orion = f"A user just performed a direct dice roll with the command `/dice_roll {dice}`."
        if reason:
            prompt_for_orion += f" The stated reason for the roll was: '{reason}'."
        prompt_for_orion += f"\n\nThe raw result of the roll is this JSON object: {roll_result}\n\nPlease present this result to the user in a clear and engaging D&D-style format. If the roll was a critical success or failure on a d20, add appropriate narrative flair."

        if isinstance(ctx.channel, discord.Thread):
            session_id = f"discord-thread-{ctx.channel.parent.id}-{ctx.channel.id}"
        elif ctx.guild:
            session_id = f"discord-channel-{ctx.channel.id}"
        else:
            session_id = f"discord-dm-{ctx.author.id}"

        response_text, token_count, _ = await asyncio.to_thread(
            self.core.process_prompt, session_id=session_id, user_prompt=prompt_for_orion, file_check=[],
            user_id=str(ctx.author.id), user_name=ctx.author.name
        )
        await ctx.respond(f"{response_text}\n\n*(`Tokens: {token_count}`)*")


# This special function is what py-cord looks for when loading a cog.
def setup(bot: discord.Bot):
    bot.add_cog(DndCommands(bot))