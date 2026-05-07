"""Step 1: Request OTP to Telegram app"""
import asyncio, json
from telethon import TelegramClient
from telethon.sessions import StringSession

API_ID   = 37171721
API_HASH = "e55c30fcf0368f49113f59cccefb19b6"
PHONE    = "+916305842166"

async def main():
    client = TelegramClient(StringSession(), API_ID, API_HASH)
    await client.connect()
    result = await client.send_code_request(PHONE)
    session_str = client.session.save()
    await client.disconnect()
    data = {"phone_code_hash": result.phone_code_hash, "session": session_str}
    with open("tg_auth_state.json", "w") as f:
        json.dump(data, f)
    print("OTP sent to your Telegram app. Check the app and run tg_step2_login.py with the code.")

asyncio.run(main())
