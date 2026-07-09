/**
 * SystemAlertsBanner — bannière temps réel affichant les problèmes actifs.
 *
 * Combinaison de :
 *   1. Poll REST /devices/alerts/system/ toutes les 30s
 *   2. Refresh instantané dès qu'un event WS agent.stale/device.disconnected arrive
 *
 * Affichée en haut du Dashboard. Se replie / se déplie automatiquement selon la
 * présence d'alertes.
 */
import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import {
  AlertTriangle, XCircle, Info, ChevronDown, ChevronUp,
  Server, Cpu, Radar, Terminal, RefreshCw, X, Check, RotateCw, Activity,
} from "lucide-react";
import toast from "react-hot-toast";

import { systemAlertsService, SystemAlert, localAgentsService, deviceCommandService } from "@/services/enrollment";
import { useDeviceStatusChannel } from "@/hooks/useDeviceStatusChannel";
import { cn } from "@/lib/cn";
import { fmtRelative } from "@/lib/format";

const TYPE_ICONS: Record<SystemAlert["type"], any> = {
  agent_offline:   <Server className="w-3.5 h-3.5" />,
  device_offline:  <Cpu className="w-3.5 h-3.5" />,
  session_stalled: <Radar className="w-3.5 h-3.5" />,
  command_timeout: <Terminal className="w-3.5 h-3.5" />,
};

const SEV_META: Record<SystemAlert["severity"], { color: string; icon: any; label: string }> = {
  critical: { color: "bg-danger/5 border-danger/40 text-danger",
              icon: <XCircle className="w-4 h-4" />, label: "critique" },
  warning:  { color: "bg-warning/5 border-warning/30 text-warning",
              icon: <AlertTriangle className="w-4 h-4" />, label: "avertissement" },
  info:     { color: "bg-info/5 border-info/20 text-info",
              icon: <Info className="w-4 h-4" />, label: "info" },
};

export function SystemAlertsBanner({ collapsible = true }: { collapsible?: boolean }) {
  const qc = useQueryClient();
  const [expanded, setExpanded] = useState(true);
  const [dismissed, setDismissed] = useState<Set<string>>(new Set());

  const { data, isFetching, refetch, dataUpdatedAt } = useQuery({
    queryKey: ["system-alerts"],
    queryFn: async () => (await systemAlertsService.list()).data,
    refetchInterval: 30_000,
  });

  // Refresh instantané sur événement WS pertinent
  useDeviceStatusChannel({
    onEvent: (evt: any) => {
      const t = evt?.event;
      if (t === "agent.disconnected" || t === "agent.stale"
          || t === "device.disconnected" || t === "device.command.failed") {
        qc.invalidateQueries({ queryKey: ["system-alerts"] });
      }
    },
  });

  const visible = useMemo(
    () => (data?.alerts || []).filter((a) => !dismissed.has(a.id)),
    [data, dismissed],
  );

  if (!data || visible.length === 0) return null;

  const critical = visible.filter((a) => a.severity === "critical").length;
  const warning = visible.filter((a) => a.severity === "warning").length;

  const outerColor = critical > 0
    ? "border-danger/40 bg-danger/5"
    : warning > 0
    ? "border-warning/30 bg-warning/5"
    : "border-info/20 bg-info/5";

  return (
    <div className={cn("rounded-lg border mb-4", outerColor)}>
      <div className="flex items-center gap-2 p-3">
        <AlertTriangle className={cn("w-4 h-4",
                                       critical > 0 ? "text-danger"
                                       : warning > 0 ? "text-warning" : "text-info")} />
        <div className="text-sm font-medium text-ink">
          {visible.length} alerte{visible.length > 1 ? "s" : ""} système
          {critical > 0 && <span className="text-danger"> · {critical} critique{critical > 1 ? "s" : ""}</span>}
          {warning > 0 && <span className="text-warning"> · {warning} avertissement{warning > 1 ? "s" : ""}</span>}
        </div>
        <div className="ml-auto flex items-center gap-1 text-xs text-ink-muted">
          {dataUpdatedAt && <span>MàJ {fmtRelative(new Date(dataUpdatedAt).toISOString())}</span>}
          <button onClick={() => refetch()} className="p-1 hover:text-ink" title="Actualiser">
            <RefreshCw className={cn("w-3.5 h-3.5", isFetching && "animate-spin")} />
          </button>
          {collapsible && (
            <button onClick={() => setExpanded((e) => !e)}
                    className="p-1 hover:text-ink" title={expanded ? "Réduire" : "Déplier"}>
              {expanded ? <ChevronUp className="w-3.5 h-3.5" /> : <ChevronDown className="w-3.5 h-3.5" />}
            </button>
          )}
        </div>
      </div>

      {expanded && (
        <div className="border-t border-current/10 divide-y divide-current/10">
          {visible.map((a) => (
            <AlertRow key={a.id} alert={a} onDismiss={() => {
              const next = new Set(dismissed);
              next.add(a.id);
              setDismissed(next);
            }} />
          ))}
        </div>
      )}
    </div>
  );
}

