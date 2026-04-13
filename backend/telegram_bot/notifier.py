"""
Telegram Bet Signal Notifier — Zero-Delay Edition

Sends all trading signals to Saved Messages via Telethon (MTProto).
- Persistent connection: initialized once at startup, kept alive
- Zero-delay: no re-init on each message — warm connection only
- All signal types: ENTER, LOSS_CUT, BOOKSET, SESSION, STOP_LOSS,
                    BOOKMAKER, ANTI_PANIC, MATCH_STARTED, INFO
- Auto-reconnect: background task pings every 60s to keep session warm
"""
import asyncio
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

_client   = None
_ready    = False
_lock     = asyncio.Lock() if asyncio.get_event_loop_policy() else None
_init_attempted = False


def _get_lock():
    global _lock
    if _lock is None:
        try:
            _lock = asyncio.Lock()
        except RuntimeError:
            pass
    return _lock


async def init_notifier():
    """
    Call this ONCE at startup (from main.py lifespan).
    Establishes a persistent Telethon connection.
    """
    global _client, _ready, _init_attempted
    if _ready or _init_attempted:
        return
    _init_attempted = True

    try:
        from config.settings import settings
        session_str = getattr(settings, "TELEGRAM_SESSION", "")
        api_id      = getattr(settings, "TELEGRAM_API_ID", "")
        api_hash    = getattr(settings, "TELEGRAM_API_HASH", "")

        if not (session_str and api_id and api_hash):
            logger.warning("Telegram notifier: missing SESSION/API_ID/HASH — signals disabled")
            return

        from telethon import TelegramClient
        from telethon.sessions import StringSession

        _client = TelegramClient(
            StringSession(session_str),
            int(api_id),
            api_hash,
            connection_retries=5,
            retry_delay=1,
            auto_reconnect=True,
        )
        await _client.connect()

        if await _client.is_user_authorized():
            _ready = True
            logger.info("Telegram notifier READY — persistent MTProto connection established")
            # Start keep-alive background task
            asyncio.create_task(_keepalive_loop())
        else:
            logger.warning("Telegram notifier: client not authorized — run tg_step1/step2 scripts")
    except Exception as e:
        logger.error(f"Telegram notifier init error: {e}")


async def _keepalive_loop():
    """Ping Telegram every 60s to keep the MTProto connection alive."""
    while True:
        await asyncio.sleep(60)
        global _client, _ready
        if _client and _ready:
            try:
                await _client.get_me()
            except Exception as e:
                logger.warning(f"Telegram keepalive failed: {e} — attempting reconnect")
                _ready = False
                try:
                    await _client.connect()
                    if await _client.is_user_authorized():
                        _ready = True
                        logger.info("Telegram reconnected")
                except Exception as re:
                    logger.error(f"Telegram reconnect failed: {re}")


async def send_signal(message: str, parse_mode: str = "md"):
    """
    Send a message to Saved Messages.
    If not initialized, try once to init (lazy fallback).
    Non-blocking: caller should await this directly for zero delay.
    """
    global _client, _ready
    if not _ready:
        await init_notifier()
    if not _ready or not _client:
        logger.debug(f"Telegram not ready — skipped: {message[:60]}")
        return
    try:
        await _client.send_message("me", message, parse_mode=parse_mode)
    except Exception as e:
        logger.error(f"Telegram send error: {e}")
        # Don't reset _ready — connection may recover on next send


# ── Signal formatters ────────────────────────────────────────────────────────

def _flag(tier: str) -> str:
    return {"scalp": "⚡", "mid": "📈", "high": "🚀", "very_high": "🎯"}.get(tier, "📌")


