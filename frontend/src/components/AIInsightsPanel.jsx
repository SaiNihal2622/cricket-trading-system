import React, { useState, useEffect, useRef } from 'react';
import Panel from './Panel';

const LLM_FAMILIES = [
  { name: 'MIMO', model: 'NVIDIA Llama-4-Maverick', color: '#76b900', icon: '🟢' },
  { name: 'Gemini', model: 'Google 2.5 Flash', color: '#4285f4', icon: '🔵' },
  { name: 'Grok', model: 'xAI Grok-3-Mini', color: '#ff6b35', icon: '🟠' },
  { name: 'Nemotron', model: 'NVIDIA Ultra 253B', color: '#00e5ff', icon: '🟣' },
];

function generateConsensus() {
  const votes = LLM_FAMILIES.map(f => ({
    ...f,
    prediction: 0.3 + Math.random() * 0.5,
    confidence: 0.6 + Math.random() * 0.35,
    reasoning: [
      'Run rate pressure mounting, chasing team under stress',
      'Pitch favors spinners in middle overs, bowling team ahead',
      'Historical data shows 73% chase success at this stage',
      'Key batsman still crease, momentum shift likely',
      'Dew factor will make bowling harder in death overs',
      'Required rate exceeds 10, pressure on new batsmen',
    ][Math.floor(Math.random() * 6)],
  }));
  const consensus = votes.reduce((s, v) => s + v.prediction * v.confidence, 0) /
    votes.reduce((s, v) => s + v.confidence, 0);
  return { votes, consensus, agreement: 0.7 + Math.random() * 0.25 };
}

export default function AIInsightsPanel() {
  const [data, setData] = useState(generateConsensus());
  const [pulses, setPulses] = useState({});
  const [thinking, setThinking] = useState(false);

  useEffect(() => {
    const interval = setInterval(() => {
      setThinking(true);
      setTimeout(() => {
        setData(generateConsensus());
        setThinking(false);
      }, 800);
    }, 8000);
    return () => clearInterval(interval);
  }, []);

  // Pulse animation on data change
  useEffect(() => {
    const newPulses = {};
    data.votes.forEach((v, i) => { newPulses[i] = true; });
    setPulses(newPulses);
    const t = setTimeout(() => setPulses({}), 600);
    return () => clearTimeout(t);
  }, [data]);

  const consensusColor = data.consensus > 0.6 ? 'var(--green)' :
    data.consensus < 0.4 ? 'var(--red)' : 'var(--amber)';

  return (
    <Panel title="🧠 MULTI-LLM CONSENSUS" accent="var(--purple)">
      {thinking && (
        <div style={styles.thinkingBar}>
          <div style={styles.thinkingDot} />
          <span>Querying 4 AI families...</span>
        </div>
      )}

      {/* Consensus Gauge */}
      <div style={styles.consensusRow}>
        <div style={styles.gaugeContainer}>
          <svg viewBox="0 0 120 70" style={styles.gauge}>
            <defs>
              <linearGradient id="gaugeGrad" x1="0%" y1="0%" x2="100%" y2="0%">
                <stop offset="0%" stopColor="var(--red)" />
                <stop offset="50%" stopColor="var(--amber)" />
                <stop offset="100%" stopColor="var(--green)" />
              </linearGradient>
            </defs>
            <path d="M 10 60 A 50 50 0 0 1 110 60" fill="none" stroke="var(--bg-base)" strokeWidth="8" strokeLinecap="round" />
            <path d="M 10 60 A 50 50 0 0 1 110 60" fill="none" stroke="url(#gaugeGrad)" strokeWidth="8" strokeLinecap="round"
              strokeDasharray={`${data.consensus * 157} 157`}
              style={{ transition: 'stroke-dasharray 0.8s ease' }} />
            <circle cx={10 + data.consensus * 100} cy={60 - Math.sin(data.consensus * Math.PI) * 50}
              r="5" fill={consensusColor} style={{ filter: `drop-shadow(0 0 6px ${consensusColor})`, transition: 'all 0.8s ease' }} />
          </svg>
          <div style={{ ...styles.consensusValue, color: consensusColor }}>
            {(data.consensus * 100).toFixed(1)}%
          </div>
          <div style={styles.consensusLabel}>WIN PROBABILITY</div>
        </div>
        <div style={styles.agreementBox}>
          <div style={styles.agreementLabel}>AGREEMENT</div>
          <div style={{ ...styles.agreementValue, color: data.agreement > 0.85 ? 'var(--green)' : 'var(--amber)' }}>
            {(data.agreement * 100).toFixed(0)}%
          </div>
          <div style={styles.agreementBar}>
            <div style={{
              ...styles.agreementFill,
              width: `${data.agreement * 100}%`,
              background: data.agreement > 0.85 ? 'var(--green)' : 'var(--amber)',
            }} />
          </div>
        </div>
      </div>

      {/* Individual LLM Votes */}
      <div style={styles.votesGrid}>
        {data.votes.map((v, i) => (
          <div key={i} style={{
            ...styles.voteCard,
            borderColor: pulses[i] ? v.color : 'var(--border)',
            boxShadow: pulses[i] ? `0 0 12px ${v.color}33` : 'none',
            transition: 'all 0.3s ease',
          }}>
            <div style={styles.voteHeader}>
              <span style={styles.voteIcon}>{v.icon}</span>
              <span style={{ ...styles.voteName, color: v.color }}>{v.name}</span>
            </div>
            <div style={styles.voteModel}>{v.model}</div>
            <div style={styles.voteMetrics}>
              <div>
                <span style={styles.voteMetricLabel}>PRED</span>
                <span style={{ ...styles.voteMetricValue, color: v.prediction > 0.5 ? 'var(--green)' : 'var(--red)' }}>
                  {(v.prediction * 100).toFixed(0)}%
                </span>
              </div>
              <div>
                <span style={styles.voteMetricLabel}>CONF</span>
                <span style={{ ...styles.voteMetricValue, color: 'var(--cyan)' }}>
                  {(v.confidence * 100).toFixed(0)}%
                </span>
              </div>
            </div>
            <div style={styles.voteReasoning}>{v.reasoning}</div>
          </div>
        ))}
      </div>
    </Panel>
  );
}

