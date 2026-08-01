export interface ChatLauncherProps {
  /** Whether the conversation window is currently open (shows an × instead of the glyph). */
  open: boolean;
  onClick: () => void;
  /** Unread message count; 0 hides the badge. */
  unread?: number;
}
