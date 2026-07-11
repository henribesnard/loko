import { useEffect, useState } from "react";
import { Link, useSearchParams } from "react-router-dom";
import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/Button";
import { LokoLockup } from "@/components/ui/LokoLockup";
import { api, ApiError } from "@/lib/api";

type VerifyState = "pending" | "success" | "error";

export function VerifyEmailPage() {
  const { t } = useTranslation();
  const [searchParams] = useSearchParams();
  const token = searchParams.get("token") || "";
  const [state, setState] = useState<VerifyState>("pending");
  const [error, setError] = useState("");

  useEffect(() => {
    let cancelled = false;

    async function verify() {
      if (!token) {
        setState("error");
        setError(t("auth.verifyEmailMissing"));
        return;
      }

      try {
        await api("/api/auth/verify-email", {
          method: "POST",
          body: JSON.stringify({ token }),
        });
        if (!cancelled) setState("success");
      } catch (err) {
        if (!cancelled) {
          setState("error");
          if (err instanceof ApiError) {
            try {
              const body = JSON.parse(err.body);
              setError(typeof body.detail === "string" ? body.detail : t("auth.verifyEmailError"));
            } catch {
              setError(t("auth.verifyEmailError"));
            }
          } else {
            setError(t("auth.verifyEmailError"));
          }
        }
      }
    }

    verify();
    return () => {
      cancelled = true;
    };
  }, [token, t]);

  const title =
    state === "pending"
      ? t("auth.verifyEmailPending")
      : state === "success"
        ? t("auth.verifyEmailSuccess")
        : t("auth.verifyEmailError");

  return (
    <div className="flex h-screen items-center justify-center" style={{ background: "var(--surface-page)" }}>
      <div className="w-full max-w-sm px-8 py-10 text-center" style={{ background: "var(--surface-card)", border: "1px solid var(--border-subtle)", borderRadius: "var(--radius-lg)" }}>
        <LokoLockup height={28} className="mx-auto mb-6" />
        <h2 className="text-lg font-semibold mb-2" style={{ color: "var(--text-primary)" }}>{title}</h2>
        {state === "pending" && (
          <p className="text-sm mb-6" style={{ color: "var(--text-secondary)" }}>{t("common.loading")}</p>
        )}
        {state === "error" && (
          <p className="text-sm mb-6" style={{ color: "var(--error-fg)" }}>{error}</p>
        )}
        {state !== "pending" && (
          <Link to="/login">
            <Button size="md" className="w-full">{t("auth.backToLogin")}</Button>
          </Link>
        )}
      </div>
    </div>
  );
}
