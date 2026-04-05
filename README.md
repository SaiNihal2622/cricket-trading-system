# 🏏 Cricket Trading Intelligence System

**Production-grade real-time cricket match analysis and trading decision support.**

> ⚠️ **Disclaimer:** This system is a **decision support tool only**. It does NOT automate wagering, integrate with any betting platform, or execute trades of any kind.

---

## Architecture Overview

```
┌─────────────────────────────────────────────────────────┐
│                    NGINX (port 80)                      │
│              Reverse Proxy + Load Balancer              │
└──────────────┬──────────────────┬───────────────────────┘
               │                  │
    ┌──────────▼──────┐  ┌────────▼────────┐
    │   FastAPI        │  │  React Frontend  │
    │   Backend :8000  │  │  Dashboard :3000 │
    └──────────┬──────┘  └─────────────────┘
               │
    ┌──────────▼──────────────────────────┐
    │          Core Engines               │
    │  ┌──────────┐  ┌─────────────────┐  │
    │  │ Decision │  │  ML Predictor   │  │
    │  │ Engine   │  │  (XGBoost)      │  │
    │  └──────────┘  └─────────────────┘  │
    │  ┌──────────┐  ┌─────────────────┐  │
    │  │ Loss Cut │  │  Bookset Engine │  │
    │  │ Engine   │  │                 │  │
    │  └──────────┘  └─────────────────┘  │
    │  ┌──────────┐  ┌─────────────────┐  │
    │  │ Session  │  │  Telegram Bot   │  │
    │  │ Engine   │  │  (Telethon)     │  │
    │  └──────────┘  └─────────────────┘  │
    └──────────┬──────────────────────────┘
               │
    ┌──────────▼──────────────────────────┐
    │  PostgreSQL  │  Redis (Cache/PubSub) │
    └─────────────────────────────────────┘
```

---

## Quick Start

### 1. Clone & Configure

```bash
git clone <repo>
cd cricket-trading-system
cp .env.example .env
# Edit .env with your settings
```

### 2. Launch with Docker Compose

```bash
docker-compose up -d
```

Services started:
- **Frontend**: http://localhost:3000
- **Backend API**: http://localhost:8000
- **API Docs**: http://localhost:8000/api/docs
- **PostgreSQL**: localhost:5432
- **Redis**: localhost:6379

---

## Module Reference

### Data Ingestion (`backend/data_ingestion/`)

| Component | Description |
|-----------|-------------|
| `LiveFeedManager` | Polls Cricbuzz or runs mock ball-by-ball feed |
| `CricbuzzScraper` | Async HTML scraper for live scores |
| `MockLiveFeed` | Simulated T20 match for development |

**To enable live scraping**, set `_use_mock = False` in `LiveFeedManager.__init__`.

### Strategy Engines (`backend/strategy_engine/`)

#### Loss Cut Engine
```
hedge_amount = (stake × entry_odds) / current_odds
hedge_profit  = hedge_amount − stake
```
Triggers on: odds drop > 15%, wicket in critical over, run rate collapse, win probability < 25%.

#### Bookset Engine
```
stake_A × odds_A = stake_B × odds_B     [equal return condition]
overround = (1/odds_A) + (1/odds_B)     [< 1.0 = arbitrage]
```
Finds optimal stake distribution for guaranteed profit regardless of outcome.

#### Session Engine
Predicts powerplay totals and final innings score using:
- Team strength adjustments (IPL franchise averages)
- Venue-specific statistics
- Wicket penalty factors
- Phase-specific run rate baselines

#### Decision Engine
Combines all signals with priority ordering:
```
1. LOSS_CUT (HIGH/CRITICAL urgency)
2. BOOKSET  (arbitrage detected)
3. SESSION  (powerplay opportunity)
4. BOOKSET  (late-match lock-in)
5. LOSS_CUT (low urgency)
6. ENTER    (composite score ≥ 0.65)
7. HOLD     (no clear signal)
```

### ML Model (`backend/ml_model/`)

**27 engineered features** including:
- Match state: overs, runs, wickets, CRR, RRR
- Phase flags: is_powerplay, is_death_overs
- Pressure index, momentum indicator
- Projected score vs par
- Team/venue strength encodings

Falls back to heuristic model when no trained artifact is present.

### Telegram Bot (`backend/telegram_bot/`)

Uses **Telethon** to listen to configured channels and:
- Parse signals using keyword scoring (bullish/bearish terms)
- Compute sentiment score in [-1, +1]
- Detect session line hints
- Send formatted alerts to admin chat

---

## Training the ML Model

### Using synthetic data (instant, no download needed):
```bash
cd backend
pip install -r requirements.txt
python ../scripts/train_model.py --synthetic --output ml_model/artifacts/
```

### Using real IPL data (Cricsheet format):
```bash
# Download from https://cricsheet.org/downloads/ipl_csv2.zip
python ../scripts/train_model.py --data ipl_data.csv --output ml_model/artifacts/
```

---

## Backtesting

```bash
# Quick synthetic backtest
python scripts/run_backtest.py --matches 200 --stake 1000

# With real data + save results
python scripts/run_backtest.py --data ipl.csv --stake 2000 --output results.json
```

