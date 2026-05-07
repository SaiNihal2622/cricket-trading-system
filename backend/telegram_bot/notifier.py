"""
Telegram Bet Signal Notifier
Sends trading calls to the user's own Saved Messages using their
Telethon StringSession — no BotFather needed.
"""
import asyncio
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

_client = None
_ready  = False


async def _init_client():
    global _client, _ready
    try:
        from config.settings import settings
        session_str = getattr(settings, "TELEGRAM_SESSION", "")
        api_id      = getattr(settings, "TELEGRAM_API_ID", "")
        api_hash    = getattr(settings, "TELEGRAM_API_HASH", "")

        if not (session_str and api_id and api_hash):
            logger.warning("Telegram notifier: missing SESSION/API_ID/HASH — alerts disabled")
            return

        from telethon import TelegramClient
        from telethon.sessions import StringSession

        _client = TelegramClient(
            StringSession(session_str),
            int(api_id),
            api_hash,
        )
        await _client.connect()
        if await _client.is_user_authorized():
            _ready = True
            logger.info("Telegram notifier ready — will send signals to Saved Messages")
        else:
            logger.warning("Telegram notifier: client not authorized")
    except Exception as e:
        logger.error(f"Telegram notifier init error: {e}")


async def send_signal(message: str):
    """Send a message to the user's Bot Chat, falling back to Saved Messages."""
    from config.settings import settings
    if settings.TELEGRAM_BOT_TOKEN and settings.TELEGRAM_ALERT_CHAT_ID:
        try:
            import httpx
            url = f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/sendMessage"
            payload = {
                "chat_id": settings.TELEGRAM_ALERT_CHAT_ID,
                "text": message,
                "parse_mode": "Markdown"
            }
            async with httpx.AsyncClient() as client:
                resp = await client.post(url, json=payload)
                if resp.status_code == 200:
                    logger.info(f"Telegram signal sent via Bot: {message[:80]}")
                    return
        except Exception as e:
            logger.error(f"Telegram Bot API send error: {e}")
            
    # Fallback to Telethon string session (Saved Messages)
    global _client, _ready
    if not _ready:
        await _init_client()
    if not _ready or not _client:
        logger.debug(f"Telegram notifier not ready, skipping: {message[:80]}")
        return
    try:
        await _client.send_message("me", message, parse_mode="md")
        logger.info(f"Telegram signal sent via StringSession: {message[:80]}")
    except Exception as e:
        logger.error(f"Telegram send error: {e}")
        _ready = False  # reset so next call re-inits


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
):
    """Format and send a bet call to Saved Messages."""
    action_emoji = {"BACK": "🟢 BACK", "LAY": "🔴 LAY", "PROGRESSIVE_BOOKSET": "🔒 BOOKSET"}.get(action, action)
    ts = datetime.now().strftime("%H:%M:%S IST")

    msg = (
        f"{_flag(tier)} **BET CALL — {match or 'IPL'}**\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"**{action_emoji} {team} @ {odds:.2f}**\n"
        f"💰 Stake: ₹{stake:.0f}  |  EV: +{ev*100:.1f}%\n"
        f"🎯 Confidence: {confidence*100:.0f}%\n"
        f"📊 Overs: {overs:.1f}  |  Score: {score}\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"📍 Bookset if odds hit **{bookset_at:.2f}**\n"
        f"🛑 Stop loss if odds hit **{stop_loss:.1f}**\n"
        f"💬 _{reasoning[:160]}_\n"
        f"⏰ {ts}"
    )
    await send_signal(msg)


async def send_bookset_call(team: str, entry_odds: float, current_odds: float, overs: float, match: str = ""):
    ts = datetime.now().strftime("%H:%M:%S IST")
    compression = current_odds / entry_odds * 100
    msg = (
        f"🔒 **BOOKSET NOW — {match or 'IPL'}**\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"Backed **{team}** @ {entry_odds:.2f}\n"
        f"Now trading @ **{current_odds:.2f}** ({compression:.0f}% of entry)\n"
        f"📊 Overs: {overs:.1f}\n"
        f"**LAY {team} now to lock guaranteed profit!**\n"
        f"⏰ {ts}"
    )
    await send_signal(msg)


async def send_stop_loss(
    team: str, entry_odds: float, current_odds: float,
    loss_pct: float, hedge_team: str, hedge_stake: float,
    overs: float, score: str, match: str = "",
):
    ts = datetime.now().strftime("%H:%M:%S IST")
    msg = (
        f"🛑 **STOP LOSS — {match or 'IPL'}**\n"
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
    team: str, entry_odds: float, current_odds: float,
    pnl: float, match: str = "",
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
    label: str, side: str, stake: float,
    confidence: float, reasoning: str,
    overs: float, score: str, match: str = "",
):
    ts = datetime.now().strftime("%H:%M:%S IST")
    side_emoji = "🔼 YES" if side.upper() == "YES" else "🔽 NO"
    msg = (
        f"📊 **SESSION CALL — {match or 'IPL'}**\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"**{side_emoji} {label}**\n"
        f"💰 Stake: ₹{stake:.0f}  |  Confidence: {confidence*100:.0f}%\n"
        f"📊 Overs: {overs:.1f}  |  Score: {score}\n"
        f"💬 _{reasoning[:160]}_\n"
        f"⏰ {ts}"
    )
    await send_signal(msg)


async def send_anti_panic(signal: str, team: str, overs: float, score: str, match: str = ""):
    ts = datetime.now().strftime("%H:%M:%S IST")
    if signal == "HOLD":
        msg = (
            f"😤 **WICKET — HOLD POSITION — {match or 'IPL'}**\n"
            f"━━━━━━━━━━━━━━━━━━━\n"
            f"Wicket fell but situation recoverable.\n"
            f"**{team}** — Overs: {overs:.1f} | Score: {score}\n"
            f"**Do NOT panic exit.** Hold your position.\n"
            f"⏰ {ts}"
        )
    else:
        msg = (
            f"🚨 **WICKET — EXIT NOW — {match or 'IPL'}**\n"
            f"━━━━━━━━━━━━━━━━━━━\n"
            f"Collapse confirmed. Cut losses immediately.\n"
            f"**{team}** — Overs: {overs:.1f} | Score: {score}\n"
            f"**LAY your position NOW.**\n"
            f"⏰ {ts}"
        )
    await send_signal(msg)


async def send_info(text: str):
    """Send a plain info/status message."""
    await send_signal(f"ℹ️ {text}")


async def send_match_started(team_a: str, team_b: str, odds_a: float, odds_b: float):
    ts = datetime.now().strftime("%H:%M:%S IST")
    msg = (
        f"🏏 **MATCH DETECTED — Live on RoyalBook**\n"
        f"━━━━━━━━━━━━━━━━━━━\n"
        f"**{team_a}** @ {odds_a:.2f}  vs  **{team_b}** @ {odds_b:.2f}\n"
        f"Bot is analysing — signals incoming...\n"
        f"⏰ {ts}"
    )
    await send_signal(msg)
