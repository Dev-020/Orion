import asyncio
import os
import dotenv
from google import genai

dotenv.load_dotenv()
client = genai.Client(api_key=os.getenv("GOOGLE_API_KEY"))
model = "gemini-live-2.5-flash-preview"
config = {"response_modalities": ["TEXT"]}

async def main():
    async with client.aio.live.connect(model=model, config=config) as session:
        print("Session methods:")
        for method in dir(session):
            if not method.startswith("_"):
                print(method)
        await session.send_input("Hello", end_of_turn=True)

if __name__ == "__main__":
    asyncio.run(main())
