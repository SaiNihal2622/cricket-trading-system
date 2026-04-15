"""
Autonomous Trading Agent — Complete Production Build.

Loop: OBSERVE → ANALYZE → DECIDE → (APPROVE?) → EXECUTE → MONITOR

Features:
- Full autopilot mode: trades without human intervention
- Semi-auto mode: proposes trades, waits for user approval (30s timeout)
- Stop loss monitoring: auto-exits when odds move against you beyond threshold
- Session market trading: analyzes fancy/over markets
- Match Odds, Bookmaker, Sessions, Premium Sessions
- Real data: Cricbuzz live + player stats + Telegram signals
- Circuit breaker: halts on consecutive losses or daily loss limit
- AI Reasoner (Groq): overrides rule engine for borderline decisions
"""
import asyncio
import logging
import uuid
from datetime import datetime, timezone
from enum import Enum
from typing import Optional, List, Dict

from agent.position_manager import PositionManager, PositionStatus
from agent.risk_manager import RiskManager
from agent.execution_engine import SimulatedExchange, create_exchange
from agent.ai_reasoner import AIReasoner
from agent.session_analyzer import SessionAnalyzer
from agent.value_strategy import ValueStrategyEngine, WaitEntry
from strategy_engine.decision_engine import DecisionEngine, MatchContext
from strategy_engine.loss_cut_engine import LossCutEngine
from strategy_engine.bookset_engine import BooksetEngine
from ml_model.predictor import CricketMLModel
from data_ingestion.historical_data import HistoricalDataEngine

logger = logging.getLogger(__name__)


class AgentState(str, Enum):
    STOPPED       = "STOPPED"
    RUNNING       = "RUNNING"
    PAUSED        = "PAUSED"
    CIRCUIT_BREAK = "CIRCUIT_BREAK"


