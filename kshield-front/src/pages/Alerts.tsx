/**
 * KAYDAN SHIELD — Historique des alertes système.
 *
 * Vue complète permettant de :
 *   - Filtrer par sévérité, type, statut (actives / résolues)
 *   - Rechercher par titre ou détail
 *   - Reconnaître plusieurs alertes en lot
 *   - Naviguer vers l'entité concernée en un clic
 */
import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import {
  AlertTriangle, XCircle, Info, Server, Cpu, Radar, Terminal,
  Check, RefreshCw, Search, Filter,
} from "lucide-react";
import toast from "react-hot-toast";

import { PageHeader } from "@/components/PageHeader";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Badge } from "@/components/ui/Badge";
import { StatsRow } from "@/components/StatsRow";
import { systemAlertsService, SystemAlert } from "@/services/enrollment";
import { useDeviceStatusChannel } from "@/hooks/useDeviceStatusChannel";
import { cn } from "@/lib/cn";
import { fmtDateTime, fmtRelative } from "@/lib/format";

const TYPE_LABELS: Record<SystemAlert["type"], { label: string; icon: any }> = {
  agent_offline:   { label: "Agent hors ligne",     icon: <Server className="w-3.5 h-3.5" /> },
  agent_stale:     { label: "Agent stale",          icon: <Server className="w-3.5 h-3.5" /> },
  device_offline:  { label: "Terminal hors ligne",  icon: <Cpu className="w-3.5 h-3.5" /> },
  session_stalled: { label: "Session bloquée",      icon: <Radar className="w-3.5 h-3.5" /> },
  command_timeout: { label: "Commande timeout",     icon: <Terminal className="w-3.5 h-3.5" /> },
};

const SEV_META: Record<SystemAlert["severity"], { color: string; icon: any; label: string }> = {
  critical: { color: "text-danger",  icon: <XCircle className="w-4 h-4" />,       label: "Critique" },
  warning:  { color: "text-warning", icon: <AlertTriangle className="w-4 h-4" />, label: "Avertissement" },
  info:     { color: "text-info",    icon: <Info className="w-4 h-4" />,          label: "Info" },
};

