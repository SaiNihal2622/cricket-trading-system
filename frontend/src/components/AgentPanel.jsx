import React, { useState, useEffect, useRef } from 'react';
import Panel from './Panel';

const WS_BASE = process.env.REACT_APP_WS_URL || 'ws://localhost:8000';

const AGENT_STATES = {
  RUNNING: { color: 'var(--green)', icon: '🟢', label: 'RUNNING' },
  PAUSED: { color: 'var(--amber)', icon: '🟡', label: 'PAUSED' },
  STOPPED: { color: 'var(--red)', icon: '🔴', label: 'STOPPED' },
  CIRCUIT_BREAK: { color: 'var(--red)', icon: '🚨', label: 'CIRCUIT BREAK' },
  disabled: { color: 'var(--text-dim)', icon: '⚪', label: 'DISABLED' },
};

export default function AgentPanel() {
  const [status, setStatus] = useState(null);
  const [loading, setLoading] = useState(false);
  const [liveLog, setLiveLog] = useState([]);
  const logRef = useRef(null);

  // Poll agent status every 3s
  const fetchStatus = async () => {
    try {
      const res = await fetch('http://localhost:8000/agent/status');
      const data = await res.json();
      setStatus(data);
    } catch (e) {
      setStatus(null);
    }
  };

  useEffect(() => {
    fetchStatus();
    const interval = setInterval(fetchStatus, 3000);
    return () => clearInterval(interval);
  }, []);

  // WebSocket for real-time agent actions
  useEffect(() => {
    let ws = null;
    let reconnectTimer = null;

    const connect = () => {
      try {
        ws = new WebSocket(`${WS_BASE}/ws/agent`);
        ws.onmessage = (e) => {
          try {
            const msg = JSON.parse(e.data);
            if (msg.type === 'agent_action') {
              setLiveLog((prev) => [msg.data, ...prev].slice(0, 50));
            }
          } catch {}
        };
        ws.onclose = () => {
          reconnectTimer = setTimeout(connect, 5000);
        };
        ws.onerror = () => ws?.close();
      } catch {
        reconnectTimer = setTimeout(connect, 5000);
      }
    };

    connect();
    return () => {
      clearTimeout(reconnectTimer);
      ws?.close();
    };
  }, []);

  // Auto-scroll live log
  useEffect(() => {
    if (logRef.current) {
      logRef.current.scrollTop = 0;
    }
  }, [liveLog]);

  const sendCommand = async (cmd) => {
    setLoading(true);
    try {
      await fetch(`http://localhost:8000/agent/${cmd}`, { method: 'POST' });
      await fetchStatus();
    } catch (e) {}
    setLoading(false);
  };

  if (!status) {
    return (
      <Panel title="🤖 AGENT" accent="var(--text-dim)">
        <div style={styles.disabled}>Agent not initialized. Set AGENT_ENABLED=true</div>
      </Panel>
    );
  }

  const stateInfo = AGENT_STATES[status.state] || AGENT_STATES.disabled;
  const risk = status.risk || {};
  const portfolio = status.portfolio || {};
  const mode = status.mode || 'simulation';
  const exchange = status.exchange || {};

  // Merge REST actions with WebSocket live log
  const allActions = liveLog.length > 0
    ? liveLog
    : (status.recent_actions || []).slice(-10).reverse().map((a) => ({
        action: a.action,
        data: a.data,
        timestamp: a.timestamp,
      }));

  return (
    <Panel title="🤖 AUTONOMOUS AGENT" accent={stateInfo.color}>
      {/* Mode & State Banner */}
      <div style={{ ...styles.banner, borderColor: stateInfo.color }}>
        <div style={styles.bannerLeft}>
          <span style={{ fontSize: 20 }}>{stateInfo.icon}</span>
          <div>
            <div style={{ ...styles.stateLabel, color: stateInfo.color }}>{stateInfo.label}</div>
            <div style={styles.mode}>
              {mode === 'simulation' ? '🟡 PAPER TRADING' : '🔴 LIVE'}
              {' | '}Cycle #{status.cycle_count || 0}
              {' | '}{status.loop_interval || 5}s interval
            </div>
          </div>
        </div>
        <div style={styles.controls}>
          {status.state === 'STOPPED' || status.state === 'disabled' ? (
            <Btn label="▶ START" color="var(--green)" onClick={() => sendCommand('start')} disabled={loading} />
          ) : (
            <>
              {status.state === 'RUNNING' && (
                <Btn label="⏸ PAUSE" color="var(--amber)" onClick={() => sendCommand('pause')} disabled={loading} />
              )}
              {status.state === 'PAUSED' && (
                <Btn label="▶ RESUME" color="var(--green)" onClick={() => sendCommand('resume')} disabled={loading} />
              )}
              <Btn label="⏹ STOP" color="var(--red)" onClick={() => sendCommand('stop')} disabled={loading} />
            </>
          )}
        </div>
      </div>

      {/* Bankroll & P&L */}
      <div style={styles.metricsRow}>
        <Metric label="BANKROLL" value={`₹${risk.bankroll?.toLocaleString() || '0'}`} color="var(--cyan)" />
        <Metric
          label="DAILY P&L"
          value={`₹${risk.daily_pnl >= 0 ? '+' : ''}${risk.daily_pnl?.toFixed(0) || '0'}`}
          color={risk.daily_pnl >= 0 ? 'var(--green)' : 'var(--red)'}
        />
        <Metric
          label="TOTAL P&L"
          value={`₹${risk.total_pnl >= 0 ? '+' : ''}${risk.total_pnl?.toFixed(0) || '0'}`}
          color={risk.total_pnl >= 0 ? 'var(--green)' : 'var(--red)'}
        />
        <Metric
          label="DRAWDOWN"
          value={`${risk.drawdown_pct?.toFixed(1) || '0'}%`}
          color={risk.drawdown_pct > 20 ? 'var(--red)' : 'var(--text-secondary)'}
        />
      </div>

      {/* Exchange balance (simulated) */}
      {exchange.balance !== undefined && (
        <div style={styles.exchangeRow}>
          <span style={styles.exchangeLabel}>EXCHANGE</span>
          <span style={styles.exchangeValue}>
            ₹{exchange.balance?.toLocaleString()} ({exchange.exchange || 'sim'})
          </span>
          <span style={{ ...styles.exchangePnl, color: exchange.pnl >= 0 ? 'var(--green)' : 'var(--red)' }}>
            {exchange.pnl >= 0 ? '+' : ''}₹{exchange.pnl?.toFixed(0)}
          </span>
          <span style={styles.exchangeOrders}>{exchange.total_orders || 0} orders</span>
        </div>
      )}

      {/* Risk meters */}
      <div style={styles.riskRow}>
        <RiskMeter
          label="EXPOSURE"
          current={portfolio.total_exposure || 0}
          max={risk.max_exposure || 5000}
        />
        <RiskMeter
          label="DAILY LOSS"
          current={Math.abs(Math.min(0, risk.daily_pnl || 0))}
          max={risk.max_daily_loss || 2000}
        />
      </div>

      {/* Circuit breaker */}
      {risk.circuit_breaker_active && (
        <div style={styles.circuitBreaker}>
          <div>
            <span style={{ fontWeight: 700 }}>🚨 CIRCUIT BREAKER ACTIVE</span>
            <div style={{ fontSize: 9, marginTop: 2 }}>{risk.circuit_breaker_reason}</div>
          </div>
          <Btn
            label="🔄 RESET"
            color="var(--amber)"
            onClick={() => sendCommand('circuit-breaker/reset')}
            disabled={loading}
          />
        </div>
      )}

      {/* Open Positions */}
      {(portfolio.positions || []).length > 0 && (
        <div style={styles.positions}>
          <div style={styles.sectionLabel}>OPEN POSITIONS</div>
          {portfolio.positions.map((p, i) => (
            <div key={i} style={styles.positionRow}>
              <span style={styles.posTeam}>
                {p.backed_team} @ {p.entry_odds}
              </span>
              <span style={styles.posStake}>₹{p.entry_stake}</span>
              <span style={{
                ...styles.posPnl,
                color: p.unrealized_pnl >= 0 ? 'var(--green)' : 'var(--red)'
              }}>
                ₹{p.unrealized_pnl >= 0 ? '+' : ''}{p.unrealized_pnl?.toFixed(0)}
              </span>
              <span style={{
                ...styles.posStatus,
                color: p.status === 'BOOKSET' ? 'var(--green)' :
                       p.status === 'HEDGED' ? 'var(--amber)' : stateInfo.color
              }}>{p.status}</span>
            </div>
          ))}
        </div>
      )}

      {/* Trade Stats */}
      <div style={styles.statsRow}>
        <StatBadge label="Trades" value={risk.total_trades || 0} />
        <StatBadge label="Wins" value={risk.winning_trades || 0} color="var(--green)" />
        <StatBadge label="Losses" value={risk.losing_trades || 0} color="var(--red)" />
        <StatBadge label="Streak" value={risk.consecutive_losses || 0} color={risk.consecutive_losses > 2 ? 'var(--red)' : 'var(--text-secondary)'} />
        <StatBadge
          label="Win%"
          value={risk.total_trades > 0 ? `${((risk.winning_trades / risk.total_trades) * 100).toFixed(0)}%` : '-'}
          color="var(--cyan)"
        />
      </div>

      {/* Live Action Log */}
      <div style={styles.actionLog} ref={logRef}>
        <div style={styles.sectionLabel}>
          LIVE ACTION LOG
          {liveLog.length > 0 && <span style={styles.liveDot}>● LIVE</span>}
        </div>
        {allActions.length === 0 && (
          <div style={{ fontSize: 10, color: 'var(--text-dim)', padding: '8px 0' }}>
            No actions yet. Agent will log decisions here...
          </div>
        )}
        {allActions.slice(0, 8).map((a, i) => (
          <div key={i} style={styles.actionRow} className="animate-in">
            <span style={styles.actionType}>
              {getActionIcon(a.action)} {a.action}
            </span>
            <span style={styles.actionData}>
              {formatActionData(a)}
            </span>
            <span style={styles.actionTime}>
              {a.timestamp ? new Date(a.timestamp).toLocaleTimeString() : ''}
            </span>
          </div>
        ))}
      </div>
    </Panel>
  );
}

