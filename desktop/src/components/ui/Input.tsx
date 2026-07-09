import { type InputHTMLAttributes, forwardRef } from "react";
import { cn } from "@/lib/cn";

interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  label?: string;
  error?: string;
}

export const Input = forwardRef<HTMLInputElement, InputProps>(
  ({ label, error, className, id, ...props }, ref) => {
    const inputId = id || label?.toLowerCase().replace(/\s/g, "-");
    return (
      <div className="space-y-1.5">
        {label && (
          <label
            htmlFor={inputId}
            className="block text-xs font-medium text-[var(--text-secondary)]"
          >
            {label}
          </label>
        )}
        <input
          ref={ref}
          id={inputId}
          className={cn(
            "w-full rounded-[var(--radius-sm)] border border-[var(--border-default)] px-3 py-2 text-sm",
            "bg-[var(--surface-page)] text-[var(--text-primary)]",
            "placeholder:text-[var(--text-tertiary)]",
            "focus:outline-none focus:shadow-[var(--focus-ring)] focus:border-[var(--border-focus)]",
            error && "border-[var(--error-fg)] focus:border-[var(--error-fg)]",
            className,
          )}
          {...props}
        />
        {error && (
          <p className="text-xs text-[var(--error-fg)]">{error}</p>
        )}
      </div>
    );
  },
);
Input.displayName = "Input";
