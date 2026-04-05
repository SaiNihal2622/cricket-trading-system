"""
Database models using SQLAlchemy async ORM
"""
from datetime import datetime
from typing import Optional
from sqlalchemy import (
    Column, Integer, Float, String, Boolean, DateTime,
    JSON, Text, ForeignKey, Index, Enum
)
from sqlalchemy.orm import DeclarativeBase, relationship
import enum


class Base(DeclarativeBase):
    pass


class MatchStatus(str, enum.Enum):
    UPCOMING = "upcoming"
    LIVE = "live"
    COMPLETED = "completed"
    ABANDONED = "abandoned"


class SignalType(str, enum.Enum):
    ENTER = "ENTER"
    LOSS_CUT = "LOSS_CUT"
    BOOKSET = "BOOKSET"
    SESSION = "SESSION"
    HOLD = "HOLD"


class Match(Base):
    __tablename__ = "matches"

    id = Column(Integer, primary_key=True)
    external_id = Column(String(100), unique=True, index=True)
    team_a = Column(String(100), nullable=False)
    team_b = Column(String(100), nullable=False)
    venue = Column(String(200))
    match_date = Column(DateTime)
    tournament = Column(String(100))
    status = Column(Enum(MatchStatus), default=MatchStatus.UPCOMING)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    # Relationships
    ball_events = relationship("BallEvent", back_populates="match")
    signals = relationship("TradingSignal", back_populates="match")
    odds_history = relationship("OddsUpdate", back_populates="match")


class BallEvent(Base):
    __tablename__ = "ball_events"

    id = Column(Integer, primary_key=True)
    match_id = Column(Integer, ForeignKey("matches.id"), nullable=False)
    innings = Column(Integer)
    over_number = Column(Float)  # e.g. 4.3 = over 4, ball 3
    runs_scored = Column(Integer, default=0)
    is_wicket = Column(Boolean, default=False)
    wicket_type = Column(String(50))
    batsman = Column(String(100))
    bowler = Column(String(100))
    extras = Column(Integer, default=0)
    total_runs = Column(Integer)
    total_wickets = Column(Integer)
    run_rate = Column(Float)
    required_run_rate = Column(Float)
    timestamp = Column(DateTime, default=datetime.utcnow)
    raw_data = Column(JSON)

    match = relationship("Match", back_populates="ball_events")

    __table_args__ = (
        Index("idx_ball_match_over", "match_id", "innings", "over_number"),
    )


class OddsUpdate(Base):
    __tablename__ = "odds_updates"

    id = Column(Integer, primary_key=True)
    match_id = Column(Integer, ForeignKey("matches.id"), nullable=False)
    team_a_odds = Column(Float, nullable=False)
    team_b_odds = Column(Float, nullable=False)
    implied_prob_a = Column(Float)
    implied_prob_b = Column(Float)
    overround = Column(Float)
    source = Column(String(50), default="manual")
    timestamp = Column(DateTime, default=datetime.utcnow)

    match = relationship("Match", back_populates="odds_history")

    __table_args__ = (
        Index("idx_odds_match_time", "match_id", "timestamp"),
    )


class TradingSignal(Base):
    __tablename__ = "trading_signals"

    id = Column(Integer, primary_key=True)
    match_id = Column(Integer, ForeignKey("matches.id"), nullable=False)
    signal_type = Column(Enum(SignalType), nullable=False)
    confidence = Column(Float)
    win_probability = Column(Float)
    momentum_score = Column(Float)
    team_a_odds = Column(Float)
    team_b_odds = Column(Float)
    current_over = Column(Float)
    current_runs = Column(Integer)
    current_wickets = Column(Integer)

    # Strategy-specific outputs
    hedge_amount = Column(Float)
    hedge_profit = Column(Float)
    bookset_stake_a = Column(Float)
    bookset_stake_b = Column(Float)
    session_prediction = Column(Float)

    reasoning = Column(Text)
    telegram_signals = Column(JSON)
    timestamp = Column(DateTime, default=datetime.utcnow)

    match = relationship("Match", back_populates="signals")

    __table_args__ = (
        Index("idx_signal_match_time", "match_id", "timestamp"),
        Index("idx_signal_type", "signal_type"),
    )


class PlayerStats(Base):
    __tablename__ = "player_stats"

    id = Column(Integer, primary_key=True)
    player_name = Column(String(100), nullable=False, index=True)
    team = Column(String(100))
    role = Column(String(50))  # batsman, bowler, allrounder

    # Batting
    batting_avg = Column(Float)
    batting_sr = Column(Float)
    t20_runs = Column(Integer)
    t20_innings = Column(Integer)

    # Bowling
    bowling_avg = Column(Float)
    bowling_economy = Column(Float)
    bowling_sr = Column(Float)
    wickets = Column(Integer)

    # Venue-specific
    venue_avg = Column(Float)
    venue_sr = Column(Float)

    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)


class VenueStats(Base):
    __tablename__ = "venue_stats"

    id = Column(Integer, primary_key=True)
    venue_name = Column(String(200), nullable=False, unique=True)
    city = Column(String(100))
    avg_first_innings_score = Column(Float)
    avg_second_innings_score = Column(Float)
    avg_powerplay_runs = Column(Float)
    avg_death_over_runs = Column(Float)
    pace_bowling_avg = Column(Float)
    spin_bowling_avg = Column(Float)
    matches_played = Column(Integer)


class TelegramMessage(Base):
    __tablename__ = "telegram_messages"

    id = Column(Integer, primary_key=True)
    channel = Column(String(200))
    message_id = Column(Integer)
    raw_text = Column(Text)
    parsed_signal = Column(JSON)
    sentiment_score = Column(Float)
    is_relevant = Column(Boolean, default=False)
    timestamp = Column(DateTime, default=datetime.utcnow)
