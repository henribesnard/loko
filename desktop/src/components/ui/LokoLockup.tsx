/**
 * LOKO horizontal lockup — "LOK" text + O glyph.
 * Source: loko-handoff/loko/project/assets/logo/lockup-horizontal-color.svg
 */
interface LokoLockupProps {
  height?: number;
  className?: string;
}

export function LokoLockup({ height = 28, className }: LokoLockupProps) {
  const w = (250 / 64) * height;
  return (
    <svg
      xmlns="http://www.w3.org/2000/svg"
      viewBox="0 0 250 64"
      width={w}
      height={height}
      className={className}
    >
      <text
        x="0"
        y="45"
        fontFamily="Geist, -apple-system, 'Segoe UI', sans-serif"
        fontWeight="600"
        fontSize="42"
        letterSpacing="-0.5"
        fill="var(--text-primary)"
      >
        LOK
      </text>
      <g fill="#0F7D63" fillRule="evenodd">
        <path d="M 96 30 m -16 0 a 16 16 0 1 0 32 0 a 16 16 0 1 0 -32 0 Z M 93 33 h6 a2.5 2.5 0 0 1 2.5 2.5 v8 a2.5 2.5 0 0 1 -2.5 2.5 h-6 a2.5 2.5 0 0 1 -2.5 -2.5 v-8 a2.5 2.5 0 0 1 2.5 -2.5 Z" />
      </g>
    </svg>
  );
}
