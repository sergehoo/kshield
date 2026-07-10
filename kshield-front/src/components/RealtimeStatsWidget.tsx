/**
 * RealtimeStatsWidget — bandeau compact affichant les compteurs temps réel.
 *
 * Poll /devices/stats/realtime/ toutes les 10 s + refresh instantané sur WS events.
 * S'affiche sur le Dashboard, sous les KPIs métiers standards.
 */
import { useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Cpu, Server, Radar, Terminal, ShieldAlert, Zap, TrendingUp, CheckCircle2,
} from "lucide-react";

import { Card } from "@/components/ui/Card";
import { realtimeStatsService } from "@/services/enrollment";
import { useDeviceStatusChannel } from "@/hooks/useDeviceStatusChannel";
import { cn } from "@/lib/cn";

// Shape par défaut si l'endpoint renvoie du vide/partiel — évite les crashes
// de type "Cannot read properties of undefined (reading 'online')".
const EMPTY_STATS = {
  devices:    { online: 0, total: 0, online_ratio: 0 },
  agents:     { connected: 0, total: 0, disconnected: 0 },
  enrollment: { sessions_active: 0, scans_last_hour: 0, enrolled_last_24h: 0 },
  commands:   { completed_last_hour: 0, total_last_hour: 0, success_ratio: 0 },
  alerts:     { total: 0, critical: 0, warning: 0 },
};

export function RealtimeStatsWidget() {
  const qc = useQueryClient();

  const { data: raw } = useQuery({
    queryKey: ["realtime-stats"],
    queryFn: async () => (await realtimeStatsService.get()).data,
    refetchInterval: 10_000,
    retry: 1, // pas de spam en cas d'endpoint HS
  });

  useDeviceStatusChannel({
    onEvent: (evt: any) => {
      // Refresh sur événements pertinents
      const t = evt?.event;
      if (t && (t.startsWith("device.") || t.startsWith("agent.")
                 || t.startsWith("rfid.") || t === "session.completed")) {
        qc.invalidateQueries({ queryKey: ["realtime-stats"] });
      }
    },
  });

  // Merge défensif : fusionne le shape par défaut avec ce qui est arrivé.
  // Protège contre : data undefined, data.devices undefined, propriétés
  // manquantes après un changement de schéma serveur.
  const data = {
    devices:    { ...EMPTY_STATS.devices,    ...(raw?.devices    ?? {}) },
    agents:     { ...EMPTY_STATS.agents,     ...(raw?.agents     ?? {}) },
    enrollment: { ...EMPTY_STATS.enrollment, ...(raw?.enrollment ?? {}) },
    commands:   { ...EMPTY_STATS.commands,   ...(raw?.commands   ?? {}) },
    alerts:     { ...EMPTY_STATS.alerts,     ...(raw?.alerts     ?? {}) },
  };

  // Si aucune data n'a encore été chargée, ne pas monter le widget.
  if (!raw) return null;

  const agentsHalfDown = data.agents.total > 0
    && data.agents.disconnected < data.agents.total / 2;

  const tiles: TileProps[] = [
    {
      label: "Terminaux",
      value: `${data.devices.online}/${data.devices.total}`,
      hint: `${data.devices.online_ratio}% en ligne`,
      icon: <Cpu className="w-4 h-4" />,
      tone: data.devices.online_ratio >= 90 ? "ok"
            : data.devices.online_ratio >= 70 ? "warn" : "danger",
    },
    {
      label: "Agents locaux",
      value: `${data.agents.connected}/${data.agents.total}`,
      hint: `${data.agents.disconnected} hors ligne`,
      icon: <Server className="w-4 h-4" />,
      tone: data.agents.disconnected === 0 ? "ok"
            : agentsHalfDown ? "warn" : "danger",
    },
    {
      label: "Sessions actives",
      value: data.enrollment.sessions_active,
      hint: `${data.enrollment.scans_last_hour} scans (1h)`,
      icon: <Radar className="w-4 h-4" />,
      tone: "info",
    },
    {
      label: "Enrôlés 24h",
      value: data.enrollment.enrolled_last_24h,
      hint: "badges créés",
      icon: <TrendingUp className="w-4 h-4" />,
      tone: "ok",
    },
    {
      label: "Commandes 1h",
      value: `${data.commands.completed_last_hour}/${data.commands.total_last_hour}`,
      hint: `${data.commands.success_ratio}% de réussite`,
      icon: <Terminal className="w-4 h-4" />,
      tone: data.commands.success_ratio >= 95 ? "ok"
            : data.commands.success_ratio >= 80 ? "warn" : "danger",
    },
    {
      label: "Alertes actives",
      value: data.alerts.total,
      hint: `${data.alerts.critical} crit. · ${data.alerts.warning} warn`,
      icon: <ShieldAlert className="w-4 h-4" />,
      tone: data.alerts.critical > 0 ? "danger"
            : data.alerts.warning > 0 ? "warn" : "ok",
    },
  ];

  return (
    <div className="mb-4">
      <div className="flex items-center gap-2 mb-2">
        <Zap className="w-3.5 h-3.5 text-info animate-pulse" />
        <span className="text-xs font-medium text-ink-muted uppercase tracking-wider">
          Métriques temps réel
        </span>
      </div>
      <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-2">
        {tiles.map((t, i) => <MiniTile key={i} {...t} />)}
      </div>
    </div>
  );
}

interface TileProps {
  label: string;
  value: string | number;
  hint?: string;
  icon: React.ReactNode;
  tone: "ok" | "warn" | "danger" | "info";
}

const TONE_MAP: Record<TileProps["tone"], string> = {
  ok:     "border-success/20 bg-success/5",
  warn:   "border-warning/20 bg-warning/5",
  danger: "border-danger/20 bg-danger/5",
  info:   "border-info/20 bg-info/5",
};

const TONE_ICON: Record<TileProps["tone"], string> = {
  ok: "text-success", warn: "text-warning", danger: "text-danger", info: "text-info",
};

function MiniTile({ label, value, hint, icon, tone }: TileProps) {
  return (
    <div className={cn("rounded-md border p-2.5", TONE_MAP[tone])}>
      <div className="flex items-center gap-1.5 text-[10px] uppercase tracking-wider text-ink-muted">
        <span className={TONE_ICON[tone]}>{icon}</span>
        <span>{label}</span>
      </div>
      <div className="mt-1 text-lg font-bold text-ink">{value}</div>
      {hint && <div className="text-[10px] text-ink-muted mt-0.5">{hint}</div>}
    </div>
  );
}
