import { cn } from "@/lib/cn";

type BadgeVariant = "success" | "warning" | "info" | "neutral" | "brand" | "error";

interface BadgeProps {
  label: string;
  variant?: BadgeVariant;
  className?: string;
}

const variantStyles: Record<BadgeVariant, { bg: string; color: string }> = {
  success: { bg: "var(--success-bg)", color: "var(--success-fg)" },
  warning: { bg: "var(--warning-bg)", color: "var(--warning-fg)" },
  error: { bg: "var(--error-bg)", color: "var(--error-fg)" },
  info: { bg: "var(--info-bg)", color: "var(--info-fg)" },
  neutral: { bg: "var(--surface-sunken)", color: "var(--text-secondary)" },
  brand: { bg: "var(--brand-primary-tint)", color: "var(--green-700)" },
};

export function Badge({ label, variant = "neutral", className }: BadgeProps) {
  const styles = variantStyles[variant];
  return (
    <span
      className={cn("inline-flex items-center px-2 py-0.5 text-[11px] font-semibold", className)}
      style={{
        borderRadius: "var(--radius-xs)",
        background: styles.bg,
        color: styles.color,
      }}
    >
      {label}
    </span>
  );
}
