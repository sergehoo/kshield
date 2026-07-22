/**
 * KAYDAN SHIELD — Page Maintenance prédictive (Vague 8).
 *
 * Liste des tickets ouverts avec filtres + résolution/assignation inline.
 * Poll REST toutes les 30 s + refresh WS sur changement device.
 */
import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import {
  Wrench, Battery, HardDrive, Thermometer, WifiOff, ScanLine,
  AlertTriangle, XCircle, Info, CheckCircle2, Search, RefreshCw, Cpu,
} from "lucide-react";
import toast from "react-hot-toast";

import { PageHeader } from "@/components/PageHeader";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Badge } from "@/components/ui/Badge";
import { StatsRow } from "@/components/StatsRow";
import { maintenanceService, MaintenanceTicket } from "@/services/enrollment";
import { cn } from "@/lib/cn";
import { fmtDateTime, fmtRelative } from "@/lib/format";

const KIND_ICONS: Record<string, any> = {
  battery_low:          <Battery className="w-3.5 h-3.5" />,
  battery_critical:     <Battery className="w-3.5 h-3.5" />,
  storage_low:          <HardDrive className="w-3.5 h-3.5" />,
  storage_critical:     <HardDrive className="w-3.5 h-3.5" />,
  temperature_high:     <Thermometer className="w-3.5 h-3.5" />,
  temperature_critical: <Thermometer className="w-3.5 h-3.5" />,
  connectivity_loss:    <WifiOff className="w-3.5 h-3.5" />,
  firmware_outdated:    <ScanLine className="w-3.5 h-3.5" />,
  high_error_rate:      <AlertTriangle className="w-3.5 h-3.5" />,
  manual:               <Wrench className="w-3.5 h-3.5" />,
};

const SEV_META = {
  critical: { color: "text-danger",  icon: <XCircle className="w-4 h-4" />,       label: "Critique" },
  warning:  { color: "text-warning", icon: <AlertTriangle className="w-4 h-4" />, label: "Avertissement" },
  info:     { color: "text-info",    icon: <Info className="w-4 h-4" />,          label: "Info" },
};

