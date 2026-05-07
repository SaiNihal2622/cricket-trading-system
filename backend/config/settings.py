import os
from typing import List, Any
from dotenv import load_dotenv

load_dotenv()

class ManualSettings:
    # App
    APP_NAME = os.getenv("APP_NAME", "Cricket Trading Intelligence System")
    DEBUG = os.getenv("DEBUG", "false").lower() == "true"
    SECRET_KEY = os.getenv("SECRET_KEY", "change-me-in-production")

    # Database (Patched for Local SQLite)
    DATABASE_URL = os.getenv("DATABASE_URL", "sqlite+aiosqlite:///cricket_trading_local.db")
    DATABASE_POOL_SIZE = int(os.getenv("DATABASE_POOL_SIZE", "10"))
    DATABASE_MAX_OVERFLOW = int(os.getenv("DATABASE_MAX_OVERFLOW", "20"))

    # Redis (Patched for Local Mock)
    REDIS_URL = os.getenv("REDIS_URL", "redis://localhost:6379/0")
    REDIS_POOL_SIZE = int(os.getenv("REDIS_POOL_SIZE", "10"))

    # CORS
    CORS_ORIGINS = os.getenv("CORS_ORIGINS", "http://localhost:3000,http://localhost:80").split(",")

    # Telegram
    TELEGRAM_ENABLED = os.getenv("TELEGRAM_ENABLED", "false").lower() == "true"
    TELEGRAM_API_ID = os.getenv("TELEGRAM_API_ID", "")
    TELEGRAM_API_HASH = os.getenv("TELEGRAM_API_HASH", "")
    TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
    _channels = os.getenv("TELEGRAM_CHANNELS", "")
    TELEGRAM_CHANNELS = [s.strip() for s in _channels.replace("[", "").replace("]", "").replace("'", "").replace("\"", "").split(",") if s.strip()]
    TELEGRAM_ALERT_CHAT_ID = os.getenv("TELEGRAM_ALERT_CHAT_ID", "")
    TELEGRAM_SESSION = os.getenv("TELEGRAM_SESSION", "")
    TELEGRAM_PHONE = os.getenv("TELEGRAM_PHONE", "")

    # Cricket API
    CRICBUZZ_BASE_URL = "https://www.cricbuzz.com"
    CRICKET_API_KEY = os.getenv("CRICKET_API_KEY", "")
    MATCH_POLL_INTERVAL = int(os.getenv("MATCH_POLL_INTERVAL", "10"))
    ODDS_SCRAPE_INTERVAL = int(os.getenv("ODDS_SCRAPE_INTERVAL", "5"))

    # ML Model
    MODEL_PATH = "backend/ml_model/artifacts/xgboost_model.pkl"
    FEATURE_SCALER_PATH = "backend/ml_model/artifacts/scaler.pkl"

    # Strategy Thresholds
    ODDS_DROP_THRESHOLD = float(os.getenv("ODDS_DROP_THRESHOLD", "0.15"))
    WIN_PROB_THRESHOLD = float(os.getenv("WIN_PROB_THRESHOLD", "0.65"))
    MOMENTUM_THRESHOLD = float(os.getenv("MOMENTUM_THRESHOLD", "0.70"))
    MIN_STAKE = float(os.getenv("MIN_STAKE", "100.0"))
    MAX_STAKE = float(os.getenv("MAX_STAKE", "10000.0"))

    # Autonomous Agent
    AGENT_ENABLED = os.getenv("AGENT_ENABLED", "false").lower() == "true"
    AGENT_MODE = os.getenv("AGENT_MODE", "live")
    AGENT_LOOP_INTERVAL = int(os.getenv("AGENT_LOOP_INTERVAL", "5"))
    AGENT_AUTOPILOT = True  # Direct bets — no approval wait
    STRICT_CONSENSUS = os.getenv("STRICT_CONSENSUS", "true").lower() == "true"
    CONSENSUS_THRESHOLD = float(os.getenv("CONSENSUS_THRESHOLD", "0.80"))

    # Stop Loss
    STOP_LOSS_ENABLED = True
    STOP_LOSS_PCT = 20.0

    # Bankroll & Risk
    INITIAL_BANKROLL = 1200.0
    MAX_STAKE_PER_TRADE = 1200.0
    MAX_EXPOSURE = 1200.0
    MAX_DAILY_LOSS = 1200.0
    MAX_CONSECUTIVE_LOSSES = 5
    MAX_DRAWDOWN_PCT = 30.0

    # Execution
    EXCHANGE_TYPE = os.getenv("EXCHANGE_TYPE", "stake")
    BETFAIR_APP_KEY = os.getenv("BETFAIR_APP_KEY", "")

    # Stake API
    STAKE_API_KEY = os.getenv("STAKE_API_KEY", "")
    STAKE_GRAPHQL_URL = os.getenv("STAKE_GRAPHQL_URL", "https://api.stake.com/graphql")

    # Groq Reasoner
    GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")
    GROQ_MODEL = os.getenv("GROQ_MODEL", "llama-3.3-70b-versatile")

    # NVIDIA Reasoner
    NVIDIA_API_KEY = os.getenv("NVIDIA_API_KEY", "")
    NVIDIA_MODEL = os.getenv("NVIDIA_MODEL", "nvidia/llama-3.1-nemotron-70b-instruct")

    # Gemini Reasoner
    GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
    GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.0-flash")

    # MIMO Reasoner (NVIDIA hosted)
    MIMO_API_KEY = os.getenv("MIMO_API_KEY", "")
    MIMO_MODEL = os.getenv("MIMO_MODEL", "nvidia/mimo-7b")
    MIMO_BASE_URL = os.getenv("MIMO_BASE_URL", "https://integrate.api.nvidia.com/v1")

    # Demo Mode
    DEMO_MODE = os.getenv("DEMO_MODE", "true").lower() == "true"
    DEMO_TARGET_ACCURACY = float(os.getenv("DEMO_TARGET_ACCURACY", "0.80"))

    # Weather API (for DLS/rain prediction)
    WEATHER_API_KEY = os.getenv("WEATHER_API_KEY", "")

    # Hard-coded Royal Constraints (Rs 1200 / 3000)
    USER_DAILY_BUDGET = 1200.0
    USER_DAILY_PROFIT_TARGET = 3000.0

settings = ManualSettings()
