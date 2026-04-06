"""
FastAPI REST API Routes
"""
import logging
from datetime import datetime
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field

from database.connection import get_db
from database.redis_client import get_redis, RedisCache
from strategy_engine.decision_engine import DecisionEngine, MatchContext
from strategy_engine.bookset_engine import BooksetEngine
from strategy_engine.loss_cut_engine import LossCutEngine
from strategy_engine.session_engine import SessionEngine
from ml_model.predictor import CricketMLModel
from config.settings import settings

logger = logging.getLogger(__name__)
router = APIRouter()

# Singletons
_decision_engine = DecisionEngine()
_ml_model = CricketMLModel(
    model_path=settings.MODEL_PATH,
    scaler_path=settings.FEATURE_SCALER_PATH
)


# ─── Request/Response Models ───────────────────────────────────────────────────

class OddsUpdateRequest(BaseModel):
    match_id: int = Field(default=1)
    teamA_odds: float = Field(gt=1.0, lt=100.0)
    teamB_odds: float = Field(gt=1.0, lt=100.0)
    source: str = Field(default="manual")


class SignalRequest(BaseModel):
    match_id: int = Field(default=1)
    stake: float = Field(default=1000.0, gt=0)
    entry_odds: float = Field(default=0.0, ge=0)
    backed_team: str = Field(default="A", pattern="^[AB]$")


class LossCutRequest(BaseModel):
    stake: float = Field(gt=0)
    entry_odds: float = Field(gt=1)
    current_team_odds: float = Field(gt=1)
    current_over: float = Field(ge=0, le=20)
    wickets_fallen: int = Field(ge=0, le=10)
    run_rate: float = Field(ge=0)
    required_run_rate: float = Field(ge=0)
    is_wicket: bool = Field(default=False)
    win_probability: float = Field(default=0.5, ge=0, le=1)


class BooksetRequest(BaseModel):
    odds_a: float = Field(gt=1)
    odds_b: float = Field(gt=1)
    total_stake: float = Field(default=1000.0, gt=0)


class SessionRequest(BaseModel):
    phase: str = Field(default="powerplay", pattern="^(powerplay|total|middle|death)$")
    current_over: float = Field(ge=0, le=20)
    current_runs: int = Field(ge=0)
    current_wickets: int = Field(ge=0, le=10)
    batting_team: str = Field(default="")
    venue: str = Field(default="")


# ─── Odds Endpoints ────────────────────────────────────────────────────────────

@router.post("/odds/update")
async def update_odds(req: OddsUpdateRequest, db=Depends(get_db)):
    """Update current odds for a match"""
    redis = await get_redis()
    cache = RedisCache(redis)

    implied_a = 1 / req.teamA_odds
    implied_b = 1 / req.teamB_odds
    overround = implied_a + implied_b

    odds_data = {
        "match_id": req.match_id,
        "team_a_odds": req.teamA_odds,
        "team_b_odds": req.teamB_odds,
        "implied_prob_a": round(implied_a * 100, 2),
        "implied_prob_b": round(implied_b * 100, 2),
        "overround": round(overround, 4),
        "source": req.source,
        "timestamp": datetime.utcnow().isoformat()
    }

    await cache.set_odds(req.match_id, odds_data)
    await cache.publish("odds:updates", odds_data)

    # Save to DB
    from database.models import OddsUpdate
    db_odds = OddsUpdate(
        match_id=req.match_id,
        team_a_odds=req.teamA_odds,
        team_b_odds=req.teamB_odds,
        implied_prob_a=implied_a,
        implied_prob_b=implied_b,
        overround=overround,
        source=req.source,
    )
    db.add(db_odds)
    await db.commit()

    return {"status": "ok", "odds": odds_data}


@router.get("/odds/{match_id}")
async def get_odds(match_id: int):
    """Get current odds for a match"""
    redis = await get_redis()
    cache = RedisCache(redis)
    odds = await cache.get_odds(match_id)

    if not odds:
        raise HTTPException(status_code=404, detail="No odds found for match")
    return odds


@router.get("/odds/{match_id}/history")
async def get_odds_history(match_id: int, limit: int = 20):
    """Get odds movement history"""
    redis = await get_redis()
    cache = RedisCache(redis)
    history = await cache.get_odds_history(match_id, limit)
    return {"match_id": match_id, "history": history}


