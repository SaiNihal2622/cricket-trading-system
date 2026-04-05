import React from 'react';
import { useStore } from '../store/useStore';
import Panel from './Panel';

export default function Scoreboard() {
  const { matchState: m } = useStore();

  const completedOvers = Math.floor(m.overs || 0);
  const progressPct = ((m.overs || 0) / 20) * 100;

  return (
    <Panel title="LIVE SCORECARD" accent="var(--cyan)">
      {/* Teams & Score */}
      <div style={styles.teamsRow}>
        <div style={styles.team}>
          <span style={styles.teamName}>{m.team_a}</span>
          <span style={styles.innings}>INN {m.innings}</span>
        </div>
        <div style={styles.score}>
          <span style={styles.scoreMain}>{m.total_runs}<span style={styles.wkts}>/{m.total_wickets}</span></span>
          <span style={styles.overs}>({m.overs?.toFixed(1)} ov)</span>
        </div>
      </div>

      {/* Overs progress bar */}
      <div style={styles.progressTrack}>
        <div style={{ ...styles.progressBar, width: `${progressPct}%` }} />
        {[6, 10, 15].map(v => (
          <div key={v} style={{ ...styles.progressMark, left: `${(v / 20) * 100}%` }} />
        ))}
      </div>
      <div style={styles.overLabels}>
        <span>PP</span><span>10</span><span>15</span><span>20</span>
      </div>

      {/* Run rates */}
      <div style={styles.statsRow}>
        <Stat label="CRR" value={m.run_rate?.toFixed(2)} color="var(--cyan)" />
        {m.required_run_rate > 0 && <Stat label="RRR" value={m.required_run_rate?.toFixed(2)} color="var(--amber)" />}
        {m.target > 0 && <Stat label="TARGET" value={m.target} color="var(--text-primary)" />}
        {m.target > 0 && <Stat label="NEED" value={Math.max(0, m.target - m.total_runs)} color="var(--red)" />}
        {m.powerplay_runs > 0 && m.overs <= 6 && <Stat label="PP RUNS" value={m.powerplay_runs} color="var(--purple)" />}
      </div>

      <div style={styles.divider} />

      {/* Batsmen */}
      <div style={styles.sectionLabel}>AT CREASE</div>
      <BatsmanRow name={m.current_batsman_1} runs={m.batsman_1_runs} balls={m.batsman_1_balls} active />
      <BatsmanRow name={m.current_batsman_2} runs={m.batsman_2_runs} balls={m.batsman_2_balls} />

      <div style={styles.divider} />

      {/* Bowler */}
      <div style={styles.sectionLabel}>BOWLING</div>
      <div style={styles.bowlerRow}>
        <span style={styles.playerName}>{m.current_bowler || '—'}</span>
        {m.bowler_runs !== undefined && (
          <span style={styles.playerStats}>{m.bowler_wickets}w / {m.bowler_runs}r</span>
        )}
      </div>

      {/* Last ball */}
      {m.last_ball && (
        <div style={styles.lastBallRow}>
          <span style={styles.lastBallLabel}>LAST BALL</span>
          <LastBall ball={m.last_ball} />
        </div>
      )}
    </Panel>
  );
}

function Stat({ label, value, color }) {
  return (
    <div style={styles.stat}>
      <span style={styles.statLabel}>{label}</span>
      <span style={{ ...styles.statValue, color }}>{value ?? '—'}</span>
    </div>
  );
}

function BatsmanRow({ name, runs, balls, active }) {
  const sr = balls > 0 ? ((runs / balls) * 100).toFixed(0) : '—';
  return (
    <div style={{ ...styles.batsmanRow, borderLeft: active ? '2px solid var(--green)' : '2px solid transparent' }}>
      <span style={styles.playerName}>{name || '—'}</span>
      <span style={styles.playerStats}>
        <span style={{ color: 'var(--text-primary)', fontWeight: 600 }}>{runs ?? 0}</span>
        <span style={{ color: 'var(--text-dim)' }}>({balls ?? 0})</span>
        <span style={{ color: 'var(--text-secondary)', marginLeft: 6 }}>SR {sr}</span>
      </span>
    </div>
  );
}

function LastBall({ ball }) {
  const colorMap = { W: 'var(--red)', '4': 'var(--green)', '6': 'var(--purple)', '0': 'var(--text-dim)' };
  const color = colorMap[ball] || 'var(--text-primary)';
  return <span style={{ ...styles.lastBall, color, borderColor: color }}>{ball}</span>;
}

const styles = {
  teamsRow: { display: 'flex', justifyContent: 'space-between', alignItems: 'flex-start', marginBottom: 8 },
  team: { display: 'flex', flexDirection: 'column' },
  teamName: { fontFamily: 'var(--font-display)', fontSize: 16, fontWeight: 700, color: 'var(--text-primary)' },
  innings: { fontSize: 9, color: 'var(--text-dim)', letterSpacing: 1 },
  score: { display: 'flex', flexDirection: 'column', alignItems: 'flex-end' },
  scoreMain: { fontFamily: 'var(--font-display)', fontSize: 32, fontWeight: 800, color: 'var(--cyan)', lineHeight: 1 },
  wkts: { fontSize: 20, color: 'var(--text-secondary)' },
  overs: { fontSize: 11, color: 'var(--text-dim)' },

  progressTrack: { position: 'relative', height: 4, background: 'var(--bg-base)', borderRadius: 2, margin: '6px 0 2px' },
  progressBar: { height: '100%', background: 'var(--cyan)', borderRadius: 2, transition: 'width 0.5s ease' },
  progressMark: { position: 'absolute', top: -2, width: 1, height: 8, background: 'var(--border-bright)' },
  overLabels: { display: 'flex', justifyContent: 'space-between', fontSize: 9, color: 'var(--text-dim)', marginBottom: 8 },

  statsRow: { display: 'flex', gap: 12, flexWrap: 'wrap', marginBottom: 8 },
  stat: { display: 'flex', flexDirection: 'column' },
  statLabel: { fontSize: 9, color: 'var(--text-dim)', letterSpacing: 1 },
  statValue: { fontSize: 15, fontWeight: 700 },

  divider: { height: 1, background: 'var(--border)', margin: '6px 0' },
  sectionLabel: { fontSize: 9, color: 'var(--text-dim)', letterSpacing: 2, marginBottom: 4 },

  batsmanRow: { display: 'flex', justifyContent: 'space-between', alignItems: 'center', padding: '3px 6px', marginBottom: 2 },
  playerName: { fontSize: 12, color: 'var(--text-primary)', fontWeight: 500 },
  playerStats: { fontSize: 12, display: 'flex', gap: 4, alignItems: 'center' },
  bowlerRow: { display: 'flex', justifyContent: 'space-between', padding: '2px 6px' },

  lastBallRow: { display: 'flex', alignItems: 'center', gap: 8, marginTop: 6 },
  lastBallLabel: { fontSize: 9, color: 'var(--text-dim)', letterSpacing: 1 },
  lastBall: {
    display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
    width: 28, height: 28, borderRadius: '50%', border: '1px solid',
    fontWeight: 700, fontSize: 13,
  },
};
