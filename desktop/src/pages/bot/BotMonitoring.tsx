/**
 * LOKO — Bot Monitoring page.
 *
 * Displays analytics monitoring dashboard: KPI cards, time series chart,
 * funnel, intent table with drill-down, errors & signals panels.
 * Three states: empty, loading (skeleton), data.
 */
import { useParams } from "react-router-dom";
import { BotSubNav } from "@/components/bot/BotSubNav";
import { useBotMonitoring } from "@/hooks/useBotMonitoring";
import { ControlBar } from "./monitoring/ControlBar";
import { KPICards } from "./monitoring/KPICards";
import { TimeSeriesChart } from "./monitoring/TimeSeriesChart";
import { FunnelChart } from "./monitoring/FunnelChart";
import { IntentTable } from "./monitoring/IntentTable";
import { ErrorsPanel } from "./monitoring/ErrorsPanel";
import { SignalsPanel } from "./monitoring/SignalsPanel";
import { MonitoringSkeletons } from "./monitoring/MonitoringSkeletons";
import { MonitoringEmptyState } from "./monitoring/MonitoringEmptyState";

export function BotMonitoring() {
  const { id: botId } = useParams<{ id: string }>();
  const mon = useBotMonitoring(botId);

  return (
    <div className="h-full flex flex-col overflow-hidden">
      <BotSubNav active="monitoring" />

      {/* Loading state */}
      {mon.loading && (
        <div className="flex-1 overflow-y-auto">
          <MonitoringSkeletons />
        </div>
      )}

      {/* Error state */}
      {!mon.loading && mon.error && (
        <div className="flex-1 flex items-center justify-center">
          <p className="text-sm text-red-500">{mon.error}</p>
        </div>
      )}

      {/* Empty state */}
      {!mon.loading && !mon.error && mon.isEmpty && (
        <div className="flex-1 overflow-y-auto">
          <MonitoringEmptyState />
        </div>
      )}

      {/* Data state */}
      {!mon.loading && !mon.error && !mon.isEmpty && mon.overview && (
        <>
          <ControlBar
            period={mon.period}
            onPeriod={mon.setPeriod}
            compare={mon.compare}
            onCompare={mon.setCompare}
            granularity={mon.granularity}
            onGranularity={mon.setGranularity}
            onExport={mon.exportCSV}
          />
          <div className="flex-1 overflow-y-auto">
            <div className="max-w-[1180px] mx-auto px-7 py-6 flex flex-col gap-5">
              <KPICards
                overview={mon.overview}
                prevOverview={mon.prevOverview}
                timeseries={mon.timeseries}
                compare={mon.compare}
              />

              <TimeSeriesChart
                data={mon.timeseries}
                prevData={mon.prevTimeseries}
                compare={mon.compare}
              />

              <FunnelChart steps={mon.funnel} />

              <IntentTable
                intents={mon.intents}
                subMotifs={mon.subMotifs}
                totalVolume={mon.totalVolume}
                drilledIntent={mon.drilledIntent}
                sortColumn={mon.sortColumn}
                sortDir={mon.sortDir}
                onSort={mon.toggleSort}
                onDrill={mon.drillDown}
                onDrillUp={mon.drillUp}
                botId={botId || ""}
              />

              <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
                <ErrorsPanel overview={mon.overview} />
                <SignalsPanel
                  overview={mon.overview}
                  intents={mon.intents}
                />
              </div>
            </div>
          </div>
        </>
      )}
    </div>
  );
}
