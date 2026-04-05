import React from 'react';
import { useStore } from '../store/useStore';
import Panel from './Panel';

const SIGNAL_CONFIG = {
  ENTER:    { color: 'var(--signal-enter)',   bg: 'var(--green-dim)',  icon: '✅', label: 'ENTER POSITION' },
  LOSS_CUT: { color: 'var(--signal-losscut)', bg: 'var(--red-dim)',    icon: '🔴', label: 'LOSS CUT' },
  BOOKSET:  { color: 'var(--signal-bookset)', bg: 'var(--amber-dim)',  icon: '💰', label: 'BOOKSET' },
  SESSION:  { color: 'var(--signal-session)', bg: '#003344',           icon: '📊', label: 'SESSION SIGNAL' },
  HOLD:     { color: 'var(--signal-hold)',    bg: '#111d2b',           icon: '⏳', label: 'HOLD' },
};

const URGENCY_COLOR = {
  CRITICAL: 'var(--red)',
  HIGH: 'var(--amber)',
  MEDIUM: 'var(--cyan)',
  LOW: 'var(--text-secondary)',
};

export default function SignalPanel() {
  const { latestSignal, signalHistory, mlPrediction } = useStore();
  const sig = latestSignal;
  const cfg = SIGNAL_CONFIG[sig?.signal] || SIGNAL_CONFIG.HOLD;

  return (
    <Panel title="DECISION ENGINE" accent={cfg.color} style={{ flex: '0 0 auto' }}>
      {/* Main signal banner */}
      <div style={{ ...styles.signalBanner, background: cfg.bg, borderColor: cfg.color }}>
        <div style={styles.bannerLeft}>
          <span style={styles.signalIcon}>{cfg.icon}</span>
          <div>
            <div style={{ ...styles.signalType, color: cfg.color }}>{cfg.label}</div>
            <div style={styles.signalReason}>{sig?.reasoning || 'Awaiting signal...'}</div>
          </div>
        </div>
        <div style={styles.bannerRight}>
          <UrgencyBadge urgency={sig?.urgency} />
          <ConfBadge confidence={sig?.confidence} />
        </div>
      </div>

      {/* ML Metrics row */}
      <div style={styles.metricsRow}>
        <Metric label="WIN PROB" value={`${((sig?.win_probability || mlPrediction.win_probability) * 100).toFixed(1)}%`}
          color={getWinProbColor(sig?.win_probability || mlPrediction.win_probability)} bar />
        <Metric label="MOMENTUM" value={`${((sig?.momentum_score || mlPrediction.momentum_score) * 100).toFixed(1)}%`}
          color="var(--purple)" bar />
        <Metric label="CONFIDENCE" value={`${((sig?.confidence || 0) * 100).toFixed(1)}%`} color="var(--cyan)" />
      </div>

      {/* Strategy details */}
      {sig?.loss_cut?.trigger && (
        <DetailBlock title="HEDGE CALCULATION" color="var(--red)">
          <Row label="Hedge Amount" value={`₹${sig.loss_cut.hedge_amount?.toFixed(2)}`} />
          <Row label="Locked Profit" value={`₹${sig.loss_cut.hedge_profit?.toFixed(2)}`} />
          <Row label="Trigger" value={sig.loss_cut.reason} small />
        </DetailBlock>
      )}

      {sig?.bookset && (
        <DetailBlock title="BOOKSET CALCULATION" color="var(--amber)">
          <Row label={`Stake (Team A)`} value={`₹${sig.bookset.stake_a?.toFixed(2)}`} />
          <Row label={`Stake (Team B)`} value={`₹${sig.bookset.stake_b?.toFixed(2)}`} />
          <Row label="Guaranteed Profit" value={`₹${sig.bookset.guaranteed_profit?.toFixed(2)}`} highlight />
          <Row label="Profit %" value={`${sig.bookset.profit_pct?.toFixed(2)}%`} />
        </DetailBlock>
      )}

      {sig?.session && (
        <DetailBlock title="SESSION PROJECTION" color="var(--blue)">
          <Row label="Phase" value={sig.session.phase?.toUpperCase()} />
          <Row label="Predicted" value={`${sig.session.predicted_runs?.toFixed(1)} runs`} highlight />
          <Row label="CI" value={`${sig.session.ci_low?.toFixed(0)} – ${sig.session.ci_high?.toFixed(0)}`} />
          <Row label="Signal" value={sig.session.signal} color={sig.session.signal === 'OVER' ? 'var(--green)' : sig.session.signal === 'UNDER' ? 'var(--red)' : 'var(--text-secondary)'} />
        </DetailBlock>
      )}

      {/* Signal history */}
      {signalHistory.length > 1 && (
        <div style={styles.history}>
          <div style={styles.histLabel}>SIGNAL HISTORY</div>
          {signalHistory.slice(1, 6).map((s, i) => {
            const c = SIGNAL_CONFIG[s.signal] || SIGNAL_CONFIG.HOLD;
            return (
              <div key={i} style={styles.histRow}>
                <span style={{ color: c.color, fontSize: 11 }}>{c.icon} {s.signal}</span>
                <span style={{ color: 'var(--text-dim)', fontSize: 10 }}>
                  {s.confidence ? `${(s.confidence * 100).toFixed(0)}%` : ''}
                </span>
                <span style={{ color: 'var(--text-dim)', fontSize: 10 }}>
                  {s.timestamp ? new Date(s.timestamp).toLocaleTimeString() : ''}
                </span>
              </div>
            );
          })}
        </div>
      )}
    </Panel>
  );
}

