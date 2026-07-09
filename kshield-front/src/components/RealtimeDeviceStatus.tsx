/**
 * RealtimeDeviceStatus — bandeau LIVE affichant le statut d'un équipement.
 *
 * Combine :
 *   - snapshot REST (last_heartbeat + probe TCP)
 *   - événements WS globaux filtrés par device_id
 */
import { useEffect, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Wifi, WifiOff, Zap, RefreshCw, Radio } from "lucide-react";
import { deviceCommandService } from "@/services/enrollment";
import { useDeviceStatusChannel } from "@/hooks/useDeviceStatusChannel";
import { cn } from "@/lib/cn";
import { fmtRelative } from "@/lib/format";

interface Props {
  deviceId: number;
  compact?: boolean;
}

export function RealtimeDeviceStatus({ deviceId, compact }: Props) {
  const [lastEvent, setLastEvent] = useState<{ kind: string; at: string } | null>(null);

  const { data: statusData, refetch, isFetching } = useQuery({
    queryKey: ["device-status", deviceId],
    queryFn: async () => (await deviceCommandService.status(deviceId)).data,
    refetchInterval: 30_000,
  });

  const { status: wsStatus } = useDeviceStatusChannel({
    enabled: true,
    onEvent: (evt: any) => {
      if (evt?.device_id !== deviceId) return;
      setLastEvent({ kind: evt.event || "?", at: evt.at || new Date().toISOString() });
      refetch();
    },
  });

  const probeOk = statusData?.probe?.reachable;
  const heartbeatAgeMs = statusData?.last_heartbeat_at
    ? Date.now() - new Date(statusData.last_heartbeat_at).getTime()
    : null;
  const heartbeatOk = heartbeatAgeMs != null && heartbeatAgeMs < 90_000;

  const stateClass = probeOk && heartbeatOk
    ? "bg-success/5 border-success/30 text-success"
    : probeOk
    ? "bg-info/5 border-info/30 text-info"
    : "bg-warning/5 border-warning/30 text-warning";

  return (
    <div className={cn("rounded-lg border p-2.5", stateClass,
                        compact ? "text-xs" : "text-sm")}>
      <div className="flex items-center gap-2">
        {probeOk ? <Wifi className="w-4 h-4 animate-pulse" /> : <WifiOff className="w-4 h-4" />}
        <span className="font-medium">
          {probeOk ? "En ligne" : "Hors ligne"}
          {statusData?.probe?.port ? ` · port ${statusData.probe.port}` : ""}
          {statusData?.probe?.latency_ms != null ? ` · ${statusData.probe.latency_ms} ms` : ""}
        </span>
        <span className="ml-auto flex items-center gap-2 text-ink-muted">
          <Radio className={cn("w-3 h-3",
                                wsStatus === "open" ? "text-success" : "text-warning")} />
          <span className="text-[10px] uppercase tracking-wider">{wsStatus}</span>
          <button onClick={() => refetch()} className="hover:text-ink" title="Actualiser">
            <RefreshCw className={cn("w-3 h-3", isFetching && "animate-spin")} />
          </button>
        </span>
      </div>
      <div className="mt-1 flex items-center gap-3 text-xs text-ink-muted">
        <span>
          Heartbeat :{" "}
          {statusData?.last_heartbeat_at
            ? fmtRelative(statusData.last_heartbeat_at)
            : "jamais"}
        </span>
        {lastEvent && (
          <span className="flex items-center gap-1">
            <Zap className="w-3 h-3 text-info" />
            {lastEvent.kind} · {fmtRelative(lastEvent.at)}
          </span>
        )}
      </div>
    </div>
  );
}
