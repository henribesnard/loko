import React from 'react';

/** Streaming/typing indicator — three dots, deliberately calm (no bounce), signals "processing", not "magic". */
export function StreamingIndicator() {
  return (
    <div
      style={{
        display: 'inline-flex',
        gap: 5,
        padding: '11px 14px',
        borderRadius: '4px 14px 14px 14px',
        background: 'var(--surface-sunken)',
        border: '1px solid var(--border-subtle)',
        width: 'fit-content',
      }}
    >
      {[0, 1, 2].map((i) => (
        <span
          key={i}
          style={{
            width: 5,
            height: 5,
            borderRadius: '50%',
            background: 'var(--text-tertiary)',
            opacity: 0.35,
            animation: `loko-pulse 1.1s ${i * 0.15}s ease-in-out infinite`,
          }}
        />
      ))}
      <style>{`@keyframes loko-pulse { 0%, 100% { opacity: 0.3; } 40% { opacity: 0.9; } }`}</style>
    </div>
  );
}
