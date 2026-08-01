export interface ChoiceButtonsProps {
  options: string[];
  onSelect: (option: string) => void;
  /** Once set, all options dim except the chosen one — makes the closed-set answer irreversible/auditable, like the rest of the flow. */
  selected?: string | null;
}
