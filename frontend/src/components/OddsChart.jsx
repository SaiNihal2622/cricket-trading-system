import React from 'react';
import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer, ReferenceLine } from 'recharts';
import { useStore } from '../store/useStore';
import Panel from './Panel';

export default function OddsChart() {
  const { oddsHistory, matchState } = useStore();

  const data = [...oddsHistory].reverse().map((o, i) => ({
    t: i,
    a: parseFloat(o.team_a_odds?.toFixed(3)),
    b: parseFloat(o.team_b_odds?.toFixed(3)),
    time: o.timestamp ? new Date(o.timestamp).toLocaleTimeString() : '',
  }));

  return (
    <Panel title="ODDS MOVEMENT" accent="var(--blue)">
      {data.length < 2 ? (
        <div style={styles.empty}>Awaiting odds data…</div>
      ) : (
        <ResponsiveContainer width="100%" height={140}>
          <LineChart data={data} margin={{ top: 4, right: 4, bottom: 0, left: -20 }}>
            <XAxis dataKey="t" hide />
            <YAxis domain={['auto', 'auto']} tick={{ fill: '#3d5c78', fontSize: 9 }} width={36} />
            <Tooltip content={<CustomTooltip teamA={matchState.team_a} teamB={matchState.team_b} />} />
            <Line
              type="monotone" dataKey="a" stroke="var(--blue)"
              strokeWidth={1.5} dot={false} name="Team A"
            />
            <Line
              type="monotone" dataKey="b" stroke="var(--purple)"
              strokeWidth={1.5} dot={false} name="Team B"
            />
          </LineChart>
        </ResponsiveContainer>
      )}

      <div style={styles.legend}>
        <LegendItem color="var(--blue)" label={matchState.team_a?.split(' ').pop() || 'Team A'} />
        <LegendItem color="var(--purple)" label={matchState.team_b?.split(' ').pop() || 'Team B'} />
      </div>
    </Panel>
  );
}

function CustomTooltip({ active, payload, teamA, teamB }) {
  if (!active || !payload?.length) return null;
  return (
    <div style={styles.tooltip}>
      <div style={{ color: 'var(--blue)', fontSize: 11 }}>{teamA}: {payload[0]?.value}</div>
      <div style={{ color: 'var(--purple)', fontSize: 11 }}>{teamB}: {payload[1]?.value}</div>
    </div>
  );
}

function LegendItem({ color, label }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
      <div style={{ width: 16, height: 2, background: color }} />
      <span style={{ fontSize: 10, color: 'var(--text-secondary)' }}>{label}</span>
    </div>
  );
}

const styles = {
  empty: { height: 140, display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--text-dim)', fontSize: 11 },
  legend: { display: 'flex', gap: 16, justifyContent: 'center', marginTop: 4 },
  tooltip: { background: 'var(--bg-card)', border: '1px solid var(--border)', padding: '6px 10px', borderRadius: 4 },
};