function Btn({ label, color, onClick, disabled }) {
  return (
    <button
      onClick={onClick}
      disabled={disabled}
      style={{
        ...styles.btn,
        borderColor: color,
        color,
        opacity: disabled ? 0.5 : 1,
      }}
    >
      {label}
    </button>
  );
}

function Metric({ label, value, color }) {
  return (
    <div style={styles.metric}>
      <div style={styles.metricLabel}>{label}</div>
      <div style={{ ...styles.metricValue, color }}>{value}</div>
    </div>
  );
}

function RiskMeter({ label, current, max }) {
  const pct = max > 0 ? Math.min(100, (current / max) * 100) : 0;
  const color = pct > 80 ? 'var(--red)' : pct > 50 ? 'var(--amber)' : 'var(--green)';
  return (
    <div style={styles.riskMeter}>
      <div style={styles.riskMeterLabel}>
        <span>{label}</span>
        <span style={{ color }}>₹{current.toFixed(0)}/{max}</span>
      </div>
      <div style={styles.riskTrack}>
        <div style={{ ...styles.riskBar, width: `${pct}%`, background: color }} />
      </div>
    </div>
  );
}

function StatBadge({ label, value, color }) {
  return (
    <div style={styles.statBadge}>
      <span style={styles.statBadgeLabel}>{label}</span>
      <span style={{ ...styles.statBadgeValue, color: color || 'var(--text-primary)' }}>{value}</span>
    </div>
  );
}

