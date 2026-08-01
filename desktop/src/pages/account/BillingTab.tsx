import { useTranslation } from "react-i18next";
import { Button } from "@/components/ui/Button";
import { Badge } from "@/components/ui/Badge";
import { QuotaBar } from "@/components/ui/QuotaBar";
import { Modal } from "@/components/ui/Modal";
import { useState } from "react";
import type { useAccountSettings } from "@/hooks/useAccountSettings";

interface Props {
  settings: ReturnType<typeof useAccountSettings>;
}

const PLAN_LABELS: Record<string, string> = {
  trial: "Trial",
  standard: "Standard",
  enterprise: "Enterprise",
  internal: "Internal",
};

export function BillingTab({ settings }: Props) {
  const { t } = useTranslation();
  const { usage } = settings;
  const [showPlanModal, setShowPlanModal] = useState(false);

  const plan = usage?.plan || "trial";

  return (
    <div className="space-y-8">
      {/* Plan */}
      <section className="space-y-4">
        <h2 className="text-base font-semibold" style={{ color: "var(--text-primary)" }}>
          {t("account.billing.title")}
        </h2>
        <div
          className="flex items-center justify-between p-4"
          style={{
            borderRadius: "var(--radius-md)",
            border: "1px solid var(--border-subtle)",
            background: "var(--surface-card)",
          }}
        >
          <div className="flex items-center gap-3">
            <span className="text-sm font-semibold" style={{ color: "var(--text-primary)" }}>
              {PLAN_LABELS[plan] || plan}
            </span>
            <Badge label={plan.toUpperCase()} variant="brand" />
          </div>
          <Button size="sm" variant="secondary" onClick={() => setShowPlanModal(true)}>
            {t("account.billing.changePlan")}
          </Button>
        </div>
      </section>

      {/* Quotas */}
      {usage && (
        <section className="space-y-4">
          <h3 className="text-sm font-semibold" style={{ color: "var(--text-primary)" }}>
            {t("account.billing.quotas")}
          </h3>
          <div className="space-y-3">
            <QuotaBar label="Bots" used={usage.quotas.bots.used} limit={usage.quotas.bots.limit} />
            <QuotaBar
              label="Intentions / bot"
              used={0}
              limit={usage.quotas.intents_per_bot.limit}
            />
            <QuotaBar label="Documents" used={0} limit={usage.quotas.documents.limit} />
          </div>
        </section>
      )}

      {/* Billing history */}
      <section className="space-y-3">
        <h3 className="text-sm font-semibold" style={{ color: "var(--text-primary)" }}>
          {t("account.billing.billingHistory")}
        </h3>
        <p className="text-xs" style={{ color: "var(--text-tertiary)" }}>
          {t("account.billing.noInvoices")}
        </p>
      </section>

      {/* Coming soon modal */}
      <Modal open={showPlanModal} onClose={() => setShowPlanModal(false)} title={t("account.billing.comingSoonTitle")}>
        <p className="text-sm" style={{ color: "var(--text-secondary)" }}>
          {t("account.billing.comingSoonDesc")}
        </p>
        <div className="flex justify-end pt-2">
          <Button size="sm" variant="secondary" onClick={() => setShowPlanModal(false)}>
            OK
          </Button>
        </div>
      </Modal>
    </div>
  );
}
