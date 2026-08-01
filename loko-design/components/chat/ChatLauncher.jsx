import React from 'react';

/** Floating launcher button that opens the LOKO chat widget. Derived from the glyph. */
export function ChatLauncher({ open, onClick, unread }) {
  return (
    <button
      onClick={onClick}
      aria-label={open ? 'Fermer le chat' : 'Ouvrir le chat'}
      style={{
        width: 56,
        height: 56,
        borderRadius: 'var(--radius-tile)',
        border: 'none',
        background: 'var(--brand-primary)',
        boxShadow: 'var(--shadow-lg)',
        cursor: 'pointer',
        display: 'flex',
        alignItems: 'center',
        justifyContent: 'center',
        position: 'relative',
        transition: 'transform var(--duration-base) var(--ease-standard), background var(--duration-base)',
      }}
      onMouseEnter={(e) => (e.currentTarget.style.background = 'var(--brand-primary-hover)')}
      onMouseLeave={(e) => (e.currentTarget.style.background = 'var(--brand-primary)')}
    >
      {open ? (
        <svg width="20" height="20" viewBox="0 0 20 20" fill="none">
          <path d="M4 4L16 16M16 4L4 16" stroke="var(--text-on-brand)" strokeWidth="2" strokeLinecap="round" />
        </svg>
      ) : (
        <svg width="22" height="22" viewBox="0 0 64 64">
          <path fillRule="evenodd" fill="var(--text-on-brand)" d="M 32 32 m -18 0 a 18 18 0 1 0 36 0 a 18 18 0 1 0 -36 0 Z M 28.5 29 h7 a3 3 0 0 1 3 3 v10 a3 3 0 0 1 -3 3 h-7 a3 3 0 0 1 -3 -3 v-10 a3 3 0 0 1 3 -3 Z"/>
        </svg>
      )}
      {!open && unread > 0 && (
        <span
          style={{
            position: 'absolute',
            top: -2,
            right: -2,
            minWidth: 18,
            height: 18,
            padding: '0 4px',
            borderRadius: 'var(--radius-pill)',
            background: 'var(--accent-primary)',
            color: '#fff',
            fontFamily: 'var(--font-mono)',
            fontSize: 10,
            fontWeight: 600,
            display: 'flex',
            alignItems: 'center',
            justifyContent: 'center',
            border: '2px solid var(--surface-page)',
          }}
        >
          {unread}
        </span>
      )}
    </button>
  );
}