class TradingAgent:
    """
    Fully autonomous cricket trading agent.

    Two modes (set via AGENT_AUTOPILOT env var):
    - autopilot=True:  places bets automatically (default)
    - autopilot=False: proposes bets, waits 30s for user approval via dashboard
    """

    def __init__(self, settings=None, rb_instance=None):
        from config.settings import settings as default_settings
        self.settings = settings or default_settings

        # Core components
        self.position_manager  = PositionManager()
        self.risk_manager      = RiskManager(
            initial_bankroll     = getattr(self.settings, 'INITIAL_BANKROLL', 10000.0),
            max_stake_per_trade  = getattr(self.settings, 'MAX_STAKE_PER_TRADE', 1000.0),
            max_exposure         = getattr(self.settings, 'MAX_EXPOSURE', 5000.0),
            max_daily_loss       = getattr(self.settings, 'MAX_DAILY_LOSS', 2000.0),
            max_consecutive_losses = getattr(self.settings, 'MAX_CONSECUTIVE_LOSSES', 5),
        )
        self.exchange = create_exchange(
            getattr(self.settings, 'EXCHANGE_TYPE', 'simulated'),
            rb_instance    = rb_instance,
            initial_balance = getattr(self.settings, 'INITIAL_BANKROLL', 10000.0),
        )
        self._rb_instance = rb_instance   # direct reference for stop loss / sessions

        self.decision_engine  = DecisionEngine()
        self.loss_cut_engine  = LossCutEngine()
        self.bookset_engine   = BooksetEngine()
        self.session_analyzer  = SessionAnalyzer()
        self.value_strategy    = ValueStrategyEngine()
        self.historical_db     = HistoricalDataEngine()
        self.ml_model          = CricketMLModel(
            ml_enabled = getattr(self.settings, 'ML_ENABLED', False),
        )
        self.ai_reasoner      = AIReasoner(
            api_key = getattr(self.settings, 'GEMINI_API_KEY', '') or getattr(self.settings, 'GROQ_API_KEY', ''),
            model   = getattr(self.settings, 'GEMINI_MODEL', 'gemini-2.0-flash'),
        )

        # Mode
        self._autopilot = getattr(self.settings, 'AGENT_AUTOPILOT', True)

        # Stop loss config
        self._stop_loss_pct  = getattr(self.settings, 'STOP_LOSS_PCT', 20.0) / 100  # 20%
        self._stop_loss_enabled = getattr(self.settings, 'STOP_LOSS_ENABLED', True)

        # State
        self.state = AgentState.STOPPED
        self._loop_task: Optional[asyncio.Task] = None
        self._loop_interval = 3  # 3s loop for fast signal delivery
        self._action_log: List[dict] = []
        self._cycle_count = 0

        # Fast event detection
        self._prev_wickets: Dict[str, int] = {}      # match_id → last known wickets
        self._prev_over_int: Dict[str, int] = {}     # match_id → last over boundary fired
        self._milestone_fired: set = set()           # "match_id:milestone" already processed
        self._last_bookmaker_check: Dict[str, float] = {}  # match_id → last bookmaker alert ts

        # Deduplication — prevent same signal bombing
        self._last_signal_sent: Dict[str, float] = {}  # "type:team:match_id" → monotonic ts
        self._signal_cooldown = 300.0  # 5 min per signal type per team per match

        # Crisis entry tracking
        self._crisis_entry_fired: set = set()  # "match_id:team" already crisis-entered

        # Semi-auto approval tracking
        self._pending_approvals: Dict[str, dict] = {}   # id → proposal
        self._approval_timeout  = 30  # seconds

    # ── Lifecycle ───────────────────────────────────────────────────────────

    async def start(self):
        if self.state == AgentState.RUNNING:
            return
        self.state = AgentState.RUNNING
        self._loop_task = asyncio.create_task(self._agent_loop())
        self._log_action("AGENT_START", {
            "mode":      "autopilot" if self._autopilot else "semi_auto",
            "exchange":  getattr(self.settings, 'EXCHANGE_TYPE', 'simulated'),
            "bankroll":  getattr(self.settings, 'INITIAL_BANKROLL', 10000.0),
            "stop_loss": f"{self._stop_loss_pct*100:.0f}%",
        })
        logger.info(f"🚀 Trading Agent STARTED | mode={'AUTOPILOT' if self._autopilot else 'SEMI-AUTO'}")

    async def stop(self):
        self.state = AgentState.STOPPED
        if self._loop_task:
            self._loop_task.cancel()
            try:
                await self._loop_task
            except asyncio.CancelledError:
                pass
        self._log_action("AGENT_STOP", "Agent stopped")
        logger.info("⏹️ Trading Agent STOPPED")

    async def pause(self):
        self.state = AgentState.PAUSED
        self._log_action("AGENT_PAUSE", "Agent paused — monitoring only")

    async def resume(self):
        self.state = AgentState.RUNNING
        self._log_action("AGENT_RESUME", "Agent resumed")

    def set_autopilot(self, enabled: bool):
        self._autopilot = enabled
        self._log_action("MODE_CHANGE", f"Autopilot {'ENABLED' if enabled else 'DISABLED — semi-auto'}")

    # ── Main Loop ───────────────────────────────────────────────────────────

    async def _agent_loop(self):
        logger.info(f"Agent loop started (interval: {self._loop_interval}s)")
        while self.state in (AgentState.RUNNING, AgentState.PAUSED, AgentState.CIRCUIT_BREAK):
            try:
                self._cycle_count += 1
                await self._execute_cycle()
            except Exception as e:
                logger.error(f"Agent cycle error: {e}", exc_info=True)
                self._log_action("CYCLE_ERROR", str(e))
            await asyncio.sleep(self._loop_interval)

    async def _execute_cycle(self):
        """Single cycle: observe → analyze → decide → (approve) → execute"""
        # Circuit breaker check
        if self.risk_manager.circuit_breaker_active and self.state != AgentState.CIRCUIT_BREAK:
            self.state = AgentState.CIRCUIT_BREAK
            self._log_action("CIRCUIT_BREAK", {
                "reason": self.risk_manager.circuit_breaker_reason,
                "message": "Trading halted — manual reset required",
            })
            await self._publish_agent_action("CIRCUIT_BREAK", {
                "reason": self.risk_manager.circuit_breaker_reason,
            })
            logger.warning(f"🚨 CIRCUIT_BREAK: {self.risk_manager.circuit_breaker_reason}")
            return

        if self.state == AgentState.CIRCUIT_BREAK:
            return

        # Gather data
        data = await self._observe()
        if not data:
            return

        for match_id, match_data in data.items():
            state    = match_data.get("state", {})
            cur_wkts = int(state.get("total_wickets", 0))
            cur_over = float(state.get("overs", 0))
            cur_over_int = int(cur_over)

            # ── Instant wicket detection ──────────────────────────────────
            prev_wkts = self._prev_wickets.get(match_id, cur_wkts)
            if cur_wkts > prev_wkts:
                self._prev_wickets[match_id] = cur_wkts
                # Force Gemini bypass-cache on wicket
                self.ai_reasoner._last_over = -1.0
                asyncio.create_task(
                    self._on_wicket_event(match_id, match_data, cur_wkts)
                )
            else:
                self._prev_wickets[match_id] = cur_wkts

            # ── Over milestone detection (3, 6, 10, 15, 16, 18) ──────────
            prev_ov = self._prev_over_int.get(match_id, 0)
            if cur_over_int > prev_ov:
                for milestone in (3, 6, 10, 15, 16, 18, 20):
                    key = f"{match_id}:ov{milestone}"
                    if prev_ov < milestone <= cur_over_int and key not in self._milestone_fired:
                        self._milestone_fired.add(key)
                        asyncio.create_task(
                            self._on_over_milestone(match_id, match_data, milestone)
                        )
                self._prev_over_int[match_id] = cur_over_int

            # ── Bookmaker edge check (every 30s per match) ────────────────
            import time as _time
            last_bm = self._last_bookmaker_check.get(match_id, 0)
            if _time.monotonic() - last_bm > 30:
                self._last_bookmaker_check[match_id] = _time.monotonic()
                asyncio.create_task(self._check_bookmaker_edge(match_id, match_data))

            # Update simulated exchange odds
            if isinstance(self.exchange, SimulatedExchange):
                self.exchange.set_odds(
                    match_id,
                    match_data.get("odds_a", 1.85),
                    match_data.get("odds_b", 2.10),
                )

            # Update positions with latest odds
            self.position_manager.update_all_odds(
                match_id,
                match_data.get("odds_a", 1.85),
                match_data.get("odds_b", 2.10),
            )

            # Stop loss check (runs even when PAUSED)
            if self._stop_loss_enabled:
                await self._check_stop_loss(match_id, match_data)

            if self.state == AgentState.PAUSED:
                continue

            # Main decision
            position = self.position_manager.get_match_position(match_id)
            decision = await self._analyze(match_id, match_data, position)

            if decision and decision.signal != "HOLD":
                await self._execute_decision(match_id, match_data, decision, position)
            elif not position:
                # Also check value/high-odds strategy when rule engine says HOLD
                await self._evaluate_value_opportunity(match_id, match_data)

            # Anti-panic check on existing positions
            if position:
                anti_panic = self.value_strategy.get_anti_panic_signal(
                    match_data["state"], position,
                    match_data["odds_a"], match_data["odds_b"]
                )
                if anti_panic == "HOLD":
                    self._log_action("ANTI_PANIC_HOLD", "Wicket panic — situation still recoverable, holding position")
                    try:
                        from telegram_bot.notifier import send_anti_panic
                        s = match_data["state"]
                        await send_anti_panic(
                            signal    = "HOLD",
                            team      = position.backed_team,
                            overs     = float(s.get("overs", 0)),
                            score     = f"{s.get('total_runs',0)}/{s.get('total_wickets',0)}",
                            match     = f"{s.get('team_a','?')} vs {s.get('team_b','?')}",
                            reasoning = "Wicket fell but match situation still recoverable — hold position.",
                        )
                    except Exception:
                        pass
                elif anti_panic == "CUT":
                    self._log_action("ANTI_PANIC_CUT", "Wicket confirms collapse — triggering loss cut")
                    try:
                        from telegram_bot.notifier import send_anti_panic
                        s = match_data["state"]
                        await send_anti_panic(
                            signal    = "CUT",
                            team      = position.backed_team,
                            overs     = float(s.get("overs", 0)),
                            score     = f"{s.get('total_runs',0)}/{s.get('total_wickets',0)}",
                            match     = f"{s.get('team_a','?')} vs {s.get('team_b','?')}",
                            reasoning = "Multiple wickets — collapse confirmed. Exit immediately.",
                        )
                    except Exception:
                        pass
                    if decision:
                        decision.signal = "LOSS_CUT"
                        await self._execute_decision(match_id, match_data, decision, position)

            # Session market analysis (separate from main match odds)
            await self._analyze_and_execute_sessions(match_id, match_data)

    # ── Observe ─────────────────────────────────────────────────────────────

    async def _observe(self) -> Dict[str, dict]:
        """Gather all live data from Redis + Cricbuzz + RoyalBook."""
        try:
            from database.redis_client import get_redis, RedisCache
            redis = await get_redis()
            cache = RedisCache(redis)

            state    = await cache.get_match_state(1) or {}
            odds     = await cache.get_odds(1) or {}
            telegram = await cache.get_telegram_signals(1) or []

            # Also try to enrich with real live data from Cricbuzz
            if not state or state.get("source") == "mock":
                try:
                    from data_ingestion.cricket_stats import cricket_stats
                    live = await cricket_stats.get_live_score_cricbuzz()
                    if live:
                        # Merge live data into state
                        state.update(live)
                        await cache.set_match_state(1, state)
                except Exception as e:
                    logger.debug(f"Cricbuzz live data error: {e}")

            # Enrich state with player/team stats
            try:
                from data_ingestion.cricket_stats import cricket_stats
                state = cricket_stats.enrich_match_state(state)
            except Exception:
                pass

            # Get session markets from RoyalBook odds (already scraped)
            sessions = odds.get("sessions", [])
            premium_sessions = odds.get("premium_sessions", [])

            if not state:
                return {}

            return {
                str(state.get("match_id", "1")): {
                    "state":            state,
                    "odds_a":           float(odds.get("team_a_odds", 1.85)),
                    "odds_b":           float(odds.get("team_b_odds", 2.10)),
                    "odds_a_lay":       float(odds.get("team_a_lay") or 0) or None,
                    "odds_b_lay":       float(odds.get("team_b_lay") or 0) or None,
                    "bookmaker":        odds.get("bookmaker", {}),
                    "sessions":         sessions,
                    "premium_sessions": premium_sessions,
                    "telegram_signals": telegram,
                    "venue":            state.get("venue", ""),
                }
            }
        except Exception as e:
            logger.debug(f"Observe error: {e}")
            return {}

    # ── Stop Loss ────────────────────────────────────────────────────────────

    async def _check_stop_loss(self, match_id: str, data: dict):
        """
        Check if any open position needs stop loss execution.
        Triggers when: current odds have moved against us by > STOP_LOSS_PCT.
        """
        position = self.position_manager.get_match_position(match_id)
        if not position or position.status != PositionStatus.OPEN:
            return

        # Determine current odds for our backed team
        state   = data["state"]
        odds_a  = data["odds_a"]
        odds_b  = data["odds_b"]

        backed_team   = position.backed_team
        entry_odds    = position.entry_odds

        if backed_team == state.get("team_a", ""):
            current_odds = odds_a
        else:
            current_odds = odds_b

        if entry_odds <= 1.0 or current_odds <= 0:
            return

        # Loss threshold: if current odds have increased by stop_loss_pct above entry
        # (higher odds = worse for backed side)
        threshold = entry_odds * (1.0 + self._stop_loss_pct)

        if current_odds >= threshold:
            loss_pct = ((current_odds - entry_odds) / entry_odds) * 100
            logger.warning(
                f"🛑 STOP LOSS triggered: {backed_team} "
                f"entry={entry_odds:.2f} current={current_odds:.2f} "
                f"loss={loss_pct:.1f}%"
            )
            self._log_action("STOP_LOSS_TRIGGERED", {
                "team": backed_team,
                "entry_odds": entry_odds,
                "current_odds": current_odds,
                "loss_pct": round(loss_pct, 1),
                "threshold_pct": self._stop_loss_pct * 100,
            })

            # ── Telegram stop loss alert ──────────────────────────────
            try:
                from telegram_bot.notifier import send_stop_loss
                s          = data["state"]
                match_name = f"{s.get('team_a','?')} vs {s.get('team_b','?')}"
                overs      = float(s.get("overs", 0))
                score      = f"{s.get('total_runs',0)}/{s.get('total_wickets',0)}"
                h_team     = s.get("team_b", "") if backed_team == s.get("team_a") else s.get("team_a", "")
                await send_stop_loss(
                    team         = backed_team,
                    entry_odds   = entry_odds,
                    current_odds = current_odds,
                    loss_pct     = loss_pct,
                    hedge_team   = h_team,
                    hedge_stake  = position.total_exposure * 0.8,
                    overs        = overs,
                    score        = score,
                    match        = match_name,
                )
            except Exception:
                pass

            await self._execute_stop_loss(match_id, position, data, current_odds)

    async def _execute_stop_loss(self, match_id, position, data, current_odds):
        """Execute stop loss: hedge by backing the opposite team."""
        state = data["state"]

        # Hedge: back the opposite team at current odds
        if position.backed_team == state.get("team_a"):
            hedge_team = state.get("team_b", position.team_b)
            hedge_odds = data["odds_b"]
        else:
            hedge_team = state.get("team_a", position.team_a)
            hedge_odds = data["odds_a"]

        # Calculate hedge amount to minimize loss
        try:
            lc = self.loss_cut_engine.evaluate(
                stake=position.total_exposure,
                entry_odds=position.entry_odds,
                current_team_odds=current_odds,
                current_over=float(state.get("overs", 0)),
                wickets_fallen=int(state.get("total_wickets", 0)),
                run_rate=float(state.get("run_rate", 0)),
                required_rr=float(state.get("required_run_rate", 0)),
                is_wicket_just_fell=state.get("last_ball") == "W",
                win_probability=0.3,  # we're stop-lossing so probability is low
            )
            hedge_amount = lc.hedge_amount
        except Exception:
            hedge_amount = position.total_exposure * 0.8  # fallback: hedge 80%

        # Execute via RoyalBook if available, else simulated
        if self._rb_instance:
            result = await self._rb_instance.place_stop_loss(hedge_team, hedge_amount)
        else:
            result = await self.exchange.place_back(match_id, hedge_team, hedge_odds, hedge_amount)

        if result.get("success", False) if isinstance(result, dict) else result.success:
            pos = self.position_manager.execute_loss_cut(
                match_id=match_id,
                hedge_odds=hedge_odds,
                hedge_stake=hedge_amount,
            )
            if pos:
                self.risk_manager.record_trade_result(pos.realized_pnl, {"type": "STOP_LOSS"})
            self._log_action("STOP_LOSS_EXECUTED", {
                "hedge_team": hedge_team,
                "hedge_odds": hedge_odds,
                "hedge_stake": hedge_amount,
            })
            await self._publish_agent_action("STOP_LOSS", {
                "team": hedge_team,
                "stake": hedge_amount,
                "pnl": pos.realized_pnl if pos else 0,
            })
        else:
            msg = result.get("message", "unknown") if isinstance(result, dict) else result.message
            self._log_action("STOP_LOSS_FAILED", msg)

    # ── Wicket Event ─────────────────────────────────────────────────────────

    async def _on_wicket_event(self, match_id: str, data: dict, wickets: int):
        """Immediate analysis on wicket — check loss cut and send alert."""
        state  = data["state"]
        odds_a = data["odds_a"]
        odds_b = data["odds_b"]
        s      = lambda k, d=None: state.get(k, d)
        overs  = float(s("overs", 0))
        runs   = int(s("total_runs", 0))
        match  = f"{s('team_a','?')} vs {s('team_b','?')}"
        score  = f"{runs}/{wickets}"

        logger.info(f"⚡ WICKET EVENT: {match} — {score} in {overs:.1f} overs")

        position = self.position_manager.get_match_position(match_id)

        # Force immediate AI analysis on wicket
        if self.ai_reasoner.is_available:
            try:
                ml_pred = self.ml_model.predict(state)
                decision = self.decision_engine.evaluate(
                    self._build_match_context(match_id, data, position)
                )
                ai_result = await self.ai_reasoner.reason(
                    match_state=state,
                    odds={"team_a_odds": odds_a, "team_b_odds": odds_b, "bookmaker": data.get("bookmaker", {})},
                    ml_prediction={"win_probability": ml_pred.win_probability, "confidence": ml_pred.confidence, "momentum_score": ml_pred.momentum_score, "model_version": ml_pred.model_version},
                    decision_engine_output=decision.to_dict(),
                    position=position.to_dict() if position else None,
                    telegram_signals=data.get("telegram_signals", []),
                    historical=self.historical_db,
                )
                action = ai_result.get("action", "HOLD")
                conf   = ai_result.get("confidence", 0)
                reason = ai_result.get("reasoning", "")

                if action == "LOSS_CUT" and position and conf >= 0.65:
                    try:
                        from telegram_bot.notifier import send_loss_cut
                        await send_loss_cut(
                            team=position.backed_team,
                            entry_odds=position.entry_odds,
                            current_odds=odds_a if position.backed_team == s("team_a") else odds_b,
                            pnl=position.unrealized_pnl,
                            match=match,
                        )
                    except Exception:
                        pass
                    await self._execute_stop_loss(match_id, position, data,
                        odds_a if position.backed_team == s("team_a") else odds_b)
                elif action in ("HOLD", "BOOKSET") and conf >= 0.70:
                    # Send anti-panic signal
                    try:
                        from telegram_bot.notifier import send_anti_panic
                        sig = "CUT" if action == "LOSS_CUT" else "HOLD"
                        await send_anti_panic(
                            signal=sig,
                            team=position.backed_team if position else s("team_a", ""),
                            overs=overs, score=score, match=match, reasoning=reason,
                        )
                    except Exception:
                        pass
            except Exception as e:
                logger.debug(f"Wicket AI analysis error: {e}")

    # ── Over Milestone ────────────────────────────────────────────────────────

    async def _on_over_milestone(self, match_id: str, data: dict, milestone: int):
        """
        Fire at key over boundaries (3, 6, 10, 15, 16, 18).
        - Over 3: predict powerplay score → SESSION call on 6-over runs market
        - Over 6: PP complete → confirm PP score, fire match odds signal
        - Over 10: midway → batting team chance assessment
        - Over 15: pre-death → ENTER or SESSION for final runs
        - Over 16+: death — high-value window
        """
        state  = data["state"]
        odds_a = data["odds_a"]
        odds_b = data["odds_b"]
        s      = lambda k, d=None: state.get(k, d)
        overs  = float(s("overs", 0))
        runs   = int(s("total_runs", 0))
        wickets= int(s("total_wickets", 0))
        rr     = float(s("run_rate", 0))
        match  = f"{s('team_a','?')} vs {s('team_b','?')}"
        venue  = s("venue", "")
        innings= int(s("innings", 1))

        logger.info(f"🎯 OVER MILESTONE {milestone}: {match} — {runs}/{wickets} in {overs:.1f}ov @ {rr:.2f}rpo")

        # Force Gemini call at each milestone (clear cache)
        self.ai_reasoner._last_over = -1.0

        # ── Powerplay prediction (at over 3, project PP total) ────────────
        if milestone == 3 and innings == 1 and wickets <= 2:
            proj_pp = runs + int(rr * 3)  # 3 more overs at current RPO
            venue_stats = self.historical_db.get_venue_stats(venue)
            pp_avg = venue_stats.get("avg_powerplay", 52)
            diff   = proj_pp - pp_avg
            side   = "YES" if diff >= 3 else "NO"
            conf   = min(0.82, 0.60 + abs(diff) * 0.015)

            if conf >= 0.70 and data.get("sessions"):
                pp_sessions = [ss for ss in data.get("sessions", []) if "6 over" in ss.get("label", "").lower() or "powerplay" in ss.get("label", "").lower() or "pp run" in ss.get("label", "").lower()]
                if not pp_sessions:
                    pp_sessions = data.get("sessions", [])[:1]
                for pp_sess in pp_sessions[:1]:
                    label = pp_sess.get("label", f"6 Over Runs {s('team_a','')}")
                    line  = pp_sess.get("yes" if side=="YES" else "no", 0)
                    proposal = {
                        "type": "SESSION", "label": label, "side": side,
                        "stake": 200.0, "confidence": conf,
                        "reasoning": f"At {overs:.1f}ov: {runs}/{wickets} @ {rr:.1f}rpo → projected PP={proj_pp}, venue avg={pp_avg}. {'Above' if diff>0 else 'Below'} par by {abs(diff)} runs.",
                        "match_id": match_id, "predicted_runs": proj_pp,
                        "prob_over": conf if side=="YES" else 1-conf,
                        "prob_under": conf if side=="NO" else 1-conf,
                        "state": state,
                    }
                    await self._route_decision(proposal, self._execute_session_trade)

        # ── PP complete (over 6) — send match state assessment ────────────
        elif milestone == 6:
            venue_stats = self.historical_db.get_venue_stats(venue)
            pp_avg = venue_stats.get("avg_powerplay", 52)
            desc   = "STRONG" if runs > pp_avg + 8 else ("WEAK" if runs < pp_avg - 8 else "ON PAR")
            try:
                from telegram_bot.notifier import send_info
                await send_info(
                    f"🏏 *PP COMPLETE — {match}*\n"
                    f"Score: *{runs}/{wickets}* in 6 overs (avg: {pp_avg})\n"
                    f"Powerplay: *{desc}* | RPO: {rr:.1f}\n"
                    f"Match odds: {s('team_a','')} {odds_a:.2f} | {s('team_b','')} {odds_b:.2f}"
                )
            except Exception:
                pass

        # ── Death entry window (over 15-16) ──────────────────────────────
        elif milestone in (15, 16) and innings == 1:
            position = self.position_manager.get_match_position(match_id)
            if not position:
                # Evaluate entry in death
                ml_pred  = self.ml_model.predict(state)
                decision = self.decision_engine.evaluate(
                    self._build_match_context(match_id, data, position)
                )
                if self.ai_reasoner.is_available:
                    try:
                        ai = await self.ai_reasoner.reason(
                            match_state=state,
                            odds={"team_a_odds": odds_a, "team_b_odds": odds_b, "bookmaker": data.get("bookmaker", {})},
                            ml_prediction={"win_probability": ml_pred.win_probability, "confidence": ml_pred.confidence, "momentum_score": ml_pred.momentum_score, "model_version": ml_pred.model_version},
                            decision_engine_output=decision.to_dict(),
                            position=None,
                            telegram_signals=data.get("telegram_signals", []),
                            historical=self.historical_db,
                        )
                        if ai.get("action") == "ENTER" and ai.get("confidence", 0) >= 0.72:
                            proposal = self._build_entry_proposal(match_id, state, decision, odds_a, odds_b)
                            if proposal:
                                proposal["confidence"] = ai["confidence"]
                                proposal["reasoning"]  = f"🧠 Death entry: {ai.get('reasoning','')}"
                                proposal["ai_source"]  = "gemini"
                                await self._route_decision(proposal, self._execute_entry_from_proposal)
                    except Exception as e:
                        logger.debug(f"Death entry AI: {e}")

        # ── Over 10 midway assessment ─────────────────────────────────────
        elif milestone == 10 and innings == 2:
            rrr = float(s("required_run_rate", 0))
            if rrr > 0 and rr > 0:
                diff = rr - rrr
                if abs(diff) >= 1.5:
                    side_desc = "CHASING WELL" if diff > 0 else "BEHIND TARGET"
                    try:
                        from telegram_bot.notifier import send_info
                        await send_info(
                            f"📊 *MIDWAY UPDATE — {match}*\n"
                            f"Score: *{runs}/{wickets}* in 10 overs\n"
                            f"CRR: {rr:.2f} | RRR: {rrr:.2f} → *{side_desc}*\n"
                            f"Odds: {s('team_a','')} {odds_a:.2f} | {s('team_b','')} {odds_b:.2f}"
                        )
                    except Exception:
                        pass

    # ── Bookmaker Edge ────────────────────────────────────────────────────────

    async def _check_bookmaker_edge(self, match_id: str, data: dict):
        """Detect bookmaker price divergence from match odds and alert."""
        bookmaker = data.get("bookmaker", {})
        if not bookmaker:
            return
        state  = data["state"]
        odds_a = data["odds_a"]
        odds_b = data["odds_b"]
        s      = lambda k, d=None: state.get(k, d)
        overs  = float(s("overs", 0))

        # Never alert before match starts
        if overs < 0.1:
            return

        runs  = int(s("total_runs", 0))
        wkts  = int(s("total_wickets", 0))
        score = f"{runs}/{wkts}"
        match = f"{s('team_a','?')} vs {s('team_b','?')}"

        for team_key, bm_data in bookmaker.items():
            if not isinstance(bm_data, dict):
                continue
            bm_back = float(bm_data.get("back", 0) or 0)
            if bm_back <= 0:
                continue

            # Convert bookmaker 100-base to decimal
            if bm_back > 10:
                bm_decimal = (bm_back / 100) + 1
            else:
                bm_decimal = bm_back

            # Determine market odds for this team
            team_a = s("team_a", "")
            team_b = s("team_b", "")
            if team_key.lower() in team_a.lower() or team_a.lower() in team_key.lower():
                market_odds = odds_a
            elif team_key.lower() in team_b.lower() or team_b.lower() in team_key.lower():
                market_odds = odds_b
            else:
                continue

            if market_odds <= 0:
                continue

            edge = abs(bm_decimal - market_odds) / market_odds
            if edge >= 0.06:  # 6%+ divergence = bookmaker edge
                stake = min(300.0, self.risk_manager.max_stake_per_trade * 0.3)
                # Route through _route_decision for dedup + confidence gate
                bm_proposal = {
                    "type":       "BOOKMAKER_EDGE",
                    "match_id":   match_id,
                    "team":       team_key,
                    "odds":       bm_decimal,
                    "stake":      stake,
                    "confidence": min(0.80, 0.60 + edge),
                    "reasoning":  f"Bookmaker {bm_decimal:.2f} vs market {market_odds:.2f} — {edge:.1%} edge on {team_key}",
                    "state":      state,
                    "_bm_send": {   # carry payload for notifier
                        "bookmaker_odds": bm_decimal, "match_odds": market_odds,
                        "edge": edge, "score": score, "match": match, "overs": overs,
                    },
                }
                async def _send_bm(p):
                    try:
                        from telegram_bot.notifier import send_bookmaker_call
                        bm = p["_bm_send"]
                        await send_bookmaker_call(
                            team=p["team"], bookmaker_odds=bm["bookmaker_odds"],
                            match_odds=bm["match_odds"], edge=bm["edge"],
                            stake=p["stake"], overs=bm["overs"],
                            score=bm["score"], match=bm["match"],
                        )
                    except Exception:
                        pass
                logger.info(f"Bookmaker edge signal: {team_key} BM={bm_decimal:.2f} MO={market_odds:.2f} edge={edge:.1%}")
                await self._route_decision(bm_proposal, _send_bm)

    def _build_match_context(self, match_id, data, position):
        """Build MatchContext for decision engine."""
        from strategy_engine.decision_engine import MatchContext
        state  = data["state"]
        odds_a = data["odds_a"]
        odds_b = data["odds_b"]
        ml     = self.ml_model.predict(state)
        if position:
            entry_odds  = position.entry_odds
            backed_team = "A" if position.backed_team == state.get("team_a") else "B"
        else:
            entry_odds  = odds_a
            backed_team = "A"
        return MatchContext(
            match_id=int(match_id) if str(match_id).isdigit() else 1,
            team_a=state.get("team_a", "Team A"),
            team_b=state.get("team_b", "Team B"),
            innings=int(state.get("innings", 1)),
            current_over=float(state.get("overs", 0)),
            total_runs=int(state.get("total_runs", 0)),
            total_wickets=int(state.get("total_wickets", 0)),
            run_rate=float(state.get("run_rate", 0)),
            required_run_rate=float(state.get("required_run_rate", 0)),
            target=int(state.get("target", 0)),
            team_a_odds=odds_a,
            team_b_odds=odds_b,
            stake=self.risk_manager.max_stake_per_trade,
            entry_odds=entry_odds,
            backed_team=backed_team,
            win_probability=ml.win_probability,
            momentum_score=ml.momentum_score,
            is_wicket_just_fell=state.get("last_ball") == "W",
            telegram_signals=data.get("telegram_signals", []),
        )

    # ── Analyze ─────────────────────────────────────────────────────────────

    async def _analyze(self, match_id, data, position) -> Optional[object]:
        """Run decision engine + optional AI override."""
        state  = data["state"]
        odds_a = data["odds_a"]
        odds_b = data["odds_b"]

        ml_pred = self.ml_model.predict(state)
        ctx     = self._build_match_context(match_id, data, position)
        decision = self.decision_engine.evaluate(ctx)

        # ── Auto-bookset: check if position profit is lockable ────────────
        if position and position.status.value == "OPEN" and decision.signal != "LOSS_CUT":
            backed_team = position.backed_team
            curr_odds   = odds_a if backed_team == state.get("team_a") else odds_b
            entry_odds  = position.entry_odds
            if entry_odds > 0 and curr_odds > 0:
                compression = curr_odds / entry_odds
                if compression <= 0.70:  # odds dropped to 70% → guaranteed profit available
                    decision.signal    = "BOOKSET"
                    decision.bookset   = True
                    decision.confidence = 0.88
                    decision.reasoning  = (
                        f"BOOKSET: {backed_team} moved from {entry_odds:.2f}→{curr_odds:.2f} "
                        f"({compression:.0%} of entry). Lock guaranteed profit now."
                    )

        # AI Reasoner for borderline/conflicting/critical moments
        telegram_signals = data.get("telegram_signals", [])
        is_borderline    = 0.40 <= decision.confidence <= 0.60
        is_conflicting   = (
            ml_pred.win_probability > 0.6
            and any(s.get("sentiment", 0) < -0.3 for s in telegram_signals)
        ) or (
            ml_pred.win_probability < 0.4
            and any(s.get("sentiment", 0) > 0.3 for s in telegram_signals)
        )
        is_critical = (
            float(state.get("overs", 0)) >= 15
            or (state.get("last_ball") == "W" and int(state.get("total_wickets", 0)) >= 5)
        )

        if self.ai_reasoner.is_available and (is_borderline or is_conflicting or is_critical):
            try:
                ai_result = await self.ai_reasoner.reason(
                    match_state            = state,
                    odds                   = {
                        "team_a_odds": odds_a,
                        "team_b_odds": odds_b,
                        "bookmaker":   data.get("bookmaker", {}),
                    },
                    ml_prediction          = {
                        "win_probability":  ml_pred.win_probability,
                        "momentum_score":   ml_pred.momentum_score,
                        "model_version":    ml_pred.model_version,
                        "confidence":       ml_pred.confidence,
                    },
                    decision_engine_output = decision.to_dict(),
                    position               = position.to_dict() if position else None,
                    telegram_signals       = telegram_signals,
                    historical             = self.historical_db,   # 17-year IPL data
                )
                ai_action = ai_result.get("action", "HOLD")
                ai_conf   = ai_result.get("confidence", 0)

                if ai_conf > decision.confidence and ai_action != decision.signal:
                    self._log_action("AI_OVERRIDE", {
                        "from": decision.signal, "to": ai_action,
                        "reasoning": ai_result.get("reasoning", ""),
                    })
                    decision.signal    = ai_action
                    decision.confidence = ai_conf
                    decision.reasoning = f"🧠 {ai_result.get('reasoning', '')}"
                    if ai_result.get("team"):
                        decision.entry_team = ai_result["team"]

                # If Gemini recommends a session call, fire it now
                sc = ai_result.get("session_call")
                if sc and isinstance(sc, dict) and ai_conf >= 0.70:
                    sess_proposal = {
                        "type":          "SESSION",
                        "label":         sc.get("label", "Session"),
                        "side":          sc.get("side", "YES"),
                        "stake":         200.0,
                        "confidence":    ai_conf,
                        "reasoning":     f"🧠 {ai_result.get('reasoning','')} | Line:{sc.get('line')} Proj:{sc.get('projected')}",
                        "match_id":      match_id,
                        "predicted_runs": float(sc.get("projected", 0) or 0),
                        "prob_over":     ai_conf if sc.get("side","YES") == "YES" else 1 - ai_conf,
                        "prob_under":    ai_conf if sc.get("side","YES") == "NO" else 1 - ai_conf,
                        "state":         state,
                    }
                    asyncio.create_task(
                        self._route_decision(sess_proposal, self._execute_session_trade)
                    )
            except Exception as e:
                logger.warning(f"AI Reasoner: {e}")

        return decision

    # ── Value Strategy ───────────────────────────────────────────────────────

    async def _evaluate_value_opportunity(self, match_id: str, data: dict):
        """
        Check for high-odds value entries when the rule engine says HOLD.
        Priority 1: CRISIS ENTRY — odds 8-20+ (team in big trouble, recovery possible)
        Priority 2: Normal value engine for mid-range opportunities.
        """
        state  = data["state"]
        odds_a = data["odds_a"]
        odds_b = data["odds_b"]
        overs  = float(state.get("overs", 0))
        wickets= int(state.get("total_wickets", 0))
        venue  = data.get("venue", state.get("venue", ""))
        bankroll = self.risk_manager.bankroll

        # ── CRISIS ENTRY: back team at very high odds (8-20+) ─────────────────
        for team_key, team_odds in (("A", odds_a), ("B", odds_b)):
            if 7.0 <= team_odds <= 25.0 and overs >= 0.5:
                crisis_key = f"{match_id}:{team_key}"
                if crisis_key in self._crisis_entry_fired:
                    continue

                team_name = state.get("team_a") if team_key == "A" else state.get("team_b")
                innings   = int(state.get("innings", 1))
                rr        = float(state.get("run_rate", 0))
                rrr       = float(state.get("required_run_rate", 0))

                # Recovery possible?
                # 1st innings: team lost 3-4 wickets but <over 12 = still set a decent total
                # 2nd innings: team needs high RRR but has wickets in hand
                recoverable = False
                if innings == 1 and wickets <= 4 and overs <= 14:
                    recoverable = True  # lower order can still score 120+
                elif innings == 2 and wickets <= 4 and rrr <= 14.0:
                    recoverable = True  # high but achievable RRR with wickets in hand

                if not recoverable:
                    continue

                # Confidence scales with how "recoverable" the situation is
                conf = 0.72 if team_odds <= 12.0 else 0.68 if team_odds <= 18.0 else 0.64
                if conf < 0.70:
                    continue

                # Stake: 40-50% of bankroll for crisis entry (high-EV bet)
                crisis_stake = min(bankroll * 0.45, 500.0)
                crisis_stake = max(100.0, crisis_stake)

                # Bookset target: when odds compress to 30% of entry
                bookset_at  = round(team_odds * 0.30, 2)
                stop_loss_at = round(team_odds * 1.35, 2)

                self._crisis_entry_fired.add(crisis_key)
                proposal = {
                    "type":          "CRISIS_ENTRY",
                    "match_id":      match_id,
                    "team":          team_name,
                    "odds":          team_odds,
                    "stake":         crisis_stake,
                    "confidence":    conf,
                    "ev":            round((team_odds - 1) * conf - (1 - conf), 3),
                    "reasoning":     f"CRISIS ENTRY: {team_name} at {team_odds:.1f} odds. {wickets} wkts in {overs:.1f} ov. Recovery possible. Bookset at {bookset_at}.",
                    "bookset_at":    bookset_at,
                    "stop_loss_at":  stop_loss_at,
                    "odds_tier":     "very_high",
                    "state":         state,
                    "ai_source":     "crisis_hunter",
                }
                logger.info(f"🚨 CRISIS ENTRY: {team_name} @ {team_odds:.1f} ({wickets}wkts/{overs:.1f}ov)")
                await self._route_decision(proposal, self._execute_entry_from_proposal)
                return  # Don't double-fire both teams

        # Evaluate at any odds — value engine decides internally
        opp = self.value_strategy.evaluate(
            state    = state,
            team_a   = state.get("team_a", "Team A"),
            team_b   = state.get("team_b", "Team B"),
            odds_a   = odds_a,
            odds_b   = odds_b,
            position = None,
            bankroll = self.risk_manager.bankroll,
            historical = self.historical_db,
        )

        if not opp:
            return

        stake = round(self.risk_manager.bankroll * opp.stake_pct / 10) * 10
        stake = max(50.0, min(stake, self.risk_manager.max_stake_per_trade))

        proposal = {
            "type":        "VALUE_" + opp.action,
            "match_id":    match_id,
            "team":        opp.team,
            "odds":        opp.target_odds,
            "stake":       stake,
            "confidence":  opp.confidence,
            "reasoning":   opp.reasoning,
            "state":       state,
            "stop_loss_at": opp.stop_loss_at,
            "bookset_at":   opp.bookset_at,
            "is_lay":       opp.is_lay,
            "ev":           opp.ev,
        }

        if opp.is_lay:
            # Lay bet: use RoyalBook lay or simulated
            async def _execute_lay(p):
                if self._rb_instance:
                    res = await self._rb_instance.place_lay_bet(p["team"], p["stake"])
                else:
                    res = await self.exchange.place_lay(p["match_id"], p["team"], p["odds"], p["stake"])
                success = res.get("success", False) if isinstance(res, dict) else res.success
                self._log_action("LAY_EXECUTED" if success else "LAY_FAILED", {
                    "team": p["team"], "odds": p["odds"], "stake": p["stake"],
                    "reasoning": p["reasoning"],
                })
                if success:
                    await self._publish_agent_action("VALUE_LAY", p)
            await self._route_decision(proposal, _execute_lay)
        else:
            await self._route_decision(proposal, self._execute_entry_from_proposal)

        self._log_action("VALUE_OPPORTUNITY_FOUND", {
            "action": opp.action, "team": opp.team,
            "odds": opp.target_odds, "ev": f"{opp.ev*100:.0f}%",
            "reasoning": opp.reasoning[:120],
        })

    # ── Session Analysis ─────────────────────────────────────────────────────

    async def _analyze_and_execute_sessions(self, match_id: str, data: dict):
        """Analyze session/fancy markets and trade the best opportunity."""
        sessions = data.get("sessions", []) + data.get("premium_sessions", [])
        if not sessions:
            return

        state   = data["state"]
        venue   = data.get("venue", state.get("venue", ""))
        bankroll = self.risk_manager.bankroll

        try:
            best = self.session_analyzer.get_best_session_trade(
                state    = state,
                sessions = sessions,
                bankroll = bankroll,
                venue    = venue,
            )
        except Exception as e:
            logger.debug(f"Session analyzer error: {e}")
            return

        if not best or best["confidence"] < 0.55:
            return

        stake = best.get("recommended_stake", 100.0)
        stake = max(50.0, min(stake, self.risk_manager.max_stake_per_trade / 2))

        proposal = {
            "type":       "SESSION",
            "label":      best["label"],
            "side":       best["side"],
            "stake":      stake,
            "confidence": best["confidence"],
            "reasoning":  best["reasoning"],
            "match_id":   match_id,
        }

        await self._route_decision(proposal, self._execute_session_trade)

    async def _execute_session_trade(self, proposal: dict):
        """Execute a session bet via RoyalBook or simulated."""
        label  = proposal["label"]
        side   = proposal["side"]
        stake  = proposal["stake"]
        match_id = proposal["match_id"]

        if self._rb_instance:
            result = await self._rb_instance.place_session_bet(label, side, stake)
            success = result.get("success", False)
            msg     = result.get("message", "")
        else:
            # Simulate session bet
            sim_result = await self.exchange.place_back(match_id, f"SESSION:{label}", 1.85, stake)
            success = sim_result.success
            msg     = sim_result.message

        self._log_action("SESSION_EXECUTED" if success else "SESSION_FAILED", {
            "label": label, "side": side, "stake": stake, "message": msg,
        })
        if success:
            await self._publish_agent_action("SESSION_BET", proposal)

    # ── Execute Decision ─────────────────────────────────────────────────────

    async def _execute_decision(self, match_id, data, decision, position):
        state  = data["state"]
        odds_a = data["odds_a"]
        odds_b = data["odds_b"]

        if decision.signal == "ENTER" and not position:
            proposal = self._build_entry_proposal(match_id, state, decision, odds_a, odds_b)
            if proposal:
                await self._route_decision(proposal, self._execute_entry_from_proposal)

        elif decision.signal == "LOSS_CUT" and position:
            await self._execute_loss_cut(match_id, position, decision, odds_a, odds_b)

        elif decision.signal == "BOOKSET" and position and decision.bookset:
            await self._execute_bookset(match_id, position, decision, odds_a, odds_b)

    def _build_entry_proposal(self, match_id, state, decision, odds_a, odds_b) -> Optional[dict]:
        """Build entry trade proposal dict."""
        raw_team = decision.entry_team or "A"
        if raw_team == "A":
            team = state.get("team_a", "Team A")
        elif raw_team == "B":
            team = state.get("team_b", "Team B")
        else:
            team = raw_team

        odds = odds_a if team == state.get("team_a") else odds_b

        approval = self.risk_manager.approve_trade(
            proposed_stake    = self.risk_manager.max_stake_per_trade,
            current_exposure  = self.position_manager.get_total_exposure(),
            win_probability   = decision.factors.get("win_probability", 0.5),
            confidence        = decision.confidence,
            odds              = odds,
        )
        if not approval["approved"]:
            self._log_action("ENTRY_REJECTED", f"Risk: {approval['rejections']}")
            return None

        return {
            "type":       "ENTRY",
            "match_id":   match_id,
            "team":       team,
            "odds":       odds,
            "stake":      approval["adjusted_stake"],
            "confidence": decision.confidence,
            "reasoning":  decision.reasoning,
            "state":      state,
            "warnings":   approval.get("warnings", []),
        }

    # ── Approval Router ──────────────────────────────────────────────────────

    async def _route_decision(self, proposal: dict, executor):
        """
        Route a trade proposal:
        - Autopilot: execute immediately
        - Semi-auto: publish for user approval, wait 30s
        Only fires Telegram if confidence >= MIN_SIGNAL_CONFIDENCE (default 0.70).
        """
        import time as _t
        confidence = float(proposal.get("confidence", 0))
        min_conf   = getattr(self.settings, "MIN_SIGNAL_CONFIDENCE", 0.70)

        # ── Pre-match guard: never signal before ball 1 ───────────────────────
        state = proposal.get("state", {})
        overs = float(state.get("overs", 0))
        if overs < 0.1 and proposal.get("type") not in ("SESSION",):
            logger.debug(f"Signal suppressed: match not started yet (overs={overs})")
            return

        # ── Deduplication: same signal+team+match → 5 min cooldown ───────────
        match_id   = str(proposal.get("match_id", "1"))
        sig_team   = str(proposal.get("team", ""))
        sig_type   = str(proposal.get("type", ""))
        dedup_key  = f"{sig_type}:{sig_team}:{match_id}"
        now_t      = _t.monotonic()
        last_t     = self._last_signal_sent.get(dedup_key, 0)
        if now_t - last_t < self._signal_cooldown:
            logger.debug(f"Dedup: {dedup_key} suppressed (sent {now_t-last_t:.0f}s ago)")
            return
        self._last_signal_sent[dedup_key] = now_t

        # ── 70%+ confidence gate ─────────────────────────────────────────────
        if confidence < min_conf:
            self._log_action("SIGNAL_FILTERED", {
                "type":       proposal.get("type"),
                "confidence": f"{confidence:.0%}",
                "threshold":  f"{min_conf:.0%}",
                "reason":     f"confidence {confidence:.0%} below threshold {min_conf:.0%} — not sending",
            })
            logger.debug(
                f"Signal filtered: {proposal.get('type')} confidence={confidence:.0%} < {min_conf:.0%}"
            )
            # Still execute in autopilot if agent is live, but NO Telegram noise
            if self._autopilot:
                await executor(proposal)
            return

        # ── Fire Telegram notification immediately (zero delay, awaited) ────────
        try:
            from telegram_bot.notifier import send_bet_call, send_bookset_call, send_session_call
            state      = proposal.get("state", {})
            ptype      = proposal.get("type", "BACK")
            action     = ptype.replace("VALUE_", "").replace("ENTRY", "BACK")
            overs      = float(state.get("overs", 0))
            runs       = state.get("total_runs", 0)
            wkts       = state.get("total_wickets", 0)
            score      = f"{runs}/{wkts}"
            match      = f"{state.get('team_a','?')} vs {state.get('team_b','?')}"
            ai_source  = proposal.get("ai_source", "")

            if action == "PROGRESSIVE_BOOKSET":
                await send_bookset_call(
                    team             = proposal.get("team", ""),
                    entry_odds       = float(proposal.get("entry_odds", proposal.get("odds", 0))),
                    current_odds     = float(proposal.get("odds", 0)),
                    overs            = overs,
                    match            = match,
                    guaranteed_profit = float(proposal.get("guaranteed_profit", 0) or 0),
                )
            elif ptype == "SESSION":
                await send_session_call(
                    label           = proposal.get("label", ""),
                    side            = proposal.get("side", "YES"),
                    stake           = float(proposal.get("stake", 0)),
                    confidence      = float(proposal.get("confidence", 0)),
                    reasoning       = proposal.get("reasoning", ""),
                    overs           = overs,
                    score           = score,
                    match           = match,
                    predicted_runs  = float(proposal.get("predicted_runs", 0) or 0),
                    prob_over       = float(proposal.get("prob_over", 0) or 0),
                    prob_under      = float(proposal.get("prob_under", 0) or 0),
                )
            else:
                await send_bet_call(
                    action     = action,
                    team       = proposal.get("team", ""),
                    odds       = float(proposal.get("odds", 0)),
                    stake      = float(proposal.get("stake", 0)),
                    ev         = float(proposal.get("ev", 0)),
                    confidence = float(proposal.get("confidence", 0)),
                    reasoning  = proposal.get("reasoning", ""),
                    overs      = overs,
                    score      = score,
                    bookset_at = float(proposal.get("bookset_at", 0) or 0),
                    stop_loss  = float(proposal.get("stop_loss_at", 0) or 0),
                    tier       = proposal.get("odds_tier", "mid"),
                    match      = match,
                    ai_source  = ai_source,
                )
        except Exception as _tg_err:
            logger.debug(f"Telegram notify error: {_tg_err}")

        if self._autopilot:
            await executor(proposal)
        else:
            approval_id = str(uuid.uuid4())[:8]
            proposal["approval_id"] = approval_id
            self._pending_approvals[approval_id] = {
                "proposal": proposal,
                "executor": executor,
                "created":  datetime.now(timezone.utc).isoformat(),
                "approved": None,
            }
            await self._publish_agent_action("AWAITING_APPROVAL", proposal)
            self._log_action("AWAITING_APPROVAL", {
                "approval_id": approval_id,
                "type":        proposal.get("type"),
                "details":     {k: v for k, v in proposal.items() if k not in ("state", "executor")},
            })
            # Schedule timeout
            asyncio.create_task(self._approval_timeout_handler(approval_id, executor))

    async def _approval_timeout_handler(self, approval_id: str, executor):
        """Auto-reject approval if not acted on within timeout."""
        await asyncio.sleep(self._approval_timeout)
        entry = self._pending_approvals.get(approval_id)
        if entry and entry["approved"] is None:
            entry["approved"] = False
            self._pending_approvals.pop(approval_id, None)
            self._log_action("APPROVAL_TIMEOUT", {"approval_id": approval_id})
            await self._publish_agent_action("APPROVAL_EXPIRED", {"approval_id": approval_id})

    async def approve_trade(self, approval_id: str) -> bool:
        """Called by the API when user clicks Accept."""
        entry = self._pending_approvals.get(approval_id)
        if not entry or entry["approved"] is not None:
            return False

        entry["approved"] = True
        proposal = entry["proposal"]
        executor = entry["executor"]
        self._pending_approvals.pop(approval_id, None)

        self._log_action("TRADE_APPROVED", {"approval_id": approval_id})
        await executor(proposal)
        return True

    async def reject_trade(self, approval_id: str) -> bool:
        """Called by the API when user clicks Reject."""
        entry = self._pending_approvals.get(approval_id)
        if not entry:
            return False

        entry["approved"] = False
        self._pending_approvals.pop(approval_id, None)
        self._log_action("TRADE_REJECTED", {"approval_id": approval_id})
        await self._publish_agent_action("TRADE_REJECTED", {"approval_id": approval_id})
        return True

    def get_pending_approvals(self) -> list:
        return [
            {**v["proposal"], "created": v["created"]}
            for k, v in self._pending_approvals.items()
            if v["approved"] is None
        ]

    # ── Trade Executors ──────────────────────────────────────────────────────

    async def _execute_entry_from_proposal(self, proposal: dict):
        """Execute an ENTER trade from an approved proposal."""
        match_id = proposal["match_id"]
        team     = proposal["team"]
        odds     = proposal["odds"]
        stake    = proposal["stake"]
        state    = proposal["state"]

        result = await self.exchange.place_back(match_id, team, odds, stake)
        if isinstance(result, dict):
            success = result.get("success", False)
            msg     = result.get("message", "")
            filled_odds  = odds
            filled_stake = stake
        else:
            success      = result.success
            msg          = result.message
            filled_odds  = result.filled_odds
            filled_stake = result.filled_stake

        if not success:
            self._log_action("ENTRY_FAILED", msg)
            return

        position = self.position_manager.open_position(
            match_id    = match_id,
            team_a      = state.get("team_a", "Team A"),
            team_b      = state.get("team_b", "Team B"),
            backed_team = team,
            odds        = filled_odds,
            stake       = filled_stake,
        )

        self._log_action("ENTRY_EXECUTED", {
            "position_id": position.position_id,
            "team":        team,
            "odds":        filled_odds,
            "stake":       filled_stake,
            "confidence":  proposal.get("confidence"),
            "reasoning":   proposal.get("reasoning"),
        })
        await self._publish_agent_action("ENTRY", position.to_dict())

    async def _execute_loss_cut(self, match_id, position, decision, odds_a, odds_b):
        if not decision.loss_cut:
            return

        hedge_amount  = decision.loss_cut.hedge_amount
        opposite_team = position.team_b if position.backed_team == position.team_a else position.team_a
        hedge_odds    = odds_b if position.backed_team == position.team_a else odds_a

        result = await self.exchange.place_back(match_id, opposite_team, hedge_odds, hedge_amount)
        if isinstance(result, dict):
            success = result.get("success", False)
            msg     = result.get("message", "")
        else:
            success = result.success
            msg     = result.message

        if not success:
            self._log_action("HEDGE_FAILED", msg)
            return

        position = self.position_manager.execute_loss_cut(
            match_id   = match_id,
            hedge_odds = hedge_odds,
            hedge_stake = hedge_amount,
        )
        if position:
            self.risk_manager.record_trade_result(position.realized_pnl, {"type": "LOSS_CUT"})
            self._log_action("LOSS_CUT_EXECUTED", {
                "position_id":  position.position_id,
                "hedge_team":   opposite_team,
                "hedge_odds":   hedge_odds,
                "hedge_stake":  hedge_amount,
                "locked_pnl":   position.realized_pnl,
            })
            await self._publish_agent_action("LOSS_CUT", position.to_dict())
            try:
                from telegram_bot.notifier import send_loss_cut
                await send_loss_cut(
                    team         = position.backed_team,
                    entry_odds   = position.entry_odds,
                    current_odds = hedge_odds,
                    pnl          = position.realized_pnl,
                    match        = f"{position.team_a} vs {position.team_b}",
                )
            except Exception:
                pass

    async def _execute_bookset(self, match_id, position, decision, odds_a, odds_b):
        bs = decision.bookset
        result_a = await self.exchange.place_back(match_id, position.team_a, odds_a, bs.stake_a)
        result_b = await self.exchange.place_back(match_id, position.team_b, odds_b, bs.stake_b)

        def _ok(r):
            return r.get("success", False) if isinstance(r, dict) else r.success

        if not (_ok(result_a) and _ok(result_b)):
            self._log_action("BOOKSET_FAILED", "One or both legs failed")
            return

        def _odds(r, fallback):
            return fallback if isinstance(r, dict) else r.filled_odds

        def _stake(r, fallback):
            return fallback if isinstance(r, dict) else r.filled_stake

        position = self.position_manager.execute_bookset(
            match_id        = match_id,
            stake_a         = _stake(result_a, bs.stake_a),
            stake_b         = _stake(result_b, bs.stake_b),
            odds_a          = _odds(result_a, odds_a),
            odds_b          = _odds(result_b, odds_b),
            guaranteed_profit = bs.guaranteed_profit,
        )
        if position:
            self.risk_manager.record_trade_result(bs.guaranteed_profit, {"type": "BOOKSET"})
            self._log_action("BOOKSET_EXECUTED", {
                "position_id":       position.position_id,
                "guaranteed_profit": bs.guaranteed_profit,
            })
            await self._publish_agent_action("BOOKSET", position.to_dict())

    # ── Publish ──────────────────────────────────────────────────────────────

    def _log_action(self, action_type: str, data):
        entry = {
            "action":    action_type,
            "data":      data if isinstance(data, dict) else {"message": str(data)},
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "cycle":     self._cycle_count,
        }
        self._action_log.append(entry)
        if len(self._action_log) > 500:
            self._action_log = self._action_log[-500:]
        logger.info(f"🤖 [{action_type}] {data}")

    async def _publish_agent_action(self, action: str, data: dict):
        try:
            from database.redis_client import get_redis, RedisCache
            redis = await get_redis()
            cache = RedisCache(redis)
            await cache.publish("agent:actions", {
                "action":    action,
                "data":      data,
                "timestamp": datetime.now(timezone.utc).isoformat(),
            })
        except Exception:
            pass

    # ── Status ──────────────────────────────────────────────────────────────

    def get_status(self) -> dict:
        exchange_stats = {}
        if isinstance(self.exchange, SimulatedExchange):
            exchange_stats = self.exchange.get_stats()

        return {
            "state":            self.state.value,
            "mode":             "autopilot" if self._autopilot else "semi_auto",
            "exchange_type":    getattr(self.settings, 'EXCHANGE_TYPE', 'simulated'),
            "cycle_count":      self._cycle_count,
            "loop_interval":    self._loop_interval,
            "stop_loss_pct":    self._stop_loss_pct * 100,
            "risk":             self.risk_manager.get_status(),
            "portfolio":        self.position_manager.get_portfolio_summary(),
            "exchange":         exchange_stats,
            "pending_approvals": self.get_pending_approvals(),
            "recent_actions":   self._action_log[-20:],
        }

    def get_action_log(self, n: int = 50) -> List[dict]:
        return self._action_log[-n:]