function UrgencyBadge({ urgency }) {
  if (!urgency) return null;
  return (
    <span style={{ ...styles.badge, color: URGENCY_COLOR[urgency] || 'var(--text-dim)', borderColor: URGENCY_COLOR[urgency] || 'var(--border)' }}>
      {urgency}
    </span>
  );
}

function ConfBadge({ confidence }) {
  if (!confidence) return null;
  return (
    <span style={{ ...styles.badge, color: 'var(--cyan)', borderColor: 'var(--cyan)' }}>
      {(confidence * 100).toFixed(0)}% conf
    </span>
  );
}

function Metric({ label, value, color, bar }) {
  const numVal = parseFloat(value);
  return (
    <div style={styles.metric}>
      <div style={styles.metricLabel}>{label}</div>
      <div style={{ ...styles.metricValue, color }}>{value}</div>
      {bar && !isNaN(numVal) && (
        <div style={styles.barTrack}>
          <div style={{ ...styles.barFill, width: `${numVal}%`, background: color }} />
        </div>
      )}
    </div>
  );
}

function DetailBlock({ title, color, children }) {
  return (
    <div style={{ ...styles.detailBlock, borderColor: color }}>
      <div style={{ ...styles.detailTitle, color }}>{title}</div>
      {children}
    </div>
  );
}

function Row({ label, value, highlight, small, color }) {
  return (
    <div style={styles.detailRow}>
      <span style={{ ...styles.detailLabel, fontSize: small ? 10 : 11 }}>{label}</span>
      <span style={{
        ...styles.detailValue,
        color: color || (highlight ? 'var(--green)' : 'var(--text-primary)'),
        fontWeight: highlight ? 700 : 500,
        fontSize: small ? 10 : 12,
      }}>{value}</span>
    </div>
  );
}

function getWinProbColor(p) {
  if (!p) return 'var(--text-secondary)';
  if (p >= 0.65) return 'var(--green)';
  if (p <= 0.35) return 'var(--red)';
  return 'var(--amber)';
}

const styles = {
  signalBanner: {
    display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start',
    padding: '10px 12px', borderRadius: 'var(--radius-md)',
    border: '1px solid', marginBottom: 10,
  },
  bannerLeft: { display: 'flex', gap: 10, alignItems: 'flex-start', flex: 1 },
  signalIcon: { fontSize: 22, lineHeight: 1 },
  signalType: { fontFamily: 'var(--font-display)', fontSize: 18, fontWeight: 800, letterSpacing: 1 },
  signalReason: { fontSize: 10, color: 'var(--text-secondary)', marginTop: 2, lineHeight: 1.4 },
  bannerRight: { display: 'flex', flexDirection: 'column', gap: 4, alignItems: 'flex-end' },
  badge: { fontSize: 9, border: '1px solid', borderRadius: 3, padding: '2px 5px', letterSpacing: 1 },

  metricsRow: { display: 'flex', gap: 8, marginBottom: 10 },
  metric: { flex: 1 },
  metricLabel: { fontSize: 9, color: 'var(--text-dim)', letterSpacing: 1, marginBottom: 2 },
  metricValue: { fontSize: 14, fontWeight: 700, marginBottom: 3 },
  barTrack: { height: 3, background: 'var(--bg-base)', borderRadius: 2 },
  barFill: { height: '100%', borderRadius: 2, transition: 'width 0.4s ease' },

  detailBlock: { border: '1px solid', borderRadius: 'var(--radius-sm)', padding: '8px 10px', marginBottom: 8 },
  detailTitle: { fontSize: 9, letterSpacing: 2, marginBottom: 6, fontWeight: 600 },
  detailRow: { display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 3 },
  detailLabel: { color: 'var(--text-secondary)' },
  detailValue: { fontFamily: 'var(--font-mono)' },

  history: { marginTop: 6, borderTop: '1px solid var(--border)', paddingTop: 6 },
  histLabel: { fontSize: 9, color: 'var(--text-dim)', letterSpacing: 2, marginBottom: 4 },
  histRow: { display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '2px 0' },
};
