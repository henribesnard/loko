/**
 * TraceTimeline — Signature decision-trace component.
 * Vertical timeline: classification → clarification → retrieval → generation.
 * Score vs threshold in Geist Mono, confidence color coding (green/amber/red),
 * cited sources, locked-template vs LLM-generated distinction.
 *
 * Ported from: loko-handoff/loko/project/TraceTimeline.dc.html
 */

export interface TraceSource {
  name: string;
  relevance: number;
}

export interface TraceStep {
  label: string;
  status: "done" | "active" | "pending";
  durationMs?: number;
  detail?: string;
  score?: number;
  threshold?: number;
  confidenceLevel?: "high" | "medium" | "low";
  kind?: "template" | "generated";
  sources?: TraceSource[];
}

interface TraceTimelineProps {
  steps: TraceStep[];
  variant?: "full" | "mini";
}

function fmtMs(ms?: number): string {
  if (ms == null) return "";
  return ms < 1000 ? `${ms} ms` : `${(ms / 1000).toFixed(1)} s`;
}

function confColors(level?: string) {
  if (level === "high")
    return {
      dot: "var(--green-500)",
      ring: "var(--green-100)",
      fg: "var(--success-fg)",
      bg: "var(--success-bg)",
      border: "var(--success-border)",
    };
  if (level === "medium")
    return {
      dot: "var(--warning-500)",
      ring: "var(--warning-100)",
      fg: "var(--warning-fg)",
      bg: "var(--warning-bg)",
      border: "var(--warning-border)",
    };
  if (level === "low")
    return {
      dot: "var(--error-500)",
      ring: "var(--error-100)",
      fg: "var(--error-fg)",
      bg: "var(--error-bg)",
      border: "var(--error-border)",
    };
  return {
    dot: "var(--gray-400)",
    ring: "var(--gray-100)",
    fg: "var(--text-tertiary)",
    bg: "var(--surface-sunken)",
    border: "var(--border-subtle)",
  };
}

