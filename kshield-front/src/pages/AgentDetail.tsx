/**
 * AgentDetailPage — fiche complète d'un agent local (Phase 6 §5).
 *
 * 4 onglets :
 *  1. Vue d'ensemble  — état + métriques temps réel + dernier heartbeat
 *  2. Heartbeats      — timeline paginée (100 derniers)
 *  3. Configurations  — versions + éditeur JSON + apply
 *  4. Logs            — tail des logs bufferisés (filtrable par niveau)
 *
 * Actions rapides : restart / stop / update / send-command.
 */
import { useState, useMemo } from "react";
import { useParams, Link } from "react-router-dom";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  ArrowLeft, Cpu, HardDrive, Activity, Wifi, WifiOff, RefreshCw,
  Play, Square, Download, FileCode2, ScrollText, Send,
  CheckCircle2, XCircle, AlertTriangle, Clock,
} from "lucide-react";
import toast from "react-hot-toast";

import { PageHeader } from "@/components/PageHeader";
import { Card } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { fmtRelative } from "@/lib/format";
import { cn } from "@/lib/cn";
import {
  agentsService, STATE_LABELS, STATE_TONES, LEVEL_TONES,
  LogLevel, AgentConfigurationDTO,
} from "@/services/agents";

type Tab = "overview" | "heartbeats" | "configs" | "logs";