const styles = {
  thinkingBar: {
    display: 'flex', alignItems: 'center', gap: 6, padding: '4px 8px',
    background: 'rgba(124,77,255,0.1)', borderRadius: 4, marginBottom: 8,
    fontSize: 10, color: 'var(--purple)', fontWeight: 600,
    animation: 'slideIn 0.3s ease',
  },
  thinkingDot: {
    width: 6, height: 6, borderRadius: '50%', background: 'var(--purple)',
    animation: 'pulse 0.8s ease-in-out infinite',
  },
  consensusRow: {
    display: 'flex', gap: 12, alignItems: 'center', marginBottom: 10,
  },
  gaugeContainer: { flex: 1, textAlign: 'center' },
  gauge: { width: '100%', maxWidth: 160 },
  consensusValue: {
    fontFamily: 'var(--font-display)', fontSize: 28, fontWeight: 800,
    marginTop: -12, transition: 'color 0.5s ease',
  },
  consensusLabel: { fontSize: 8, color: 'var(--text-dim)', letterSpacing: 2 },
  agreementBox: { flex: '0 0 80px', textAlign: 'center' },
  agreementLabel: { fontSize: 8, color: 'var(--text-dim)', letterSpacing: 1 },
  agreementValue: { fontSize: 20, fontWeight: 700, fontFamily: 'var(--font-display)' },
  agreementBar: { height: 3, background: 'var(--bg-base)', borderRadius: 2, marginTop: 4 },
  agreementFill: { height: '100%', borderRadius: 2, transition: 'width 0.8s ease' },
  votesGrid: { display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 6 },
  voteCard: {
    padding: '6px 8px', background: 'var(--bg-card)', borderRadius: 6,
    border: '1px solid var(--border)', transition: 'all 0.3s ease',
  },
  voteHeader: { display: 'flex', alignItems: 'center', gap: 4, marginBottom: 2 },
  voteIcon: { fontSize: 12 },
  voteName: { fontSize: 11, fontWeight: 700, fontFamily: 'var(--font-display)', letterSpacing: 0.5 },
  voteModel: { fontSize: 8, color: 'var(--text-dim)', marginBottom: 4 },
  voteMetrics: { display: 'flex', gap: 10, marginBottom: 4 },
  voteMetricLabel: { fontSize: 7, color: 'var(--text-dim)', letterSpacing: 1, marginRight: 4 },
  voteMetricValue: { fontSize: 12, fontWeight: 700 },
  voteReasoning: {
    fontSize: 9, color: 'var(--text-secondary)', lineHeight: 1.3,
    overflow: 'hidden', textOverflow: 'ellipsis', display: '-webkit-box',
    WebkitLineClamp: 2, WebkitBoxOrient: 'vertical',
  },
};