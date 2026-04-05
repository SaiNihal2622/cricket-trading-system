import React from 'react';
import { useStore } from '../store/useStore';

export default function Header() {
  const { wsConnected, lastUpdate, matchState } = useStore();

  return (
    <header style={styles.header}>
      <div style={styles.left}>
        <span style={styles.logo}>🏏 CRICKET INTEL</span>
        <span style={styles.subtitle}>TRADING DECISION SUPPORT SYSTEM</span>
      </div>

      <div style={styles.center}>
        <TickerItem label="MATCH" value={`${matchState.team_a} vs ${matchState.team_b}`} />
        <TickerItem label="OVER" value={matchState.overs?.toFixed(1)} />
        <TickerItem label="SCORE" value={`${matchState.total_runs}/${matchState.total_wickets}`} />
        <TickerItem label="CRR" value={matchState.run_rate?.toFixed(2)} color="var(--cyan)" />
        {matchState.required_run_rate > 0 &&
          <TickerItem label="RRR" value={matchState.required_run_rate?.toFixed(2)} color="var(--amber)" />
        }
      </div>

      <div style={styles.right}>
        <div style={styles.wsStatus}>
          <span
            className="live-pulse"
            style={{ ...styles.dot, background: wsConnected ? 'var(--green)' : 'var(--red)' }}
          />
          <span style={{ color: wsConnected ? 'var(--green)' : 'var(--red)', fontSize: 11 }}>
            {wsConnected ? 'LIVE' : 'RECONNECTING'}
          </span>
        </div>
        {lastUpdate && (
          <span style={styles.time}>
            {new Date(lastUpdate).toLocaleTimeString()}
          </span>
        )}
      </div>
    </header>
  );
}

function TickerItem({ label, value, color }) {
  return (
    <div style={styles.ticker}>
      <span style={styles.tickerLabel}>{label}</span>
      <span style={{ ...styles.tickerValue, color: color || 'var(--text-primary)' }}>{value || '—'}</span>
    </div>
  );
}

const styles = {
  header: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    padding: '6px 12px',
    background: 'var(--bg-panel)',
    borderBottom: '1px solid var(--border)',
    height: 44,
    flexShrink: 0,
  },
  left: { display: 'flex', alignItems: 'baseline', gap: 10 },
  logo: {
    fontFamily: 'var(--font-display)',
    fontSize: 20,
    fontWeight: 800,
    color: 'var(--cyan)',
    letterSpacing: 1,
  },
  subtitle: { fontSize: 9, color: 'var(--text-dim)', letterSpacing: 2 },
  center: { display: 'flex', gap: 20, alignItems: 'center' },
  ticker: { display: 'flex', flexDirection: 'column', alignItems: 'center' },
  tickerLabel: { fontSize: 9, color: 'var(--text-dim)', letterSpacing: 1 },
  tickerValue: { fontSize: 13, fontWeight: 600 },
  right: { display: 'flex', alignItems: 'center', gap: 12 },
  wsStatus: { display: 'flex', alignItems: 'center', gap: 5 },
  dot: { width: 7, height: 7, borderRadius: '50%', display: 'inline-block' },
  time: { fontSize: 10, color: 'var(--text-dim)' },
};
