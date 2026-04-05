"""
Decision Engine
Combines ML predictions, odds movement, session signals, and Telegram
to produce unified trading decision: ENTER / LOSS_CUT / BOOKSET / SESSION / HOLD
"""
import logging
from dataclasses import dataclass, field
from typing import Optional
from datetime import datetime

from strategy_engine.loss_cut_engine import LossCutEngine, LossCutResult
from strategy_engine.bookset_engine import BooksetEngine, BooksetResult
from strategy_engine.session_engine import SessionEngine, SessionPrediction
from config.settings import settings

logger = logging.getLogger(__name__)


@dataclass
class MatchContext:
    """Full context for decision making"""
    match_id: int
    team_a: str
    team_b: str
    innings: int
    current_over: float
    total_runs: int
    total_wickets: int
    run_rate: float
    required_run_rate: float
    target: int
    team_a_odds: float
    team_b_odds: float
    prev_team_a_odds: float = 0.0
    prev_team_b_odds: float = 0.0
    stake: float = 1000.0
    entry_odds: float = 0.0
    backed_team: str = "A"  # which team user backed
    is_wicket_just_fell: bool = False
    telegram_signals: list = field(default_factory=list)
    win_probability: float = 0.5  # from ML model
    momentum_score: float = 0.5
    batting_team: str = ""
    venue: str = ""


@dataclass
class DecisionOutput:
    """Unified decision output"""
    signal: str  # ENTER, LOSS_CUT, BOOKSET, SESSION, HOLD
    confidence: float
    urgency: str  # LOW, MEDIUM, HIGH, CRITICAL
    win_probability: float
    momentum_score: float

    # Strategy details
    loss_cut: Optional[LossCutResult] = None
    bookset: Optional[BooksetResult] = None
    session: Optional[SessionPrediction] = None

    # Entry signal details
    entry_team: Optional[str] = None
    entry_reason: Optional[str] = None

    # Meta
    reasoning: str = ""
    factors: dict = field(default_factory=dict)
    timestamp: str = field(default_factory=lambda: datetime.utcnow().isoformat())

    def to_dict(self) -> dict:
        d = {
            "signal": self.signal,
            "confidence": self.confidence,
            "urgency": self.urgency,
            "win_probability": self.win_probability,
            "momentum_score": self.momentum_score,
            "reasoning": self.reasoning,
            "factors": self.factors,
            "timestamp": self.timestamp,
            "entry_team": self.entry_team,
            "entry_reason": self.entry_reason,
        }
        if self.loss_cut:
            d["loss_cut"] = {
                "trigger": self.loss_cut.should_trigger,
                "hedge_amount": self.loss_cut.hedge_amount,
                "hedge_profit": self.loss_cut.hedge_profit,
                "reason": self.loss_cut.trigger_reason,
                "urgency": self.loss_cut.urgency,
            }
        if self.bookset:
            d["bookset"] = {
                "stake_a": self.bookset.stake_a,
                "stake_b": self.bookset.stake_b,
                "guaranteed_profit": self.bookset.guaranteed_profit,
                "profit_pct": self.bookset.profit_percentage,
                "overround": self.bookset.overround,
                "explanation": self.bookset.explanation,
            }
        if self.session:
            d["session"] = {
                "phase": self.session.phase,
                "predicted_runs": self.session.predicted_runs,
                "ci_low": self.session.confidence_interval_low,
                "ci_high": self.session.confidence_interval_high,
                "prob_over": self.session.probability_over,
                "prob_under": self.session.probability_under,
                "line": self.session.recommended_line,
                "signal": self.session.value_signal,
            }
        return d


