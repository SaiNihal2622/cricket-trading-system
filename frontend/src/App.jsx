import React, { useEffect, useCallback, useState } from 'react';
import axios from 'axios';
import { useStore } from './store/useStore';
import { useWebSocket } from './hooks/useWebSocket';
import { evaluateSignal, getMlPrediction, getTelegramSignals } from './services/api';

import Header from './components/Header';
import Scoreboard from './components/Scoreboard';
import OddsPanel from './components/OddsPanel';
import SignalPanel from './components/SignalPanel';
import PnLChart from './components/PnLChart';
import TelegramFeed from './components/TelegramFeed';
import StrategyCalculator from './components/StrategyCalculator';
import OddsChart from './components/OddsChart';
import AgentPanel from './components/AgentPanel';
import TradeApproval from './components/TradeApproval';

const API = process.env.REACT_APP_API_URL || '';

export default function App() {
  const { activeMatchId, stakeConfig, setSignal, setMlPrediction, addTelegramSignal } = useStore();
  useWebSocket(activeMatchId);

  const [autopilot, setAutopilot]   = useState(true);
  const [modeLoading, setModeLoading] = useState(false);

  // Poll for signal + ML every 15s
  const refreshSignal = useCallback(async () => {
    try {
      const [sigRes, mlRes] = await Promise.all([
        evaluateSignal(activeMatchId, stakeConfig.stake, stakeConfig.entryOdds, stakeConfig.backedTeam),
        getMlPrediction(activeMatchId),
      ]);
      setSignal(sigRes.data);
      setMlPrediction(mlRes.data);
    } catch {}
  }, [activeMatchId, stakeConfig, setSignal, setMlPrediction]);

  // Poll Telegram signals every 20s
  const refreshTelegram = useCallback(async () => {
    try {
      const res = await getTelegramSignals();
      (res.data.signals || []).forEach(addTelegramSignal);
    } catch {}
  }, [addTelegramSignal]);

  useEffect(() => {
    refreshSignal();
    refreshTelegram();
    const si = setInterval(refreshSignal, 15000);
    const ti = setInterval(refreshTelegram, 20000);
    return () => { clearInterval(si); clearInterval(ti); };
  }, [refreshSignal, refreshTelegram]);

  const toggleMode = async () => {
    setModeLoading(true);
    const newMode = !autopilot;
    try {
      await axios.post(`${API}/api/v1/agent/mode?autopilot=${newMode}`);
      setAutopilot(newMode);
    } catch {}
    setModeLoading(false);
  };

  return (
    <div style={styles.root}>
      <Header />

      {/* Mode toggle bar */}
      <div style={styles.modebar}>
        <span style={styles.modeLabel}>Agent Mode:</span>
        <button
          onClick={toggleMode}
          disabled={modeLoading}
          style={{
            ...styles.modeBtn,
            background: autopilot ? '#16a34a' : '#2563eb',
          }}
        >
          {autopilot ? '🤖 AUTOPILOT' : '🧑 SEMI-AUTO (approval required)'}
        </button>
        {!autopilot && (
          <span style={styles.modeHint}>
            Each trade will need your approval within 30s
          </span>
        )}
      </div>

      <div style={styles.body}>
        {/* Left column */}
        <div style={styles.col}>
          <Scoreboard />
          <OddsPanel />
          <StrategyCalculator />
        </div>

        {/* Center column */}
        <div style={{ ...styles.col, flex: '1 1 480px' }}>
          <SignalPanel />
          <OddsChart />
          <PnLChart />
        </div>

        {/* Right column */}
        <div style={{ ...styles.col, flex: '0 0 340px' }}>
          <AgentPanel />
          <TelegramFeed />
        </div>
      </div>

      {/* Semi-auto approval overlay — only shows in semi-auto mode */}
      <TradeApproval isAutopilot={autopilot} />
    </div>
  );
}

const styles = {
  root: {
    display: 'flex',
    flexDirection: 'column',
    height: '100vh',
    overflow: 'hidden',
    background: 'var(--bg-base)',
  },
  modebar: {
    display: 'flex',
    alignItems: 'center',
    gap: 10,
    padding: '4px 12px',
    background: '#0f0f1a',
    borderBottom: '1px solid #1e1e2e',
  },
  modeLabel: {
    fontSize: 11,
    color: '#64748b',
    fontWeight: 600,
  },
  modeBtn: {
    border: 'none',
    borderRadius: 5,
    padding: '4px 14px',
    color: '#fff',
    fontSize: 12,
    fontWeight: 700,
    cursor: 'pointer',
    letterSpacing: 0.5,
  },
  modeHint: {
    fontSize: 10,
    color: '#3b82f6',
    fontStyle: 'italic',
  },
  body: {
    display: 'flex',
    flex: 1,
    gap: 8,
    padding: '8px',
    overflow: 'hidden',
  },
  col: {
    display: 'flex',
    flexDirection: 'column',
    gap: 8,
    flex: '0 0 300px',
    overflow: 'hidden',
  },
};