export function MaintenancePage() {
  const qc = useQueryClient();
  const [q, setQ] = useState("");
  const [sevFilter, setSevFilter] = useState<"" | "critical" | "warning" | "info">("");
  const [statusFilter, setStatusFilter] = useState<"open" | "in_progress" | "resolved" | "all">("open");

  const { data, isFetching, refetch } = useQuery({
    queryKey: ["maintenance-tickets", statusFilter, sevFilter],
    queryFn: async () => (await maintenanceService.list({
      status: statusFilter === "all" ? "open,in_progress,resolved" : statusFilter,
      severity: sevFilter || undefined,
      limit: 500,
    })).data,
    refetchInterval: 30_000,
  });

  const filtered = useMemo(() => {
    const list = data?.tickets || [];
    if (!q) return list;
    const needle = q.toLowerCase();
    return list.filter((t) =>
      `${t.title} ${t.description} ${t.device_serial ?? ""}`.toLowerCase().includes(needle),
    );
  }, [data, q]);

  const stats = useMemo(() => {
    const list = data?.tickets || [];
    return {
      total: list.length,
      critical: list.filter((t) => t.severity === "critical" && t.status !== "resolved").length,
      warning: list.filter((t) => t.severity === "warning" && t.status !== "resolved").length,
      info: list.filter((t) => t.severity === "info" && t.status !== "resolved").length,
      auto: list.filter((t) => t.created_by_engine).length,
    };
  }, [data]);

  const updateStatusMut = useMutation({
    mutationFn: ({ id, status }: {
      id: string; status: "open" | "in_progress" | "resolved" | "cancelled";
    }) => maintenanceService.update(id, { status }),
    onSuccess: () => {
      toast.success("Ticket mis à jour");
      qc.invalidateQueries({ queryKey: ["maintenance-tickets"] });
    },
  });

  return (
    <div>
      <PageHeader
        title="Maintenance prédictive"
        subtitle={`${stats.total} ticket${stats.total > 1 ? "s" : ""} · ${stats.auto} générés automatiquement`}
        actions={
          <Button size="sm" variant="ghost"
                  leftIcon={<RefreshCw className={cn("w-3.5 h-3.5", isFetching && "animate-spin")} />}
                  onClick={() => refetch()}>
            Actualiser
          </Button>
        }
      />

      <StatsRow stats={[
        { label: "Critiques", value: stats.critical, icon: <XCircle className="w-4 h-4" />, tone: "danger",
          onClick: () => { setSevFilter("critical"); setStatusFilter("open"); } },
        { label: "Avertissements", value: stats.warning, icon: <AlertTriangle className="w-4 h-4" />, tone: "warn",
          onClick: () => { setSevFilter("warning"); setStatusFilter("open"); } },
        { label: "Infos", value: stats.info, icon: <Info className="w-4 h-4" />, tone: "info" },
        { label: "Auto-générés", value: stats.auto, icon: <Cpu className="w-4 h-4" />, tone: "brand" },
      ]} />

      <Card padded={false}>
        {/* Filtres */}
        <div className="p-3 border-b border-surface-border flex flex-col md:flex-row gap-2">
          <div className="flex-1">
            <Input placeholder="Rechercher…" value={q}
                   onChange={(e) => setQ(e.target.value)}
                   leftIcon={<Search className="w-4 h-4" />} />
          </div>
          <select className="field md:w-40" value={statusFilter}
                  onChange={(e) => setStatusFilter(e.target.value as any)}>
            <option value="open">Ouverts</option>
            <option value="in_progress">En cours</option>
            <option value="resolved">Résolus</option>
            <option value="all">Tous</option>
          </select>
          <select className="field md:w-40" value={sevFilter}
                  onChange={(e) => setSevFilter(e.target.value as any)}>
            <option value="">Toutes sévérités</option>
            <option value="critical">Critiques</option>
            <option value="warning">Avertissements</option>
            <option value="info">Infos</option>
          </select>
        </div>

        {filtered.length === 0 ? (
          <div className="p-12 text-center text-ink-muted text-sm">
            Aucun ticket ne correspond à ces filtres.
          </div>
        ) : (
          <div className="divide-y divide-surface-border">
            {filtered.map((t) => {
              const sev = SEV_META[t.severity];
              return (
                <div key={t.id} className={cn(
                  "p-3 hover:bg-surface-soft/40 flex items-center gap-3",
                  t.status === "resolved" && "opacity-60",
                )}>
                  <span className={cn("shrink-0", sev.color)}>{sev.icon}</span>
                  <span className="text-ink-muted shrink-0">{KIND_ICONS[t.kind] || <Wrench className="w-3.5 h-3.5" />}</span>
                  <div className="flex-1 min-w-0">
                    <div className="text-sm font-medium text-ink truncate">
                      <Link to={`/devices/${t.device_id}`} className="hover:underline">
                        {t.title}
                      </Link>
                    </div>
                    <div className="text-xs text-ink-muted truncate">
                      {t.device_serial && <span className="font-mono">{t.device_serial} · </span>}
                      {t.description}
                    </div>
                  </div>
                  <div className="text-xs text-ink-muted shrink-0 hidden md:flex flex-col items-end">
                    {t.created_by_engine && (
                      <span className="text-[10px] text-brand-ink">
                        auto · conf {Math.round(t.confidence * 100)}%
                      </span>
                    )}
                    <span>{fmtRelative(t.created_at)}</span>
                  </div>
                  <Badge tone={t.status === "resolved" ? "ok"
                                : t.status === "in_progress" ? "info" : "warn"}>
                    {t.status}
                  </Badge>
                  {t.status !== "resolved" && (
                    <div className="flex gap-1">
                      {t.status === "open" && (
                        <button onClick={() => updateStatusMut.mutate({ id: t.id, status: "in_progress" })}
                                className="p-1.5 rounded hover:bg-info/10 text-info"
                                title="Prendre en charge">
                          <Wrench className="w-3.5 h-3.5" />
                        </button>
                      )}
                      <button onClick={() => updateStatusMut.mutate({ id: t.id, status: "resolved" })}
                              className="p-1.5 rounded hover:bg-success/10 text-success"
                              title="Résoudre">
                        <CheckCircle2 className="w-3.5 h-3.5" />
                      </button>
                    </div>
                  )}
                </div>
              );
            })}
          </div>
        )}
      </Card>
    </div>
  );
}