export function TraceTimeline({ steps, variant = "full" }: TraceTimelineProps) {
  const totalMs = steps.reduce((a, s) => a + (s.durationMs ?? 0), 0);

  return (
    <div
      style={{
        fontFamily: "var(--font-sans)",
        background: "var(--surface-card)",
        border: "1px solid var(--border-subtle)",
        borderRadius: "var(--radius-lg)",
        padding: 18,
        display: "flex",
        flexDirection: "column",
        gap: 2,
        width: "100%",
      }}
    >
      {/* Header */}
      <div
        style={{
          display: "flex",
          alignItems: "center",
          justifyContent: "space-between",
          marginBottom: 12,
        }}
      >
        <div
          style={{ fontSize: 13, fontWeight: 600, color: "var(--text-primary)" }}
        >
          Trace de decision
        </div>
        <div
          style={{
            fontFamily: "var(--font-mono)",
            fontSize: 11,
            color: "var(--text-tertiary)",
          }}
        >
          {totalMs > 0 ? `total ${fmtMs(totalMs)}` : ""}
        </div>
      </div>

      {/* Steps */}
      {steps.map((step, i) => {
        const isPending = step.status === "pending";
        const conf = confColors(
          isPending ? undefined : step.confidenceLevel ?? "high"
        );
        const dotColor = isPending ? "var(--gray-300)" : conf.dot;
        const ringColor = isPending ? "var(--gray-50)" : conf.ring;
        const hasLine = i < steps.length - 1;
        const showScore =
          !isPending && step.score != null && variant === "full";
        const showKind =
          !isPending && !!step.kind && variant === "full";
        const showSources =
          !isPending &&
          !!step.sources &&
          step.sources.length > 0 &&
          variant === "full";

        return (
          <div
            key={`${step.label}-${i}`}
            style={{ display: "flex", gap: 12, position: "relative" }}
          >
            {/* Dot + vertical line */}
            <div
              style={{
                display: "flex",
                flexDirection: "column",
                alignItems: "center",
                width: 20,
                flex: "none",
              }}
            >
              <div
                style={{
                  width: 11,
                  height: 11,
                  borderRadius: "50%",
                  background: dotColor,
                  border: `2px solid ${ringColor}`,
                  zIndex: 1,
                  marginTop: 2,
                }}
              />
              {hasLine && (
                <div
                  style={{
                    width: 2,
                    flex: 1,
                    background: "var(--border-default)",
                    minHeight: 20,
                    marginTop: 2,
                  }}
                />
              )}
            </div>

            {/* Content */}
            <div style={{ flex: 1, paddingBottom: 18 }}>
              <div
                style={{
                  display: "flex",
                  alignItems: "baseline",
                  justifyContent: "space-between",
                  gap: 8,
                }}
              >
                <div
                  style={{
                    fontSize: 13.5,
                    fontWeight: 600,
                    color: "var(--text-primary)",
                  }}
                >
                  {step.label}
                </div>
                <div
                  style={{
                    fontFamily: "var(--font-mono)",
                    fontSize: 11.5,
                    color: "var(--text-tertiary)",
                    flex: "none",
                    whiteSpace: "nowrap",
                  }}
                >
                  {isPending ? "" : fmtMs(step.durationMs)}
                </div>
              </div>
              <div
                style={{
                  fontSize: 12.5,
                  color: "var(--text-secondary)",
                  marginTop: 3,
                  lineHeight: "var(--leading-snug)",
                }}
              >
                {isPending ? "En attente\u2026" : step.detail ?? ""}
              </div>

              {/* Score badge */}
              {showScore && (
                <div
                  style={{
                    display: "flex",
                    alignItems: "center",
                    gap: 8,
                    marginTop: 8,
                  }}
                >
                  <div
                    style={{
                      fontFamily: "var(--font-mono)",
                      fontSize: 11.5,
                      fontWeight: 600,
                      color: conf.fg,
                      background: conf.bg,
                      border: `1px solid ${conf.border}`,
                      borderRadius: 6,
                      padding: "2px 8px",
                    }}
                  >
                    {step.score!.toFixed(2)}
                  </div>
                  <div
                    style={{
                      fontFamily: "var(--font-mono)",
                      fontSize: 10.5,
                      color: "var(--text-tertiary)",
                    }}
                  >
                    seuil {step.threshold?.toFixed(2)}
                  </div>
                </div>
              )}

              {/* Kind badge */}
              {showKind && (
                <div
                  style={{
                    display: "inline-flex",
                    alignItems: "center",
                    gap: 5,
                    marginTop: 8,
                    fontFamily: "var(--font-mono)",
                    fontSize: 10.5,
                    fontWeight: 600,
                    letterSpacing: "0.02em",
                    textTransform: "uppercase",
                    color:
                      step.kind === "template"
                        ? "var(--green-700)"
                        : "var(--bronze-600)",
                    background:
                      step.kind === "template"
                        ? "var(--brand-primary-tint)"
                        : "var(--accent-tint)",
                    border: `1px solid ${
                      step.kind === "template"
                        ? "var(--brand-primary-border)"
                        : "var(--accent-border)"
                    }`,
                    borderRadius: 5,
                    padding: "3px 7px",
                  }}
                >
                  {step.kind === "template" ? "\uD83D\uDD12" : "\u25C6"}{" "}
                  {step.kind === "template"
                    ? "Template verrouille"
                    : "Generation LLM"}
                </div>
              )}

              {/* Sources */}
              {showSources && (
                <div
                  style={{
                    display: "flex",
                    flexDirection: "column",
                    gap: 6,
                    marginTop: 9,
                  }}
                >
                  {step.sources!.map((src, si) => (
                    <div
                      key={si}
                      style={{
                        display: "flex",
                        alignItems: "center",
                        justifyContent: "space-between",
                        gap: 8,
                        background: "var(--surface-sunken)",
                        border: "1px solid var(--border-subtle)",
                        borderRadius: 7,
                        padding: "6px 10px",
                        minWidth: 0,
                      }}
                    >
                      <div
                        style={{
                          fontSize: 11,
                          color: "var(--text-secondary)",
                          fontFamily: "var(--font-mono)",
                          whiteSpace: "nowrap",
                          overflow: "hidden",
                          textOverflow: "ellipsis",
                          minWidth: 0,
                        }}
                      >
                        {src.name}
                      </div>
                      <div
                        style={{
                          fontFamily: "var(--font-mono)",
                          fontSize: 11,
                          fontWeight: 600,
                          color: "var(--text-tertiary)",
                          flex: "none",
                        }}
                      >
                        {Math.round(src.relevance * 100)}%
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}
