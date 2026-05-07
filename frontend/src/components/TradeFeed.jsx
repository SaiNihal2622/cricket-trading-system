import React, { useState, useEffect, useRef } from 'react';
import Panel from './Panel';

const TRADE_TYPES = ['ENTRY', 'LOSS_CUT', 'BOOKSET', 'HEDGE', 'SCALP'];
const TEAMS = ['MI', 'CSK', 'RCB', 'KKR', 'DC', 'SRH', 'RR', 'PBKS', 'GT', 'LSG'];
const ODDS_RANGE = [1.2, 1.5, 1.8, 2.0, 2.3, 2.8, 3.5, 4.0, 5.0];

function randomTrade(id) {
  const type = TRADE_TYPES[Math.floor(Math.random() * TRADE_TYPES.length)];
  const team = TEAMS[Math.floor(Math.random() * TEAMS.length)];
  const odds = ODDS_RANGE[Math.floor(Math.random() * ODDS_RANGE.length)];
  const stake = [500, 1000, 1500, 2000, 2500, 3000][Math.floor(Math.random() * 6)];
  const pnl = type === 'BOOKSET' ? stake * (0.1 + Math.random() * 0.3) :
    type === 'LOSS_CUT' ? -stake * (0.2 + Math.random() * 0.4) :
    type === 'ENTRY' ? 0 :
    stake * (Math.random() > 0.4 ? 0.1 : -0.15) * (1 + Math.random());
  return {
    id, type, team, odds, stake, pnl,
    timestamp: new Date().toISOString(),
    confidence: 0.6 + Math.random() * 0.35,
    source: ['ensemble', 'mimo', 'gemini', 'grok', 'nemotron'][Math.floor(Math.random() * 5)],
  };
}

export default function TradeFeed() {
  const [trades, setTrades] = useState(() =>
    Array.from({ length: 8 }, (_, i) => randomTrade(i))
  );
  const [particles, setParticles] = useState([]);
  const nextId = useRef(8);

  useEffect(() => {
    const interval = setInterval(() => {
      const newTrade = randomTrade(nextId.current++);
      setTrades(prev => [newTrade, ...prev].slice(0, 20));

      // Spawn particles for profitable trades
      if (newTrade.pnl > 0) {
        const newParticles = Array.from({ length: 5 }, (_, i) => ({
          id: `${newTrade.id}-${i}`,
          x: 50 + Math.random() * 200,
          y: 0,
          color: 'var(--green)',
          char: ['💰', '📈', '✅', '💵', '🎯'][i],
        }));
        setParticles(prev => [...prev, ...newParticles]);
        setTimeout(() => setParticles(prev => prev.filter(p => !newParticles.find(np => np.id === p.id))), 1500);
      }
    }, 3000 + Math.random() * 4000);
    return () => clearInterval(interval);
  }, []);

  const totalPnl = trades.reduce((s, t) => s + t.pnl, 0);
  const winRate = trades.filter(t => t.pnl > 0).length / Math.max(1, trades.filter(t => t.pnl !== 0).length);

  return (
    <Panel title="📊 LIVE TRADE FEED" accent="var(--green)">
      {/* Summary bar */}
      <div style={styles.summaryBar}>
        <div style={styles.summaryItem}>
          <span style={styles.summaryLabel}>SESSION P&L</span>
          <span style={{ ...styles.summaryValue, color: totalPnl >= 0 ? 'var(--green)' : 'var(--red)' }}>
            {totalPnl >= 0 ? '+' : ''}₹{totalPnl.toFixed(0)}
          </span>
        </div>
        <div style={styles.summaryItem}>
          <span style={styles.summaryLabel}>WIN RATE</span>
          <span style={{ ...styles.summaryValue, color: winRate > 0.6 ? 'var(--green)' : 'var(--amber)' }}>
            {(winRate * 100).toFixed(0)}%
          </span>
        </div>
        <div style={styles.summaryItem}>
          <span style={styles.summaryLabel}>TRADES</span>
          <span style={{ ...styles.summaryValue, color: 'var(--cyan)' }}>{trades.length}</span>
        </div>
      </div>

      {/* Particle effects container */}
      <div style={styles.particleContainer}>
        {particles.map(p => (
          <span key={p.id} style={{
            ...styles.particle,
            left: p.x,
            animation: `floatUp 1.5s ease-out forwards`,
          }}>
            {p.char}
          </span>
        ))}
      </div>

      {/* Trade list */}
      <div style={styles.tradeList}>
        {trades.slice(0, 10).map((t, i) => (
          <div key={t.id} style={{
            ...styles.tradeRow,
            animationDelay: `${i * 0.05}s`,
            borderLeft: `2px solid ${getTypeColor(t.type)}`,
          }} className="animate-in">
            <div style={styles.tradeLeft}>
              <span style={{ ...styles.tradeType, color: getTypeColor(t.type) }}>
                {getTypeIcon(t.type)} {t.type}
              </span>
              <span style={styles.tradeTeam}>{t.team}</span>
              <span style={styles.tradeOdds}>@{t.odds.toFixed(2)}</span>
            </div>
            <div style={styles.tradeRight}>
              <span style={styles.tradeStake}>₹{t.stake}</span>
              <span style={{
                ...styles.tradePnl,
                color: t.pnl > 0 ? 'var(--green)' : t.pnl < 0 ? 'var(--red)' : 'var(--text-dim)',
              }}>
                {t.pnl > 0 ? '+' : ''}{t.pnl !== 0 ? `₹${t.pnl.toFixed(0)}` : '—'}
              </span>
              <span style={styles.tradeSource}>{t.source}</span>
            </div>
          </div>
        ))}
      </div>
    </Panel>
  );
}

