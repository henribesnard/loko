/**
 * LOKO Monitoring — Shimmer loading skeleton state.
 */
export function MonitoringSkeletons() {
  return (
    <div className="px-7 py-5 flex flex-col gap-4">
      {/* KPI cards skeleton */}
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-3">
        {Array.from({ length: 6 }).map((_, i) => (
          <div
            key={i}
            className="relative overflow-hidden rounded-[var(--radius-lg)]"
            style={{
              height: 88,
              background: "var(--surface-card)",
              border: "1px solid var(--border-subtle)",
            }}
          >
            <div
              className="absolute inset-0"
              style={{
                background:
                  "linear-gradient(90deg, transparent, var(--surface-sunken), transparent)",
                animation: "loko-shimmer 1.4s infinite",
              }}
            />
          </div>
        ))}
      </div>

      {/* Chart skeleton */}
      <div
        className="relative overflow-hidden rounded-[var(--radius-lg)]"
        style={{
          height: 260,
          background: "var(--surface-card)",
          border: "1px solid var(--border-subtle)",
        }}
      >
        <div
          className="absolute inset-0"
          style={{
            background:
              "linear-gradient(90deg, transparent, var(--surface-sunken), transparent)",
            animation: "loko-shimmer 1.4s infinite",
          }}
        />
      </div>

      {/* Table skeleton */}
      <div
        className="relative overflow-hidden rounded-[var(--radius-lg)]"
        style={{
          height: 320,
          background: "var(--surface-card)",
          border: "1px solid var(--border-subtle)",
        }}
      >
        <div
          className="absolute inset-0"
          style={{
            background:
              "linear-gradient(90deg, transparent, var(--surface-sunken), transparent)",
            animation: "loko-shimmer 1.4s infinite",
          }}
        />
      </div>

      <style>{`
        @keyframes loko-shimmer {
          0% { transform: translateX(-100%); }
          100% { transform: translateX(100%); }
        }
      `}</style>
    </div>
  );
}
