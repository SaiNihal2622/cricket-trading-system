import React, { useState } from 'react';
import { useStore } from '../store/useStore';
import { updateOdds } from '../services/api';
import Panel from './Panel';

export default function OddsPanel() {
  const { odds, matchState } = useStore();
  const [oddsA, setOddsA] = useState('');
  const [oddsB, setOddsB] = useState('');
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState('');

  const handleSubmit = async () => {
    const a = parseFloat(oddsA);
    const b = parseFloat(oddsB);
    if (isNaN(a) || isNaN(b) || a <= 1 || b <= 1) {
      setError('Odds must be > 1');
      return;
    }
    setError('');
    setSaving(true);
    try {
      await updateOdds(matchState.match_id || 1, a, b);
    } catch (e) {
      setError('Failed to update odds');
    } finally {
      setSaving(false);
    }
  };

  const impliedA = odds.team_a_odds > 0 ? (100 / odds.team_a_odds).toFixed(1) : '—';
  const impliedB = odds.team_b_odds > 0 ? (100 / odds.team_b_odds).toFixed(1) : '—';
  const overround = odds.overround ? (odds.overround * 100).toFixed(2) : '—';

  return (
    <Panel title="ODDS TERMINAL" accent="var(--amber)">
      {/* Current odds display */}
      <div style={styles.oddsDisplay}>
        <OddsCard
          team={matchState.team_a}
          odds={odds.team_a_odds}
          implied={impliedA}
          color="var(--blue)"
        />
        <div style={styles.vs}>VS</div>
        <OddsCard
          team={matchState.team_b}
          odds={odds.team_b_odds}
          implied={impliedB}
          color="var(--purple)"
          align="right"
        />
      </div>

      {/* Overround indicator */}
      <div style={styles.overroundRow}>
        <span style={styles.orLabel}>OVERROUND</span>
        <span style={{
          ...styles.orValue,
          color: parseFloat(overround) < 100 ? 'var(--green)' : 'var(--amber)'
        }}>
          {overround}%
        </span>
        {parseFloat(overround) < 100 && (
          <span style={styles.arbBadge}>ARB OPPORTUNITY</span>
        )}
      </div>

      <div style={styles.divider} />

      {/* Manual input */}
      <div style={styles.inputLabel}>UPDATE ODDS</div>
      <div style={styles.inputRow}>
        <input
          style={styles.input}
          placeholder={`${matchState.team_a?.split(' ')[0]} odds`}
          value={oddsA}
          onChange={e => setOddsA(e.target.value)}
          type="number"
          step="0.01"
          min="1.01"
        />
        <input
          style={styles.input}
          placeholder={`${matchState.team_b?.split(' ')[0]} odds`}
          value={oddsB}
          onChange={e => setOddsB(e.target.value)}
          type="number"
          step="0.01"
          min="1.01"
        />
        <button
          style={{ ...styles.btn, opacity: saving ? 0.6 : 1 }}
          onClick={handleSubmit}
          disabled={saving}
        >
          {saving ? '...' : 'SET'}
        </button>
      </div>
      {error && <div style={styles.error}>{error}</div>}

      {odds.timestamp && (
        <div style={styles.updatedAt}>
          Updated {new Date(odds.timestamp).toLocaleTimeString()}
        </div>
      )}
    </Panel>
  );
}

function OddsCard({ team, odds, implied, color, align = 'left' }) {
  return (
    <div style={{ ...styles.oddsCard, textAlign: align }}>
      <div style={{ fontSize: 10, color: 'var(--text-dim)', letterSpacing: 1 }}>
        {team?.split(' ').map(w => w[0]).join('') || '??'}
      </div>
      <div style={{ fontSize: 28, fontWeight: 800, color, fontFamily: 'var(--font-display)' }}>
        {odds?.toFixed(2) || '—'}
      </div>
      <div style={{ fontSize: 9, color: 'var(--text-secondary)' }}>{implied}% impl.</div>
    </div>
  );
}

const styles = {
  oddsDisplay: { display: 'flex', alignItems: 'center', justifyContent: 'space-between', marginBottom: 8 },
  oddsCard: { flex: 1 },
  vs: { fontFamily: 'var(--font-display)', fontSize: 16, color: 'var(--text-dim)', padding: '0 8px' },
  overroundRow: { display: 'flex', alignItems: 'center', gap: 8, marginBottom: 8 },
  orLabel: { fontSize: 9, color: 'var(--text-dim)', letterSpacing: 1 },
  orValue: { fontSize: 14, fontWeight: 700 },
  arbBadge: { fontSize: 9, background: 'var(--green-dim)', color: 'var(--green)', padding: '2px 6px', borderRadius: 3, letterSpacing: 1 },
  divider: { height: 1, background: 'var(--border)', margin: '8px 0' },
  inputLabel: { fontSize: 9, color: 'var(--text-dim)', letterSpacing: 2, marginBottom: 6 },
  inputRow: { display: 'flex', gap: 6 },
  input: {
    flex: 1, background: 'var(--bg-base)', border: '1px solid var(--border)',
    borderRadius: 'var(--radius-sm)', padding: '6px 8px',
    color: 'var(--text-primary)', fontFamily: 'var(--font-mono)', fontSize: 12,
    outline: 'none',
  },
  btn: {
    background: 'var(--amber)', color: '#000', border: 'none',
    borderRadius: 'var(--radius-sm)', padding: '6px 12px',
    cursor: 'pointer', fontWeight: 700, fontSize: 11, letterSpacing: 1,
    fontFamily: 'var(--font-mono)',
  },
  error: { color: 'var(--red)', fontSize: 11, marginTop: 4 },
  updatedAt: { fontSize: 9, color: 'var(--text-dim)', marginTop: 4 },
};
