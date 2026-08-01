import React from 'react';

/** A single message bubble in the LOKO conversation window. */
export function MessageBubble({ from = 'bot', children, traceLabel }) {
  const isBot = from === 'bot';
  return (
    <div style={{ display: 'flex', flexDirection: 'column', alignItems: isBot ? 'flex-start' : 'flex-end', gap: 4 }}>
      <div
        style={{
          maxWidth: '82%',
          padding: '10px 14px',
          borderRadius: isBot ? '4px 14px 14px 14px' : '14px 4px 14px 14px',
          background: isBot ? 'var(--surface-sunken)' : 'var(--brand-primary)',
          color: isBot ? 'var(--text-primary)' : 'var(--text-on-brand)',
          border: isBot ? '1px solid var(--border-subtle)' : 'none',
          fontFamily: 'var(--font-sans)',
          fontSize: 'var(--text-body-sm)',
          lineHeight: 'var(--leading-normal)',
        }}
      >
        {children}
      </div>
      {traceLabel && isBot && (
        <div
          style={{
            fontFamily: 'var(--font-mono)',
            fontSize: 10.5,
            color: 'var(--text-tertiary)',
            padding: '0 4px',
            display: 'flex',
            alignItems: 'center',
            gap: 4,
          }}
        >
          <span style={{ width: 4, height: 4, borderRadius: '50%', background: 'var(--brand-primary)' }} />
          {traceLabel}
        </div>
      )}
    </div>
  );
}