class DecisionEngine:
    """
    Master decision engine.
    
    Priority order:
    1. LOSS_CUT (emergency / risk management)
    2. BOOKSET (lock profit)
    3. SESSION (phase opportunity)
    4. ENTER (new position)
    5. HOLD (no action)
    """

    def __init__(self):
        self.loss_cut_engine = LossCutEngine()
        self.bookset_engine = BooksetEngine()
        self.session_engine = SessionEngine()

    def evaluate(self, ctx: MatchContext) -> DecisionOutput:
        """
        Main evaluation pipeline.
        Combines all signals into a unified decision.
        """
        factors = {}

        # ── 1. RUN LOSS CUT ENGINE ─────────────────────────────────────────
        current_team_odds = (
            ctx.team_a_odds if ctx.backed_team == "A" else ctx.team_b_odds
        )
        entry_odds = ctx.entry_odds or current_team_odds

        loss_cut = self.loss_cut_engine.evaluate(
            stake=ctx.stake,
            entry_odds=entry_odds,
            current_team_odds=current_team_odds,
            current_over=ctx.current_over,
            wickets_fallen=ctx.total_wickets,
            run_rate=ctx.run_rate,
            required_rr=ctx.required_run_rate,
            is_wicket_just_fell=ctx.is_wicket_just_fell,
            win_probability=ctx.win_probability,
        )
        factors["loss_cut_triggered"] = loss_cut.should_trigger
        factors["loss_cut_urgency"] = loss_cut.urgency

        if loss_cut.should_trigger and loss_cut.urgency in ("HIGH", "CRITICAL"):
            return DecisionOutput(
                signal="LOSS_CUT",
                confidence=0.90 if loss_cut.urgency == "CRITICAL" else 0.75,
                urgency=loss_cut.urgency,
                win_probability=ctx.win_probability,
                momentum_score=ctx.momentum_score,
                loss_cut=loss_cut,
                reasoning=f"🔴 LOSS CUT: {loss_cut.trigger_reason}",
                factors=factors,
            )

        # ── 2. RUN BOOKSET ENGINE ──────────────────────────────────────────
        bookset = self.bookset_engine.calculate(
            odds_a=ctx.team_a_odds,
            odds_b=ctx.team_b_odds,
            total_stake=ctx.stake,
        )
        factors["bookset_overround"] = bookset.overround
        factors["bookset_profit"] = bookset.guaranteed_profit
        factors["arb_opportunity"] = bookset.is_profitable

        # Bookset recommended in late match with good odds spread
        bookset_recommended = (
            bookset.is_profitable or
            (ctx.current_over >= 15 and bookset.profit_percentage > -3.0 and ctx.win_probability > 0.65)
        )

        # ── 3. SESSION SIGNAL ──────────────────────────────────────────────
        session = None
        session_signal = "NEUTRAL"
        if ctx.current_over < 6:
            session = self.session_engine.predict_powerplay(
                ctx.current_over, ctx.total_runs, ctx.total_wickets,
                ctx.batting_team, ctx.venue
            )
            session_signal = session.value_signal

        total_session = self.session_engine.predict_total_score(
            ctx.current_over, ctx.total_runs, ctx.total_wickets,
            ctx.batting_team, ctx.venue
        )
        factors["session_signal"] = session_signal
        factors["predicted_total"] = total_session.predicted_runs

        # ── 4. TELEGRAM SIGNAL AGGREGATION ───────────────────────────────
        telegram_sentiment = self._aggregate_telegram(ctx.telegram_signals)
        factors["telegram_sentiment"] = telegram_sentiment
        factors["telegram_signal_count"] = len(ctx.telegram_signals)

        # ── 5. MOMENTUM & WIN PROBABILITY ─────────────────────────────────
        factors["win_probability"] = ctx.win_probability
        factors["momentum_score"] = ctx.momentum_score

        # Odds momentum
        if ctx.prev_team_a_odds > 0:
            odds_drift_a = (ctx.team_a_odds - ctx.prev_team_a_odds) / ctx.prev_team_a_odds
            factors["odds_drift_a"] = round(odds_drift_a * 100, 2)
        else:
            factors["odds_drift_a"] = 0

        # ── 6. COMPOSITE SCORING ──────────────────────────────────────────
        entry_score = self._score_entry(ctx, telegram_sentiment)
        factors["entry_score"] = entry_score

        # ── 7. DECISION TREE ──────────────────────────────────────────────

        # BOOKSET: ARB available or lock in late match
        if bookset.is_profitable:
            return DecisionOutput(
                signal="BOOKSET",
                confidence=0.88,
                urgency="HIGH",
                win_probability=ctx.win_probability,
                momentum_score=ctx.momentum_score,
                bookset=bookset,
                reasoning=f"💰 BOOKSET ARB: {bookset.explanation}",
                factors=factors,
            )

        # SESSION: Strong powerplay signal
        if session and session_signal != "NEUTRAL" and ctx.current_over < 5:
            return DecisionOutput(
                signal="SESSION",
                confidence=0.72,
                urgency="MEDIUM",
                win_probability=ctx.win_probability,
                momentum_score=ctx.momentum_score,
                session=session,
                reasoning=f"📊 SESSION {session_signal}: {session.reasoning}",
                factors=factors,
            )

        # BOOKSET: Late match lock-in
        if bookset_recommended and ctx.current_over >= 15:
            return DecisionOutput(
                signal="BOOKSET",
                confidence=0.65,
                urgency="MEDIUM",
                win_probability=ctx.win_probability,
                momentum_score=ctx.momentum_score,
                bookset=bookset,
                session=total_session,
                reasoning=f"🔒 LATE BOOKSET: Lock profit at over {ctx.current_over:.1f}",
                factors=factors,
            )

        # LOSS CUT (lower urgency)
        if loss_cut.should_trigger:
            return DecisionOutput(
                signal="LOSS_CUT",
                confidence=0.60,
                urgency="LOW",
                win_probability=ctx.win_probability,
                momentum_score=ctx.momentum_score,
                loss_cut=loss_cut,
                reasoning=f"⚠️ SOFT LOSS CUT: {loss_cut.trigger_reason}",
                factors=factors,
            )

        # ENTER: Strong positive signal
        if entry_score >= settings.WIN_PROB_THRESHOLD:
            team_to_back = "A" if ctx.win_probability > 0.5 else "B"
            team_name = ctx.team_a if team_to_back == "A" else ctx.team_b
            return DecisionOutput(
                signal="ENTER",
                confidence=min(0.85, entry_score),
                urgency="MEDIUM",
                win_probability=ctx.win_probability,
                momentum_score=ctx.momentum_score,
                entry_team=team_to_back,
                entry_reason=f"Win prob {ctx.win_probability*100:.1f}% | Momentum {ctx.momentum_score*100:.1f}%",
                session=total_session,
                reasoning=f"✅ ENTER: Back {team_name} | {self._build_entry_reason(ctx, telegram_sentiment)}",
                factors=factors,
            )

        # HOLD
        return DecisionOutput(
            signal="HOLD",
            confidence=0.55,
            urgency="LOW",
            win_probability=ctx.win_probability,
            momentum_score=ctx.momentum_score,
            session=total_session,
            reasoning="⏳ HOLD: No clear signal. Monitoring...",
            factors=factors,
        )

    def _score_entry(self, ctx: MatchContext, telegram_sentiment: float) -> float:
        """Composite entry score (0-1)"""
        score = 0.0

        # Win probability (40% weight)
        score += ctx.win_probability * 0.40

        # Momentum (25% weight)
        score += ctx.momentum_score * 0.25

        # Telegram sentiment (15% weight)
        # Normalize sentiment from [-1,1] to [0,1]
        score += ((telegram_sentiment + 1) / 2) * 0.15

        # Odds value (20% weight)
        # Check if odds offer value vs model probability
        implied_prob = 1 / ctx.team_a_odds if ctx.team_a_odds > 1 else 0.5
        edge = ctx.win_probability - implied_prob
        value_score = max(0, min(1, 0.5 + edge * 2))
        score += value_score * 0.20

        return round(score, 3)

    def _aggregate_telegram(self, signals: list) -> float:
        """Aggregate Telegram signals into sentiment score [-1, 1]"""
        if not signals:
            return 0.0

        total = sum(s.get("sentiment", 0) for s in signals)
        return round(max(-1, min(1, total / len(signals))), 3)

    def _build_entry_reason(self, ctx: MatchContext, sentiment: float) -> str:
        parts = []
        if ctx.win_probability > 0.6:
            parts.append(f"ML: {ctx.win_probability*100:.1f}%")
        if ctx.momentum_score > 0.65:
            parts.append(f"Momentum: {ctx.momentum_score*100:.1f}%")
        if sentiment > 0.3:
            parts.append(f"Telegram: Bullish ({sentiment:.2f})")
        elif sentiment < -0.3:
            parts.append(f"Telegram: Bearish ({sentiment:.2f})")
        return " | ".join(parts) if parts else "Composite signal"
