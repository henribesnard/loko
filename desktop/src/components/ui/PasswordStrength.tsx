import { useMemo } from "react";
import { useTranslation } from "react-i18next";

interface PasswordStrengthProps {
  password: string;
}

function getStrength(pw: string): number {
  let score = 0;
  if (pw.length >= 12) score++;
  if (/[A-Z]/.test(pw)) score++;
  if (/[0-9]/.test(pw)) score++;
  if (/[^a-zA-Z0-9]/.test(pw)) score++;
  if (pw.length >= 16) score++;
  return Math.min(score, 3); // 0-3
}

const levels = [
  { color: "var(--error-fg)", key: "weak" },
  { color: "var(--warning-fg)", key: "medium" },
  { color: "var(--success-fg)", key: "strong" },
] as const;

export function PasswordStrength({ password }: PasswordStrengthProps) {
  const { t } = useTranslation();
  const strength = useMemo(() => getStrength(password), [password]);

  if (!password) return null;

  const level = Math.max(0, Math.min(strength - 1, 2));
  const info = levels[level];

  return (
    <div className="space-y-1">
      <div className="flex gap-1">
        {[0, 1, 2].map((i) => (
          <div
            key={i}
            className="h-1 flex-1 transition-colors"
            style={{
              borderRadius: "var(--radius-xs)",
              background: i <= level ? info.color : "var(--surface-sunken)",
            }}
          />
        ))}
      </div>
      <p className="text-[11px]" style={{ color: info.color }}>
        {t(`account.security.strength.${info.key}`)}
      </p>
    </div>
  );
}
