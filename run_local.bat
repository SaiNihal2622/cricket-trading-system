@echo off
REM ─────────────────────────────────────────────────────────────────────────────
REM  Cricket Trading Bot — LOCAL RUNNER
REM  Runs the backend on YOUR machine (trusted Indian IP for RoyalBook)
REM  Shares Railway PostgreSQL + Redis with the cloud dashboard
REM ─────────────────────────────────────────────────────────────────────────────

cd /d "%~dp0\backend"

REM ── Railway shared DB/Redis (public URLs) ────────────────────────────────────
set DATABASE_URL=postgresql+asyncpg://postgres:STfTUcTQQapxWGrMuPFcVnlAvljnsWMf@junction.proxy.rlwy.net:22100/railway
set REDIS_URL=redis://default:rlaSNcAoZtFZUzsmhGileyfRsKNSQlpi@junction.proxy.rlwy.net:43260

REM ── RoyalBook credentials ────────────────────────────────────────────────────
set ROYALBOOK_USERNAME=sainihal2622204
set ROYALBOOK_PASSWORD=Sainihal@22
set ROYALBOOK_HEADLESS=false
set ROYALBOOK_AUTO_NAVIGATE=true

REM ── Agent settings ───────────────────────────────────────────────────────────
set EXCHANGE_TYPE=royalbook
set AGENT_ENABLED=true
set AGENT_MODE=live
set AGENT_AUTOPILOT=true
set AGENT_LOOP_INTERVAL=5
set STOP_LOSS_ENABLED=true
set STOP_LOSS_PCT=20
set INITIAL_BANKROLL=1000
set MAX_STAKE_PER_TRADE=100
set MAX_EXPOSURE=500
set MAX_DAILY_LOSS=200
set MAX_CONSECUTIVE_LOSSES=5
set MAX_DRAWDOWN_PCT=30

REM ── Optional: Telegram (add your creds here) ─────────────────────────────────
set TELEGRAM_ENABLED=false
set TELEGRAM_API_ID=
set TELEGRAM_API_HASH=
set TELEGRAM_CHANNELS=

REM ── Optional: Groq AI (free at console.groq.com) ────────────────────────────
set GROQ_API_KEY=
set GROQ_MODEL=llama-3.1-8b-instant

REM ── App settings ─────────────────────────────────────────────────────────────
set DEBUG=false
set SECRET_KEY=local-runner-secret
set CORS_ORIGINS=["http://localhost:3000","https://backend-production-a6c8.up.railway.app"]

echo.
echo  ██████╗██████╗ ██╗ ██████╗██╗  ██╗███████╗████████╗    ██████╗  ██████╗ ████████╗
echo  ██╔════╝██╔══██╗██║██╔════╝██║ ██╔╝██╔════╝╚══██╔══╝    ██╔══██╗██╔═══██╗╚══██╔══╝
echo  ██║     ██████╔╝██║██║     █████╔╝ █████╗     ██║       ██████╔╝██║   ██║   ██║
echo  ██║     ██╔══██╗██║██║     ██╔═██╗ ██╔══╝     ██║       ██╔══██╗██║   ██║   ██║
echo  ╚██████╗██║  ██║██║╚██████╗██║  ██╗███████╗   ██║       ██████╔╝╚██████╔╝   ██║
echo   ╚═════╝╚═╝  ╚═╝╚═╝ ╚═════╝╚═╝  ╚═╝╚══════╝   ╚═╝       ╚═════╝  ╚═════╝    ╚═╝
echo.
echo  Local Runner: RoyalBook automation from YOUR machine (Indian IP)
echo  Dashboard:    https://backend-production-a6c8.up.railway.app
echo  Mode:         LIVE (real bets)  Bankroll: Rs. 1000
echo.

REM ── Install requirements if needed ───────────────────────────────────────────
pip show fastapi >nul 2>&1 || (
  echo Installing Python requirements...
  pip install -r requirements.txt
  playwright install chromium
)

REM ── Start backend ────────────────────────────────────────────────────────────
echo Starting backend on http://localhost:8000 ...
echo Press Ctrl+C to stop.
echo.
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
