"""
Telegram Integration
- Listens to configured channels for cricket signals
- Parses and scores signal sentiment
- Sends trading alerts to admin chat
"""
import asyncio
import logging
import re
from datetime import datetime
from typing import Optional

from config.settings import settings

logger = logging.getLogger(__name__)

# Keywords for signal parsing
BULLISH_KEYWORDS = [
    "back", "entry", "buy", "favourite", "strong", "dominating",
    "chase", "easy", "win", "confident", "back it", "lay the field",
    "momentum", "six", "boundary", "powerplay strong"
]

BEARISH_KEYWORDS = [
    "lay", "avoid", "wicket", "collapse", "struggling", "slow",
    "danger", "exit", "out", "loss cut", "too slow", "pressure",
    "falling apart", "abort", "risky", "skip"
]

SESSION_KEYWORDS = ["over", "runs", "powerplay", "session", "total", "line"]
SIGNAL_KEYWORDS = ["signal", "entry", "trade", "play", "bet", "back", "lay"]


class TelegramSignalParser:
    """Parses raw Telegram messages into structured signals"""

    def parse(self, text: str, channel: str) -> dict:
        """Extract signal from message text"""
        text_lower = text.lower()

        # Sentiment scoring
        bullish_count = sum(1 for kw in BULLISH_KEYWORDS if kw in text_lower)
        bearish_count = sum(1 for kw in BEARISH_KEYWORDS if kw in text_lower)

        total = bullish_count + bearish_count
        if total == 0:
            sentiment = 0.0
        else:
            sentiment = (bullish_count - bearish_count) / total

        # Is it a trading signal?
        is_signal = any(kw in text_lower for kw in SIGNAL_KEYWORDS)

        # Extract numbers (odds, runs, etc.)
        numbers = re.findall(r'\b\d+\.?\d*\b', text)
        odds_candidates = [float(n) for n in numbers if 1.1 <= float(n) <= 20.0]
        run_candidates = [int(float(n)) for n in numbers if 30 <= float(n) <= 250]

        # Signal type
        signal_type = "NEUTRAL"
        if bullish_count > bearish_count:
            signal_type = "BULLISH"
        elif bearish_count > bullish_count:
            signal_type = "BEARISH"

        # Session signal detection
        is_session = any(kw in text_lower for kw in SESSION_KEYWORDS)
        session_line = run_candidates[0] if run_candidates else None

        return {
            "channel": channel,
            "raw_text": text[:500],  # Truncate
            "sentiment": round(sentiment, 3),
            "signal_type": signal_type,
            "is_signal": is_signal,
            "is_session": is_session,
            "session_line": session_line,
            "suggested_odds": odds_candidates[:3],
            "bullish_score": bullish_count,
            "bearish_score": bearish_count,
            "timestamp": datetime.utcnow().isoformat()
        }


