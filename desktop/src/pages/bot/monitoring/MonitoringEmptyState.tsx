/**
 * LOKO Monitoring — Empty state when bot has no conversations yet.
 */
import { useTranslation } from "react-i18next";
import { useNavigate, useParams } from "react-router-dom";
import { Button } from "@/components/ui/Button";

export function MonitoringEmptyState() {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const { id: botId } = useParams<{ id: string }>();

  return (
    <div className="flex flex-col items-center justify-center py-24 px-7 text-center">
      <div
        className="w-[52px] h-[52px] rounded-full flex items-center justify-center mb-4"
        style={{ background: "var(--brand-primary-tint)" }}
      >
        <svg
          width={22}
          height={22}
          viewBox="0 0 24 24"
          fill="none"
        >
          <path
            d="M4 4h16v12H8l-4 4V4z"
            stroke="var(--brand-primary)"
            strokeWidth={1.6}
            strokeLinejoin="round"
          />
        </svg>
      </div>
      <h2
        className="text-base font-semibold mb-2"
        style={{ color: "var(--text-primary)" }}
      >
        {t(
          "monitoring.empty.title",
          "Votre bot n'a pas encore reçu de conversations",
        )}
      </h2>
      <p
        className="text-[13.5px] mb-5 max-w-[380px]"
        style={{ color: "var(--text-secondary)" }}
      >
        {t(
          "monitoring.empty.description",
          "Les statistiques apparaîtront ici dès les premiers échanges. En attendant, testez le parcours dans le playground.",
        )}
      </p>
      <Button onClick={() => navigate(`/bot/${botId}/playground`)}>
        {t("monitoring.empty.cta", "Ouvrir le playground")}
      </Button>
    </div>
  );
}
