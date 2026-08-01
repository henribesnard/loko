export interface MessageBubbleProps {
  from?: 'bot' | 'user';
  children: React.ReactNode;
  /** Optional mono trace line under bot replies, e.g. "cgv-2026.pdf · state.confirm_return" — makes the answer auditable. */
  traceLabel?: string;
}
