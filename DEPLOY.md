# One-Time Setup & Free Deployment Guide

## What You Need To Provide (ONE TIME)

| Credential | Where to get | Required? |
|---|---|---|
| **RoyalBook username** | Your royalbook.win account | YES (for live trading) |
| **RoyalBook password** | Your royalbook.win account | YES (for live trading) |
| **Telegram API ID** | https://my.telegram.org/apps | YES (to read your channels) |
| **Telegram API Hash** | https://my.telegram.org/apps | YES (to read your channels) |
| **Groq API key** | https://console.groq.com (free) | Recommended (AI reasoning) |
| **CricAPI key** | https://cricapi.com (100 free/day) | Optional (live player stats) |

---

## Option A: Local Docker Deploy (Recommended to start)

```bash
# 1. Fill in your credentials in .env
#    ROYALBOOK_USERNAME=your_username
#    ROYALBOOK_PASSWORD=your_password
#    TELEGRAM_API_ID=12345678
#    TELEGRAM_API_HASH=abcdef123456
#    GROQ_API_KEY=gsk_xxxxx
#    EXCHANGE_TYPE=royalbook
#    TELEGRAM_ENABLED=true
#    AGENT_ENABLED=true

# 2. Start everything
cd cricket-trading-system
docker compose up --build

# 3. Open dashboard
# http://localhost:3000

# 4. Agent control
# http://localhost:8000/api/docs
```

---

## Option B: Free Cloud Deploy (Railway.app)

**Railway gives $5/month free credit = ~500 hours of runtime**

### Steps:
1. **Push to GitHub**
   ```bash
   git init
   git add .
   git commit -m "Cricket Trading System"
   gh repo create cricket-trading --private --push
   ```

2. **Connect to Railway**
   - Go to https://railway.app
   - New Project → Deploy from GitHub → select your repo
   - Add services: PostgreSQL plugin + Redis plugin (both free)

3. **Set environment variables** in Railway dashboard:
   ```
   ROYALBOOK_USERNAME = your_username
   ROYALBOOK_PASSWORD = your_password
   TELEGRAM_API_ID = 12345678
   TELEGRAM_API_HASH = abcdef123456
   GROQ_API_KEY = gsk_xxxxx
   EXCHANGE_TYPE = royalbook
   TELEGRAM_ENABLED = true
   AGENT_ENABLED = true
   AGENT_AUTOPILOT = true
   DATABASE_URL = (Railway auto-fills from PostgreSQL plugin)
   REDIS_URL = (Railway auto-fills from Redis plugin)
   ```

4. **Deploy** — Railway auto-builds and deploys. Get your URL like `https://cricket-trading.up.railway.app`

5. **Dashboard** — open the Railway URL in browser

---

## How It Works

### Autopilot Mode (default)
- Agent runs fully automatically
- Monitors RoyalBook + Cricbuzz + Telegram
- Places bets, stop losses, booksets without asking you
- You watch the dashboard at `/`

### Semi-Auto Mode
- Toggle the mode button at top of dashboard
- Agent proposes trades → shows you a notification
- You have **30 seconds** to Accept (✓) or Reject (✕)
- If no response in 30s → auto-rejected (safe)

### What the Agent Trades
- **Match Odds**: BACK/LAY on team win
- **Sessions**: Over runs YES/NO (6-over, powerplay, total runs)
- **Premium Sessions**: Player runs, partnerships
- **Bookmaker**: Integer odds markets
- **Bookset**: Both-sides hedge for guaranteed profit
- **Stop Loss**: Auto-exit when odds move >20% against entry
- **Loss Cut**: Smart hedge to limit losses

### Risk Controls
- Max stake per trade: ₹1,000 (change MAX_STAKE_PER_TRADE)
- Max daily loss: ₹2,000 (change MAX_DAILY_LOSS)
- Circuit breaker: pauses after 5 consecutive losses
- Stop loss: auto-exits at 20% adverse move

### With ₹1,000 Starting Bankroll
Set these in `.env`:
```
INITIAL_BANKROLL=1000
MAX_STAKE_PER_TRADE=100
MAX_EXPOSURE=500
MAX_DAILY_LOSS=200
MAX_CONSECUTIVE_LOSSES=3
STOP_LOSS_PCT=15
```

---

## Agent Control Endpoints
- `GET  /health` — system health
- `GET  /status` — full system status
- `POST /agent/start` — start agent
- `POST /agent/stop`  — stop agent
- `POST /agent/pause` — pause (monitor only)
- `GET  /agent/status` — agent state + positions + risk
- `GET  /agent/actions` — trade history
- `POST /agent/mode?autopilot=true/false` — switch modes
- `POST /agent/circuit-breaker/reset` — reset after loss streak
- `GET  /api/v1/sessions/analysis` — session market recommendations
- `GET  /api/v1/matches/live-ipl` — live IPL match data
