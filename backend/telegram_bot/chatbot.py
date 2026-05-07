"""
Interactive Telegram Chatbot using python-telegram-bot v20+
Provides a /start and /balance interface, ties to the trading agent.
"""
import logging
import asyncio
from telegram import Update
from telegram.ext import Application, CommandHandler, ContextTypes

from config.settings import settings

logger = logging.getLogger(__name__)

class InteractiveChatbot:
    def __init__(self, agent=None):
        self.agent = agent
        self.app = None
        self._running = False
        self._task = None

    async def start(self):
        if not settings.TELEGRAM_ENABLED:
            logger.info("Interactive Chatbot disabled in settings.")
            return
        if not settings.TELEGRAM_BOT_TOKEN:
            logger.error("Interactive Chatbot: No TELEGRAM_BOT_TOKEN provided. Cannot start.")
            return

        logger.info("Starting Interactive Chatbot...")
        self.app = Application.builder().token(settings.TELEGRAM_BOT_TOKEN).build()

        self.app.add_handler(CommandHandler("start", self.cmd_start))
        self.app.add_handler(CommandHandler("status", self.cmd_status))
        self.app.add_handler(CommandHandler("balance", self.cmd_balance))
        self.app.add_handler(CommandHandler("trade", self.cmd_trade))
        self.app.add_handler(CommandHandler("profit", self.cmd_profit))
        self.app.add_handler(CommandHandler("tookbet", self.cmd_tookbet))

        await self.app.initialize()
        await self.app.start()
        await self.app.updater.start_polling(drop_pending_updates=True)
        self._running = True
        logger.info("Interactive Chatbot is now polling.")

    async def stop(self):
        if self._running and self.app:
            await self.app.updater.stop()
            await self.app.stop()
            await self.app.shutdown()
            self._running = False
            logger.info("Interactive Chatbot stopped.")

    # ─── Commands ─────────────────────────────────────────────────────────────

    async def cmd_start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        await update.message.reply_text(
            "🏏 *Cricket Trading Agent Interactive Bot*\n\n"
            "Welcome! I am active and listening for signals.\n"
            "Use `/status` to see current agent status.\n"
            "Use `/balance <amount>` to update your bankroll.\n"
            "Use `/trade <amount>` to set max stake per trade.\n"
            "Use `/tookbet <team> <amount> <odds>` to record a trade.",
            parse_mode="Markdown"
        )
        # Store user chat ID for alerts if not already set or override it if allowed
        settings.TELEGRAM_ALERT_CHAT_ID = str(update.message.chat_id)

    async def cmd_status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self.agent:
            await update.message.reply_text("Trading Agent is not initialized.")
            return
            
        status = self.agent.get_status()
        state = status.get('state', 'Unknown')
        risk = self.agent.risk_manager.get_status()
        
        msg = (
            f"📊 *Agent Status*\n"
            f"State: `{state}`\n"
            f"Bankroll: `₹{risk.get('current_bankroll', 0):.2f}`\n"
            f"Max Stake: `₹{risk.get('max_stake', 0):.2f}`\n"
            f"Exposure: `₹{risk.get('current_exposure', 0):.2f}`\n"
            f"Daily P&L: `₹{risk.get('daily_pnl', 0):.2f}`"
        )
        await update.message.reply_text(msg, parse_mode="Markdown")

    async def cmd_balance(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        try:
            amount = float(context.args[0])
            if self.agent and hasattr(self.agent, 'risk_manager'):
                self.agent.risk_manager.initial_bankroll = amount
                self.agent.risk_manager.current_bankroll = amount + self.agent.risk_manager.daily_pnl
                await update.message.reply_text(f"✅ Bankroll updated to ₹{amount:.2f}")
            else:
                await update.message.reply_text("Agent or RiskManager not ready.")
        except (IndexError, ValueError):
            await update.message.reply_text("Usage: `/balance <amount>`\nExample: `/balance 10000`", parse_mode="Markdown")

    async def cmd_trade(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        try:
            amount = float(context.args[0])
            if self.agent and hasattr(self.agent, 'risk_manager'):
                self.agent.risk_manager.max_stake_per_trade = amount
                await update.message.reply_text(f"✅ Max stake per trade updated to ₹{amount:.2f}")
            else:
                await update.message.reply_text("Agent or RiskManager not ready.")
        except (IndexError, ValueError):
            await update.message.reply_text("Usage: `/trade <amount>`\nExample: `/trade 1000`", parse_mode="Markdown")

    async def cmd_profit(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        try:
            amount = float(context.args[0])
            # Assuming we can store this on the agent for AI reasoning context
            if self.agent:
                self.agent.daily_profit_expectation = amount
                await update.message.reply_text(f"✅ Daily profit expectation set to ₹{amount:.2f}. I will adapt the strategy accordingly.")
            else:
                await update.message.reply_text("Agent not ready.")
        except (IndexError, ValueError):
            await update.message.reply_text("Usage: `/profit <amount>`\nExample: `/profit 2000`", parse_mode="Markdown")

    async def cmd_tookbet(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        if not self.agent:
            await update.message.reply_text("Agent not running.")
            return
            
        try:
            if len(context.args) < 3:
                raise ValueError
                
            team = context.args[0].upper()
            amount = float(context.args[1])
            odds = float(context.args[2])
            
            # Simple wrapper to inject a manual position into the position manager
            if hasattr(self.agent, 'position_manager'):
                from agent.position_manager import Position
                pos = Position(
                    match_id="manual",
                    team=team,
                    entry_odds=odds,
                    stake=amount,
                    action="BACK",
                    reasoning="User manual entry via Bot"
                )
                self.agent.position_manager.add_position(pos)
                self.agent.risk_manager.add_exposure(amount)
                
                await update.message.reply_text(f"✅ Registered manual bet:\nBACK {team} | Stake: ₹{amount} | Odds: {odds}")
            else:
                await update.message.reply_text("Position Manager not available.")
                
        except (IndexError, ValueError):
            await update.message.reply_text(
                "Usage: `/tookbet <team> <amount> <odds>`\n"
                "Example: `/tookbet MI 1000 1.85`",
                parse_mode="Markdown"
            )

    async def send_alert(self, text: str):
        """Sends an alert to the configured chat if available"""
        if self.app and settings.TELEGRAM_ALERT_CHAT_ID:
            try:
                await self.app.bot.send_message(
                    chat_id=settings.TELEGRAM_ALERT_CHAT_ID,
                    text=text,
                    parse_mode="Markdown"
                )
            except Exception as e:
                logger.error(f"Failed to send alert to Chatbot: {e}")
