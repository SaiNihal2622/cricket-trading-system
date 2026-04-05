/**
 * TradeApproval — Semi-auto mode overlay.
 *
 * Shows pending trade proposals as a notification stack.
 * User has 30s to Accept or Reject each trade.
 * In autopilot mode, this component is hidden.
 */
import React, { useState, useEffect, useCallback, useRef } from 'react';
import axios from 'axios';

const API = process.env.REACT_APP_API_URL || '';

export default function TradeApproval({ isAutopilot }) {
  const [approvals, setApprovals] = useState([]);
  const [timers, setTimers]       = useState({});
  const intervalRef = useRef(null);

  const fetchApprovals = useCallback(async () => {
    try {
      const res = await axios.get(`${API}/api/v1/agent/pending-approvals`);
      const incoming = res.data.approvals || [];

      setApprovals(prev => {
        // Merge: keep existing with timers, add new ones
        const existingIds = new Set(prev.map(a => a.approval_id));
        const newOnes = incoming.filter(a => !existingIds.has(a.approval_id));

        // Start timers for new approvals
        newOnes.forEach(a => {
          setTimers(t => ({ ...t, [a.approval_id]: 30 }));
        });

        // Remove approvals no longer pending
        const incomingIds = new Set(incoming.map(a => a.approval_id));
        const filtered = prev.filter(a => incomingIds.has(a.approval_id));
        return [...filtered, ...newOnes];
      });
    } catch {}
  }, []);

  // Countdown timers
  useEffect(() => {
    const tick = setInterval(() => {
      setTimers(prev => {
        const updated = { ...prev };
        Object.keys(updated).forEach(id => {
          if (updated[id] > 0) updated[id]--;
          else {
            // Timer expired — remove from list
            setApprovals(a => a.filter(x => x.approval_id !== id));
            delete updated[id];
          }
        });
        return updated;
      });
    }, 1000);
    return () => clearInterval(tick);
  }, []);

  useEffect(() => {
    if (isAutopilot) {
      setApprovals([]);
      return;
    }
    fetchApprovals();
    intervalRef.current = setInterval(fetchApprovals, 3000);
    return () => clearInterval(intervalRef.current);
  }, [isAutopilot, fetchApprovals]);

  const handleAction = async (approvalId, action) => {
    try {
      await axios.post(`${API}/api/v1/agent/${action}/${approvalId}`);
    } catch {}
    setApprovals(prev => prev.filter(a => a.approval_id !== approvalId));
    setTimers(prev => { const t = { ...prev }; delete t[approvalId]; return t; });
  };

  if (isAutopilot || approvals.length === 0) return null;

  return (
    <div style={styles.container}>
      <div style={styles.header}>
        ⚡ Trade Approvals ({approvals.length})
      </div>
      {approvals.map(a => (
        <ApprovalCard
          key={a.approval_id}
          approval={a}
          timeLeft={timers[a.approval_id] ?? 30}
          onApprove={() => handleAction(a.approval_id, 'approve')}
          onReject={() => handleAction(a.approval_id, 'reject')}
        />
      ))}
    </div>
  );
}

function ApprovalCard({ approval, timeLeft, onApprove, onReject }) {
  const type       = approval.type || 'TRADE';
  const label      = approval.label || approval.team || '';
  const side       = approval.side || '';
  const stake      = approval.stake || 0;
  const confidence = approval.confidence || 0;
  const reasoning  = approval.reasoning || '';
  const timerPct   = (timeLeft / 30) * 100;

  const typeColors = {
    ENTRY:   { bg: '#1a2d1a', border: '#22c55e', badge: '#22c55e' },
    SESSION: { bg: '#1a1f2d', border: '#3b82f6', badge: '#3b82f6' },
    default: { bg: '#2d1a1a', border: '#f97316', badge: '#f97316' },
  };
  const colors = typeColors[type] || typeColors.default;

  return (
    <div style={{ ...styles.card, background: colors.bg, borderColor: colors.border }}>
      {/* Timer bar */}
      <div style={styles.timerTrack}>
        <div style={{
          ...styles.timerBar,
          width: `${timerPct}%`,
          background: timeLeft > 10 ? '#22c55e' : '#ef4444',
        }} />
      </div>

      <div style={styles.cardRow}>
        <span style={{ ...styles.badge, background: colors.badge }}>{type}</span>
        <span style={styles.timer}>{timeLeft}s</span>
      </div>

      <div style={styles.tradeInfo}>
        <span style={styles.teamName}>
          {type === 'SESSION' ? `${label} — ${side?.toUpperCase()}` : `BACK ${label}`}
        </span>
        <span style={styles.stakeAmt}>₹{stake.toFixed(0)}</span>
      </div>

      <div style={styles.confidence}>
        Confidence: <strong>{(confidence * 100).toFixed(0)}%</strong>
      </div>

      {reasoning && (
        <div style={styles.reasoning}>{reasoning.substring(0, 120)}</div>
      )}

      <div style={styles.btnRow}>
        <button style={styles.acceptBtn} onClick={onApprove}>
          ✓ ACCEPT
        </button>
        <button style={styles.rejectBtn} onClick={onReject}>
          ✕ REJECT
        </button>
      </div>
    </div>
  );
}

const styles = {
  container: {
    position: 'fixed',
    bottom: 16,
    right: 16,
    width: 320,
    zIndex: 1000,
    display: 'flex',
    flexDirection: 'column',
    gap: 8,
    maxHeight: '80vh',
    overflowY: 'auto',
  },
  header: {
    background: '#1e1e2e',
    border: '1px solid #333',
    borderRadius: 6,
    padding: '6px 12px',
    fontSize: 12,
    color: '#aaa',
    fontWeight: 600,
  },
  card: {
    border: '1px solid',
    borderRadius: 8,
    padding: '10px 12px',
    display: 'flex',
    flexDirection: 'column',
    gap: 6,
    boxShadow: '0 4px 12px rgba(0,0,0,0.4)',
  },
  timerTrack: {
    height: 3,
    background: '#333',
    borderRadius: 2,
    overflow: 'hidden',
    marginBottom: 4,
  },
  timerBar: {
    height: '100%',
    borderRadius: 2,
    transition: 'width 1s linear, background 0.3s',
  },
  cardRow: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  badge: {
    borderRadius: 4,
    padding: '2px 6px',
    fontSize: 10,
    fontWeight: 700,
    color: '#fff',
  },
  timer: {
    fontSize: 11,
    color: '#888',
  },
  tradeInfo: {
    display: 'flex',
    justifyContent: 'space-between',
    alignItems: 'center',
  },
  teamName: {
    fontSize: 14,
    fontWeight: 700,
    color: '#e2e8f0',
  },
  stakeAmt: {
    fontSize: 14,
    fontWeight: 700,
    color: '#22c55e',
  },
  confidence: {
    fontSize: 11,
    color: '#94a3b8',
  },
  reasoning: {
    fontSize: 11,
    color: '#64748b',
    lineHeight: 1.4,
    fontStyle: 'italic',
  },
  btnRow: {
    display: 'flex',
    gap: 8,
    marginTop: 4,
  },
  acceptBtn: {
    flex: 1,
    padding: '7px 0',
    background: '#16a34a',
    color: '#fff',
    border: 'none',
    borderRadius: 5,
    cursor: 'pointer',
    fontWeight: 700,
    fontSize: 12,
  },
  rejectBtn: {
    flex: 1,
    padding: '7px 0',
    background: '#dc2626',
    color: '#fff',
    border: 'none',
    borderRadius: 5,
    cursor: 'pointer',
    fontWeight: 700,
    fontSize: 12,
  },
};
