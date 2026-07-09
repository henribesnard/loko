import { type ButtonHTMLAttributes, forwardRef } from "react";
import { cn } from "@/lib/cn";

type Variant = "primary" | "secondary" | "ghost" | "danger";
type Size = "sm" | "md" | "lg";

interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant;
  size?: Size;
}

const variantStyles: Record<Variant, string> = {
  primary:
    "bg-brand-500 text-[var(--text-on-brand)] hover:bg-brand-600 active:bg-brand-700",
  secondary:
    "bg-[var(--surface-card)] text-[var(--text-secondary)] border border-[var(--border-default)] hover:bg-[var(--surface-sunken)]",
  ghost:
    "text-[var(--text-secondary)] hover:bg-[var(--surface-sunken)]",
  danger:
    "bg-[var(--error-fg)] text-white hover:opacity-90",
};

const sizeStyles: Record<Size, string> = {
  sm: "px-2.5 py-1.5 text-xs",
  md: "px-4 py-2 text-sm",
  lg: "px-5 py-2.5 text-sm",
};

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(
  ({ variant = "primary", size = "md", className, disabled, ...props }, ref) => (
    <button
      ref={ref}
      disabled={disabled}
      className={cn(
        "inline-flex items-center justify-center gap-2 rounded-[var(--radius-md)] font-semibold transition-colors",
        "focus-visible:outline-none focus-visible:shadow-[var(--focus-ring)]",
        "disabled:opacity-50 disabled:cursor-not-allowed",
        variantStyles[variant],
        sizeStyles[size],
        className,
      )}
      {...props}
    />
  ),
);
Button.displayName = "Button";
