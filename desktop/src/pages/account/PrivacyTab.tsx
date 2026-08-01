import { useState } from "react";
import { useTranslation } from "react-i18next";
import { Download, Trash2 } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Modal } from "@/components/ui/Modal";
import type { useAccountSettings } from "@/hooks/useAccountSettings";

interface Props {
  settings: ReturnType<typeof useAccountSettings>;
}

export function PrivacyTab({ settings }: Props) {
  const { t } = useTranslation();
  const { exportData, deleteAccount } = settings;

  // Export state
  const [exportState, setExportState] = useState<"idle" | "generating" | "ready">("idle");
  const [exportUrl, setExportUrl] = useState<string | null>(null);

  // Delete state
  const [showDelete, setShowDelete] = useState(false);
  const [deletePw, setDeletePw] = useState("");
  const [deleteConfirm, setDeleteConfirm] = useState("");
  const [deleteError, setDeleteError] = useState("");
  const [deleting, setDeleting] = useState(false);

  const handleExport = async () => {
    setExportState("generating");
    try {
      const data = await exportData();
      const blob = new Blob([JSON.stringify(data, null, 2)], { type: "application/json" });
      const url = URL.createObjectURL(blob);
      setExportUrl(url);
      setExportState("ready");
    } catch {
      setExportState("idle");
    }
  };

  const handleDelete = async () => {
    setDeleteError("");
    if (deleteConfirm !== "SUPPRIMER") {
      setDeleteError(t("account.privacy.deleteConfirmError"));
      return;
    }
    setDeleting(true);
    try {
      await deleteAccount(deletePw);
      window.location.href = "/";
    } catch (e: any) {
      setDeleteError(e.message || "Erreur");
      setDeleting(false);
    }
  };

  return (
    <div className="space-y-8">
      {/* Data export */}
      <section className="space-y-3">
        <h2 className="text-base font-semibold" style={{ color: "var(--text-primary)" }}>
          {t("account.privacy.exportTitle")}
        </h2>
        <p className="text-xs" style={{ color: "var(--text-tertiary)" }}>
          {t("account.privacy.exportDesc")}
        </p>
        {exportState === "idle" && (
          <Button size="sm" variant="secondary" onClick={handleExport}>
            <Download size={14} /> {t("account.privacy.exportButton")}
          </Button>
        )}
        {exportState === "generating" && (
          <p className="text-xs" style={{ color: "var(--text-secondary)" }}>
            {t("account.privacy.exporting")}
          </p>
        )}
        {exportState === "ready" && exportUrl && (
          <a
            href={exportUrl}
            download="loko-export.json"
            className="inline-flex items-center gap-1.5 text-xs font-medium underline"
            style={{ color: "var(--text-link)" }}
          >
            <Download size={14} /> {t("account.privacy.download")}
          </a>
        )}
      </section>

      {/* Delete account */}
      <section
        className="p-4 space-y-3"
        style={{
          borderRadius: "var(--radius-md)",
          border: "1px solid var(--error-fg)",
          background: "var(--error-bg)",
        }}
      >
        <h2 className="text-base font-semibold" style={{ color: "var(--error-fg)" }}>
          {t("account.privacy.deleteTitle")}
        </h2>
        <p className="text-xs" style={{ color: "var(--text-secondary)" }}>
          {t("account.privacy.deleteDesc")}
        </p>
        <Button size="sm" variant="danger" onClick={() => setShowDelete(true)}>
          <Trash2 size={14} /> {t("account.privacy.deleteButton")}
        </Button>
      </section>

      {/* Delete modal */}
      <Modal
        open={showDelete}
        onClose={() => setShowDelete(false)}
        title={t("account.privacy.deleteModalTitle")}
      >
        <div className="space-y-4">
          <p className="text-sm" style={{ color: "var(--text-secondary)" }}>
            {t("account.privacy.deleteModalDesc")}
          </p>
          <Input
            label={t("account.privacy.deletePassword")}
            type="password"
            value={deletePw}
            onChange={(e) => setDeletePw(e.target.value)}
          />
          <Input
            label={t("account.privacy.deleteConfirmLabel")}
            value={deleteConfirm}
            onChange={(e) => setDeleteConfirm(e.target.value)}
            placeholder="SUPPRIMER"
          />
          {deleteError && (
            <p className="text-xs" style={{ color: "var(--error-fg)" }}>{deleteError}</p>
          )}
          <div className="flex justify-end gap-2 pt-2">
            <Button size="sm" variant="ghost" onClick={() => setShowDelete(false)}>
              {t("common.cancel")}
            </Button>
            <Button
              size="sm"
              variant="danger"
              onClick={handleDelete}
              disabled={deleting || deleteConfirm !== "SUPPRIMER" || !deletePw}
            >
              {t("account.privacy.deleteConfirm")}
            </Button>
          </div>
        </div>
      </Modal>
    </div>
  );
}
