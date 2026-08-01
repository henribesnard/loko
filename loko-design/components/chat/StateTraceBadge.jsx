import React from 'react';

/** Small mono badge showing the current conversation state — the visible proof of determinism. */
export function StateTraceBadge({ state, confidence }) {
  return (
    <div
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        gap: 6,
        padding: '4px 9px',
        borderRadius: 'var(--radius-sm)',
        background: 'var(--surface-sunken)',
        border: '1px solid var(--border-subtle)',
        fontFamily: 'var(--font-mono)',
        fontSize: 'var(--text-mono-sm)',
        color: 'var(--text-secondary)',
      }}
    >
      <span style={{ width: 6, height: 6, borderRadius: '50%', background: 'var(--brand-primary)' }} />
      {state}
      {confidence != null && (
        <span style={{ color: 'var(--text-tertiary)' }}>· {confidence.toFixed(2)}</span>
      )}
    </div>
  );
}
