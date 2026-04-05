import { create } from 'zustand';

export const useStore = create((set, get) => ({
  // Match state
  matchState: {
    match_id: 1,
    team_a: 'Mumbai Indians',
    team_b: 'Chennai Super Kings',
    innings: 1,
    total_runs: 0,
    total_wickets: 0,
    overs: 0.0,
    run_rate: 0.0,
    required_run_rate: 0.0,
    target: 0,
    current_batsman_1: 'Rohit Sharma',
    current_batsman_2: 'Ishan Kishan',
    current_bowler: 'Deepak Chahar',
    batsman_1_runs: 0,
    batsman_2_runs: 0,
    batsman_1_balls: 0,
    batsman_2_balls: 0,
    last_ball: '',
    powerplay_runs: 0,
    status: 'live',
  },

  // Odds
  odds: { team_a_odds: 1.85, team_b_odds: 2.1, timestamp: null },
  oddsHistory: [],

  // Signals
  latestSignal: null,
  signalHistory: [],

  // Telegram signals
  telegramSignals: [],

  // ML prediction
  mlPrediction: { win_probability: 0.5, momentum_score: 0.5 },

  // PnL simulation
  pnlHistory: [],
  totalPnl: 0,

  // UI state
  activeMatchId: 1,
  wsConnected: false,
  lastUpdate: null,

  // Stake config
  stakeConfig: { stake: 1000, entryOdds: 0, backedTeam: 'A' },

  // Actions
  setMatchState: (state) => set((s) => ({
    matchState: { ...s.matchState, ...state },
    lastUpdate: new Date().toISOString(),
  })),

  setOdds: (odds) => set((s) => ({
    odds: { ...odds, timestamp: new Date().toISOString() },
    oddsHistory: [
      { ...odds, timestamp: new Date().toISOString() },
      ...s.oddsHistory,
    ].slice(0, 100),
  })),

  setSignal: (signal) => set((s) => ({
    latestSignal: signal,
    signalHistory: [signal, ...s.signalHistory].slice(0, 50),
    pnlHistory: signal.pnl !== undefined
      ? [...s.pnlHistory, { pnl: signal.pnl, time: new Date().toISOString() }]
      : s.pnlHistory,
  })),

  addTelegramSignal: (sig) => set((s) => ({
    telegramSignals: [sig, ...s.telegramSignals].slice(0, 30),
  })),

  setMlPrediction: (pred) => set({ mlPrediction: pred }),

  setWsConnected: (v) => set({ wsConnected: v }),

  setStakeConfig: (cfg) => set((s) => ({
    stakeConfig: { ...s.stakeConfig, ...cfg }
  })),

  addPnl: (amount) => set((s) => ({
    totalPnl: s.totalPnl + amount,
    pnlHistory: [
      ...s.pnlHistory,
      { pnl: s.totalPnl + amount, time: new Date().toISOString() }
    ].slice(-200),
  })),
}));
