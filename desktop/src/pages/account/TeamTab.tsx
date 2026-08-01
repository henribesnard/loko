import { useState } from "react";
import { useTranslation } from "react-i18next";
import { UserPlus, MoreHorizontal, Users } from "lucide-react";
import { Button } from "@/components/ui/Button";
import { Badge } from "@/components/ui/Badge";
import { Modal } from "@/components/ui/Modal";
import type { useAccountSettings } from "@/hooks/useAccountSettings";

interface Props {
  settings: ReturnType<typeof useAccountSettings>;
}

const ROLE_VARIANTS: Record<string, "brand" | "info" | "neutral"> = {
  owner: "brand",
  editor: "info",
  viewer: "neutral",
};

export function TeamTab({ settings }: Props) {
  const { t } = useTranslation();
  const {
    team,
    profile,
    inviteMembers,
    updateMemberRole,
    removeMember,
    cancelInvitation,
    resendInvitation,
  } = settings;
  const [showInvite, setShowInvite] = useState(false);
  const [inviteEmails, setInviteEmails] = useState("");
  const [inviteRole, setInviteRole] = useState<"editor" | "viewer">("editor");
  const [inviting, setInviting] = useState(false);
  const [menuOpen, setMenuOpen] = useState<string | null>(null);

  const isOwner = profile?.role === "owner";
  const members = team?.members || [];
  const invitations = team?.invitations || [];
  const ownerCount = members.filter((m) => m.role === "owner").length;

  const handleInvite = async () => {
    setInviting(true);
    try {
      const emails = inviteEmails
        .split(/[,\n]/)
        .map((e) => e.trim())
        .filter(Boolean);
      await inviteMembers(emails, inviteRole);
      setShowInvite(false);
      setInviteEmails("");
    } finally {
      setInviting(false);
    }
  };

  const initials = (name: string, email: string) => {
    if (name) return name.slice(0, 2).toUpperCase();
    return email.slice(0, 2).toUpperCase();
  };

  // Empty state
  if (members.length <= 1 && invitations.length === 0) {
    return (
      <div className="space-y-6">
        <div className="flex items-center justify-between">
          <h2 className="text-base font-semibold" style={{ color: "var(--text-primary)" }}>
            {t("account.team.title")}
          </h2>
          {isOwner && (
            <Button size="sm" onClick={() => setShowInvite(true)}>
              <UserPlus size={14} /> {t("account.team.invite")}
            </Button>
          )}
        </div>
        <div
          className="flex flex-col items-center justify-center py-12 text-center"
          style={{
            borderRadius: "var(--radius-md)",
            border: "1px dashed var(--border-default)",
          }}
        >
          <Users size={32} style={{ color: "var(--text-tertiary)" }} />
          <p className="mt-3 text-sm font-medium" style={{ color: "var(--text-primary)" }}>
            {t("account.team.emptyTitle")}
          </p>
          <p className="mt-1 text-xs" style={{ color: "var(--text-tertiary)" }}>
            {t("account.team.emptyDesc")}
          </p>
          {isOwner && (
            <Button size="sm" className="mt-4" onClick={() => setShowInvite(true)}>
              <UserPlus size={14} /> {t("account.team.invite")}
            </Button>
          )}
        </div>
        <InviteModal
          open={showInvite}
          onClose={() => setShowInvite(false)}
          emails={inviteEmails}
          setEmails={setInviteEmails}
          role={inviteRole}
          setRole={setInviteRole}
          onInvite={handleInvite}
          inviting={inviting}
          t={t}
        />
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex items-center justify-between">
        <h2 className="text-base font-semibold" style={{ color: "var(--text-primary)" }}>
          {t("account.team.title")}
        </h2>
        {isOwner && (
          <Button size="sm" onClick={() => setShowInvite(true)}>
            <UserPlus size={14} /> {t("account.team.invite")}
          </Button>
        )}
      </div>

      {/* Members table */}
      <div
        style={{
          borderRadius: "var(--radius-md)",
          border: "1px solid var(--border-subtle)",
          overflow: "hidden",
        }}
      >
        <table className="w-full text-sm">
          <thead>
            <tr style={{ background: "var(--surface-sunken)" }}>
              <th className="text-left px-4 py-2.5 text-xs font-medium" style={{ color: "var(--text-secondary)" }}>
                {t("account.team.member")}
              </th>
              <th className="text-left px-4 py-2.5 text-xs font-medium" style={{ color: "var(--text-secondary)" }}>
                {t("account.team.role")}
              </th>
              <th className="text-left px-4 py-2.5 text-xs font-medium" style={{ color: "var(--text-secondary)" }}>
                {t("account.team.status")}
              </th>
              <th className="text-left px-4 py-2.5 text-xs font-medium" style={{ color: "var(--text-secondary)" }}>
                {t("account.team.addedOn")}
              </th>
              <th className="w-10" />
            </tr>
          </thead>
          <tbody>
            {members.map((m) => {
              const isLastOwner = m.role === "owner" && ownerCount <= 1;
              return (
                <tr
                  key={m.user_id}
                  style={{ borderTop: "1px solid var(--border-subtle)" }}
                >
                  <td className="px-4 py-3">
                    <div className="flex items-center gap-2.5">
                      <div
                        className="flex items-center justify-center w-7 h-7 text-[11px] font-semibold shrink-0"
                        style={{
                          borderRadius: "var(--radius-pill)",
                          background: "var(--brand-primary-tint)",
                          color: "var(--green-700)",
                        }}
                      >
                        {initials(m.display_name, m.email)}
                      </div>
                      <div>
                        <p style={{ color: "var(--text-primary)" }}>
                          {m.display_name || m.email.split("@")[0]}
                        </p>
                        <p className="text-xs" style={{ color: "var(--text-tertiary)" }}>
                          {m.email}
                        </p>
                      </div>
                    </div>
                  </td>
                  <td className="px-4 py-3">
                    <Badge
                      label={t(`account.team.roles.${m.role}`)}
                      variant={ROLE_VARIANTS[m.role] || "neutral"}
                    />
                  </td>
                  <td className="px-4 py-3">
                    <Badge label={t("account.team.statuses.active")} variant="success" />
                  </td>
                  <td className="px-4 py-3 text-xs" style={{ color: "var(--text-tertiary)" }}>
                    {new Date(m.created_at).toLocaleDateString()}
                  </td>
                  <td className="px-4 py-3">
                    {isOwner && (
                      <div className="relative">
                        <button
                          onClick={() => setMenuOpen(menuOpen === m.user_id ? null : m.user_id)}
                          disabled={isLastOwner}
                          className="p-1 hover:opacity-70 disabled:opacity-30"
                          title={isLastOwner ? t("account.team.lastOwnerTooltip") : ""}
                        >
                          <MoreHorizontal size={16} style={{ color: "var(--text-tertiary)" }} />
                        </button>
                        {menuOpen === m.user_id && !isLastOwner && (
                          <div
                            className="absolute right-0 top-full mt-1 py-1 z-10 w-44"
                            style={{
                              borderRadius: "var(--radius-sm)",
                              background: "var(--surface-card)",
                              border: "1px solid var(--border-default)",
                              boxShadow: "0 4px 16px rgba(0,0,0,0.08)",
                            }}
                          >
                            {m.role !== "editor" && (
                              <MenuItem
                                label={t("account.team.setEditor")}
                                onClick={() => { updateMemberRole(m.user_id, "editor"); setMenuOpen(null); }}
                              />
                            )}
                            {m.role !== "viewer" && (
                              <MenuItem
                                label={t("account.team.setViewer")}
                                onClick={() => { updateMemberRole(m.user_id, "viewer"); setMenuOpen(null); }}
                              />
                            )}
                            <MenuItem
                              label={t("account.team.remove")}
                              danger
                              onClick={() => { removeMember(m.user_id); setMenuOpen(null); }}
                            />
                          </div>
                        )}
                      </div>
                    )}
                  </td>
                </tr>
              );
            })}
            {/* Pending invitations */}
            {invitations.map((inv) => (
              <tr key={inv.id} style={{ borderTop: "1px solid var(--border-subtle)" }}>
                <td className="px-4 py-3">
                  <div className="flex items-center gap-2.5">
                    <div
                      className="flex items-center justify-center w-7 h-7 text-[11px] font-semibold shrink-0"
                      style={{
                        borderRadius: "var(--radius-pill)",
                        background: "var(--surface-sunken)",
                        color: "var(--text-tertiary)",
                      }}
                    >
                      {inv.email.slice(0, 2).toUpperCase()}
                    </div>
                    <p className="text-sm" style={{ color: "var(--text-secondary)" }}>
                      {inv.email}
                    </p>
                  </div>
                </td>
                <td className="px-4 py-3">
                  <Badge label={t(`account.team.roles.${inv.role}`)} variant={ROLE_VARIANTS[inv.role] || "neutral"} />
                </td>
                <td className="px-4 py-3">
                  <Badge label={t("account.team.statuses.pending")} variant="warning" />
                </td>
                <td className="px-4 py-3 text-xs" style={{ color: "var(--text-tertiary)" }}>
                  {new Date(inv.created_at).toLocaleDateString()}
                </td>
                <td className="px-4 py-3">
                  {isOwner && (
                    <div className="flex gap-1">
                      <button
                        onClick={() => resendInvitation(inv.id)}
                        className="text-xs underline"
                        style={{ color: "var(--text-link)" }}
                      >
                        {t("account.team.resend")}
                      </button>
                      <button
                        onClick={() => cancelInvitation(inv.id)}
                        className="text-xs underline"
                        style={{ color: "var(--error-fg)" }}
                      >
                        {t("account.team.cancel")}
                      </button>
                    </div>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <InviteModal
        open={showInvite}
        onClose={() => setShowInvite(false)}
        emails={inviteEmails}
        setEmails={setInviteEmails}
        role={inviteRole}
        setRole={setInviteRole}
        onInvite={handleInvite}
        inviting={inviting}
        t={t}
      />
    </div>
  );
}

// --- Sub-components ---

function MenuItem({ label, onClick, danger }: { label: string; onClick: () => void; danger?: boolean }) {
  return (
    <button
      onClick={onClick}
      className="w-full text-left px-3 py-1.5 text-xs hover:bg-[var(--surface-sunken)] transition-colors"
      style={{ color: danger ? "var(--error-fg)" : "var(--text-primary)" }}
    >
      {label}
    </button>
  );
}

function InviteModal({
  open,
  onClose,
  emails,
  setEmails,
  role,
  setRole,
  onInvite,
  inviting,
  t,
}: {
  open: boolean;
  onClose: () => void;
  emails: string;
  setEmails: (v: string) => void;
  role: "editor" | "viewer";
  setRole: (v: "editor" | "viewer") => void;
  onInvite: () => void;
  inviting: boolean;
  t: (k: string) => string;
}) {
  return (
    <Modal open={open} onClose={onClose} title={t("account.team.inviteTitle")}>
      <div className="space-y-4">
        <div className="space-y-1.5">
          <label className="block text-xs font-medium" style={{ color: "var(--text-secondary)" }}>
            {t("account.team.inviteEmails")}
          </label>
          <textarea
            value={emails}
            onChange={(e) => setEmails(e.target.value)}
            placeholder={t("account.team.inviteEmailsPlaceholder")}
            rows={3}
            className="w-full rounded-[var(--radius-sm)] border border-[var(--border-default)] px-3 py-2 text-sm bg-[var(--surface-page)] text-[var(--text-primary)] placeholder:text-[var(--text-tertiary)] resize-none"
          />
        </div>

        <div className="grid grid-cols-2 gap-3">
          {(["editor", "viewer"] as const).map((r) => (
            <button
              key={r}
              onClick={() => setRole(r)}
              className="text-left p-3 transition-colors"
              style={{
                borderRadius: "var(--radius-sm)",
                border: `2px solid ${role === r ? "var(--brand-primary)" : "var(--border-default)"}`,
                background: role === r ? "var(--brand-primary-tint)" : "var(--surface-card)",
              }}
            >
              <p className="text-sm font-medium" style={{ color: "var(--text-primary)" }}>
                {t(`account.team.roles.${r}`)}
              </p>
              <p className="text-xs mt-0.5" style={{ color: "var(--text-tertiary)" }}>
                {t(`account.team.${r}Desc`)}
              </p>
            </button>
          ))}
        </div>

        <div className="flex justify-end gap-2 pt-2">
          <Button size="sm" variant="ghost" onClick={onClose}>
            {t("common.cancel")}
          </Button>
          <Button size="sm" onClick={onInvite} disabled={inviting || !emails.trim()}>
            {t("account.team.sendInvitations")}
          </Button>
        </div>
      </div>
    </Modal>
  );
}
