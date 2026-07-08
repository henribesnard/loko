import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { LokoGlyph } from "@/components/ui/LokoGlyph";

interface LoginPageProps {
  onLogin: (token: string) => Promise<boolean>;
}

export function LoginPage({ onLogin }: LoginPageProps) {
  const { t } = useTranslation();
  const [token, setToken] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!token.trim()) return;
    setLoading(true);
    setError(null);
    const ok = await onLogin(token.trim());
    if (!ok) setError(t("auth.error"));
    setLoading(false);
  };

  return (
    <div className="flex h-screen items-center justify-center bg-gray-50 dark:bg-gray-950">
      <div className="w-full max-w-sm px-6">
        {/* Logo */}
        <div className="flex items-center justify-center gap-3 mb-8">
          <LokoGlyph size={40} />
          <span className="text-xl font-semibold text-gray-900 dark:text-gray-100">
            LOKO
          </span>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4">
          <Input
            type="password"
            label={t("auth.tokenLabel")}
            placeholder={t("auth.tokenPlaceholder")}
            value={token}
            onChange={(e) => setToken(e.target.value)}
            error={error ?? undefined}
            autoFocus
          />
          <Button
            type="submit"
            size="md"
            className="w-full"
            disabled={loading || !token.trim()}
          >
            {t("auth.login")}
          </Button>
        </form>
      </div>
    </div>
  );
}