export function AgentDetailPage() {
  const { id = "" } = useParams<{ id: string }>();
  const qc = useQueryClient();
  const [tab, setTab] = useState<Tab>("overview");

  const { data: agent, isLoading } = useQuery({
    queryKey: ["agents", "detail", id],
    queryFn: async () => (await agentsService.detail(id)).data,
    enabled: !!id,
    refetchInterval: 15_000,
  });

  const cmdMut = useMutation({
    mutationFn: (cmd: string) => agentsService.sendCommand(id, cmd),
    onSuccess: (_r, cmd) => toast.success(`Commande "${cmd}" envoyée`),
    onError: (e: any) => toast.error(e?.response?.data?.error || "Erreur"),
  });

  if (!id) return null;

  return (
    <div>
      <div className="mb-3">
        <Link
          to="/agents"
          className="inline-flex items-center gap-2 text-sm text-ink-muted hover:text-ink"
        >
          <ArrowLeft size={14} /> Supervision agents
        </Link>
      </div>

      <PageHeader
        title={agent?.name || "…"}
        subtitle={
          agent ? (
            <span className="flex items-center gap-2 flex-wrap">
              <Badge tone={STATE_TONES[agent.last_state] ?? "muted"} dot>
                {STATE_LABELS[agent.last_state] ?? agent.last_state}
              </Badge>
              <span className="text-ink-muted">
                {agent.type_label} · {agent.site_label || "aucun site"} · v{agent.version || "?"}
              </span>
            </span>
          ) : null
        }
        icon={<Cpu size={20} />}
        actions={
          <div className="flex items-center gap-2 flex-wrap">
            <Button variant="secondary" size="sm" leftIcon={<Play size={14} />}
                    onClick={() => cmdMut.mutate("restart")}>
              Restart
            </Button>
            <Button variant="secondary" size="sm" leftIcon={<Square size={14} />}
                    onClick={() => cmdMut.mutate("stop")}>
              Stop
            </Button>
            <Button variant="secondary" size="sm" leftIcon={<Download size={14} />}
                    onClick={() => cmdMut.mutate("update")}>
              Update
            </Button>
            <Button variant="ghost" size="sm" leftIcon={<RefreshCw size={14} />}
                    onClick={() => qc.invalidateQueries({ queryKey: ["agents", "detail", id] })}>
              Rafraîchir
            </Button>
          </div>
        }
      />

      {/* Tabs */}
      <div className="flex items-center gap-2 mb-4 border-b border-surface-border/60">
        {(["overview", "heartbeats", "configs", "logs"] as Tab[]).map((t) => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={cn(
              "px-4 py-2.5 text-sm font-medium border-b-2 transition-colors",
              tab === t
                ? "border-ink text-ink"
                : "border-transparent text-ink-muted hover:text-ink",
            )}
          >
            {t === "overview"   && "Vue d'ensemble"}
            {t === "heartbeats" && "Heartbeats"}
            {t === "configs"    && "Configurations"}
            {t === "logs"       && "Logs"}
          </button>
        ))}
      </div>

      {isLoading && (
        <div className="rounded-3xl bg-surface-soft/60 h-64 animate-pulse" />
      )}

      {agent && tab === "overview"   && <OverviewTab agent={agent} />}
      {tab === "heartbeats" && <HeartbeatsTab agentId={id} />}
      {tab === "configs"    && <ConfigsTab agentId={id} currentVersion={agent?.current_config?.version} />}
      {tab === "logs"       && <LogsTab agentId={id} />}
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════
// Overview
// ═══════════════════════════════════════════════════════════════
function OverviewTab({ agent }: { agent: any }) {
  return (
    <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
      <Card title="Ressources" padded className="lg:col-span-2">
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <ResourceGauge label="CPU"    value={agent.cpu_percent}     icon={<Cpu size={14} />} />
          <ResourceGauge label="RAM"    value={agent.memory_percent}  icon={<Activity size={14} />}
                          detail={`${agent.metadata?.memory_mb || "-"} MiB`} />
          <ResourceGauge label="Disque" value={agent.storage_percent} icon={<HardDrive size={14} />} />
        </div>

        <div className="mt-6 grid grid-cols-2 md:grid-cols-4 gap-3">
          <KVBox label="File d'événements" value={agent.events_pending} />
          <KVBox label="Équipements"        value={`${agent.devices_connected}/${agent.devices_expected}`} />
          <KVBox label="Erreurs (1 h)"      value={agent.errors_last_hour}
                  tone={agent.errors_last_hour > 20 ? "danger" : undefined} />
          <KVBox label="Dernier sync OK"    value={agent.sync_last_success_at
                                                    ? fmtRelative(agent.sync_last_success_at)
                                                    : "—"} />
        </div>
      </Card>

      <Card title="Identité" padded>
        <dl className="space-y-2 text-sm">
          <Row k="ID"           v={<span className="font-mono text-xs">{agent.id}</span>} />
          <Row k="Type"         v={agent.type_label || agent.type_code} />
          <Row k="Site"         v={agent.site_label || "—"} />
          <Row k="Version"      v={<span className="font-mono">v{agent.version || "?"}</span>} />
          <Row k="Dernier vu"   v={agent.last_seen_at ? fmtRelative(agent.last_seen_at) : "jamais"} />
          <Row k="Activé"       v={agent.activated_at ? fmtRelative(agent.activated_at) : "—"} />
          <Row k="Token rotate" v={agent.hmac_secret_last_rotated_at ? fmtRelative(agent.hmac_secret_last_rotated_at) : "—"} />
        </dl>
      </Card>
    </div>
  );
}

function ResourceGauge({ label, value, icon, detail }: {
  label: string; value: number; icon?: React.ReactNode; detail?: string;
}) {
  const pct = Math.max(0, Math.min(100, Math.round(value || 0)));
  const tone =
    pct >= 90 ? "text-danger stroke-danger" :
    pct >= 70 ? "text-warn stroke-warn" :
                "text-ink stroke-ink";

  return (
    <div className="rounded-2xl bg-surface-soft/60 p-4 text-center">
      <div className="text-xs text-ink-muted inline-flex items-center gap-1">{icon} {label}</div>
      <div className={cn("mt-2 text-3xl font-bold tabular-nums", tone)}>{pct}%</div>
      <div className="mt-2 h-1.5 rounded-full bg-ink/5 overflow-hidden">
        <div className={cn(
          "h-full rounded-full transition-all",
          pct >= 90 ? "bg-danger" : pct >= 70 ? "bg-warn" : "bg-ink",
        )} style={{ width: `${pct}%` }} />
      </div>
      {detail && <div className="mt-2 text-xs text-ink-muted">{detail}</div>}
    </div>
  );
}

function KVBox({ label, value, tone }: { label: string; value: React.ReactNode; tone?: "danger" }) {
  return (
    <div className={cn(
      "rounded-xl p-3",
      tone === "danger" ? "bg-danger/10 text-danger" : "bg-ink/5 text-ink",
    )}>
      <div className="text-xs opacity-70 uppercase tracking-wide">{label}</div>
      <div className="text-lg font-semibold mt-1 tabular-nums">{value}</div>
    </div>
  );
}

function Row({ k, v }: { k: string; v: React.ReactNode }) {
  return (
    <div className="flex items-center justify-between gap-3 py-1 border-b border-surface-border/40 last:border-0">
      <dt className="text-xs uppercase tracking-wide text-ink-muted">{k}</dt>
      <dd className="text-sm text-ink text-right truncate max-w-[60%]">{v}</dd>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════
// Heartbeats
// ═══════════════════════════════════════════════════════════════
function HeartbeatsTab({ agentId }: { agentId: string }) {
  const { data, isLoading } = useQuery({
    queryKey: ["agents", "heartbeats", agentId],
    queryFn: async () => (await agentsService.heartbeats(agentId, { limit: 100 })).data,
    refetchInterval: 20_000,
  });

  const rows = data?.results ?? [];

  return (
    <Card title={`Historique heartbeats · ${data?.count ?? 0} entrées`} padded>
      {isLoading ? (
        <div className="h-56 rounded-2xl bg-surface-soft/60 animate-pulse" />
      ) : rows.length === 0 ? (
        <div className="py-12 text-center text-ink-muted text-sm">Aucun heartbeat reçu.</div>
      ) : (
        <div className="overflow-x-auto">
          <table className="min-w-full text-sm">
            <thead>
              <tr className="text-xs uppercase tracking-wide text-ink-muted">
                <th className="text-left py-2 pr-3">Reçu</th>
                <th className="text-left pr-3">État</th>
                <th className="text-right pr-3">CPU</th>
                <th className="text-right pr-3">RAM</th>
                <th className="text-right pr-3">Disque</th>
                <th className="text-right pr-3">File</th>
                <th className="text-right pr-3">Devices</th>
                <th className="text-right pr-3">Err/1h</th>
                <th className="text-left">Version</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((h) => (
                <tr key={h.id} className="border-t border-surface-border/40">
                  <td className="py-2 pr-3 text-ink whitespace-nowrap">
                    {fmtRelative(h.received_at)}
                  </td>
                  <td className="pr-3">
                    <Badge tone={STATE_TONES[h.state] ?? "muted"} dot>
                      {STATE_LABELS[h.state] ?? h.state}
                    </Badge>
                  </td>
                  <td className="text-right pr-3 tabular-nums">{Math.round(h.cpu_percent)}%</td>
                  <td className="text-right pr-3 tabular-nums">{Math.round(h.memory_percent)}%</td>
                  <td className="text-right pr-3 tabular-nums">{Math.round(h.storage_percent)}%</td>
                  <td className="text-right pr-3 tabular-nums">{h.events_pending}</td>
                  <td className="text-right pr-3 tabular-nums">
                    {h.devices_connected}/{h.devices_expected}
                  </td>
                  <td className={cn(
                    "text-right pr-3 tabular-nums",
                    h.errors_last_hour > 20 && "text-danger font-semibold",
                  )}>
                    {h.errors_last_hour}
                  </td>
                  <td className="text-ink-muted font-mono text-xs">v{h.version || "?"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Card>
  );
}

// ═══════════════════════════════════════════════════════════════
// Configurations — éditeur JSON versionné
// ═══════════════════════════════════════════════════════════════
function ConfigsTab({ agentId, currentVersion }: { agentId: string; currentVersion?: number }) {
  const qc = useQueryClient();
  const [selected, setSelected] = useState<AgentConfigurationDTO | null>(null);
  const [draft, setDraft] = useState<string>("{}");
  const [notes, setNotes] = useState("");
  const [err, setErr] = useState<string | null>(null);

  const { data, isLoading } = useQuery({
    queryKey: ["agents", "configs", agentId],
    queryFn: async () => (await agentsService.listConfigs(agentId)).data,
  });

  const rows = data?.results ?? [];

  const createMut = useMutation({
    mutationFn: () => {
      let payload: any;
      try { payload = JSON.parse(draft); }
      catch (e: any) { throw new Error(`JSON invalide : ${e.message}`); }
      return agentsService.createConfig(agentId, { payload, notes, is_draft: true });
    },
    onSuccess: () => {
      toast.success("Draft de configuration créé");
      setDraft("{}"); setNotes(""); setErr(null);
      qc.invalidateQueries({ queryKey: ["agents", "configs", agentId] });
    },
    onError: (e: any) => setErr(e?.message || e?.response?.data?.error || "Erreur"),
  });

  const applyMut = useMutation({
    mutationFn: (version: number) => agentsService.applyConfig(agentId, version),
    onSuccess: () => {
      toast.success("Configuration marquée comme courante");
      qc.invalidateQueries({ queryKey: ["agents", "configs", agentId] });
      qc.invalidateQueries({ queryKey: ["agents", "detail", agentId] });
    },
    onError: (e: any) => toast.error(e?.response?.data?.error || "Erreur"),
  });

  return (
    <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
      <Card title="Versions" subtitle={`${rows.length} configurations`} padded>
        {isLoading ? (
          <div className="h-40 rounded-2xl bg-surface-soft/60 animate-pulse" />
        ) : rows.length === 0 ? (
          <div className="py-6 text-center text-ink-muted text-sm">Aucune configuration.</div>
        ) : (
          <ul className="space-y-2 max-h-[520px] overflow-y-auto pr-1">
            {rows.map((c) => (
              <li
                key={c.id}
                onClick={() => {
                  setSelected(c);
                  setDraft(JSON.stringify(c.payload, null, 2));
                }}
                className={cn(
                  "rounded-xl p-3 cursor-pointer border transition-colors",
                  selected?.id === c.id
                    ? "border-ink bg-ink/5"
                    : "border-surface-border/40 hover:bg-surface-soft/60",
                )}
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="font-mono text-sm">v{c.version}</span>
                  <div className="flex items-center gap-1">
                    {c.is_current && <Badge tone="ok">courante</Badge>}
                    {c.is_draft && <Badge tone="info">draft</Badge>}
                  </div>
                </div>
                <div className="text-[11px] text-ink-muted mt-1">
                  {fmtRelative(c.created_at)}
                </div>
                {c.notes && (
                  <div className="text-xs text-ink mt-1 line-clamp-2">{c.notes}</div>
                )}
              </li>
            ))}
          </ul>
        )}
      </Card>

      <Card
        title={selected ? `Éditeur — v${selected.version}` : "Nouvelle configuration"}
        subtitle="Édite le JSON puis crée une nouvelle version. Applique-la ensuite pour la marquer courante."
        padded
        className="lg:col-span-2"
      >
        <textarea
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          spellCheck={false}
          rows={18}
          className="w-full rounded-xl border border-surface-border bg-surface-soft/40 p-3 font-mono text-xs text-ink focus:outline-none focus:ring-2 focus:ring-ink/20"
        />
        <div className="mt-3">
          <label className="text-xs text-ink-muted uppercase tracking-wide">Notes</label>
          <input
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            placeholder="Motif du changement, à quoi ça sert…"
            className="mt-1 w-full rounded-xl border border-surface-border bg-surface-card px-3 py-2 text-sm text-ink"
          />
        </div>
        {err && (
          <div className="mt-3 rounded-xl border border-danger/30 bg-danger/10 p-3 text-xs text-danger">
            {err}
          </div>
        )}
        <div className="mt-4 flex flex-wrap items-center gap-2">
          <Button
            variant="dark"
            leftIcon={<FileCode2 size={14} />}
            loading={createMut.isPending}
            onClick={() => createMut.mutate()}
          >
            Créer une nouvelle version
          </Button>
          {selected && !selected.is_current && (
            <Button
              variant="primary"
              leftIcon={<CheckCircle2 size={14} />}
              loading={applyMut.isPending}
              onClick={() => applyMut.mutate(selected.version)}
            >
              Appliquer v{selected.version} comme courante
            </Button>
          )}
          {currentVersion !== undefined && (
            <span className="ml-auto text-xs text-ink-muted">
              Version courante côté serveur : v{currentVersion}
            </span>
          )}
        </div>
      </Card>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════
// Logs
// ═══════════════════════════════════════════════════════════════
function LogsTab({ agentId }: { agentId: string }) {
  const [level, setLevel] = useState<LogLevel | "all">("all");
  const [q, setQ] = useState("");

  const { data, isLoading } = useQuery({
    queryKey: ["agents", "logs", agentId, { level, q }],
    queryFn: async () => (await agentsService.logs(agentId, {
      ...(level !== "all" ? { level } : {}),
      ...(q ? { q } : {}),
      limit: 300,
    })).data,
    refetchInterval: 15_000,
  });

  const rows = data?.results ?? [];

  return (
    <Card title="Logs récents" subtitle={`${data?.count ?? 0} entrées`} padded>
      <div className="flex flex-wrap items-center gap-2 mb-3">
        {(["all", "debug", "info", "warning", "error", "critical"] as any[]).map((lvl) => (
          <button
            key={lvl}
            onClick={() => setLevel(lvl)}
            className={cn(
              "px-3 py-1.5 rounded-lg text-xs font-medium capitalize transition-colors",
              level === lvl
                ? "bg-ink text-surface-card"
                : "bg-ink/5 text-ink hover:bg-ink/10",
            )}
          >
            {lvl === "all" ? "Tous" : lvl}
          </button>
        ))}
        <input
          value={q}
          onChange={(e) => setQ(e.target.value)}
          placeholder="Rechercher dans les messages…"
          className="ml-auto rounded-xl border border-surface-border bg-surface-card px-3 py-2 text-sm text-ink min-w-[240px]"
        />
      </div>

      {isLoading ? (
        <div className="h-48 rounded-2xl bg-surface-soft/60 animate-pulse" />
      ) : rows.length === 0 ? (
        <div className="py-10 text-center text-ink-muted text-sm">
          <ScrollText className="mx-auto opacity-40 mb-2" size={24} />
          Aucun log pour ces filtres.
        </div>
      ) : (
        <div className="rounded-2xl bg-obsidian text-white/90 p-4 font-mono text-xs max-h-[520px] overflow-y-auto border border-white/10">
          {rows.map((l) => (
            <div key={l.id} className="py-1 border-b border-white/5 last:border-0">
              <span className="text-white/40">{new Date(l.ts).toLocaleString("fr-FR")}</span>
              {" · "}
              <span className={cn(
                "uppercase font-semibold",
                l.level === "critical" && "text-danger",
                l.level === "error"    && "text-danger",
                l.level === "warning"  && "text-warn",
                l.level === "info"     && "text-info",
                l.level === "debug"    && "text-white/50",
              )}>{l.level}</span>
              {l.source && <span className="text-white/50"> [{l.source}]</span>}
              {" "}
              <span className="text-white">{l.message}</span>
            </div>
          ))}
        </div>
      )}
    </Card>
  );
}

export default AgentDetailPage;
