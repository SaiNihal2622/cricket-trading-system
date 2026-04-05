import React from 'react';
import { useStore } from '../store/useStore';
import Panel from './Panel';

const SENTIMENT_COLOR = { BULLISH: 'var(--green)', BEARISH: 'var(--red)', NEUTRAL: 'var(--text-secondary)' };
const SENTIMENT_ICON = { BULLISH: '▲', BEARISH: '▼', NEUTRAL: '—' };

export default function TelegramFeed() {
  const { telegramSignals } = useStore();

  return (
    <Panel title="TELEGRAM SIGNALS" accent="var(--cyan)" style={{ flex: 1, overflow: 'hidden' }}>
      <div style={styles.feed}>
        {telegramSignals.length === 0 ? (
          <div style={styles.empty}>
            <div style={styles.emptyIcon}>📡</div>
            <div>Monitoring channels…</div>
            <div style={{ fontSize: 10, color: 'var(--text-dim)', marginTop: 4 }}>
              Configure TELEGRAM_CHANNELS in .env
            </div>
          </div>
        ) : (
          telegramSignals.map((sig, i) => (
            <SignalCard key={i} sig={sig} />
          ))
        )}
      </div>
    </Panel>
  );
}

function SignalCard({ sig }) {
  const color = SENTIMENT_COLOR[sig.signal_type] || 'var(--text-secondary)';
  const icon = SENTIMENT_ICON[sig.signal_type] || '—';
  const sentiment = sig.sentiment?.toFixed(2);
  const sentimentPct = Math.abs(sig.sentiment || 0) * 100;

  return (
    <div className="animate-in" style={{ ...styles.card, borderLeftColor: color }}>
      <div style={styles.cardHeader}>
        <span style={{ color, fontSize: 12, fontWeight: 700 }}>{icon} {sig.signal_type}</span>
        <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
          {sig.is_session && <span style={styles.sessionTag}>SESSION</span>}
          {sig.is_signal && <span style={styles.signalTag}>SIGNAL</span>}
        </div>
      </div>

      <div style={styles.msgText}>{sig.raw_text?.slice(0, 120)}{sig.raw_text?.length > 120 ? '…' : ''}</div>

      <div style={styles.cardFooter}>
        <div style={styles.sentimentBar}>
          <div style={{ ...styles.sentimentFill, width: `${sentimentPct}%`, background: color }} />
        </div>
        <span style={{ color, fontSize: 10 }}>{sentiment}</span>
        <span style={styles.channel}>#{sig.channel?.slice(-8) || 'chan'}</span>
        <span style={styles.time}>{sig.timestamp ? new Date(sig.timestamp).toLocaleTimeString() : ''}</span>
      </div>

      {sig.session_line && (
        <div style={styles.sessionLine}>LINE: {sig.session_line} runs</div>
      )}
    </div>
  );
}

const styles = {
  feed: { display: 'flex', flexDirection: 'column', gap: 6, overflowY: 'auto', flex: 1, paddingRight: 2 },
  empty: { display: 'flex', flexDirection: 'column', alignItems: 'center', justifyContent: 'center', height: '100%', color: 'var(--text-secondary)', fontSize: 12, gap: 6 },
  emptyIcon: { fontSize: 32, opacity: 0.4 },
  card: {
    background: 'var(--bg-card)', borderRadius: 'var(--radius-sm)',
    padding: '8px 10px', borderLeft: '3px solid',
    flexShrink: 0,
  },
  cardHeader: { display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 4 },
  msgText: { fontSize: 11, color: 'var(--text-secondary)', lineHeight: 1.4, marginBottom: 6 },
  cardFooter: { display: 'flex', alignItems: 'center', gap: 8 },
  sentimentBar: { flex: 1, height: 3, background: 'var(--bg-base)', borderRadius: 2 },
  sentimentFill: { height: '100%', borderRadius: 2, transition: 'width 0.3s' },
  channel: { fontSize: 9, color: 'var(--text-dim)' },
  time: { fontSize: 9, color: 'var(--text-dim)' },
  sessionTag: { fontSize: 9, background: '#003344', color: 'var(--blue)', padding: '1px 4px', borderRadius: 2 },
  signalTag: { fontSize: 9, background: 'var(--green-dim)', color: 'var(--green)', padding: '1px 4px', borderRadius: 2 },
  sessionLine: { marginTop: 4, fontSize: 10, color: 'var(--amber)', fontWeight: 600 },
};