class AlertFormatter:
    """Formats trading signals for Telegram alerts"""

    SIGNAL_EMOJI = {
        "ENTER": "✅",
        "LOSS_CUT": "🔴",
        "BOOKSET": "💰",
        "SESSION": "📊",
        "HOLD": "⏳",
    }

    URGENCY_EMOJI = {
        "CRITICAL": "🚨",
        "HIGH": "⚠️",
        "MEDIUM": "📌",
        "LOW": "ℹ️",
    }

    def format_signal(self, signal: dict, match_info: dict) -> str:
        """Format a trading signal for Telegram"""
        signal_type = signal.get("signal", "HOLD")
        urgency = signal.get("urgency", "LOW")
        confidence = signal.get("confidence", 0) * 100
        win_prob = signal.get("win_probability", 0) * 100
        momentum = signal.get("momentum_score", 0) * 100

        team_a = match_info.get("team_a", "Team A")
        team_b = match_info.get("team_b", "Team B")
        over = match_info.get("overs", 0)
        runs = match_info.get("total_runs", 0)
        wickets = match_info.get("total_wickets", 0)

        sig_emoji = self.SIGNAL_EMOJI.get(signal_type, "📡")
        urg_emoji = self.URGENCY_EMOJI.get(urgency, "ℹ️")

        lines = [
            f"{sig_emoji} *{signal_type}* {urg_emoji}",
            f"",
            f"🏏 *{team_a}* vs *{team_b}*",
            f"📍 Over {over:.1f} | {runs}/{wickets}",
            f"",
            f"🎯 Confidence: `{confidence:.1f}%`",
            f"📈 Win Prob: `{win_prob:.1f}%`",
            f"⚡ Momentum: `{momentum:.1f}%`",
            f"",
        ]

        # Add strategy-specific info
        if signal_type == "LOSS_CUT" and "loss_cut" in signal:
            lc = signal["loss_cut"]
            lines += [
                f"🔴 *Loss Cut Details*",
                f"Hedge: `₹{lc.get('hedge_amount', 0):.2f}`",
                f"Profit Lock: `₹{lc.get('hedge_profit', 0):.2f}`",
                f"Reason: {lc.get('reason', '')}",
                f"",
            ]

        elif signal_type == "BOOKSET" and "bookset" in signal:
            bs = signal["bookset"]
            lines += [
                f"💰 *Bookset Details*",
                f"Stake A: `₹{bs.get('stake_a', 0):.2f}`",
                f"Stake B: `₹{bs.get('stake_b', 0):.2f}`",
                f"Guaranteed: `₹{bs.get('guaranteed_profit', 0):.2f}`",
                f"Profit%: `{bs.get('profit_pct', 0):.2f}%`",
                f"",
            ]

        elif signal_type == "SESSION" and "session" in signal:
            sess = signal["session"]
            lines += [
                f"📊 *Session Details*",
                f"Phase: `{sess.get('phase', '').upper()}`",
                f"Predicted: `{sess.get('predicted_runs', 0):.1f}` runs",
                f"CI: `{sess.get('ci_low', 0):.0f} - {sess.get('ci_high', 0):.0f}`",
                f"Signal: `{sess.get('signal', 'NEUTRAL')}`",
                f"",
            ]

        elif signal_type == "ENTER" and "entry_team" in signal:
            lines += [
                f"✅ *Entry Signal*",
                f"Back: `{signal.get('entry_team', '')}`",
                f"Reason: {signal.get('entry_reason', '')}",
                f"",
            ]

        lines.append(f"💬 _{signal.get('reasoning', '')}_")
        lines.append(f"")
        lines.append(f"⏰ `{datetime.utcnow().strftime('%H:%M:%S UTC')}`")

        return "\n".join(lines)