# ─── Match State ───────────────────────────────────────────────────────────────

@router.get("/matches/live")
async def get_live_matches(request: Request):
    """Get all active live matches"""
    feed = getattr(request.app.state, "live_feed", None)
    if feed:
        return {"matches": feed.get_active_matches()}
    return {"matches": {}}


@router.get("/match/{match_id}/state")
async def get_match_state(match_id: int):
    """Get current match state from Redis"""
    redis = await get_redis()
    cache = RedisCache(redis)
    state = await cache.get_match_state(match_id)

    if not state:
        # Return mock state for demo
        state = {
            "match_id": str(match_id),
            "team_a": "Mumbai Indians",
            "team_b": "Chennai Super Kings",
            "innings": 1,
            "total_runs": 0,
            "total_wickets": 0,
            "overs": 0.0,
            "run_rate": 0.0,
            "required_run_rate": 0.0,
            "target": 0,
            "current_batsman_1": "Rohit Sharma",
            "current_batsman_2": "Ishan Kishan",
            "current_bowler": "Deepak Chahar",
            "status": "upcoming"
        }
    return state


# ─── Decision Signal ───────────────────────────────────────────────────────────

@router.post("/signal/evaluate")
async def evaluate_signal(req: SignalRequest, request: Request):
    """
    Evaluate current match state and generate trading signal.
    Combines ML, odds, session, and Telegram signals.
    """
    redis = await get_redis()
    cache = RedisCache(redis)

    # Get match state
    state = await cache.get_match_state(req.match_id) or {}
    odds = await cache.get_odds(req.match_id) or {
        "team_a_odds": 1.85, "team_b_odds": 2.1
    }
    telegram_signals = await cache.get_telegram_signals(req.match_id)

    # ML prediction
    ml_pred = _ml_model.predict(state)

    # Build context
    ctx = MatchContext(
        match_id=req.match_id,
        team_a=state.get("team_a", "Team A"),
        team_b=state.get("team_b", "Team B"),
        innings=int(state.get("innings", 1)),
        current_over=float(state.get("overs", 0)),
        total_runs=int(state.get("total_runs", 0)),
        total_wickets=int(state.get("total_wickets", 0)),
        run_rate=float(state.get("run_rate", 0)),
        required_run_rate=float(state.get("required_run_rate", 0)),
        target=int(state.get("target", 0)),
        team_a_odds=float(odds.get("team_a_odds", 1.85)),
        team_b_odds=float(odds.get("team_b_odds", 2.1)),
        stake=req.stake,
        entry_odds=req.entry_odds,
        backed_team=req.backed_team,
        is_wicket_just_fell=state.get("last_ball") == "W",
        telegram_signals=telegram_signals,
        win_probability=ml_pred.win_probability,
        momentum_score=ml_pred.momentum_score,
        batting_team=state.get("team_a", ""),
        venue=state.get("venue", ""),
    )

    # Evaluate
    decision = _decision_engine.evaluate(ctx)
    result = decision.to_dict()
    result["ml_model_version"] = ml_pred.model_version
    result["ml_confidence"] = ml_pred.confidence

    # Cache signal
    await cache.set_signal(req.match_id, result)
    await cache.publish("signals:new", result)

    # Send Telegram alert for important signals
    if decision.signal in ("LOSS_CUT", "ENTER", "BOOKSET") and decision.confidence > 0.7:
        try:
            bot = getattr(request.app.state, "telegram_bot", None)
            if bot:
                await bot.send_alert(result, state)
        except Exception:
            pass

    return result


@router.get("/signal/{match_id}/latest")
async def get_latest_signal(match_id: int):
    """Get most recent signal for a match"""
    redis = await get_redis()
    cache = RedisCache(redis)
    signal = await cache.get_signal(match_id)
    if not signal:
        raise HTTPException(status_code=404, detail="No signal found")
    return signal


@router.get("/signal/{match_id}/history")
async def get_signal_history(match_id: int, limit: int = 20):
    """Get signal history"""
    redis = await get_redis()
    cache = RedisCache(redis)
    history = await cache.get_signal_history(match_id, limit)
    return {"match_id": match_id, "history": history}


