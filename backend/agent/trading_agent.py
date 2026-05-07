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
from ml_model.ensemble_predictor import EnsemblePredictor
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

    def __init__(self, settings=None, exchange_instance=None):
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
            exchange_instance = exchange_instance,
            initial_balance = getattr(self.settings, 'INITIAL_BANKROLL', 10000.0),
        )
        self._exchange_instance = exchange_instance   # direct reference for stop loss / sessions

        self.decision_engine  = DecisionEngine()
        self.loss_cut_engine  = LossCutEngine()
        self.bookset_engine   = BooksetEngine()
        self.session_analyzer  = SessionAnalyzer()
        self.value_strategy    = ValueStrategyEngine()
        self.historical_db     = HistoricalDataEngine()
        self.ml_model          = CricketMLModel()
        self.ensemble_predictor = EnsemblePredictor()
        self.ai_reasoner      = AIReasoner(
            api_key = getattr(self.settings, 'GROQ_API_KEY', ''),
            model   = getattr(self.settings, 'GROQ_MODEL', 'llama-3.3-70b-versatile'),
        )
        try:
            from agent.strategy_engine.arbitrage_engine import ArbitrageEngine
            self.arbitrage_engine = ArbitrageEngine(getattr(self.settings, 'BETFAIR_API_KEY', ''))
        except ImportError:
            self.arbitrage_engine = None

        # Mode
        self._autopilot = getattr(self.settings, 'AGENT_AUTOPILOT', True)

        # Stop loss config
        self._stop_loss_pct  = getattr(self.settings, 'STOP_LOSS_PCT', 20.0) / 100  # 20%
        self._stop_loss_enabled = getattr(self.settings, 'STOP_LOSS_ENABLED', True)

        # State
        self.state = AgentState.STOPPED
        self._loop_task: Optional[asyncio.Task] = None
        self._loop_interval = getattr(self.settings, 'AGENT_LOOP_INTERVAL', 5)
        self._action_log: List[dict] = []
        self._cycle_count = 0

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
                
            # Arbitrage check against global sharp sources
            if getattr(self, 'arbitrage_engine', None):
                sharp_odds = await self.arbitrage_engine.get_sharp_odds("A", "B")
                if sharp_odds:
                    arb = self.arbitrage_engine.analyze_arbitrage({"A": match_data["odds_a"]}, sharp_odds)
                    if arb:
                        self._log_action("ARBITRAGE_FOUND", arb)
                        try:
                            from telegram_bot.notifier import send_signal
                            msg = f"🚨 **ARBITRAGE DETECTED** 🚨\\n\\n**Delta:** {arb['delta']} | **Confidence**: 100%\\n**RoyalBook:** {arb['royalbook_odds']} vs **Sharp Market:** {arb['sharp_odds']}\\n**Strategy:** {arb['strategy']}"
                            asyncio.create_task(send_signal(msg))
                        except Exception:
                            pass

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
                        asyncio.create_task(send_anti_panic(
                            "HOLD", position.backed_team,
                            float(s.get("overs",0)),
                            f"{s.get('total_runs',0)}/{s.get('total_wickets',0)}",
                            f"{s.get('team_a','?')} vs {s.get('team_b','?')}",
                        ))
                    except Exception:
                        pass
                elif anti_panic == "CUT":
                    self._log_action("ANTI_PANIC_CUT", "Wicket confirms collapse — triggering loss cut")
                    try:
                        from telegram_bot.notifier import send_anti_panic
                        s = match_data["state"]
                        asyncio.create_task(send_anti_panic(
                            "CUT", position.backed_team,
                            float(s.get("overs",0)),
                            f"{s.get('total_runs',0)}/{s.get('total_wickets',0)}",
                            f"{s.get('team_a','?')} vs {s.get('team_b','?')}",
                        ))
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

            # Try multiple match IDs (auto-discovery)
            match_ids = [1, "1", "current", "live"]
            state = {}
            for mid in match_ids:
                state = await cache.get_match_state(mid) or {}
                if state: break
            
            odds = await cache.get_odds(state.get("match_id", 1)) or {}
            telegram = await cache.get_telegram_signals(state.get("match_id", 1)) or []

            # Also try to enrich with real live data from Cricbuzz
            if not state or state.get("source") == "mock" or not state.get("team_a"):
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
                s = data["state"]
                match_name = f"{s.get('team_a','?')} vs {s.get('team_b','?')}"
                overs = float(s.get("overs", 0))
                score = f"{s.get('total_runs',0)}/{s.get('total_wickets',0)}"
                if backed_team == s.get("team_a"):
                    h_team = s.get("team_b", "")
                else:
                    h_team = s.get("team_a", "")
                asyncio.create_task(send_stop_loss(
                    team=backed_team, entry_odds=entry_odds,
                    current_odds=current_odds, loss_pct=loss_pct,
                    hedge_team=h_team, hedge_stake=position.total_exposure * 0.8,
                    overs=overs, score=score, match=match_name,
                ))
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

        # Execute via direct API if available, else simulated
        if self._exchange_instance:
            result = await self._exchange_instance.place_bet(match_id, "BACK", hedge_amount, hedge_odds)
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

    # ── Analyze ─────────────────────────────────────────────────────────────

    async def _analyze(self, match_id, data, position) -> Optional[object]:
        """
        Sniper v3 Analysis Pipeline:
        1. Rule Engine (Direction)
        2. Heterogeneous Consensus (Verification)
        3. Threshold Gates (Materiality/Edge)
        4. Signal Grading (S/A/B)
        """
        state  = data["state"]
        odds_a = data["odds_a"]
        odds_b = data["odds_b"]
        
        # Use ensemble predictor for higher accuracy
        ensemble_pred = self.ensemble_predictor.predict(state)
        ml_pred = self.ml_model.predict(state)
        
        # Override ML prediction with ensemble for better accuracy
        ml_pred.win_probability = ensemble_pred.win_probability
        ml_pred.momentum_score = ensemble_pred.momentum_score
        ml_pred.confidence = ensemble_pred.confidence
        
        # 1. Direction (Rule Engine)
        ctx = MatchContext(
            match_id         = int(match_id) if str(match_id).isdigit() else 1,
            team_a           = state.get("team_a", "Team A"),
            team_b           = state.get("team_b", "Team B"),
            innings          = int(state.get("innings", 1)),
            current_over     = float(state.get("overs", 0)),
            total_runs       = int(state.get("total_runs", 0)),
            total_wickets    = int(state.get("total_wickets", 0)),
            run_rate         = float(state.get("run_rate", 0)),
            required_run_rate = float(state.get("required_run_rate", 0)),
            target           = int(state.get("target", 0)),
            team_a_odds      = odds_a,
            team_b_odds      = odds_b,
            stake            = self.risk_manager.max_stake_per_trade,
            entry_odds       = position.entry_odds if position else odds_a,
            backed_team      = ("A" if position.backed_team == state.get("team_a") else "B") if position else "A",
            win_probability  = ml_pred.win_probability,
            momentum_score   = ml_pred.momentum_score,
            is_wicket_just_fell = state.get("last_ball") == "W",
            telegram_signals = data.get("telegram_signals", []),
        )
        decision = self.decision_engine.evaluate(ctx)

        # 2. Consensus Verification (Fail-fast)
        if decision.signal == "ENTER" and self.ai_reasoner.is_available:
            ai_result = await self.ai_reasoner.get_heterogeneous_consensus(
                match_state=state,
                odds={"team_a_odds": odds_a, "team_b_odds": odds_b},
                ml_prediction={"win_probability": ml_pred.win_probability, "momentum_score": ml_pred.momentum_score},
                decision_engine_output=decision.to_dict(),
                position=position.to_dict() if position else None,
                telegram_signals=data.get("telegram_signals", []),
            )
            
            if ai_result["action"] != "ENTER":
                self._log_action("SNIPER_REJECTED", {"reason": "No consensus", "votes": ai_result.get("reasoning")})
                decision.signal = "HOLD"
                return decision

            # 3. Threshold Gates (Materiality & Edge)
            materiality = ai_result["confidence"]
            edge = abs(ml_pred.win_probability - (1/odds_a if ai_result["team"] == state.get("team_a") else 1/odds_b))
            
            if materiality < self.settings.CONSENSUS_THRESHOLD / 100.0:
                self._log_action("SNIPER_REJECTED", {"reason": "Low materiality", "value": materiality})
                decision.signal = "HOLD"
                return decision
                
            # 4. Signal Grading
            grade = "B"
            if materiality >= 0.90 and edge >= 0.15: grade = "S"
            elif materiality >= 0.85 and edge >= 0.10: grade = "A"
            
            decision.grade = grade
            decision.reasoning = f"[{grade}-Tier] Consensus Verified. Edge: {edge:.2f}. {ai_result['reasoning']}"
            
        return decision

    # ── Value Strategy ───────────────────────────────────────────────────────

    async def _evaluate_value_opportunity(self, match_id: str, data: dict):
        """
        Check for high-odds value entries when the rule engine says HOLD.
        This catches: teams at 10+ odds where recovery is possible.
        Also handles: 40+ odds via lay on opposite side.
        """
        state  = data["state"]
        odds_a = data["odds_a"]
        odds_b = data["odds_b"]
        venue  = data.get("venue", state.get("venue", ""))

        # Evaluate at any odds — value engine decides internally
        opp = self.value_strategy.evaluate(
            state    = state,
            team_a   = state.get("team_a", "Team A"),
            team_b   = state.get("team_b", "Team B"),
            odds_a   = odds_a,
            odds_b   = odds_b,
            position = None,
            bankroll = self.risk_manager.current_bankroll,
            historical = self.historical_db,
        )

        if not opp:
            return

        strict_consensus = getattr(self.settings, 'STRICT_CONSENSUS', True)
        consensus_threshold = getattr(self.settings, 'CONSENSUS_THRESHOLD', 80)
        
        if strict_consensus and self.ai_reasoner.is_available:
            try:
                ai_result = await self.ai_reasoner.multi_pass_reason(
                    match_state = state,
                    odds = {"team_a_odds": odds_a, "team_b_odds": odds_b},
                    ml_prediction = {"win_probability": 0.5, "momentum_score": 0.5, "model_version": "value"},
                    decision_engine_output = {"signal": "ENTER", "confidence": opp.confidence, "reasoning": opp.reasoning},
                    position = None,
                    telegram_signals = data.get("telegram_signals", [])
                )
                ai_conf = ai_result.get("confidence", 0)
                ai_action = ai_result.get("action", "HOLD")
                threshold = consensus_threshold / 100.0
                
                if ai_action == "HOLD" or ai_conf < threshold:
                    self._log_action("REJECTED_BY_CONSENSUS", {
                        "original_signal": "VALUE_ENTER",
                        "ai_confidence": f"{ai_conf*100:.0f}%",
                        "reasoning": ai_result.get("reasoning", "")
                    })
                    return
                else:
                    opp.confidence = ai_conf
                    opp.reasoning = f"✅ Consensus Approved. {ai_result.get('reasoning', '')}"
            except Exception as e:
                logger.warning(f"Value AI Reasoner: {e}")

        # Aggressive staking for small budgets (< ₹2000)
        if self.risk_manager.current_bankroll < 2000:
            stake = round(self.risk_manager.current_bankroll * 0.25 / 10) * 10 # 25% stake
        else:
            stake = round(self.risk_manager.current_bankroll * opp.stake_pct / 10) * 10
        
        stake = max(100.0, min(stake, self.risk_manager.max_stake_per_trade))

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
            # Lay bet: use direct API lay or simulated
            async def _execute_lay(p):
                if self._exchange_instance:
                    res = await self._exchange_instance.place_bet(p["match_id"], "LAY", p["stake"], p["odds"])
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
        bankroll = self.risk_manager.current_bankroll

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

        strict_consensus = getattr(self.settings, 'STRICT_CONSENSUS', True)
        consensus_threshold = getattr(self.settings, 'CONSENSUS_THRESHOLD', 80)
        
        if strict_consensus and self.ai_reasoner.is_available:
            try:
                ai_result = await self.ai_reasoner.multi_pass_reason(
                    match_state = state,
                    odds = {"team_a_odds": data["odds_a"], "team_b_odds": data["odds_b"]},
                    ml_prediction = {"win_probability": 0.5, "momentum_score": 0.5, "model_version": "session"},
                    decision_engine_output = {"signal": "SESSION", "confidence": best["confidence"], "reasoning": best["reasoning"]},
                    position = None,
                    telegram_signals = data.get("telegram_signals", [])
                )
                ai_conf = ai_result.get("confidence", 0)
                ai_action = ai_result.get("action", "HOLD")
                threshold = consensus_threshold / 100.0
                
                if ai_action == "HOLD" or ai_conf < threshold:
                    self._log_action("REJECTED_BY_CONSENSUS", {
                        "original_signal": "SESSION",
                        "label": best["label"],
                        "ai_confidence": f"{ai_conf*100:.0f}%",
                        "reasoning": ai_result.get("reasoning", "")
                    })
                    return
                else:
                    best["confidence"] = ai_conf
                    best["reasoning"] = f"✅ Consensus Approved. {ai_result.get('reasoning', '')}"
            except Exception as e:
                logger.warning(f"Session AI Reasoner: {e}")

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
        """Execute a session bet via Stake API or simulated."""
        label  = proposal["label"]
        side   = proposal["side"]
        stake  = proposal["stake"]
        match_id = proposal["match_id"]

        if self._exchange_instance:
            result = await self._exchange_instance.place_bet(match_id, f"SESSION:{label}:{side}", stake, 1.85)
            success = result if isinstance(result, bool) else result.get("success", False)
            msg     = "Stake API Bet Placed" if success else "Failed to place bet"
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
        Always fires a Telegram signal so the user can place manually.
        """
        # ── Fire Telegram notification regardless of autopilot mode ──────────
        try:
            from telegram_bot.notifier import send_bet_call, send_bookset_call, send_session_call
            state  = proposal.get("state", {})
            ptype  = proposal.get("type", "BACK")
            action = ptype.replace("VALUE_", "").replace("ENTRY", "BACK")
            overs  = float(state.get("overs", 0))
            runs   = state.get("total_runs", 0)
            wkts   = state.get("total_wickets", 0)
            score  = f"{runs}/{wkts}"
            match  = f"{state.get('team_a','?')} vs {state.get('team_b','?')}"

            if action == "PROGRESSIVE_BOOKSET":
                asyncio.create_task(send_bookset_call(
                    team         = proposal.get("team", ""),
                    entry_odds   = proposal.get("odds", 0),
                    current_odds = proposal.get("odds", 0),
                    overs        = overs,
                    match        = match,
                ))
            elif ptype == "SESSION":
                asyncio.create_task(send_session_call(
                    label       = proposal.get("label", ""),
                    side        = proposal.get("side", "YES"),
                    stake       = float(proposal.get("stake", 0)),
                    confidence  = float(proposal.get("confidence", 0)),
                    reasoning   = proposal.get("reasoning", ""),
                    overs       = overs,
                    score       = score,
                    match       = match,
                ))
            else:
                asyncio.create_task(send_bet_call(
                    action      = action,
                    team        = proposal.get("team", ""),
                    odds        = float(proposal.get("odds", 0)),
                    stake       = float(proposal.get("stake", 0)),
                    ev          = float(proposal.get("ev", 0)),
                    confidence  = float(proposal.get("confidence", 0)),
                    reasoning   = proposal.get("reasoning", ""),
                    overs       = overs,
                    score       = score,
                    bookset_at  = float(proposal.get("bookset_at", 0) or 0),
                    stop_loss   = float(proposal.get("stop_loss_at", 0) or 0),
                    tier        = proposal.get("odds_tier", "mid"),
                    match       = match,
                ))
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
