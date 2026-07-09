/**
 * DigitalTwinPanel — jumeau numérique d'un équipement.
 *
 * Le front lit UNIQUEMENT le twin (jamais directement l'équipement).
 * Poll REST 30 s + refresh WS instantané.
 */
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Activity, Cpu, HardDrive, Thermometer, Battery, Wifi, Zap, RefreshCw,
  CheckCircle2, AlertTriangle, XCircle,
} from "lucide-react";
import toast from "react-hot-toast";

import { twinService } from "@/services/enrollment";
import { useDeviceStatusChannel } from "@/hooks/useDeviceStatusChannel";
import { cn } from "@/lib/cn";
import { fmtRelative } from "@/lib/format";
import { Button } from "@/components/ui/Button";

interface Props { deviceId: number }

const HEALTH_META = {
  excellent: { color: "text-success", bg: "bg-success/10 border-success/30", label: "Excellent" },
  good:      { color: "text-success", bg: "bg-success/5 border-success/20",  label: "Bon" },
  degraded:  { color: "text-warning", bg: "bg-warning/5 border-warning/30",  label: "Dégradé" },
  critical:  { color: "text-danger",  bg: "bg-danger/5 border-danger/40",    label: "Critique" },
};

export function DigitalTwinPanel({ deviceId }: Props) {
  const qc = useQueryClient();
  const { data: twin, isLoading } = useQuery({
    queryKey: ["twin", deviceId],
    queryFn: async () => (await twinService.get(deviceId)).data,
    refetchInterval: 30_000,
  });

  useDeviceStatusChannel({
    onEvent: (evt: any) => {
      if (evt?.device_id === deviceId) {
        qc.invalidateQueries({ queryKey: ["twin", deviceId] });
      }
    },
  });

  const refreshMut = useMutation({
    mutationFn: () => twinService.refresh(deviceId),
    onSuccess: () => {
      toast.success("Twin rafraîchi via driver");
      qc.invalidateQueries({ queryKey: ["twin", deviceId] });
    },
    onError: () => toast.error("Refresh impossible"),
  });

  if (isLoading || !twin) {
    return (
      <div className="p-4 text-center text-ink-muted text-sm">
        Chargement du jumeau numérique…
      </div>
    );
  }

  const health = HEALTH_META[twin.health_status] || HEALTH_META.good;

  const tiles = [
    { icon: <Cpu className="w-3.5 h-3.5" />,         label: "CPU",         value: fmtPct(twin.metrics.cpu_percent) },
    { icon: <HardDrive className="w-3.5 h-3.5" />,   label: "RAM",         value: fmtPct(twin.metrics.ram_percent) },
    { icon: <HardDrive className="w-3.5 h-3.5" />,   label: "Stockage",    value: fmtPct(twin.metrics.storage_percent) },
    { icon: <Thermometer className="w-3.5 h-3.5" />, label: "Température", value: fmtTemp(twin.metrics.temperature_c) },
    { icon: <Battery className="w-3.5 h-3.5" />,     label: "Batterie",    value: twin.metrics.battery_percent != null ? `${twin.metrics.battery_percent}%` : "—" },
    { icon: <Wifi className="w-3.5 h-3.5" />,        label: "Réseau",      value: twin.metrics.network_quality != null ? `${twin.metrics.network_quality}%` : "—" },
    { icon: <Activity className="w-3.5 h-3.5" />,    label: "Latence",     value: twin.metrics.latency_ms != null ? `${twin.metrics.latency_ms} ms` : "—" },
    { icon: <Zap className="w-3.5 h-3.5" />,         label: "Uptime",      value: fmtUptime(twin.metrics.uptime_seconds) },
  ];

  return (
    <div className="space-y-3">
      {/* Header Health Score */}
      <div className={cn("rounded-lg border p-3 flex items-center gap-3", health.bg)}>
        <div className={cn("shrink-0 text-3xl font-bold", health.color)}>
          {twin.health_score}
        </div>
        <div className="flex-1 min-w-0">
          <div className={cn("text-sm font-semibold", health.color)}>
            Santé : {health.label}
          </div>
          <div className="text-xs text-ink-muted truncate">
            {twin.reachable ? "En ligne" : "Injoignable"}
            {twin.driver_class && ` · driver ${twin.driver_class}`}
            {twin.last_seen_at && ` · vu ${fmtRelative(twin.last_seen_at)}`}
          </div>
        </div>
        <Button size="sm" variant="ghost"
                leftIcon={<RefreshCw className={cn("w-3.5 h-3.5",
                                                    refreshMut.isPending && "animate-spin")} />}
                onClick={() => refreshMut.mutate()}
                loading={refreshMut.isPending}>
          Refresh
        </Button>
      </div>

      {/* Raisons de baisse du score */}
      {twin.health_reasons?.length > 0 && (
        <div className="rounded-md border border-warning/30 bg-warning/5 p-2.5">
          <div className="flex items-center gap-1.5 text-xs font-medium text-warning mb-1">
            <AlertTriangle className="w-3.5 h-3.5" />
            {twin.health_reasons.length} raison{twin.health_reasons.length > 1 ? "s" : ""} de baisse
          </div>
          <ul className="text-xs text-ink space-y-0.5 ml-5 list-disc">
            {twin.health_reasons.map((r, i) => <li key={i}>{r}</li>)}
          </ul>
        </div>
      )}

      {/* Métriques runtime */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-2">
        {tiles.map((t, i) => (
          <div key={i} className="rounded-md border border-surface-border bg-surface-soft p-2">
            <div className="flex items-center gap-1 text-[10px] uppercase tracking-wider text-ink-muted">
              {t.icon}{t.label}
            </div>
            <div className="text-sm font-semibold text-ink mt-0.5">{t.value}</div>
          </div>
        ))}
      </div>

      {/* Erreurs récentes */}
      {twin.recent_errors?.length > 0 && (
        <details className="border border-surface-border rounded-md">
          <summary className="p-2 text-xs text-ink-muted cursor-pointer flex items-center gap-1">
            <XCircle className="w-3 h-3 text-danger" />
            {twin.recent_errors.length} erreur{twin.recent_errors.length > 1 ? "s" : ""} récente{twin.recent_errors.length > 1 ? "s" : ""}
          </summary>
          <div className="p-2 space-y-0.5 text-xs font-mono max-h-40 overflow-auto">
            {twin.recent_errors.slice().reverse().map((e, i) => (
              <div key={i} className="text-ink-muted">
                <span className="text-danger">{(e.at || "").slice(11, 19)}</span>
                {" "}{e.msg}
              </div>
            ))}
          </div>
        </details>
      )}

      {/* Info technique */}
      <div className="text-xs text-ink-muted grid grid-cols-2 gap-2">
        <div>Firmware : <span className="text-ink font-mono">{twin.firmware || "—"}</span></div>
        <div>Hardware : <span className="text-ink font-mono">{twin.hardware || "—"}</span></div>
        <div className="col-span-2">
          Dernière sonde :{" "}
          <span className="text-ink">{twin.last_probed_at ? fmtRelative(twin.last_probed_at) : "jamais"}</span>
        </div>
      </div>
    </div>
  );
}

function fmtPct(v: number | null | undefined): string {
  return v != null ? `${v.toFixed(0)}%` : "—";
}
function fmtTemp(v: number | null | undefined): string {
  return v != null ? `${v.toFixed(1)}°C` : "—";
}
function fmtUptime(seconds: number | null | undefined): string {
  if (seconds == null) return "—";
  const d = Math.floor(seconds / 86400);
  const h = Math.floor((seconds % 86400) / 3600);
  if (d > 0) return `${d}j ${h}h`;
  const m = Math.floor((seconds % 3600) / 60);
  return h > 0 ? `${h}h ${m}m` : `${m}m`;
}
