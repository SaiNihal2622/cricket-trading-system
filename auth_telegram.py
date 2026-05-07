"""Run ONCE locally to generate Telegram session string for Railway."""
import asyncio
from telethon import TelegramClient
from telethon.sessions import StringSession

API_ID   = 37171721
API_HASH = "e55c30fcf0368f49113f59cccefb19b6"
PHONE    = "+916305842166"

async def main():
    client = TelegramClient(StringSession(), API_ID, API_HASH)
    await client.connect()

    await client.send_code_request(PHONE)
    code = input("Enter the OTP from your Telegram app: ").strip()
    await client.sign_in(PHONE, code)

    session_str = client.session.save()
    print("\n" + "="*60)
    print("SESSION STRING:")
    print(session_str)
    print("="*60)
    await client.disconnect()

asyncio.run(main())
