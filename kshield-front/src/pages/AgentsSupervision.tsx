/**
 * AgentsSupervision — page principale Phase 6 (cahier §5).
 *
 * Liste des agents locaux avec état, métriques temps réel, filtres par
 * site/type/état, recherche, et lien vers la fiche détail.
 *
 * La donnée provient de GET /api/v1/devices/agents/ et est rafraîchie
 * toutes les 10 s. Les événements WebSocket "agent.heartbeat" pourraient
 * être branchés plus tard, mais le polling suffit ici (10 s de latence).
 */
import { useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import {
  Cpu, HardDrive, Activity, Layers, Search, Wifi, WifiOff,
  ArrowRight, RefreshCcw, AlertTriangle,
} from "lucide-react";

import { PageHeader } from "@/components/PageHeader";
import { Card } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { Input } from "@/components/ui/Input";
import { StatsRow, Stat } from "@/components/StatsRow";
import { fmtRelative } from "@/lib/format";
import { cn } from "@/lib/cn";
import {
  agentsService, STATE_LABELS, STATE_TONES,
  AgentState, AgentSummaryDTO,
} from "@/services/agents";

const STATE_FILTERS: (AgentState | "all")[] = [
  "all", "running", "degraded", "unreachable", "crashed",
  "stopped", "disabled", "updating",
];

export function AgentsSupervisionPage() {
  const [q, setQ] = useState("");
  const [stateFilter, setStateFilter] = useState<AgentState | "all">("all");
  const [typeFilter, setTypeFilter] = useState<string>("all");

  const { data, isLoading, refetch, isFetching } = useQuery({
    queryKey: ["agents", "list", { stateFilter, typeFilter }],
    queryFn: async () => (await agentsService.list({
      ...(stateFilter !== "all" ? { state: stateFilter } : {}),
      ...(typeFilter !== "all" ? { type: typeFilter } : {}),
      page_size: 100,
    })).data,
    refetchInterval: 10_000,
  });

  const { data: types } = useQuery({
    queryKey: ["agents", "types"],
    queryFn: async () => (await agentsService.types()).data,
  });

  const agents = data?.results ?? [];
  const filtered = useMemo(() => {
    if (!q.trim()) return agents;
    const needle = q.trim().toLowerCase();
    return agents.filter((a) =>
      a.name?.toLowerCase().includes(needle) ||
      a.site_label?.toLowerCase().includes(needle) ||
      a.type_label?.toLowerCase().includes(needle),
    );
  }, [agents, q]);

  const stats: Stat[] = useMemo(() => {
    const online = agents.filter((a) => a.is_online).length;
    const degraded = agents.filter(
      (a) => a.last_state === "degraded" || a.last_state === "unreachable",
    ).length;
    const crashed = agents.filter((a) => a.last_state === "crashed").length;
    const pending = agents.reduce((s, a) => s + (a.events_pending || 0), 0);
    return [
      { label: "Agents actifs",    value: online,          icon: <Wifi size={18} />,     tone: "ok" },
      { label: "Total agents",     value: agents.length,   icon: <Layers size={18} />,   tone: "brand" },
      { label: "Dégradés",         value: degraded,        icon: <AlertTriangle size={18} />, tone: "warn" },
      { label: "Crashés",          value: crashed,         icon: <WifiOff size={18} />,  tone: "danger" },
      { label: "Événements en file", value: pending,       icon: <Activity size={18} />, tone: "info" },
    ];
  }, [agents]);

  return (
    <div>
      <PageHeader
        title="Supervision des agents"
        subtitle="État en temps réel des agents locaux — métriques CPU / RAM / queue / erreurs."
        icon={<Cpu size={20} />}
        live={isFetching}
        actions={
          <button
            onClick={() => refetch()}
            className="inline-flex items-center gap-2 rounded-xl px-4 py-2.5 text-sm font-medium bg-ink text-white hover:bg-ink/85"
          >
            <RefreshCcw size={16} /> Rafraîchir
          </button>
        }
      />

      <StatsRow stats={stats} loading={isLoading} />

      {/* Filtres */}
      <Card className="mb-4" padded>
        <div className="flex flex-col md:flex-row md:items-center gap-3">
          <div className="relative flex-1 max-w-md">
            <Search
              size={16}
              className="absolute left-3 top-1/2 -translate-y-1/2 text-ink-muted"
            />
            <Input
              value={q}
              onChange={(e) => setQ(e.target.value)}
              placeholder="Rechercher un agent, un site, un type…"
              className="pl-9"
            />
          </div>

          <div className="flex items-center gap-2 flex-wrap">
            <span className="text-xs text-ink-muted uppercase tracking-wide">
              État
            </span>
            {STATE_FILTERS.map((s) => (
              <button
                key={s}
                onClick={() => setStateFilter(s)}
                className={cn(
                  "px-3 py-1.5 rounded-lg text-xs font-medium transition-colors",
                  stateFilter === s
                    ? "bg-ink text-white"
                    : "bg-ink/5 text-ink hover:bg-ink/10",
                )}
              >
                {s === "all" ? "Tous" : STATE_LABELS[s as AgentState]}
              </button>
            ))}
          </div>

          {types?.results?.length ? (
            <select
              value={typeFilter}
              onChange={(e) => setTypeFilter(e.target.value)}
              className="rounded-xl border border-surface-border bg-white px-3 py-2 text-sm text-ink"
            >
              <option value="all">Tous les types</option>
              {types.results.map((t) => (
                <option key={t.code} value={t.code}>{t.label}</option>
              ))}
            </select>
          ) : null}
        </div>
      </Card>

      {/* Grille des agents */}
      {isLoading ? (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
          {[...Array(6)].map((_, i) => (
            <div key={i} className="rounded-3xl bg-surface-soft/60 h-52 animate-pulse" />
          ))}
        </div>
      ) : filtered.length === 0 ? (
        <Card padded>
          <div className="py-14 text-center text-ink-muted">
            <WifiOff className="mx-auto mb-2 opacity-40" size={28} />
            <p className="text-sm">Aucun agent trouvé avec ces filtres.</p>
          </div>
        </Card>
      ) : (
        <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-4">
          {filtered.map((a) => (
            <AgentCard key={a.id} agent={a} />
          ))}
        </div>
      )}
    </div>
  );
}

function AgentCard({ agent }: { agent: AgentSummaryDTO }) {
  const tone = STATE_TONES[agent.last_state] ?? "muted";

  return (
    <Link
      to={`/agents/${agent.id}`}
      className="block rounded-3xl bg-surface-card p-5 shadow-dappr hover:shadow-lg transition-shadow"
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex items-center gap-2 flex-wrap">
            <h3 className="text-base font-semibold text-ink truncate max-w-[220px]">
              {agent.name || "(sans nom)"}
            </h3>
            <Badge tone={tone} dot>
              {STATE_LABELS[agent.last_state] ?? agent.last_state}
            </Badge>
          </div>
          <div className="mt-1 text-xs text-ink-muted flex items-center gap-2 flex-wrap">
            <span>{agent.type_label || agent.type_code}</span>
            <span aria-hidden>·</span>
            <span>{agent.site_label || "aucun site"}</span>
            {agent.version && (
              <>
                <span aria-hidden>·</span>
                <span className="font-mono">v{agent.version}</span>
              </>
            )}
          </div>
        </div>
        <ArrowRight size={16} className="text-ink-muted shrink-0" />
      </div>

      {/* Barres CPU / RAM / disque */}
      <div className="mt-4 space-y-2">
        <Bar label="CPU"    value={agent.cpu_percent}     icon={<Cpu size={12} />} />
        <Bar label="RAM"    value={agent.memory_percent}  icon={<Activity size={12} />} />
        <Bar label="Disque" value={agent.storage_percent} icon={<HardDrive size={12} />} />
      </div>

      {/* Métriques secondaires */}
      <div className="mt-4 grid grid-cols-3 gap-2 text-xs">
        <Metric label="File events"   value={agent.events_pending} tone={agent.events_pending > 500 ? "warn" : undefined} />
        <Metric label="Équipements"   value={`${agent.devices_connected}/${agent.devices_expected}`} tone={agent.devices_connected < agent.devices_expected ? "warn" : undefined} />
        <Metric label="Erreurs 1 h"   value={agent.errors_last_hour} tone={agent.errors_last_hour > 20 ? "danger" : undefined} />
      </div>

      <div className="mt-3 text-[11px] text-ink-muted">
        Dernier heartbeat :{" "}
        {agent.last_seen_at
          ? fmtRelative(agent.last_seen_at)
          : <span className="text-danger">jamais</span>}
      </div>
    </Link>
  );
}

function Bar({ label, value, icon }: { label: string; value: number; icon?: React.ReactNode }) {
  const pct = Math.max(0, Math.min(100, Math.round(value || 0)));
  const tone =
    pct >= 90 ? "bg-danger" :
    pct >= 70 ? "bg-warn" :
                "bg-ink";
  return (
    <div>
      <div className="flex items-center justify-between text-[11px] text-ink-muted mb-0.5">
        <span className="inline-flex items-center gap-1">{icon} {label}</span>
        <span className="font-mono tabular-nums">{pct}%</span>
      </div>
      <div className="h-1.5 rounded-full bg-ink/5 overflow-hidden">
        <div className={cn("h-full rounded-full transition-all", tone)} style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}

function Metric({ label, value, tone }: { label: string; value: React.ReactNode; tone?: "warn" | "danger" }) {
  return (
    <div className={cn(
      "rounded-xl px-2.5 py-2 text-center",
      tone === "danger" ? "bg-danger/10 text-danger" :
      tone === "warn"   ? "bg-warn/10 text-warn" :
                          "bg-ink/5 text-ink",
    )}>
      <div className="text-sm font-semibold tabular-nums leading-tight">{value}</div>
      <div className="text-[10px] uppercase tracking-wide opacity-70">{label}</div>
    </div>
  );
}

export default AgentsSupervisionPage;
