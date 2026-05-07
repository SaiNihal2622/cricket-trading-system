import os
import requests
from dotenv import load_dotenv

load_dotenv()

bot_token = os.getenv("TELEGRAM_BOT_TOKEN")
if not bot_token:
    print("No TELEGRAM_BOT_TOKEN found in .env")
    exit(1)

url = f"https://api.telegram.org/bot{bot_token}/getUpdates"
r = requests.get(url)
data = r.json()

if not data.get('ok') or not data.get('result'):
    print("Could not find any recent messages. Make sure you typed /start to @RoyalBookCricket_bot!")
    exit(1)

# Get the chat ID of the last person who messaged the bot
chat_id = data['result'][-1]['message']['chat']['id']

send_url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
payload = {
    "chat_id": chat_id,
    "text": "🏏 SYSTEM ONLINE! The ML Trading Agent is awake and ready. Gathering live match data...",
    "parse_mode": "Markdown"
}
r2 = requests.post(send_url, json=payload)
print("Telegram send ok?", r2.json())
