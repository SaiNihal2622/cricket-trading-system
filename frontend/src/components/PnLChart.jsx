import React from 'react';
import { AreaChart, Area, XAxis, YAxis, Tooltip, ResponsiveContainer, ReferenceLine } from 'recharts';
import { useStore } from '../store/useStore';
import Panel from './Panel';

export default function PnLChart() {
  const { pnlHistory, totalPnl } = useStore();

  const data = pnlHistory.map((p, i) => ({ t: i, pnl: parseFloat(p.pnl?.toFixed(2) || 0) }));
  const isPositive = totalPnl >= 0;
  const color = isPositive ? 'var(--green)' : 'var(--red)';

  return (
    <Panel title="P&L SIMULATION" accent={color}>
      <div style={styles.header}>
        <div>
          <div style={styles.label}>TOTAL P&L</div>
          <div style={{ ...styles.pnl, color }}>
            {isPositive ? '+' : ''}₹{totalPnl.toFixed(2)}
          </div>
        </div>
        <div style={styles.stats}>
          <MiniStat label="TRADES" value={pnlHistory.length} />
          <MiniStat label="WINS" value={pnlHistory.filter((_, i) => i > 0 && pnlHistory[i].pnl > pnlHistory[i-1].pnl).length} color="var(--green)" />
          <MiniStat label="LOSSES" value={pnlHistory.filter((_, i) => i > 0 && pnlHistory[i].pnl < pnlHistory[i-1].pnl).length} color="var(--red)" />
        </div>
      </div>

      {data.length < 2 ? (
        <div style={styles.empty}>Signals will populate P&L curve…</div>
      ) : (
        <ResponsiveContainer width="100%" height={100}>
          <AreaChart data={data} margin={{ top: 4, right: 4, bottom: 0, left: -20 }}>
            <defs>
              <linearGradient id="pnlGrad" x1="0" y1="0" x2="0" y2="1">
                <stop offset="5%" stopColor={color} stopOpacity={0.3} />
                <stop offset="95%" stopColor={color} stopOpacity={0} />
              </linearGradient>
            </defs>
            <XAxis dataKey="t" hide />
            <YAxis tick={{ fill: '#3d5c78', fontSize: 9 }} width={36} />
            <Tooltip content={<PnLTooltip />} />
            <ReferenceLine y={0} stroke="var(--border)" strokeDasharray="3 3" />
            <Area
              type="monotone" dataKey="pnl" stroke={color}
              fill="url(#pnlGrad)" strokeWidth={1.5} dot={false}
            />
          </AreaChart>
        </ResponsiveContainer>
      )}
    </Panel>
  );
}

function MiniStat({ label, value, color }) {
  return (
    <div style={{ textAlign: 'center' }}>
      <div style={{ fontSize: 9, color: 'var(--text-dim)', letterSpacing: 1 }}>{label}</div>
      <div style={{ fontSize: 13, fontWeight: 700, color: color || 'var(--text-primary)' }}>{value}</div>
    </div>
  );
}

function PnLTooltip({ active, payload }) {
  if (!active || !payload?.length) return null;
  const v = payload[0]?.value;
  return (
    <div style={{ background: 'var(--bg-card)', border: '1px solid var(--border)', padding: '4px 8px', borderRadius: 4, fontSize: 11 }}>
      <span style={{ color: v >= 0 ? 'var(--green)' : 'var(--red)' }}>
        {v >= 0 ? '+' : ''}₹{v}
      </span>
    </div>
  );
}

const styles = {
  header: { display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 8 },
  label: { fontSize: 9, color: 'var(--text-dim)', letterSpacing: 1 },
  pnl: { fontFamily: 'var(--font-display)', fontSize: 26, fontWeight: 800, lineHeight: 1 },
  stats: { display: 'flex', gap: 16 },
  empty: { height: 100, display: 'flex', alignItems: 'center', justifyContent: 'center', color: 'var(--text-dim)', fontSize: 11 },
};
