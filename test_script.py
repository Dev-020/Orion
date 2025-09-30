import functions
import dotenv
import os
from google import genai
from google.genai import types, chats
import importlib
import os
import sqlite3
from datetime import datetime, timezone
from google import genai
from google.genai import types, chats
import functions
import io
from dotenv import load_dotenv
import json
import asyncio, queue
import discord
import os
import asyncio
from dotenv import load_dotenv
from orion_core import OrionCore
from discord.ext import commands

dotenv.load_dotenv()

client = genai.Client(
    api_key=os.getenv("GOOGLE_API_KEY"),
    http_options=types.HttpOptions(api_version='v1alpha')
)

chat = client.aio.chats.create(model='gemini-2.0-flash-001')
response = chat.send_message('tell me a story')
print(response.text)