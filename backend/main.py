"""
Cricket Trading Intelligence System - FastAPI Backend
Production-grade autonomous trading agent + decision support system
"""
import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.middleware.gzip import GZipMiddleware

from api.routes import router as api_router
from api.websocket import router as ws_router
from database.connection import init_db, close_db
from database.redis_client import init_redis, close_redis
from data_ingestion.live_feed import LiveFeedManager
from data_ingestion.odds_scraper import OddsScraper
from telegram_bot.bot import TelegramBot
from telegram_bot.chatbot import InteractiveChatbot
from config.settings import settings

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(name)s | %(levelname)s | %(message)s"
)
logger = logging.getLogger(__name__)

# Global managers
live_feed_manager: LiveFeedManager = None
odds_scraper: OddsScraper = None
telegram_bot: TelegramBot = None
interactive_chatbot: InteractiveChatbot = None
trading_agent = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager"""
    global live_feed_manager, odds_scraper, telegram_bot, interactive_chatbot, trading_agent

    logger.info("🏏 Starting Cricket Trading Intelligence System...")

    # Init DB connections
    await init_db()
    await init_redis()
    logger.info("✅ Database connections established")

    # Start live feed manager
    live_feed_manager = LiveFeedManager()
    asyncio.create_task(live_feed_manager.start())
    logger.info("✅ Live feed manager started")

    # Start odds scraper
    odds_scraper = OddsScraper()

    # ── Stake API integration ──────────────────────────────────────────────
    exchange_instance = None
    if settings.EXCHANGE_TYPE == "stake" and settings.STAKE_API_KEY:
        from exchange.stake_exchange import StakeExchange
        exchange_instance = StakeExchange(
            settings.STAKE_API_KEY,
            settings.STAKE_GRAPHQL_URL
        )

        async def _init_exchange():
            try:
                await exchange_instance.start()
                odds_scraper.attach_exchange(exchange_instance)
                logger.info("✅ Stake exchange API started in background")
            except Exception as e:
                logger.error(f"❌ Failed to start Stake API: {e}")

        asyncio.create_task(_init_exchange())
        app.state.exchange = exchange_instance

    asyncio.create_task(odds_scraper.start())
    logger.info(f"✅ Odds scraper started (source: {'stake_api' if exchange_instance else 'mock'})")

    # Start Telegram bot
    if settings.TELEGRAM_ENABLED:
        logger.info("Initializing Telegram Signal Listener...")
        telegram_bot = TelegramBot()
        asyncio.create_task(telegram_bot.start())
    else:
        logger.info("Telegram Signal Listener is disabled.")

    # Start autonomous trading agent
    if settings.AGENT_ENABLED:
        logger.info(f"Starting Trading Agent in {settings.AGENT_MODE} mode...")
        from agent.trading_agent import TradingAgent
        trading_agent = TradingAgent(settings, exchange_instance=exchange_instance)
        asyncio.create_task(trading_agent.start())
    else:
        logger.info("Trading Agent is disabled.")

    # Start Interactive Chatbot
    if settings.TELEGRAM_ENABLED and settings.TELEGRAM_BOT_TOKEN:
        logger.info("Initializing Interactive Telegram Chatbot...")
        interactive_chatbot = InteractiveChatbot(agent=trading_agent)
        asyncio.create_task(interactive_chatbot.start())
    else:
        logger.info("Interactive Chatbot is disabled (no BOT_TOKEN).")

    app.state.live_feed = live_feed_manager
    app.state.odds_scraper = odds_scraper
    app.state.telegram_bot = telegram_bot
    app.state.interactive_chatbot = interactive_chatbot
    app.state.trading_agent = trading_agent

    # ── Startup ping on Telegram ──────────────────────────────────────────────
    try:
        from telegram_bot.notifier import send_info
        exchange_status = "✅ Stake API connected" if exchange_instance else "⚠️ Stake API offline"
        asyncio.create_task(send_info(
            f"🏏 Bot restarted — watching for IPL matches\n"
            f"{exchange_status} | Mode: {settings.AGENT_MODE.upper()}\n"
            f"Bankroll: ₹{getattr(settings, 'INITIAL_BANKROLL', '?')} | "
            f"Max stake: ₹{getattr(settings, 'MAX_STAKE_PER_TRADE', '?')}\n"
            f"Signals will arrive here. Agent will bet via Stake API."
        ))
    except Exception:
        pass

    yield

    # Shutdown
    logger.info("🛑 Shutting down...")
    if trading_agent:
        await trading_agent.stop()
    if odds_scraper:
        await odds_scraper.stop()
    exchange = getattr(app.state, "exchange", None)
    if exchange:
        await exchange.stop()
    if live_feed_manager:
        await live_feed_manager.stop()
    if telegram_bot:
        await telegram_bot.stop()
    if interactive_chatbot:
        await interactive_chatbot.stop()
    await close_db()
    await close_redis()


app = FastAPI(
    title="Cricket Trading Intelligence System",
    description="Autonomous cricket trading agent with real-time analysis and signal generation",
    version="2.0.0",
    lifespan=lifespan,
    docs_url="/api/docs",
    redoc_url="/api/redoc",
)

# Middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
app.add_middleware(GZipMiddleware, minimum_size=1000)

# Routers
app.include_router(api_router, prefix="/api/v1")
app.include_router(ws_router, prefix="/ws")


# ── Health & Status ─────────────────────────────────────────────────────────

@app.get("/health")
async def health_check():
    feed = getattr(app.state, "live_feed", None)
    agent = getattr(app.state, "trading_agent", None)
    return {
        "status": "healthy",
        "service": "cricket-trading-intelligence",
        "version": "2.0.0",
        "data_source": feed.get_data_source() if feed else "unknown",
        "agent_state": agent.state.value if agent else "disabled",
    }


@app.get("/status")
async def system_status():
    """Detailed system status including all subsystems"""
    feed = getattr(app.state, "live_feed", None)
    bot = getattr(app.state, "telegram_bot", None)
    agent = getattr(app.state, "trading_agent", None)

    status = {
        "service": "cricket-trading-intelligence",
        "version": "2.0.0",
        "subsystems": {
            "data_source": feed.get_data_source() if feed else "offline",
            "active_matches": len(feed.get_active_matches()) if feed else 0,
            "telegram": "active" if bot and bot._running else "inactive",
            "agent": agent.get_status() if agent else {"state": "disabled"},
        },
    }

    if feed and feed.cricapi and feed.cricapi.is_configured:
        status["subsystems"]["cricapi"] = feed.cricapi.get_usage()

    return status


# ── Agent Control Endpoints ─────────────────────────────────────────────────

@app.post("/agent/start")
async def agent_start():
    """Start the autonomous trading agent"""
    global trading_agent
    if not trading_agent:
        from agent.trading_agent import TradingAgent
        trading_agent = TradingAgent(settings)
        app.state.trading_agent = trading_agent

    await trading_agent.start()
    return {"status": "started", "state": trading_agent.state.value}


@app.post("/agent/stop")
async def agent_stop():
    """Stop the trading agent"""
    if not trading_agent:
        raise HTTPException(404, "Agent not initialized")
    await trading_agent.stop()
    return {"status": "stopped", "state": trading_agent.state.value}


@app.post("/agent/pause")
async def agent_pause():
    """Pause the agent (monitoring only, no trades)"""
    if not trading_agent:
        raise HTTPException(404, "Agent not initialized")
    await trading_agent.pause()
    return {"status": "paused", "state": trading_agent.state.value}


@app.post("/agent/resume")
async def agent_resume():
    """Resume the agent from pause"""
    if not trading_agent:
        raise HTTPException(404, "Agent not initialized")
    await trading_agent.resume()
    return {"status": "resumed", "state": trading_agent.state.value}


@app.get("/agent/status")
async def agent_status():
    """Full agent status: positions, risk, bankroll, actions"""
    if not trading_agent:
        return {"state": "disabled", "message": "Set AGENT_ENABLED=true to activate"}
    return trading_agent.get_status()


@app.get("/agent/actions")
async def agent_actions(limit: int = 50):
    """Recent agent actions / trade log"""
    if not trading_agent:
        return {"actions": []}
    return {"actions": trading_agent.get_action_log(limit)}


@app.post("/agent/circuit-breaker/reset")
async def agent_reset_circuit_breaker():
    """Manually reset circuit breaker after consecutive losses"""
    if not trading_agent:
        raise HTTPException(404, "Agent not initialized")
    trading_agent.risk_manager.reset_circuit_breaker()
    # Also restore agent state from CIRCUIT_BREAK back to RUNNING
    from agent.trading_agent import AgentState
    if trading_agent.state == AgentState.CIRCUIT_BREAK:
        trading_agent.state = AgentState.RUNNING
        trading_agent._log_action("CIRCUIT_RESET", "Circuit breaker reset — trading resumed")
    return {"status": "circuit_breaker_reset", "risk": trading_agent.risk_manager.get_status()}
