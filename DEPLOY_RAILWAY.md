# Deploy to Railway — Step by Step

## 1. Push to GitHub (one time)

```bash
# In your project folder
git remote add origin https://github.com/YOUR_USERNAME/cricket-trading-system.git
git push -u origin claude/wonderful-beaver
```

## 2. Create New Railway Project

1. Go to https://railway.app/new
2. Click **"Deploy from GitHub repo"**
3. Select your repo → select branch **`claude/wonderful-beaver`**
4. Railway auto-detects the Dockerfile ✅

## 3. Add PostgreSQL

1. In your Railway project → **+ New** → **Database** → **PostgreSQL**
2. Railway auto-sets `DATABASE_URL` in your service ✅

## 4. Add Redis

1. **+ New** → **Database** → **Redis**
2. Railway auto-sets `REDIS_URL` ✅

## 5. Set Environment Variables

Go to your service → **Variables** tab → add these one by one:

```
GEMINI_API_KEY=AIzaSyCSSovMtJMry0_7yjhTdxt_-qXBSrKHWvU
GEMINI_MODEL=gemini-2.0-flash

TELEGRAM_ENABLED=true
TELEGRAM_API_ID=37171721
TELEGRAM_API_HASH=e55c30fcf0368f49113f59cccefb19b6
TELEGRAM_BOT_TOKEN=8228656220:AAESFZw66K7_SmsJJUgPmXVQKTO-eX9jDuk
TELEGRAM_BOT_CHAT_ID=        ← GET THIS: send /start to your bot, run ping_bot.py
TELEGRAM_PHONE=+916305842166
TELEGRAM_SESSION=1BVtsOK4Bu25uVk689zCRt1osUTecTjcmtsYQ8ZyL6i9rX_RTPDChrXDbknRzFXyaUe3YeBh5dla4dKujLJk2fh2_Ip2lrqR2BScaWOqosMjFBKV337FpjLqD39vB6eW3vwl4vUy1RJ9YuSqODoZ59TGiIRNLEAVltFA0BO8bt6pRSllN9QPi7t0KTeKuJFBDQ4r5XiZoyE3ZvtZIepHNijTYEJXetrHSMyaCGBbUxJ21jU0zQoPw23IPb_X0hTu-3BMLsNy5ALJKAQLfUXuyxTZldbiVpbg4O3vZeR0AtAIFZ0nOEF_143M0bqKr6y-bLjHm5HfzehUChwJmBHG5bYSMM6njjCM=

EXCHANGE_TYPE=royalbook
ROYALBOOK_USERNAME=sainihal262204
ROYALBOOK_PASSWORD=Sainihal@22
ROYALBOOK_HEADLESS=true
ROYALBOOK_AUTO_NAVIGATE=true
ROYALBOOK_DEMO_ONLY=true

AGENT_ENABLED=true
AGENT_MODE=simulation
AGENT_AUTOPILOT=false
INITIAL_BANKROLL=10000
MAX_STAKE_PER_TRADE=1000
STOP_LOSS_PCT=20
MIN_SIGNAL_CONFIDENCE=0.70
ML_ENABLED=false
MATCH_POLL_INTERVAL=10
ODDS_SCRAPE_INTERVAL=5
```

## 6. Deploy

Railway deploys automatically on push. Wait ~3-5 min for Docker build.

## 7. Get your Telegram chat_id (REQUIRED for Bot API)

After deploy, do this:
1. Open Telegram → search **@RoyalBookCricket_bot** → send `/start`
2. Visit: `https://api.telegram.org/bot8228656220:AAESFZw66K7_SmsJJUgPmXVQKTO-eX9jDuk/getUpdates`
3. Find the `"id"` number under `"chat"` — that is your `TELEGRAM_BOT_CHAT_ID`
4. Add it to Railway Variables

Until then, Telethon StringSession (TELEGRAM_SESSION) sends to your Saved Messages automatically.

## Latency you'll see

| Event | Time |
|---|---|
| Ball bowled → Cricbuzz updates | 2–5 sec |
| Our scraper picks up score | +0–10 sec |
| RoyalBook odds scraped | +0–5 sec |
| Agent analyzes (Gemini) | +0.8 sec |
| Telegram message arrives | +0.2 sec |
| **Total worst case** | **~20 sec** |
| **Total typical** | **5–10 sec** |

Fastest path (no Gemini, rule engine only): **~5 sec**

## Health check

After deploy: `https://YOUR_APP.railway.app/health`
Logs: Railway dashboard → Deployments → View Logs
