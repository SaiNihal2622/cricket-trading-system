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
import AIInsightsPanel from './components/AIInsightsPanel';
import TradeFeed from './components/TradeFeed';

const API = process.env.REACT_APP_API_URL || '';

export default function App() {
  const { activeMatchId, stakeConfig, setSignal, setMlPrediction, addTelegramSignal } = useStore();
  useWebSocket(activeMatchId);

  const [autopilot, setAutopilot]   = useState(true);
  const [modeLoading, setModeLoading] = useState(false);
  const [demoMode, setDemoMode] = useState(true);
  const [systemHealth, setSystemHealth] = useState({ cpu: 23, mem: 41, latency: 45, uptime: '2h 34m' });

  // Simulate system health metrics
  useEffect(() => {
    if (!demoMode) return;
    const interval = setInterval(() => {
      setSystemHealth(prev => ({
        cpu: Math.max(5, Math.min(95, prev.cpu + (Math.random() - 0.5) * 10)),
        mem: Math.max(20, Math.min(85, prev.mem + (Math.random() - 0.5) * 5)),
        latency: Math.max(10, Math.min(200, prev.latency + (Math.random() - 0.5) * 20)),
        uptime: prev.uptime,
      }));
    }, 3000);
    return () => clearInterval(interval);
  }, [demoMode]);

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

        {/* Demo mode badge */}
        {demoMode && (
          <div style={styles.demoBadge}>
            <span style={styles.demoDot} className="live-pulse" />
            <span>DEMO MODE — 80%+ ACCURACY TARGET</span>
          </div>
        )}

        {/* System health mini-bar */}
        <div style={styles.healthBar}>
          <HealthChip label="CPU" value={`${systemHealth.cpu.toFixed(0)}%`} color={systemHealth.cpu > 80 ? 'var(--red)' : 'var(--green)'} />
          <HealthChip label="MEM" value={`${systemHealth.mem.toFixed(0)}%`} color={systemHealth.mem > 70 ? 'var(--amber)' : 'var(--green)'} />
          <HealthChip label="PING" value={`${systemHealth.latency.toFixed(0)}ms`} color={systemHealth.latency > 150 ? 'var(--red)' : 'var(--cyan)'} />
          <HealthChip label="UP" value={systemHealth.uptime} color="var(--text-secondary)" />
        </div>
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
          <AIInsightsPanel />
          <OddsChart />
          <PnLChart />
        </div>

        {/* Right column */}
        <div style={{ ...styles.col, flex: '0 0 360px' }}>
          <AgentPanel />
          <TradeFeed />
          <TelegramFeed />
        </div>
      </div>

      {/* Semi-auto approval overlay — only shows in semi-auto mode */}
      <TradeApproval isAutopilot={autopilot} />
    </div>
  );
}

function HealthChip({ label, value, color }) {
  return (
    <div style={healthStyles.chip}>
      <span style={healthStyles.label}>{label}</span>
      <span style={{ ...healthStyles.value, color }}>{value}</span>
    </div>
  );
}

const healthStyles = {
  chip: { display: 'flex', flexDirection: 'column', alignItems: 'center', minWidth: 36 },
  label: { fontSize: 7, color: 'var(--text-dim)', letterSpacing: 1 },
  value: { fontSize: 10, fontWeight: 700, fontFamily: 'var(--font-mono)' },
};

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
  demoBadge: {
    display: 'flex',
    alignItems: 'center',
    gap: 5,
    marginLeft: 'auto',
    padding: '2px 10px',
    background: 'rgba(124,77,255,0.15)',
    border: '1px solid rgba(124,77,255,0.3)',
    borderRadius: 4,
    fontSize: 9,
    color: 'var(--purple)',
    fontWeight: 700,
    letterSpacing: 1,
  },
  demoDot: {
    width: 6,
    height: 6,
    borderRadius: '50%',
    background: 'var(--purple)',
    display: 'inline-block',
  },
  healthBar: {
    display: 'flex',
    gap: 10,
    marginLeft: 12,
    alignItems: 'center',
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