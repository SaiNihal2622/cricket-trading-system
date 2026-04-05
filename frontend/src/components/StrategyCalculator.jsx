import React, { useState } from 'react';
import { calcLossCut, calcBookset, calcSession } from '../services/api';
import { useStore } from '../store/useStore';
import Panel from './Panel';

const TABS = ['LOSS CUT', 'BOOKSET', 'SESSION'];

export default function StrategyCalculator() {
  const [tab, setTab] = useState(0);
  const [result, setResult] = useState(null);
  const [loading, setLoading] = useState(false);
  const { matchState, odds, stakeConfig, setStakeConfig } = useStore();

  // Loss cut form
  const [lcForm, setLcForm] = useState({
    stake: 1000, entryOdds: 1.85, currentOdds: 1.85,
    wickets: matchState.total_wickets, isWicket: false
  });

  // Bookset form
  const [bsForm, setBsForm] = useState({
    oddsA: odds.team_a_odds || 1.85,
    oddsB: odds.team_b_odds || 2.1,
    stake: 1000
  });

  // Session form
  const [sessForm, setSessForm] = useState({
    phase: 'powerplay', over: matchState.overs || 0,
    runs: matchState.total_runs || 0, wickets: matchState.total_wickets || 0,
    team: matchState.team_a || ''
  });

  const handleLossCut = async () => {
    setLoading(true);
    try {
      const res = await calcLossCut({
        stake: lcForm.stake, entry_odds: lcForm.entryOdds,
        current_team_odds: lcForm.currentOdds,
        current_over: matchState.overs || 0,
        wickets_fallen: lcForm.wickets,
        run_rate: matchState.run_rate || 0,
        required_run_rate: matchState.required_run_rate || 0,
        is_wicket: lcForm.isWicket,
        win_probability: 0.5,
      });
      setResult({ type: 'losscut', data: res.data });
    } catch {}
    setLoading(false);
  };

  const handleBookset = async () => {
    setLoading(true);
    try {
      const res = await calcBookset(bsForm.oddsA, bsForm.oddsB, bsForm.stake);
      setResult({ type: 'bookset', data: res.data });
    } catch {}
    setLoading(false);
  };

  const handleSession = async () => {
    setLoading(true);
    try {
      const res = await calcSession({
        phase: sessForm.phase, current_over: sessForm.over,
        current_runs: sessForm.runs, current_wickets: sessForm.wickets,
        batting_team: sessForm.team,
      });
      setResult({ type: 'session', data: res.data });
    } catch {}
    setLoading(false);
  };

  return (
    <Panel title="STRATEGY CALCULATOR" accent="var(--purple)">
      {/* Tabs */}
      <div style={styles.tabs}>
        {TABS.map((t, i) => (
          <button key={t} style={{ ...styles.tab, ...(tab === i ? styles.tabActive : {}) }} onClick={() => { setTab(i); setResult(null); }}>
            {t}
          </button>
        ))}
      </div>

      {/* Loss Cut */}
      {tab === 0 && (
        <div style={styles.form}>
          <Row2>
            <Field label="Stake (₹)" value={lcForm.stake} onChange={v => setLcForm(f => ({ ...f, stake: v }))} />
            <Field label="Entry Odds" value={lcForm.entryOdds} onChange={v => setLcForm(f => ({ ...f, entryOdds: v }))} step="0.01" />
          </Row2>
          <Row2>
            <Field label="Current Odds" value={lcForm.currentOdds} onChange={v => setLcForm(f => ({ ...f, currentOdds: v }))} step="0.01" />
            <Field label="Wickets" value={lcForm.wickets} onChange={v => setLcForm(f => ({ ...f, wickets: v }))} />
          </Row2>
          <CalcBtn onClick={handleLossCut} loading={loading} color="var(--red)">CALCULATE HEDGE</CalcBtn>

          {result?.type === 'losscut' && (
            <div style={styles.result}>
              <ResultRow label="Triggered" value={result.data.triggered ? 'YES' : 'NO'} color={result.data.triggered ? 'var(--red)' : 'var(--green)'} />
              {result.data.triggered && <>
                <ResultRow label="Hedge Amount" value={`₹${result.data.hedge_amount?.toFixed(2)}`} highlight />
                <ResultRow label="Hedge Profit" value={`₹${result.data.hedge_profit?.toFixed(2)}`} color="var(--green)" />
                <ResultRow label="Urgency" value={result.data.urgency} color="var(--amber)" />
                <ResultRow label="Reason" value={result.data.trigger_reason} small />
              </>}
            </div>
          )}
        </div>
      )}

      {/* Bookset */}
      {tab === 1 && (
        <div style={styles.form}>
          <Row2>
            <Field label="Odds A" value={bsForm.oddsA} onChange={v => setBsForm(f => ({ ...f, oddsA: v }))} step="0.01" />
            <Field label="Odds B" value={bsForm.oddsB} onChange={v => setBsForm(f => ({ ...f, oddsB: v }))} step="0.01" />
          </Row2>
          <Field label="Total Stake (₹)" value={bsForm.stake} onChange={v => setBsForm(f => ({ ...f, stake: v }))} />
          <CalcBtn onClick={handleBookset} loading={loading} color="var(--amber)">CALCULATE BOOKSET</CalcBtn>

          {result?.type === 'bookset' && (
            <div style={styles.result}>
              <ResultRow label="Stake Team A" value={`₹${result.data.stake_a?.toFixed(2)}`} />
              <ResultRow label="Stake Team B" value={`₹${result.data.stake_b?.toFixed(2)}`} />
              <ResultRow label="Guaranteed Profit" value={`₹${result.data.guaranteed_profit?.toFixed(2)}`} highlight color={result.data.guaranteed_profit >= 0 ? 'var(--green)' : 'var(--red)'} />
              <ResultRow label="Profit %" value={`${result.data.profit_percentage?.toFixed(2)}%`} />
              <ResultRow label="Overround" value={`${(result.data.overround * 100)?.toFixed(2)}%`} color={result.data.overround < 1 ? 'var(--green)' : 'var(--text-secondary)'} />
              {result.data.is_profitable && <div style={styles.arbAlert}>⚡ ARB OPPORTUNITY DETECTED</div>}
            </div>
          )}
        </div>
      )}

      {/* Session */}
      {tab === 2 && (
        <div style={styles.form}>
          <div style={styles.selectRow}>
            {['powerplay', 'total'].map(p => (
              <button key={p} style={{ ...styles.phaseBtn, ...(sessForm.phase === p ? styles.phaseBtnActive : {}) }}
                onClick={() => setSessForm(f => ({ ...f, phase: p }))}>
                {p.toUpperCase()}
              </button>
            ))}
          </div>
          <Row2>
            <Field label="Current Over" value={sessForm.over} onChange={v => setSessForm(f => ({ ...f, over: v }))} step="0.1" />
            <Field label="Current Runs" value={sessForm.runs} onChange={v => setSessForm(f => ({ ...f, runs: v }))} />
          </Row2>
          <Field label="Wickets" value={sessForm.wickets} onChange={v => setSessForm(f => ({ ...f, wickets: v }))} />
          <CalcBtn onClick={handleSession} loading={loading} color="var(--blue)">PREDICT SESSION</CalcBtn>

          {result?.type === 'session' && (
            <div style={styles.result}>
              <ResultRow label="Predicted Runs" value={result.data.predicted_runs?.toFixed(1)} highlight />
              <ResultRow label="CI (95%)" value={`${result.data.ci_low?.toFixed(0)} – ${result.data.ci_high?.toFixed(0)}`} />
              <ResultRow label="P(Over)" value={`${result.data.prob_over?.toFixed(1)}%`} color="var(--green)" />
              <ResultRow label="P(Under)" value={`${result.data.prob_under?.toFixed(1)}%`} color="var(--red)" />
              <ResultRow label="Line" value={result.data.recommended_line} />
              <ResultRow label="Signal" value={result.data.value_signal}
                color={result.data.value_signal === 'OVER' ? 'var(--green)' : result.data.value_signal === 'UNDER' ? 'var(--red)' : 'var(--text-secondary)'} />
            </div>
          )}
        </div>
      )}
    </Panel>
  );
}

