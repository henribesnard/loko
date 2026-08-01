export interface StateTraceBadgeProps {
  /** Machine-readable state name, e.g. "state.confirm_return". */
  state: string;
  /** 0–1 confidence score, shown in mono next to the state. */
  confidence?: number;
}
