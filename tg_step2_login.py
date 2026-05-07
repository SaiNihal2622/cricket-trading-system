"""Step 2: Complete login with OTP code. Pass code as argument: python tg_step2_login.py 12345"""
import asyncio, json, sys
from telethon import TelegramClient
from telethon.sessions import StringSession

API_ID   = 37171721
API_HASH = "e55c30fcf0368f49113f59cccefb19b6"
PHONE    = "+916305842166"

async def main():
    code = sys.argv[1] if len(sys.argv) > 1 else input("Enter OTP: ").strip()
    with open("tg_auth_state.json") as f:
        data = json.load(f)
    client = TelegramClient(StringSession(data["session"]), API_ID, API_HASH)
    await client.connect()
    await client.sign_in(PHONE, code, phone_code_hash=data["phone_code_hash"])
    session_str = client.session.save()
    await client.disconnect()
    print("\n" + "="*60)
    print("TELEGRAM_SESSION=" + session_str)
    print("="*60)

asyncio.run(main())