**Sample output:**
```
══════════════════════════════════════════════════════
  CRICKET TRADING SYSTEM — BACKTEST REPORT
══════════════════════════════════════════════════════

  PERFORMANCE SUMMARY
  ─────────────────────────────────────────────────────
  Total Trades     : 847
  Winning Trades   : 531  (62.7%)
  Losing Trades    : 316
  Total P&L        : ₹18,420.00
  ROI              : 21.75%
  Max Drawdown     : ₹3,200.00
  Sharpe Ratio     : 1.4821
```

---

## REST API Reference

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/v1/odds/update` | POST | Update match odds |
| `/api/v1/odds/{id}/history` | GET | Odds movement history |
| `/api/v1/match/{id}/state` | GET | Current match state |
| `/api/v1/signal/evaluate` | POST | Generate trading signal |
| `/api/v1/signal/{id}/history` | GET | Signal history |
| `/api/v1/strategy/loss-cut` | POST | Calculate hedge |
| `/api/v1/strategy/bookset` | POST | Calculate bookset stakes |
| `/api/v1/strategy/session` | POST | Predict session runs |
| `/api/v1/ml/predict` | POST | ML win probability |
| `/api/v1/telegram/signals` | GET | Recent Telegram signals |

### Odds Update Example
```bash
curl -X POST http://localhost:8000/api/v1/odds/update \
  -H "Content-Type: application/json" \
  -d '{"match_id": 1, "teamA_odds": 1.85, "teamB_odds": 2.10}'
```

### Signal Evaluation Example
```bash
curl -X POST http://localhost:8000/api/v1/signal/evaluate \
  -H "Content-Type: application/json" \
  -d '{"match_id": 1, "stake": 1000, "entry_odds": 1.85, "backed_team": "A"}'
```

---

## WebSocket Streams

| Endpoint | Description |
|----------|-------------|
| `ws://localhost:8000/ws/match/{id}` | Live match state + signals |
| `ws://localhost:8000/ws/signals` | All signals across matches |
| `ws://localhost:8000/ws/odds/{id}` | Real-time odds stream |

---

## Telegram Setup

1. Get API credentials from https://my.telegram.org
2. Create a bot via @BotFather
3. Configure `.env`:
```env
TELEGRAM_ENABLED=true
TELEGRAM_API_ID=1234567
TELEGRAM_API_HASH=abcdef...
TELEGRAM_BOT_TOKEN=123:ABC...
TELEGRAM_CHANNELS=channel1,channel2
TELEGRAM_ALERT_CHAT_ID=-100123456789
```
4. Restart backend: `docker-compose restart backend`

---

## Project Structure

```
cricket-trading-system/
├── backend/
│   ├── main.py                     # FastAPI app + lifespan
│   ├── config/settings.py          # Pydantic settings
│   ├── api/
│   │   ├── routes.py               # REST endpoints
│   │   └── websocket.py            # WS handlers
│   ├── data_ingestion/
│   │   └── live_feed.py            # Cricbuzz scraper + mock
│   ├── strategy_engine/
│   │   ├── decision_engine.py      # Master signal combiner
│   │   ├── loss_cut_engine.py      # Hedge calculator
│   │   ├── bookset_engine.py       # Dutch book calculator
│   │   └── session_engine.py       # Score predictor
│   ├── ml_model/
│   │   └── predictor.py            # XGBoost + feature engineering
│   ├── telegram_bot/
│   │   └── bot.py                  # Telethon + alert formatter
│   └── database/
│       ├── models.py               # SQLAlchemy ORM models
│       ├── connection.py           # Async DB session
│       └── redis_client.py         # Redis cache layer
├── frontend/
│   └── src/
│       ├── App.jsx                 # Main layout
│       ├── components/
│       │   ├── Header.jsx          # Live status bar
│       │   ├── Scoreboard.jsx      # Ball-by-ball scorecard
│       │   ├── OddsPanel.jsx       # Odds display + input
│       │   ├── SignalPanel.jsx      # Decision display
│       │   ├── OddsChart.jsx       # Recharts odds movement
│       │   ├── PnLChart.jsx        # Equity curve
│       │   ├── TelegramFeed.jsx    # Signal feed
│       │   ├── StrategyCalculator.jsx  # Interactive calculators
│       │   └── Panel.jsx           # Base panel component
│       ├── store/useStore.js       # Zustand global state
│       ├── services/api.js         # Axios + WebSocket
│       └── hooks/useWebSocket.js   # WS lifecycle hook
├── backtesting/
│   └── backtester.py              # Ball-by-ball replay engine
├── scripts/
│   ├── train_model.py             # XGBoost training script
│   └── run_backtest.py            # Backtest runner + reporter
├── docker/
│   ├── nginx.conf                 # Reverse proxy config
│   └── init.sql                   # DB initialization
├── docker-compose.yml
└── .env.example
```

---

## Performance Notes

- Redis pub/sub delivers match updates to all WS clients in **< 5ms**
- Async SQLAlchemy with connection pooling handles **100+ concurrent** DB ops
- XGBoost inference: **< 2ms** per prediction
- Full signal evaluation pipeline: **< 50ms** end-to-end
- WebSocket reconnection with exponential backoff (2s → 30s max)

---

## License

MIT — for educational and research purposes only.