function AlertRow({ alert, onDismiss }: { alert: SystemAlert; onDismiss: () => void }) {
  const meta = SEV_META[alert.severity];
  const qc = useQueryClient();

  const ackMut = useMutation({
    mutationFn: () => systemAlertsService.acknowledge(alert.id),
    onSuccess: () => {
      toast.success("Alerte reconnue");
      qc.invalidateQueries({ queryKey: ["system-alerts"] });
    },
  });

  // Action contextuelle selon le type d'alerte
  const rotateAgentMut = useMutation({
    mutationFn: () => localAgentsService.rotateToken(alert.target_id!),
    onSuccess: () => {
      toast.success("Token régénéré — reconfigure l'agent");
      qc.invalidateQueries({ queryKey: ["system-alerts"] });
    },
    onError: () => toast.error("Rotation impossible"),
  });

  const pingDeviceMut = useMutation({
    mutationFn: () => deviceCommandService.send(Number(alert.target_id), "PING_DEVICE"),
    onSuccess: () => toast.success("Ping envoyé"),
    onError: () => toast.error("Ping impossible"),
  });

  const content = (
    <>
      <span className={cn("shrink-0", meta.color.split(" ")[2])}>{meta.icon}</span>
      <span className="text-ink-muted shrink-0">{TYPE_ICONS[alert.type]}</span>
      <div className="flex-1 min-w-0">
        <div className="text-sm font-medium text-ink truncate">{alert.title}</div>
        <div className="text-xs text-ink-muted truncate">{alert.detail}</div>
      </div>
      {alert.since && (
        <span className="text-xs text-ink-muted shrink-0">
          {fmtRelative(alert.since)}
        </span>
      )}
    </>
  );

  const showActions = !alert.acknowledged_at;

  return (
    <div className={cn("flex items-center gap-2 p-2.5 hover:bg-surface-soft/50 group",
                        alert.acknowledged_at && "opacity-60")}>
      {alert.target_url ? (
        <Link to={alert.target_url} className="flex-1 flex items-center gap-2 min-w-0">
          {content}
        </Link>
      ) : (
        <div className="flex-1 flex items-center gap-2 min-w-0">{content}</div>
      )}

      <div className="flex items-center gap-0.5 opacity-0 group-hover:opacity-100 transition">
        {/* Action contextuelle selon type */}
        {showActions && alert.type === "agent_offline" && alert.target_id && (
          <button
            onClick={(e) => { e.stopPropagation();
              if (confirm("Régénérer le token de cet agent ? L'ancien deviendra invalide."))
                rotateAgentMut.mutate();
            }}
            className="p-1 text-ink-muted hover:text-warning" title="Rotate token"
          >
            <RotateCw className="w-3.5 h-3.5" />
          </button>
        )}
        {showActions && alert.type === "device_offline" && alert.target_id && (
          <button
            onClick={(e) => { e.stopPropagation(); pingDeviceMut.mutate(); }}
            className="p-1 text-ink-muted hover:text-info" title="Ping"
          >
            <Activity className="w-3.5 h-3.5" />
          </button>
        )}
        {showActions && (
          <button
            onClick={(e) => { e.stopPropagation(); ackMut.mutate(); }}
            className="p-1 text-ink-muted hover:text-success"
            title="Reconnaître l'alerte"
          >
            <Check className="w-3.5 h-3.5" />
          </button>
        )}
        <button
          onClick={(e) => { e.stopPropagation(); onDismiss(); }}
          className="p-1 text-ink-muted hover:text-danger"
          title="Masquer pour cette session"
        >
          <X className="w-3.5 h-3.5" />
        </button>
      </div>
    </div>
  );
}
