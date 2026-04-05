import axios from 'axios';

const BASE = process.env.REACT_APP_API_URL || 'http://localhost:8000';
const WS_BASE = process.env.REACT_APP_WS_URL || 'ws://localhost:8000';

const api = axios.create({ baseURL: `${BASE}/api/v1`, timeout: 10000 });

// ── REST API ──────────────────────────────────────────────────────────────────

export const updateOdds = (matchId, oddsA, oddsB) =>
  api.post('/odds/update', { match_id: matchId, teamA_odds: oddsA, teamB_odds: oddsB });

export const getOddsHistory = (matchId) =>
  api.get(`/odds/${matchId}/history`);

export const getMatchState = (matchId) =>
  api.get(`/match/${matchId}/state`);

export const getLiveMatches = () =>
  api.get('/matches/live');

export const evaluateSignal = (matchId, stake, entryOdds, backedTeam) =>
  api.post('/signal/evaluate', {
    match_id: matchId, stake, entry_odds: entryOdds, backed_team: backedTeam
  });

export const getSignalHistory = (matchId) =>
  api.get(`/signal/${matchId}/history`);

export const calcLossCut = (params) =>
  api.post('/strategy/loss-cut', params);

export const calcBookset = (oddsA, oddsB, stake) =>
  api.post('/strategy/bookset', { odds_a: oddsA, odds_b: oddsB, total_stake: stake });

export const calcSession = (params) =>
  api.post('/strategy/session', params);

export const getMlPrediction = (matchId) =>
  api.post(`/ml/predict?match_id=${matchId}`);

export const getTelegramSignals = () =>
  api.get('/telegram/signals');

// ── WebSocket ─────────────────────────────────────────────────────────────────

export class CricketWebSocket {
  constructor(matchId, handlers) {
    this.matchId = matchId;
    this.handlers = handlers;
    this.ws = null;
    this.reconnectTimer = null;
    this.reconnectDelay = 2000;
    this._dead = false;
  }

  connect() {
    this._dead = false;
    try {
      this.ws = new WebSocket(`${WS_BASE}/ws/match/${this.matchId}`);

      this.ws.onopen = () => {
        this.reconnectDelay = 2000;
        this.handlers.onConnect?.();
      };

      this.ws.onmessage = (e) => {
        try {
          const msg = JSON.parse(e.data);
          switch (msg.type) {
            case 'match_state':  this.handlers.onMatchState?.(msg.data); break;
            case 'odds_update':  this.handlers.onOdds?.(msg.data); break;
            case 'signal':       this.handlers.onSignal?.(msg.data); break;
            default: break;
          }
        } catch {}
      };

      this.ws.onclose = () => {
        this.handlers.onDisconnect?.();
        if (!this._dead) this._scheduleReconnect();
      };

      this.ws.onerror = () => {
        this.ws?.close();
      };
    } catch (e) {
      if (!this._dead) this._scheduleReconnect();
    }
  }

  _scheduleReconnect() {
    clearTimeout(this.reconnectTimer);
    this.reconnectTimer = setTimeout(() => {
      this.reconnectDelay = Math.min(this.reconnectDelay * 1.5, 30000);
      this.connect();
    }, this.reconnectDelay);
  }

  disconnect() {
    this._dead = true;
    clearTimeout(this.reconnectTimer);
    this.ws?.close();
  }
}
