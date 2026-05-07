import os
import sys
import asyncio
import logging
import uvicorn

# ── Add backend to sys.path ──────────────────────────────────────────────────
current_dir = os.path.dirname(os.path.abspath(__file__))
backend_dir = os.path.join(current_dir, "backend")
if backend_dir not in sys.path:
    sys.path.append(backend_dir)

from main import app
from config.settings import settings

# ── Force Override Settings for Local Mode ──────────────────────────────────
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("LocalRunner")

# Hardcode the essential overrides to bypass .env parsing errors
settings.DATABASE_URL = "sqlite+aiosqlite:///cricket_trading_local.db"
settings.REDIS_URL = "redis://localhost:6379/0"
settings.AGENT_ENABLED = True
settings.AGENT_MODE = "live"
settings.AGENT_AUTOPILOT = False  # Analysis only — signals via Telegram, no bets placed
settings.AGENT_LOOP_INTERVAL = 30  # Slow loop to avoid Telegram flood wait
settings.TELEGRAM_ENABLED = True
settings.TELEGRAM_BOT_TOKEN = "8228656220:AAESFZw66K7_SmsJJUgPmXVQKTO-eX9jDuk"

# Ensure List fields are actually handled (we patched Settings to use str)
if isinstance(settings.TELEGRAM_CHANNELS, str):
    settings.TELEGRAM_CHANNELS = []

logger.info("🚀 Starting Royal Trading Bot in Local Mode...")
logger.info(f"📍 Database: {settings.DATABASE_URL}")

if __name__ == "__main__":
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=False)