async def send_bet_call(
    action: str,
    team: str,
    odds: float,
    stake: float,
    ev: float,
    confidence: float,
    reasoning: str,
    overs: float,
    score: str,
    bookset_at: float,
    stop_loss: float,
    tier: str = "mid",
    match: str = "",
    ai_source: str = "",
):
    action_emoji = {"BACK": "🟢 BACK", "LAY": "🔴 LAY", "PROGRESSIVE_BOOKSET": "🔒 BOOKSET"}.get(action, action)
    ts = datetime.now().strftime("%H:%M:%S IST")
    ai_tag = f" 🧠 {ai_source.upper()}" if ai_source and ai_source != "rule_engine" else ""

    msg = (
        f"{_flag(tier)} **BET CALL{ai_tag} — {match or 'IPL'}**\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"**{action_emoji} {team} @ {odds:.2f}**\n"
        f"💰 Stake: ₹{stake:.0f}  |  EV: +{ev*100:.1f}%\n"
        f"🎯 Confidence: {confidence*100:.0f}%\n"
        f"📊 Overs: {overs:.1f}  |  Score: {score}\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        + (f"📍 Bookset target: **{bookset_at:.2f}**\n" if bookset_at else "")
        + (f"🛑 Stop loss at: **{stop_loss:.2f}**\n" if stop_loss else "")
        + f"💬 _{reasoning[:160]}_\n"
        f"⏰ {ts}"
    )
    await send_signal(msg)


async def send_bookset_call(
    team: str,
    entry_odds: float,
    current_odds: float,
    overs: float,
    match: str = "",
    stake_a: float = 0,
    stake_b: float = 0,
    guaranteed_profit: float = 0,
):
    ts = datetime.now().strftime("%H:%M:%S IST")
    compression = (current_odds / entry_odds * 100) if entry_odds > 0 else 0
    profit_line = f"**Guaranteed profit: ₹{guaranteed_profit:.0f}**\n" if guaranteed_profit else ""
    lay_line    = f"LAY {team} ₹{stake_a:.0f} @ {current_odds:.2f}\n" if stake_a else f"LAY {team} now\n"

    msg = (
        f"🔒 **BOOKSET NOW — {match or 'IPL'}**\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"Backed **{team}** @ {entry_odds:.2f}\n"
        f"Now trading @ **{current_odds:.2f}** ({compression:.0f}% of entry)\n"
        f"📊 Overs: {overs:.1f}\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"{lay_line}"
        f"{profit_line}"
        f"⏰ {ts}"
    )
    await send_signal(msg)


async def send_stop_loss(
    team: str,
    entry_odds: float,
    current_odds: float,
    loss_pct: float,
    hedge_team: str,
    hedge_stake: float,
    overs: float,
    score: str,
    match: str = "",
):
    ts = datetime.now().strftime("%H:%M:%S IST")
    msg = (
        f"🛑 **STOP LOSS TRIGGERED — {match or 'IPL'}**\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"Backed **{team}** @ {entry_odds:.2f}\n"
        f"Now @ **{current_odds:.2f}** — loss {loss_pct:.1f}%\n"
        f"📊 Overs: {overs:.1f} | Score: {score}\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"**HEDGE: BACK {hedge_team} ₹{hedge_stake:.0f}** to cut losses\n"
        f"⏰ {ts}"
    )
    await send_signal(msg)


async def send_loss_cut(
    team: str,
    entry_odds: float,
    current_odds: float,
    pnl: float,
    match: str = "",
):
    ts = datetime.now().strftime("%H:%M:%S IST")
    emoji = "💚" if pnl >= 0 else "💔"
    msg = (
        f"{emoji} **LOSS CUT EXECUTED — {match or 'IPL'}**\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"**{team}** entry @ {entry_odds:.2f} → exit @ {current_odds:.2f}\n"
        f"P&L: **₹{pnl:+.0f}**\n"
        f"⏰ {ts}"
    )
    await send_signal(msg)


async def send_session_call(
    label: str,
    side: str,
    stake: float,
    confidence: float,
    reasoning: str,
    overs: float,
    score: str,
    match: str = "",
    predicted_runs: float = 0,
    prob_over: float = 0,
    prob_under: float = 0,
):
    ts = datetime.now().strftime("%H:%M:%S IST")
    side_emoji = "🔼 YES (OVER)" if side.upper() in ("YES", "OVER") else "🔽 NO (UNDER)"
    stats_line = (
        f"📈 P(OVER): {prob_over:.0%} | P(UNDER): {prob_under:.0%}\n"
        if prob_over else ""
    )
    pred_line = f"🎯 Model predicts: {predicted_runs:.0f} runs\n" if predicted_runs else ""

    msg = (
        f"📊 **SESSION CALL — {match or 'IPL'}**\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"**{side_emoji} {label}**\n"
        f"💰 Stake: ₹{stake:.0f}  |  Confidence: {confidence*100:.0f}%\n"
        f"📊 Overs: {overs:.1f}  |  Score: {score}\n"
        f"{pred_line}"
        f"{stats_line}"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"💬 _{reasoning[:160]}_\n"
        f"⏰ {ts}"
    )
    await send_signal(msg)


