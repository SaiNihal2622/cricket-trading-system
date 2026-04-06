@echo off
REM ── SIMULATION MODE — no real bets placed ────────────────────────────────────
cd /d "%~dp0\backend"

set DATABASE_URL=postgresql+asyncpg://postgres:STfTUcTQQapxWGrMuPFcVnlAvljnsWMf@junction.proxy.rlwy.net:22100/railway
set REDIS_URL=redis://default:rlaSNcAoZtFZUzsmhGileyfRsKNSQlpi@junction.proxy.rlwy.net:43260
set ROYALBOOK_USERNAME=sainihal2622204
set ROYALBOOK_PASSWORD=Sainihal@22
set ROYALBOOK_HEADLESS=false
set ROYALBOOK_AUTO_NAVIGATE=true
set EXCHANGE_TYPE=royalbook
set AGENT_ENABLED=true
set AGENT_MODE=simulation
set AGENT_AUTOPILOT=true
set AGENT_LOOP_INTERVAL=5
set STOP_LOSS_ENABLED=true
set STOP_LOSS_PCT=20
set INITIAL_BANKROLL=1000
set MAX_STAKE_PER_TRADE=100
set MAX_EXPOSURE=500
set TELEGRAM_ENABLED=false
set GROQ_API_KEY=
set DEBUG=false
set SECRET_KEY=local-runner-secret
set CORS_ORIGINS=["http://localhost:3000","https://backend-production-a6c8.up.railway.app"]

echo.
echo  [SIMULATION MODE — watching odds, NOT placing real bets]
echo  Dashboard: https://backend-production-a6c8.up.railway.app
echo  Local UI:  http://localhost:8000/api/docs
echo.

pip show fastapi >nul 2>&1 || (pip install -r requirements.txt && playwright install chromium)
uvicorn main:app --host 0.0.0.0 --port 8000 --reload
