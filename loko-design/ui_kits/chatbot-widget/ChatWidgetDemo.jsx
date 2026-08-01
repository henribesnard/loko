import React from 'react';
import { ChatLauncher } from '../../components/chat/ChatLauncher.jsx';
import { MessageBubble } from '../../components/chat/MessageBubble.jsx';
import { ChoiceButtons } from '../../components/chat/ChoiceButtons.jsx';
import { StreamingIndicator } from '../../components/chat/StreamingIndicator.jsx';

/** Full embedded widget: launcher + conversation window, as it would sit on a client site. */
export function ChatWidgetDemo({ theme = 'light' }) {
  const [open, setOpen] = React.useState(true);
  const [answer, setAnswer] = React.useState(null);
  const [showTrace, setShowTrace] = React.useState(false);

  return (
    <div data-theme={theme} style={{ position: 'relative', width: '100%', height: '100%' }}>
      <div
        style={{
          position: 'absolute',
          right: 24,
          bottom: 24,
          width: 360,
          maxHeight: 500,
          borderRadius: 'var(--radius-xl)',
          background: 'var(--surface-card)',
          border: '1px solid var(--border-subtle)',
          boxShadow: 'var(--shadow-lg)',
          display: open ? 'flex' : 'none',
          flexDirection: 'column',
          overflow: 'hidden',
          fontFamily: 'var(--font-sans)',
        }}
      >
        {/* Header */}
        <div
          style={{
            display: 'flex',
            alignItems: 'center',
            gap: 10,
            padding: '14px 16px',
            borderBottom: '1px solid var(--border-subtle)',
            background: 'var(--surface-card)',
          }}
        >
          <svg width="26" height="26" viewBox="0 0 64 64">
            <rect x="1" y="1" width="62" height="62" rx="14" fill="var(--brand-primary)" />
            <path fillRule="evenodd" fill="var(--text-on-brand)" d="M 32 32 m -18 0 a 18 18 0 1 0 36 0 a 18 18 0 1 0 -36 0 Z M 28.5 29 h7 a3 3 0 0 1 3 3 v10 a3 3 0 0 1 -3 3 h-7 a3 3 0 0 1 -3 -3 v-10 a3 3 0 0 1 3 -3 Z"/>
          </svg>
          <div style={{ flex: 1 }}>
            <div style={{ fontSize: 14, fontWeight: 600, color: 'var(--text-primary)' }}>Assistant Loko</div>
            <div style={{ fontSize: 11.5, color: 'var(--text-tertiary)', display: 'flex', alignItems: 'center', gap: 5 }}>
              <span style={{ width: 6, height: 6, borderRadius: '50%', background: 'var(--brand-primary)' }} />
              En ligne — données traitées localement
            </div>
          </div>
          <button
            onClick={() => setShowTrace((s) => !s)}
            title="Voir pourquoi le bot répond ceci"
            style={{
              width: 26,
              height: 26,
              borderRadius: 'var(--radius-sm)',
              border: '1px solid var(--border-default)',
              background: 'transparent',
              color: 'var(--text-secondary)',
              fontFamily: 'var(--font-mono)',
              fontSize: 12,
              cursor: 'pointer',
            }}
          >
            i
          </button>
        </div>

        {/* Messages */}
        <div style={{ flex: 1, padding: 16, display: 'flex', flexDirection: 'column', gap: 12, overflowY: 'auto', background: 'var(--surface-page)' }}>
          <MessageBubble from="bot">Bonjour 👋 Comment puis-je vous aider aujourd'hui ?</MessageBubble>
          <MessageBubble from="user">J'ai un souci avec ma dernière commande.</MessageBubble>
          <MessageBubble
            from="bot"
            traceLabel={showTrace ? 'state.qualify_issue · cgv-2026.pdf' : undefined}
          >
            Bien sûr. De quel type de demande s'agit-il ?
          </MessageBubble>
          <ChoiceButtons options={['Livraison', 'Retour', 'Facturation']} onSelect={setAnswer} selected={answer} />
          {answer && (
            <MessageBubble
              from="bot"
              traceLabel={showTrace ? `state.confirm_${answer.toLowerCase()} · 0.94` : undefined}
            >
              {answer === 'Retour'
                ? 'Le retour est possible si la commande a moins de 30 jours. Voulez-vous démarrer la procédure ?'
                : answer === 'Livraison'
                ? "Votre colis est en cours d'acheminement. Je peux vous donner le suivi si vous avez le numéro de commande."
                : 'Je peux vous montrer le détail de la dernière facture émise.'}
            </MessageBubble>
          )}
          {!answer && <StreamingIndicator />}
        </div>

        {/* Composer */}
        <div style={{ display: 'flex', gap: 8, padding: 12, borderTop: '1px solid var(--border-subtle)' }}>
          <input
            placeholder="Écrire un message…"
            style={{
              flex: 1,
              border: '1px solid var(--border-default)',
              borderRadius: 'var(--radius-pill)',
              padding: '9px 14px',
              fontSize: 13.5,
              fontFamily: 'var(--font-sans)',
              background: 'var(--surface-card)',
              color: 'var(--text-primary)',
              outline: 'none',
            }}
          />
          <button
            style={{
              width: 36,
              height: 36,
              borderRadius: '50%',
              border: 'none',
              background: 'var(--brand-primary)',
              color: 'var(--text-on-brand)',
              cursor: 'pointer',
            }}
          >
            →
          </button>
        </div>
      </div>

      <div style={{ position: 'absolute', right: 24, bottom: open ? 536 : 24 }}>
        <ChatLauncher open={open} onClick={() => setOpen((o) => !o)} unread={open ? 0 : 1} />
      </div>
    </div>
  );
}
