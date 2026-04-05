import React from 'react';

export default function Panel({ title, accent, children, style }) {
  return (
    <div style={{ ...styles.panel, ...style }}>
      <div style={{ ...styles.header, borderLeftColor: accent || 'var(--border-bright)' }}>
        <span style={styles.title}>{title}</span>
        <div style={{ ...styles.accentDot, background: accent || 'var(--text-dim)' }} />
      </div>
      <div style={styles.body}>{children}</div>
    </div>
  );
}

const styles = {
  panel: {
    background: 'var(--bg-panel)',
    border: '1px solid var(--border)',
    borderRadius: 'var(--radius-md)',
    display: 'flex',
    flexDirection: 'column',
    overflow: 'hidden',
    boxShadow: 'var(--shadow-panel)',
  },
  header: {
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    padding: '6px 12px',
    borderBottom: '1px solid var(--border)',
    borderLeft: '3px solid',
    background: 'var(--bg-card)',
  },
  title: {
    fontSize: 9,
    fontWeight: 600,
    letterSpacing: 2,
    color: 'var(--text-secondary)',
  },
  accentDot: {
    width: 5,
    height: 5,
    borderRadius: '50%',
    opacity: 0.8,
  },
  body: {
    padding: '10px 12px',
    flex: 1,
    overflowY: 'auto',
    display: 'flex',
    flexDirection: 'column',
    gap: 4,
  },
};