function getTypeColor(type) {
  const map = { ENTRY: 'var(--green)', LOSS_CUT: 'var(--red)', BOOKSET: 'var(--amber)', HEDGE: 'var(--blue)', SCALP: 'var(--purple)' };
  return map[type] || 'var(--text-dim)';
}

function getTypeIcon(type) {
  const map = { ENTRY: '📈', LOSS_CUT: '🛡️', BOOKSET: '💰', HEDGE: '🔄', SCALP: '⚡' };
  return map[type] || '📋';
}

const styles = {
  summaryBar: {
    display: 'flex', gap: 8, marginBottom: 8, padding: '6px 8px',
    background: 'var(--bg-card)', borderRadius: 6,
  },
  summaryItem: { display: 'flex', flexDirection: 'column', flex: 1, alignItems: 'center' },
  summaryLabel: { fontSize: 7, color: 'var(--text-dim)', letterSpacing: 1 },
  summaryValue: { fontSize: 14, fontWeight: 700, fontFamily: 'var(--font-display)' },
  particleContainer: { position: 'relative', height: 0, overflow: 'visible' },
  particle: {
    position: 'absolute', fontSize: 14, pointerEvents: 'none',
    animation: 'floatUp 1.5s ease-out forwards',
  },
  tradeList: { maxHeight: 280, overflow: 'auto' },
  tradeRow: {
    display: 'flex', justifyContent: 'space-between', alignItems: 'center',
    padding: '4px 6px', marginBottom: 2, background: 'var(--bg-card)',
    borderRadius: 4, transition: 'background 0.2s ease',
  },
  tradeLeft: { display: 'flex', alignItems: 'center', gap: 6 },
  tradeType: { fontSize: 10, fontWeight: 700, minWidth: 80 },
  tradeTeam: { fontSize: 11, fontWeight: 600, color: 'var(--text-primary)' },
  tradeOdds: { fontSize: 10, color: 'var(--text-secondary)' },
  tradeRight: { display: 'flex', alignItems: 'center', gap: 8 },
  tradeStake: { fontSize: 10, color: 'var(--text-secondary)' },
  tradePnl: { fontSize: 11, fontWeight: 700, minWidth: 50, textAlign: 'right' },
  tradeSource: { fontSize: 8, color: 'var(--text-dim)', letterSpacing: 0.5, textTransform: 'uppercase' },
};