function Field({ label, value, onChange, step = '1' }) {
  return (
    <div style={styles.field}>
      <label style={styles.fieldLabel}>{label}</label>
      <input style={styles.input} type="number" step={step} value={value}
        onChange={e => onChange(parseFloat(e.target.value) || 0)} />
    </div>
  );
}

function Row2({ children }) {
  return <div style={{ display: 'flex', gap: 8 }}>{React.Children.map(children, c => React.cloneElement(c, { style: { flex: 1 } }))}</div>;
}

function CalcBtn({ onClick, loading, color, children }) {
  return (
    <button style={{ ...styles.calcBtn, background: color, opacity: loading ? 0.7 : 1 }} onClick={onClick} disabled={loading}>
      {loading ? 'CALCULATING…' : children}
    </button>
  );
}

function ResultRow({ label, value, highlight, small, color }) {
  return (
    <div style={styles.resultRow}>
      <span style={{ fontSize: small ? 10 : 11, color: 'var(--text-secondary)' }}>{label}</span>
      <span style={{ fontSize: small ? 10 : 12, fontWeight: highlight ? 700 : 500, color: color || 'var(--text-primary)' }}>{value}</span>
    </div>
  );
}

const styles = {
  tabs: { display: 'flex', gap: 2, marginBottom: 10, background: 'var(--bg-base)', borderRadius: 'var(--radius-sm)', padding: 2 },
  tab: { flex: 1, padding: '5px 0', fontSize: 10, fontFamily: 'var(--font-mono)', background: 'transparent', border: 'none', color: 'var(--text-secondary)', cursor: 'pointer', borderRadius: 'var(--radius-sm)', letterSpacing: 1 },
  tabActive: { background: 'var(--bg-panel)', color: 'var(--text-primary)', fontWeight: 600 },
  form: { display: 'flex', flexDirection: 'column', gap: 6 },
  field: { display: 'flex', flexDirection: 'column', gap: 3 },
  fieldLabel: { fontSize: 9, color: 'var(--text-dim)', letterSpacing: 1 },
  input: {
    background: 'var(--bg-base)', border: '1px solid var(--border)', borderRadius: 'var(--radius-sm)',
    padding: '5px 8px', color: 'var(--text-primary)', fontFamily: 'var(--font-mono)', fontSize: 12, outline: 'none',
    width: '100%',
  },
  calcBtn: {
    width: '100%', padding: '7px', border: 'none', borderRadius: 'var(--radius-sm)',
    color: '#000', fontWeight: 700, fontSize: 11, letterSpacing: 1,
    cursor: 'pointer', fontFamily: 'var(--font-mono)', marginTop: 2,
  },
  result: { background: 'var(--bg-base)', borderRadius: 'var(--radius-sm)', padding: '8px 10px', display: 'flex', flexDirection: 'column', gap: 4 },
  resultRow: { display: 'flex', justifyContent: 'space-between', alignItems: 'center' },
  arbAlert: { marginTop: 4, textAlign: 'center', color: 'var(--green)', fontSize: 11, fontWeight: 700, letterSpacing: 1 },
  selectRow: { display: 'flex', gap: 4 },
  phaseBtn: { flex: 1, padding: '4px', background: 'var(--bg-base)', border: '1px solid var(--border)', borderRadius: 'var(--radius-sm)', color: 'var(--text-secondary)', fontSize: 10, cursor: 'pointer', fontFamily: 'var(--font-mono)' },
  phaseBtnActive: { borderColor: 'var(--blue)', color: 'var(--blue)', background: '#003344' },
};
