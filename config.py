"""Configuration for Cricket Trading System."""
import os
from dotenv import load_dotenv

load_dotenv()

# ── Trading Mode ──────────────────────────────────────────────
TRADING_MODE = os.getenv("TRADING_MODE", "demo")  # "demo" or "live"
MAX_BET_SIZE = float(os.getenv("MAX_BET_SIZE", "2.0"))
MIN_CONFIDENCE = float(os.getenv("MIN_CONFIDENCE", "0.65"))
KELLY_FRACTION = float(os.getenv("KELLY_FRACTION", "0.25"))
MIN_EDGE = float(os.getenv("MIN_EDGE", "0.05"))

# ── API Keys ──────────────────────────────────────────────────
CLOUDBET_API_KEY = os.getenv("CLOUDBET_API_KEY", "")
NVIDIA_API_KEY = os.getenv("NVIDIA_API_KEY", "")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY", "")
GROK_API_KEY = os.getenv("GROK_API_KEY", "")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
MIMO_API_KEY = os.getenv("MIMO_API_KEY", "")

# ── AI Model Endpoints ────────────────────────────────────────
NVIDIA_BASE_URL = "https://integrate.api.nvidia.com/v1"
GROK_BASE_URL = "https://api.x.ai/v1"
MIMO_BASE_URL = "https://token-plan-sgp.xiaomimimo.com/v1"
GEMINI_MODEL = "gemini-2.0-flash"
NVIDIA_MODEL = "nvidia/llama-3.1-nemotron-70b-instruct"
GROK_MODEL = "grok-3"
MIMO_MODEL = "mimo-v2-omni"

# ── Cloudbet ──────────────────────────────────────────────────
CLOUDBET_BASE = "https://sports-api.cloudbet.com/pub/v2"
IPL_COMPETITION = "cricket-india-indian-premier-league"

# ── Dashboard ─────────────────────────────────────────────────
DASHBOARD_PORT = int(os.getenv("DASHBOARD_PORT", "8080"))

# ── Database ──────────────────────────────────────────────────
DB_PATH = os.getenv("DB_PATH", "cricket_trading.db")

# ── Team Data (IPL 2026) ──────────────────────────────────────
TEAMS = {
    "Chennai Super Kings": {"short": "CSK", "home_ground": "MA Chidambaram Stadium", "avg_score": 172},
    "Delhi Capitals": {"short": "DC", "home_ground": "Arun Jaitley Stadium", "avg_score": 168},
    "Gujarat Titans": {"short": "GT", "home_ground": "Narendra Modi Stadium", "avg_score": 170},
    "Kolkata Knight Riders": {"short": "KKR", "home_ground": "Eden Gardens", "avg_score": 175},
    "Lucknow Super Giants": {"short": "LSG", "home_ground": "Ekana Stadium", "avg_score": 165},
    "Mumbai Indians": {"short": "MI", "home_ground": "Wankhede Stadium", "avg_score": 178},
    "Punjab Kings": {"short": "PBKS", "home_ground": "IS Bindra Stadium", "avg_score": 170},
    "Rajasthan Royals": {"short": "RR", "home_ground": "Sawai Mansingh Stadium", "avg_score": 168},
    "Royal Challengers Bangalore": {"short": "RCB", "home_ground": "M Chinnaswamy Stadium", "avg_score": 180},
    "Sunrisers Hyderabad": {"short": "SRH", "home_ground": "Rajiv Gandhi Intl", "avg_score": 174},
}

# Venue scoring patterns (avg 1st innings score, powerplay avg, death overs avg)
VENUE_PATTERNS = {
    "Arun Jaitley Stadium": {"avg_1st": 170, "powerplay": 52, "death": 48, "spin_friendly": False},
    "Eden Gardens": {"avg_1st": 175, "powerplay": 55, "death": 50, "spin_friendly": False},
    "Wankhede Stadium": {"avg_1st": 180, "powerplay": 58, "death": 52, "spin_friendly": False},
    "M Chinnaswamy Stadium": {"avg_1st": 185, "powerplay": 60, "death": 55, "spin_friendly": False},
    "MA Chidambaram Stadium": {"avg_1st": 165, "powerplay": 48, "death": 45, "spin_friendly": True},
    "Narendra Modi Stadium": {"avg_1st": 172, "powerplay": 52, "death": 48, "spin_friendly": False},
    "Ekana Stadium": {"avg_1st": 160, "powerplay": 46, "death": 44, "spin_friendly": True},
    "Sawai Mansingh Stadium": {"avg_1st": 168, "powerplay": 50, "death": 46, "spin_friendly": True},
    "Rajiv Gandhi Intl": {"avg_1st": 174, "powerplay": 54, "death": 50, "spin_friendly": False},
    "IS Bindra Stadium": {"avg_1st": 170, "powerplay": 52, "death": 48, "spin_friendly": False},
}