# ─── Strategy Calculators ──────────────────────────────────────────────────────

@router.post("/strategy/loss-cut")
async def calculate_loss_cut(req: LossCutRequest):
    """Calculate loss cut / hedge position"""
    engine = LossCutEngine()
    result = engine.evaluate(
        stake=req.stake,
        entry_odds=req.entry_odds,
        current_team_odds=req.current_team_odds,
        current_over=req.current_over,
        wickets_fallen=req.wickets_fallen,
        run_rate=req.run_rate,
        required_rr=req.required_run_rate,
        is_wicket_just_fell=req.is_wicket,
        win_probability=req.win_probability,
    )
    return {
        "triggered": result.should_trigger,
        "hedge_amount": result.hedge_amount,
        "hedge_profit": result.hedge_profit,
        "loss_reduction": result.loss_reduction,
        "trigger_reason": result.trigger_reason,
        "urgency": result.urgency,
    }


@router.post("/strategy/bookset")
async def calculate_bookset(req: BooksetRequest):
    """Calculate bookset stakes for guaranteed profit"""
    engine = BooksetEngine()
    result = engine.calculate(req.odds_a, req.odds_b, req.total_stake)
    return {
        "stake_a": result.stake_a,
        "stake_b": result.stake_b,
        "guaranteed_profit": result.guaranteed_profit,
        "profit_percentage": result.profit_percentage,
        "total_investment": result.total_investment,
        "implied_prob_a": result.implied_prob_a,
        "implied_prob_b": result.implied_prob_b,
        "overround": result.overround,
        "is_profitable": result.is_profitable,
        "explanation": result.explanation,
    }


@router.post("/strategy/session")
async def calculate_session(req: SessionRequest):
    """Predict session/phase runs"""
    engine = SessionEngine()
    result = engine.predict_phase_score(
        phase=req.phase,
        current_over=req.current_over,
        current_runs=req.current_runs,
        current_wickets=req.current_wickets,
        batting_team=req.batting_team,
    )
    return {
        "phase": result.phase,
        "predicted_runs": result.predicted_runs,
        "ci_low": result.confidence_interval_low,
        "ci_high": result.confidence_interval_high,
        "prob_over": result.probability_over,
        "prob_under": result.probability_under,
        "recommended_line": result.recommended_line,
        "value_signal": result.value_signal,
        "reasoning": result.reasoning,
    }


# ─── ML Predictions ────────────────────────────────────────────────────────────

@router.post("/ml/predict")
async def ml_predict(match_id: int = 1):
    """Get ML win probability prediction"""
    redis = await get_redis()
    cache = RedisCache(redis)
    state = await cache.get_match_state(match_id) or {}

    prediction = _ml_model.predict(state)
    result = {
        "win_probability": prediction.win_probability,
        "momentum_score": prediction.momentum_score,
        "confidence": prediction.confidence,
        "model_version": prediction.model_version,
    }

    await cache.set_win_probability(match_id, result)
    return result


# ─── Telegram ─────────────────────────────────────────────────────────────────

@router.get("/telegram/signals")
async def get_telegram_signals(match_id: int = 0, limit: int = 20):
    """Get recent Telegram signals"""
    redis = await get_redis()
    cache = RedisCache(redis)
    signals = await cache.get_telegram_signals(match_id)
    return {"signals": signals[-limit:]}


# ─── Agent Approval (Semi-auto mode) ──────────────────────────────────────────

@router.post("/agent/approve/{approval_id}")
async def approve_trade(approval_id: str, request: Request):
    """Approve a pending trade (semi-auto mode)"""
    agent = getattr(request.app.state, "trading_agent", None)
    if not agent:
        raise HTTPException(404, "Agent not running")
    ok = await agent.approve_trade(approval_id)
    if not ok:
        raise HTTPException(404, f"Approval {approval_id} not found or already actioned")
    return {"status": "approved", "approval_id": approval_id}


@router.post("/agent/reject/{approval_id}")
async def reject_trade(approval_id: str, request: Request):
    """Reject a pending trade (semi-auto mode)"""
    agent = getattr(request.app.state, "trading_agent", None)
    if not agent:
        raise HTTPException(404, "Agent not running")
    ok = await agent.reject_trade(approval_id)
    if not ok:
        raise HTTPException(404, f"Approval {approval_id} not found")
    return {"status": "rejected", "approval_id": approval_id}


