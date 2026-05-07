import asyncio
import os
from telethon import TelegramClient
from telethon.sessions import StringSession
from dotenv import load_dotenv

load_dotenv()

async def list_channels():
    session_str = os.getenv("TELEGRAM_SESSION")
    api_id = os.getenv("TELEGRAM_API_ID")
    api_hash = os.getenv("TELEGRAM_API_HASH")

    if not session_str:
        print("No TELEGRAM_SESSION found in .env")
        return

    client = TelegramClient(StringSession(session_str), int(api_id), api_hash)
    await client.connect()
    
    if not await client.is_user_authorized():
        print("Session is unauthorized.")
        return
        
    print("Listing your joined channels/groups...")
    with open("channels_utf8.txt", "w", encoding="utf-8") as f:
        async for dialog in client.iter_dialogs():
            if dialog.is_channel or dialog.is_group:
                line = f"- {dialog.name} (ID: {dialog.id})"
                print(line)
                f.write(line + "\n")
            
    await client.disconnect()

if __name__ == "__main__":
    asyncio.run(list_channels())