async def send_bookmaker_call(
    team: str,
    bookmaker_odds: float,
    match_odds: float,
    edge: float,
    stake: float,
    overs: float,
    score: str,
    match: str = "",
):
    """Alert when bookmaker odds offer edge vs match odds."""
    ts = datetime.now().strftime("%H:%M:%S IST")
    action = "🟢 BACK" if bookmaker_odds < match_odds else "🔴 LAY"
    msg = (
        f"📋 **BOOKMAKER EDGE — {match or 'IPL'}**\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"**{action} {team}**\n"
        f"Bookmaker: {bookmaker_odds:.2f}  |  Match Odds: {match_odds:.2f}\n"
        f"Edge: **{edge*100:.1f}%** | Stake: ₹{stake:.0f}\n"
        f"📊 Overs: {overs:.1f}  |  Score: {score}\n"
        f"⏰ {ts}"
    )
    await send_signal(msg)


async def send_anti_panic(
    signal: str,
    team: str,
    overs: float,
    score: str,
    match: str = "",
    reasoning: str = "",
):
    ts = datetime.now().strftime("%H:%M:%S IST")
    reason_line = f"💬 _{reasoning[:120]}_\n" if reasoning else ""
    if signal == "HOLD":
        msg = (
            f"😤 **WICKET — HOLD POSITION — {match or 'IPL'}**\n"
            f"━━━━━━━━━━━━━━━━━━━\n"
            f"Wicket fell but **recoverable situation**.\n"
            f"**{team}** — Overs: {overs:.1f} | Score: {score}\n"
            f"{reason_line}"
            f"**Do NOT panic exit. Hold your position.**\n"
            f"⏰ {ts}"
        )
    else:
        msg = (
            f"🚨 **WICKET — EXIT NOW — {match or 'IPL'}**\n"
            f"━━━━━━━━━━━━━━━━━━━\n"
            f"Collapse confirmed. Cut losses immediately.\n"
            f"**{team}** — Overs: {overs:.1f} | Score: {score}\n"
            f"{reason_line}"
            f"**LAY your position NOW.**\n"
            f"⏰ {ts}"
        )
    await send_signal(msg)


async def send_match_started(
    team_a: str,
    team_b: str,
    odds_a: float,
    odds_b: float,
    venue: str = "",
):
    ts = datetime.now().strftime("%H:%M:%S IST")
    venue_line = f"🏟️ Venue: {venue}\n" if venue else ""
    msg = (
        f"🏏 **MATCH DETECTED — Live on RoyalBook**\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"**{team_a}** @ {odds_a:.2f}  vs  **{team_b}** @ {odds_b:.2f}\n"
        f"{venue_line}"
        f"🤖 Gemini analyst online — signals incoming...\n"
        f"⏰ {ts}"
    )
    await send_signal(msg)


async def send_info(text: str):
    """Send a plain info/status message."""
    await send_signal(f"ℹ️ {text}")


async def send_daily_summary(
    total_pnl: float,
    trades: int,
    win_rate: float,
    bankroll: float,
    match: str = "",
):
    ts = datetime.now().strftime("%H:%M IST")
    emoji = "📈" if total_pnl >= 0 else "📉"
    msg = (
        f"{emoji} **DAILY SUMMARY — {match or 'IPL'}**\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"P&L: **₹{total_pnl:+.0f}**\n"
        f"Trades: {trades}  |  Win Rate: {win_rate:.0%}\n"
        f"Bankroll: ₹{bankroll:.0f}\n"
        f"⏰ {ts}"
    )
    await send_signal(msg)