export function AlertsPage() {
  const qc = useQueryClient();
  const [q, setQ] = useState("");
  const [sevFilter, setSevFilter] = useState<"" | SystemAlert["severity"]>("");
  const [typeFilter, setTypeFilter] = useState<"" | SystemAlert["type"]>("");
  const [statusFilter, setStatusFilter] = useState<"active" | "resolved" | "all">("active");
  const [selected, setSelected] = useState<Set<string>>(new Set());

  const { data, isFetching, refetch } = useQuery({
    queryKey: ["alerts-history", statusFilter],
    queryFn: async () => (await systemAlertsService.list({
      include_resolved: statusFilter !== "active",
      limit: 500,
    })).data,
    refetchInterval: 30_000,
  });

  useDeviceStatusChannel({
    onEvent: (evt: any) => {
      const t = evt?.event;
      if (t === "agent.disconnected" || t === "agent.stale"
          || t === "device.disconnected" || t === "device.command.failed") {
        qc.invalidateQueries({ queryKey: ["alerts-history"] });
      }
    },
  });

  const filtered = useMemo(() => {
    const list = data?.alerts || [];
    return list.filter((a) => {
      if (statusFilter === "resolved" && !a.resolved_at) return false;
      if (statusFilter === "active" && a.resolved_at) return false;
      if (sevFilter && a.severity !== sevFilter) return false;
      if (typeFilter && a.type !== typeFilter) return false;
      if (q) {
        const needle = q.toLowerCase();
        const hay = `${a.title} ${a.detail}`.toLowerCase();
        if (!hay.includes(needle)) return false;
      }
      return true;
    });
  }, [data, sevFilter, typeFilter, statusFilter, q]);

  const stats = useMemo(() => {
    const list = data?.alerts || [];
    return {
      total: list.length,
      critical: list.filter((a) => a.severity === "critical" && !a.resolved_at).length,
      warning:  list.filter((a) => a.severity === "warning"  && !a.resolved_at).length,
      info:     list.filter((a) => a.severity === "info"     && !a.resolved_at).length,
      acknowledged: list.filter((a) => a.acknowledged_at && !a.resolved_at).length,
      resolved: list.filter((a) => a.resolved_at).length,
    };
  }, [data]);

  const ackOneMut = useMutation({
    mutationFn: (id: string) => systemAlertsService.acknowledge(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["alerts-history"] }),
  });

  const ackBulkMut = useMutation({
    mutationFn: async (ids: string[]) => {
      await Promise.all(ids.map((id) => systemAlertsService.acknowledge(id)));
    },
    onSuccess: () => {
      toast.success(`${selected.size} alerte${selected.size > 1 ? "s reconnues" : " reconnue"}`);
      setSelected(new Set());
      qc.invalidateQueries({ queryKey: ["alerts-history"] });
    },
  });

  const toggleSelect = (id: string) => {
    const next = new Set(selected);
    if (next.has(id)) next.delete(id);
    else next.add(id);
    setSelected(next);
  };

  const toggleAll = () => {
    if (selected.size === filtered.length) setSelected(new Set());
    else setSelected(new Set(filtered.map((a) => a.id)));
  };

  return (
    <div>
      <PageHeader
        title="Alertes système"
        subtitle={`${stats.total} alerte${stats.total > 1 ? "s" : ""} au total`}
        live
        actions={
          <div className="flex items-center gap-2">
            {selected.size > 0 && (
              <Button size="sm" variant="secondary"
                      leftIcon={<Check className="w-3.5 h-3.5" />}
                      onClick={() => ackBulkMut.mutate(Array.from(selected))}
                      loading={ackBulkMut.isPending}>
                Reconnaître ({selected.size})
              </Button>
            )}
            <Button size="sm" variant="ghost"
                    leftIcon={<RefreshCw className={cn("w-3.5 h-3.5",
                                                        isFetching && "animate-spin")} />}
                    onClick={() => refetch()}>
              Actualiser
            </Button>
          </div>
        }
      />

      <StatsRow stats={[
        { label: "Critiques", value: stats.critical,
          icon: <XCircle className="w-4 h-4" />, tone: "danger",
          onClick: () => { setSevFilter("critical"); setStatusFilter("active"); } },
        { label: "Avertissements", value: stats.warning,
          icon: <AlertTriangle className="w-4 h-4" />, tone: "warn",
          onClick: () => { setSevFilter("warning"); setStatusFilter("active"); } },
        { label: "Infos", value: stats.info,
          icon: <Info className="w-4 h-4" />, tone: "info",
          onClick: () => { setSevFilter("info"); setStatusFilter("active"); } },
        { label: "Reconnues", value: stats.acknowledged,
          icon: <Check className="w-4 h-4" />, tone: "muted" },
        { label: "Résolues", value: stats.resolved,
          icon: <Check className="w-4 h-4" />, tone: "ok",
          onClick: () => setStatusFilter("resolved") },
      ]} />

      <Card padded={false}>
        {/* Barre de filtres */}
        <div className="p-3 border-b border-surface-border flex flex-col md:flex-row gap-2">
          <div className="flex-1">
            <Input placeholder="Rechercher…" value={q}
                   onChange={(e) => setQ(e.target.value)}
                   leftIcon={<Search className="w-4 h-4" />} />
          </div>
          <select className="field md:w-40" value={statusFilter}
                  onChange={(e) => setStatusFilter(e.target.value as any)}>
            <option value="active">Actives seulement</option>
            <option value="resolved">Résolues seulement</option>
            <option value="all">Toutes (actives + résolues)</option>
          </select>
          <select className="field md:w-40" value={sevFilter}
                  onChange={(e) => setSevFilter(e.target.value as any)}>
            <option value="">Toutes sévérités</option>
            <option value="critical">Critiques</option>
            <option value="warning">Avertissements</option>
            <option value="info">Infos</option>
          </select>
          <select className="field md:w-52" value={typeFilter}
                  onChange={(e) => setTypeFilter(e.target.value as any)}>
            <option value="">Tous types</option>
            {Object.entries(TYPE_LABELS).map(([k, v]) => (
              <option key={k} value={k}>{v.label}</option>
            ))}
          </select>
          {(sevFilter || typeFilter || q || statusFilter !== "active") && (
            <Button variant="ghost" size="sm" onClick={() => {
              setSevFilter(""); setTypeFilter(""); setQ("");
              setStatusFilter("active");
            }}>
              <Filter className="w-3.5 h-3.5 mr-1" />
              Réinitialiser
            </Button>
          )}
        </div>

        {/* Table */}
        {filtered.length === 0 ? (
          <div className="p-12 text-center text-ink-muted text-sm">
            Aucune alerte ne correspond à ces filtres.
          </div>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="bg-surface-soft/60 text-xs uppercase tracking-wider text-ink-muted">
                <tr>
                  <th className="p-2 w-8">
                    <input type="checkbox"
                           checked={selected.size === filtered.length && filtered.length > 0}
                           onChange={toggleAll} />
                  </th>
                  <th className="p-2 text-left">Sév.</th>
                  <th className="p-2 text-left">Type</th>
                  <th className="p-2 text-left">Titre</th>
                  <th className="p-2 text-left">Détail</th>
                  <th className="p-2 text-left">Créée</th>
                  <th className="p-2 text-left">Statut</th>
                  <th className="p-2"></th>
                </tr>
              </thead>
              <tbody className="divide-y divide-surface-border">
                {filtered.map((a) => {
                  const sev = SEV_META[a.severity];
                  const type = TYPE_LABELS[a.type];
                  return (
                    <tr key={a.id} className={cn(
                      "hover:bg-surface-soft/40",
                      a.acknowledged_at && !a.resolved_at && "opacity-70",
                      a.resolved_at && "opacity-50",
                    )}>
                      <td className="p-2">
                        <input type="checkbox"
                               checked={selected.has(a.id)}
                               onChange={() => toggleSelect(a.id)}
                               disabled={!!a.resolved_at} />
                      </td>
                      <td className="p-2">
                        <span className={cn("inline-flex items-center gap-1", sev.color)}>
                          {sev.icon}
                          <span className="text-xs">{sev.label}</span>
                        </span>
                      </td>
                      <td className="p-2">
                        <span className="inline-flex items-center gap-1 text-ink-muted text-xs">
                          {type?.icon}
                          <span>{type?.label || a.type}</span>
                        </span>
                      </td>
                      <td className="p-2 font-medium text-ink">
                        {a.target_url ? (
                          <Link to={a.target_url} className="hover:underline">
                            {a.title}
                          </Link>
                        ) : a.title}
                      </td>
                      <td className="p-2 text-ink-muted text-xs max-w-md truncate">
                        {a.detail}
                      </td>
                      <td className="p-2 text-ink-muted text-xs" title={fmtDateTime(a.since)}>
                        {a.since ? fmtRelative(a.since) : "—"}
                      </td>
                      <td className="p-2">
                        {a.resolved_at ? (
                          <Badge tone="ok">Résolue</Badge>
                        ) : a.acknowledged_at ? (
                          <Badge tone="muted">Reconnue</Badge>
                        ) : (
                          <Badge tone={a.severity === "critical" ? "danger"
                                       : a.severity === "warning" ? "warn" : "info"}>
                            Active
                          </Badge>
                        )}
                      </td>
                      <td className="p-2">
                        {!a.acknowledged_at && !a.resolved_at && (
                          <button
                            onClick={() => ackOneMut.mutate(a.id)}
                            className="p-1.5 rounded-md hover:bg-success/10 text-ink-muted hover:text-success"
                            title="Reconnaître">
                            <Check className="w-3.5 h-3.5" />
                          </button>
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </Card>
    </div>
  );
}
