"""Application configuration via environment variables"""
from typing import List
from pydantic_settings import BaseSettings
from pydantic import Field


class Settings(BaseSettings):
    # App
    APP_NAME: str = "Cricket Trading Intelligence System"
    DEBUG: bool = False
    SECRET_KEY: str = "change-me-in-production"

    # Database
    DATABASE_URL: str = "postgresql+asyncpg://cricket:cricket123@postgres:5432/cricket_trading"
    DATABASE_POOL_SIZE: int = 10
    DATABASE_MAX_OVERFLOW: int = 20

    # Redis
    REDIS_URL: str = "redis://redis:6379/0"
    REDIS_POOL_SIZE: int = 10

    # CORS
    CORS_ORIGINS: List[str] = ["http://localhost:3000", "http://localhost:80"]

    # Telegram
    TELEGRAM_ENABLED: bool = False
    TELEGRAM_API_ID: str = ""
    TELEGRAM_API_HASH: str = ""
    TELEGRAM_BOT_TOKEN: str = ""
    TELEGRAM_CHANNELS: List[str] = []
    TELEGRAM_ALERT_CHAT_ID: str = ""
    TELEGRAM_SESSION: str = ""   # StringSession string for Railway (no TTY)
    TELEGRAM_PHONE: str = ""

    # Cricket API
    CRICBUZZ_BASE_URL: str = "https://www.cricbuzz.com"
    CRICKET_API_KEY: str = ""
    MATCH_POLL_INTERVAL: int = 10  # seconds
    ODDS_SCRAPE_INTERVAL: int = 5  # seconds between odds updates

    # ML Model
    MODEL_PATH: str = "/app/ml_model/artifacts/xgboost_model.pkl"
    FEATURE_SCALER_PATH: str = "/app/ml_model/artifacts/scaler.pkl"

    # Strategy Thresholds
    ODDS_DROP_THRESHOLD: float = 0.15      # 15% drop triggers loss cut
    WIN_PROB_THRESHOLD: float = 0.65        # 65% win prob for ENTER signal
    MOMENTUM_THRESHOLD: float = 0.70        # 70% momentum for strong signal
    MIN_STAKE: float = 100.0
    MAX_STAKE: float = 10000.0

    # ── Autonomous Agent ────────────────────────────────────────────────────
    AGENT_ENABLED: bool = False             # Master switch
    AGENT_MODE: str = "simulation"          # "simulation" or "live"
    AGENT_LOOP_INTERVAL: int = 5            # seconds between decisions
    AGENT_AUTOPILOT: bool = True            # True=fully auto, False=require approval

    # Stop Loss
    STOP_LOSS_ENABLED: bool = True
    STOP_LOSS_PCT: float = 20.0             # exit when odds rise >20% above entry

    # Bankroll & Risk
    INITIAL_BANKROLL: float = 10000.0
    MAX_STAKE_PER_TRADE: float = 1000.0
    MAX_EXPOSURE: float = 5000.0
    MAX_DAILY_LOSS: float = 2000.0
    MAX_CONSECUTIVE_LOSSES: int = 5
    MAX_DRAWDOWN_PCT: float = 30.0

    # Execution
    EXCHANGE_TYPE: str = "simulated"        # "simulated", "betfair", "royalbook"
    BETFAIR_APP_KEY: str = ""
    BETFAIR_USERNAME: str = ""
    BETFAIR_PASSWORD: str = ""

    # RoyalBook
    ROYALBOOK_USERNAME: str = ""
    ROYALBOOK_PASSWORD: str = ""
    ROYALBOOK_HEADLESS: bool = True
    ROYALBOOK_AUTO_NAVIGATE: bool = True

    # CricAPI (optional — for richer live data)
    CRICAPI_KEY: str = ""

    # AI Reasoner (Groq)
    GROQ_API_KEY: str = ""
    GROQ_MODEL: str = "llama-3.3-70b-versatile"

    class Config:
        env_file = ".env"
        case_sensitive = True


settings = Settings()