@router.get("/agent/pending-approvals")
async def get_pending_approvals(request: Request):
    """Get list of trades awaiting user approval"""
    agent = getattr(request.app.state, "trading_agent", None)
    if not agent:
        return {"approvals": []}
    return {"approvals": agent.get_pending_approvals()}


@router.post("/agent/mode")
async def set_agent_mode(autopilot: bool, request: Request):
    """Switch between autopilot and semi-auto mode"""
    agent = getattr(request.app.state, "trading_agent", None)
    if not agent:
        raise HTTPException(404, "Agent not running")
    agent.set_autopilot(autopilot)
    return {"mode": "autopilot" if autopilot else "semi_auto"}


# ─── Session Markets ───────────────────────────────────────────────────────────

@router.get("/sessions/analysis")
async def get_session_analysis(request: Request, match_id: int = 1):
    """Get current session market analysis and recommendations"""
    redis = await get_redis()
    cache = RedisCache(redis)
    state = await cache.get_match_state(match_id) or {}
    odds  = await cache.get_odds(match_id) or {}

    sessions = odds.get("sessions", []) + odds.get("premium_sessions", [])
    if not sessions:
        return {"recommendations": [], "message": "No session markets available"}

    from agent.session_analyzer import SessionAnalyzer
    analyzer = SessionAnalyzer()
    venue = state.get("venue", "")
    recs = analyzer.analyze_sessions(state, sessions, venue)

    return {
        "match_id": match_id,
        "total_sessions": len(sessions),
        "recommendations": [r.to_dict() for r in recs[:5]],
        "timestamp": datetime.utcnow().isoformat(),
    }


# ─── Live Match Data ───────────────────────────────────────────────────────────

@router.get("/agent/status")
async def api_agent_status(request: Request):
    """Full agent status: positions, risk, bankroll, actions"""
    agent = getattr(request.app.state, "trading_agent", None)
    if not agent:
        return {"state": "disabled"}
    return agent.get_status()


@router.get("/agent/actions")
async def api_agent_actions(request: Request, limit: int = 50):
    """Recent agent trade log"""
    agent = getattr(request.app.state, "trading_agent", None)
    if not agent:
        return {"actions": []}
    return {"actions": agent.get_action_log(limit)}


@router.post("/agent/start")
async def api_agent_start(request: Request):
    agent = getattr(request.app.state, "trading_agent", None)
    if not agent:
        raise HTTPException(404, "Agent not initialized")
    await agent.start()
    return {"status": "started", "state": agent.state.value}


@router.post("/agent/pause")
async def api_agent_pause(request: Request):
    agent = getattr(request.app.state, "trading_agent", None)
    if not agent:
        raise HTTPException(404, "Agent not initialized")
    await agent.pause()
    return {"status": "paused", "state": agent.state.value}


@router.post("/agent/resume")
async def api_agent_resume(request: Request):
    agent = getattr(request.app.state, "trading_agent", None)
    if not agent:
        raise HTTPException(404, "Agent not initialized")
    await agent.resume()
    return {"status": "resumed", "state": agent.state.value}


@router.post("/agent/circuit-breaker/reset")
async def api_agent_reset_circuit_breaker(request: Request):
    agent = getattr(request.app.state, "trading_agent", None)
    if not agent:
        raise HTTPException(404, "Agent not initialized")
    agent.risk_manager.reset_circuit_breaker()
    from agent.trading_agent import AgentState
    if agent.state == AgentState.CIRCUIT_BREAK:
        agent.state = AgentState.RUNNING
    return {"status": "reset"}


@router.get("/matches/live-ipl")
async def get_live_ipl_matches():
    """Fetch live IPL matches from Cricbuzz"""
    try:
        from data_ingestion.cricket_stats import cricket_stats
        matches = await cricket_stats.get_live_ipl_matches()
        live_score = await cricket_stats.get_live_score_cricbuzz()
        return {
            "matches": matches,
            "current_match": live_score,
            "source": "cricbuzz",
        }
    except Exception as e:
        return {"matches": [], "error": str(e)}