class TelegramBot:
    """
    Telegram bot using Telethon.
    - Listens to cricket signal channels
    - Sends alerts to admin chat
    """

    def __init__(self):
        self.client = None
        self.alert_client = None
        self.parser = TelegramSignalParser()
        self.formatter = AlertFormatter()
        self._running = False
        self._collected_signals: list = []

    async def start(self):
        """Initialize and start Telegram client"""
        if not settings.TELEGRAM_ENABLED:
            logger.info("Telegram disabled, skipping bot start")
            return

        try:
            from telethon import TelegramClient, events
            from telethon.tl.types import Channel, Chat

            # Use StringSession from env (for Railway) or file session (local)
            session_str = getattr(settings, "TELEGRAM_SESSION", None)
            if session_str:
                from telethon.sessions import StringSession
                session = StringSession(session_str)
                logger.info("Telegram: using StringSession from env var")
            else:
                session = "cricket_signal_listener"
                logger.info("Telegram: using file-based session")

            self.client = TelegramClient(
                session,
                int(settings.TELEGRAM_API_ID),
                settings.TELEGRAM_API_HASH,
            )

            await self.client.connect()
            if not await self.client.is_user_authorized():
                logger.warning("Telegram: Session not authorized. Falling back to Mock Mode.")
                raise Exception("Unauthorized Telegram Session")
                
            logger.info("Telegram client connected — scanning ALL joined channels")

            # Discover ALL joined channels/groups (not just configured ones)
            all_channel_ids = []
            async for dialog in self.client.iter_dialogs():
                entity = dialog.entity
                if isinstance(entity, (Channel, Chat)):
                    all_channel_ids.append(entity.id)

            # Also add any explicitly configured channels
            explicit = list(settings.TELEGRAM_CHANNELS or [])
            logger.info(f"Monitoring {len(all_channel_ids)} channels + {len(explicit)} configured")

            # Listen to ALL channels — filter for cricket/trading keywords in handler
            @self.client.on(events.NewMessage)
            async def handle_message(event):
                text_lower = (event.message.message or "").lower()
                # Only process messages with relevant keywords
                relevant = any(kw in text_lower for kw in
                               SIGNAL_KEYWORDS + SESSION_KEYWORDS + ["ipl", "cricket", "match", "run", "wicket"])
                if relevant:
                    await self._process_message(event)

            self._running = True
            logger.info("Telegram: listening to all channels for cricket signals")
            await self.client.run_until_disconnected()

        except ImportError:
            logger.warning("Telethon not installed. Using mock Telegram mode.")
            await self._mock_mode()
        except Exception as e:
            logger.error(f"Telegram start error: {e}")
            await self._mock_mode()

    async def _mock_mode(self):
        """
        Fallback mock mode when Telethon is unavailable or credentials missing.
        Generates realistic sample signals so the agent has something to consume.
        """
        import random
        rng = random.Random(123)

        mock_messages = [
            "Strong back on MI in powerplay, going well!",
            "CSK looking shaky, 3 wickets in 8 overs - watch out",
            "Entry signal: KKR chasing well, back them at 1.85",
            "Session: Powerplay over 58 runs - BACK OVER",
            "Loss cut suggested - RR falling badly",
            "Bookset opportunity at 1.95 / 2.1 - lock profit",
            "IPL match: RCB dominating, back at 1.75",
            "Wicket alert! MI lost 3 in 2 overs — lay MI now",
            "Signal: DC momentum strong, entry 1.90",
            "Session line 62 runs — BACK OVER strong tip",
        ]

        channels = settings.TELEGRAM_CHANNELS or ["mock_cricket_tips"]
        self._running = True
        logger.info("Telegram mock mode active — generating synthetic signals")

        while self._running:
            msg = rng.choice(mock_messages)
            channel = rng.choice(channels)
            signal = self.parser.parse(msg, channel)
            self._collected_signals.append(signal)
            if len(self._collected_signals) > 50:
                self._collected_signals = self._collected_signals[-50:]

            # Push to Redis so trading agent can consume
            try:
                from database.redis_client import get_redis, RedisCache
                redis = await get_redis()
                cache = RedisCache(redis)
                await cache.set_telegram_signals(0, self._collected_signals[-20:])
                await cache.publish("telegram:signals", signal)
            except Exception:
                pass

            await asyncio.sleep(45)  # New signal every 45s in mock

    async def _process_message(self, event):
        """Process incoming Telegram message"""
        try:
            text = event.message.message or ""
            if not text.strip():
                return

            channel = str(event.chat_id)
            signal = self.parser.parse(text, channel)

            # Store in memory
            self._collected_signals.append(signal)
            if len(self._collected_signals) > 100:
                self._collected_signals = self._collected_signals[-100:]

            # Cache in Redis
            from database.redis_client import get_redis, RedisCache
            redis = await get_redis()
            cache = RedisCache(redis)
            await cache.set_telegram_signals(0, self._collected_signals[-20:])
            await cache.publish("telegram:signals", signal)

            logger.info(f"Telegram signal: {signal['signal_type']} | {signal['sentiment']}")

        except Exception as e:
            logger.error(f"Error processing Telegram message: {e}")

    async def send_alert(self, signal: dict, match_info: dict):
        """Send formatted alert to admin chat"""
        if not settings.TELEGRAM_ALERT_CHAT_ID:
            return

        try:
            msg = self.formatter.format_signal(signal, match_info)

            if self.client and self.client.is_connected():
                await self.client.send_message(
                    int(settings.TELEGRAM_ALERT_CHAT_ID),
                    msg,
                    parse_mode="markdown"
                )
            else:
                logger.info(f"[Mock Alert]\n{msg}")

        except Exception as e:
            logger.error(f"Error sending alert: {e}")

    def get_recent_signals(self, limit: int = 20) -> list:
        """Get recent parsed signals"""
        return self._collected_signals[-limit:]

    async def stop(self):
        self._running = False
        if self.client:
            await self.client.disconnect()
