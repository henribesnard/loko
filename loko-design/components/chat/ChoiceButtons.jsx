import React from 'react';

/** Closed-set choice buttons the bot offers instead of free text — the deterministic-flow UI pattern. */
export function ChoiceButtons({ options, onSelect, selected }) {
  return (
    <div style={{ display: 'flex', flexWrap: 'wrap', gap: 8, paddingLeft: 2 }}>
      {options.map((opt) => {
        const isSelected = selected === opt;
        return (
          <button
            key={opt}
            onClick={() => onSelect(opt)}
            disabled={selected != null}
            style={{
              padding: '8px 14px',
              borderRadius: 'var(--radius-pill)',
              border: '1px solid',
              borderColor: isSelected ? 'var(--brand-primary)' : 'var(--border-default)',
              background: isSelected ? 'var(--brand-primary-tint)' : 'var(--surface-card)',
              color: isSelected ? 'var(--green-700)' : 'var(--text-primary)',
              fontFamily: 'var(--font-sans)',
              fontSize: 'var(--text-body-sm)',
              fontWeight: 500,
              cursor: selected == null ? 'pointer' : 'default',
              opacity: selected != null && !isSelected ? 0.45 : 1,
              transition: 'all var(--duration-fast) var(--ease-standard)',
            }}
          >
            {opt}
          </button>
        );
      })}
    </div>
  );
}