function getActionIcon(action) {
  const icons = {
    ENTRY_EXECUTED: '📈', LOSS_CUT_EXECUTED: '🛡️', BOOKSET_EXECUTED: '💰',
    AGENT_START: '🚀', AGENT_STOP: '⏹️', AGENT_PAUSE: '⏸️', AGENT_RESUME: '▶️',
    ENTRY_REJECTED: '❌', HEDGE_FAILED: '⚠️', CYCLE_ERROR: '🔥',
    CIRCUIT_BREAK: '🚨', AI_OVERRIDE: '🧠', ENTRY: '📈',
    LOSS_CUT: '🛡️', BOOKSET: '💰',
  };
  return icons[action] || '📋';
}

function formatActionData(action) {
  const d = action.data || action;
  if (typeof d === 'string') return d.slice(0, 80);
  if (d.message) return d.message.slice(0, 80);
  if (d.reasoning) return d.reasoning.slice(0, 80);
  if (d.team) return `${d.team} @ ${d.odds || '?'} ₹${d.stake || d.filled_stake || '?'}`;
  if (d.guaranteed_profit) return `Guaranteed ₹${d.guaranteed_profit}`;
  if (d.reason) return d.reason;
  return JSON.stringify(d).slice(0, 70);
}

const styles = {
  disabled: { color: 'var(--text-dim)', fontSize: 11, textAlign: 'center', padding: 20 },
  banner: {
    display: 'flex', justifyContent: 'space-between', alignItems: 'center',
    padding: '8px 10px', borderRadius: 'var(--radius-md)', border: '1px solid',
    background: 'var(--bg-card)', marginBottom: 10,
  },
  bannerLeft: { display: 'flex', gap: 8, alignItems: 'center' },
  stateLabel: { fontFamily: 'var(--font-display)', fontSize: 16, fontWeight: 800, letterSpacing: 1 },
  mode: { fontSize: 9, color: 'var(--text-dim)', letterSpacing: 1 },
  controls: { display: 'flex', gap: 6 },
  btn: {
    background: 'transparent', border: '1px solid', borderRadius: 4,
    padding: '4px 10px', fontSize: 10, fontWeight: 700, cursor: 'pointer',
    fontFamily: 'var(--font-mono)', letterSpacing: 1,
  },
  metricsRow: { display: 'flex', gap: 8, marginBottom: 8 },
  metric: { flex: 1 },
  metricLabel: { fontSize: 8, color: 'var(--text-dim)', letterSpacing: 1, marginBottom: 2 },
  metricValue: { fontSize: 14, fontWeight: 700 },
  exchangeRow: {
    display: 'flex', gap: 8, alignItems: 'center', marginBottom: 8,
    padding: '4px 8px', background: 'var(--bg-card)', borderRadius: 4, fontSize: 10,
  },
  exchangeLabel: { fontSize: 8, color: 'var(--text-dim)', letterSpacing: 1 },
  exchangeValue: { flex: 1, color: 'var(--text-primary)', fontWeight: 600 },
  exchangePnl: { fontWeight: 700 },
  exchangeOrders: { color: 'var(--text-dim)' },
  riskRow: { display: 'flex', gap: 8, marginBottom: 8 },
  riskMeter: { flex: 1 },
  riskMeterLabel: { display: 'flex', justifyContent: 'space-between', fontSize: 9, color: 'var(--text-secondary)', marginBottom: 3 },
  riskTrack: { height: 4, background: 'var(--bg-base)', borderRadius: 2 },
  riskBar: { height: '100%', borderRadius: 2, transition: 'width 0.5s ease' },
  circuitBreaker: {
    display: 'flex', justifyContent: 'space-between', alignItems: 'center',
    padding: '8px 10px', borderRadius: 4, background: 'rgba(255,60,60,0.08)',
    border: '1px solid var(--red)', marginBottom: 8, fontSize: 11, color: 'var(--red)',
  },
  positions: { marginBottom: 8 },
  sectionLabel: {
    fontSize: 8, color: 'var(--text-dim)', letterSpacing: 2, marginBottom: 4,
    display: 'flex', justifyContent: 'space-between', alignItems: 'center',
  },
  liveDot: { color: 'var(--green)', fontSize: 9, fontWeight: 700, letterSpacing: 0 },
  positionRow: {
    display: 'flex', justifyContent: 'space-between', alignItems: 'center',
    padding: '3px 6px', background: 'var(--bg-card)', borderRadius: 4, marginBottom: 2,
  },
  posTeam: { fontSize: 11, fontWeight: 600, flex: 1 },
  posStake: { fontSize: 11, color: 'var(--text-secondary)', marginRight: 10 },
  posPnl: { fontSize: 11, fontWeight: 700, marginRight: 10 },
  posStatus: { fontSize: 9, letterSpacing: 1, fontWeight: 700 },
  statsRow: { display: 'flex', gap: 6, marginBottom: 8 },
  statBadge: { display: 'flex', flexDirection: 'column', alignItems: 'center', flex: 1 },
  statBadgeLabel: { fontSize: 8, color: 'var(--text-dim)', letterSpacing: 1 },
  statBadgeValue: { fontSize: 16, fontWeight: 700 },
  actionLog: { borderTop: '1px solid var(--border)', paddingTop: 6, maxHeight: 200, overflow: 'auto' },
  actionRow: {
    display: 'flex', justifyContent: 'space-between', alignItems: 'center',
    padding: '3px 0', borderBottom: '1px solid var(--bg-hover)',
  },
  actionType: { fontSize: 10, fontWeight: 600, color: 'var(--cyan)', minWidth: 130 },
  actionData: { fontSize: 10, color: 'var(--text-secondary)', flex: 1, overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap', margin: '0 8px' },
  actionTime: { fontSize: 9, color: 'var(--text-dim)', minWidth: 60, textAlign: 'right' },
};
