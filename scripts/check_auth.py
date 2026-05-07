import json
import asyncio
from telethon import TelegramClient
from telethon.sessions import StringSession

API_ID   = 37171721
API_HASH = "e55c30fcf0368f49113f59cccefb19b6"

async def main():
    with open("tg_auth_state.json") as f:
        data = json.load(f)
    client = TelegramClient(StringSession(data["session"]), API_ID, API_HASH)
    await client.connect()
    if await client.is_user_authorized():
        print("AUTHORIZED=YES")
        with open(".new_session", "w") as f:
            f.write(client.session.save())
    else:
        print("AUTHORIZED=NO")
    await client.disconnect()

asyncio.run(main())
