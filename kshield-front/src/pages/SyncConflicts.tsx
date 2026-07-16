/**
 * SyncConflicts — page Phase 4.5 (cahier §4.5).
 *
 * Liste les conflits Edge Sync et permet à un admin de trancher
 * en visualisant les 2 payloads côte à côte (edge vs cloud). Les
 * résolutions possibles : cloud_wins / edge_wins / merge / ignore / escalated.
 */
import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  GitPullRequestArrow, Cloud, Server, RefreshCcw, CheckCircle2,
  ArrowLeftRight, Merge, Ban, AlertOctagon, Search,
} from "lucide-react";
import toast from "react-hot-toast";

import { PageHeader } from "@/components/PageHeader";
import { Card } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { StatsRow, Stat } from "@/components/StatsRow";
import { fmtRelative } from "@/lib/format";
import { cn } from "@/lib/cn";
import {
  syncService, SyncConflictDTO, Resolution,
  RESOLUTION_LABELS, RESOLUTION_TONES,
} from "@/services/sync";

const RESOLUTIONS: Resolution[] = ["pending", "cloud_wins", "edge_wins", "merge", "ignore", "escalated"];

export function SyncConflictsPage() {
  const qc = useQueryClient();
  const [filter, setFilter] = useState<Resolution>("pending");
  const [q, setQ] = useState("");
  const [selected, setSelected] = useState<SyncConflictDTO | null>(null);

  const { data, isLoading, refetch, isFetching } = useQuery({
    queryKey: ["sync", "conflicts", filter],
    queryFn: async () => (await syncService.conflicts({
      resolution: filter, limit: 300,
    })).data,
    refetchInterval: 30_000,
  });

  const rows = data?.results ?? [];

  const filtered = useMemo(() => {
    if (!q.trim()) return rows;
    const n = q.trim().toLowerCase();
    return rows.filter(
      (c) =>
        c.entity_type?.toLowerCase().includes(n) ||
        c.entity_key?.toLowerCase().includes(n) ||
        c.gateway_label?.toLowerCase().includes(n) ||
        c.batch_batch_id?.toLowerCase().includes(n),
    );
  }, [rows, q]);

  const stats: Stat[] = useMemo(() => {
    const pending = rows.filter((c) => c.resolution === "pending").length;
    const escalated = rows.filter((c) => c.resolution === "escalated").length;
    const resolvedToday = rows.filter(
      (c) => c.resolution !== "pending" && c.resolved_at &&
             (Date.now() - new Date(c.resolved_at).getTime() < 86_400_000),
    ).length;
    return [
      { label: "Conflits (filtre)",  value: rows.length,  icon: <GitPullRequestArrow size={18} />, tone: "brand" },
      { label: "En attente",         value: pending,      icon: <AlertOctagon size={18} />,        tone: "warn" },
      { label: "Escaladés",          value: escalated,    icon: <AlertOctagon size={18} />,        tone: "danger" },
      { label: "Résolus (24 h)",     value: resolvedToday, icon: <CheckCircle2 size={18} />,       tone: "ok" },
    ];
  }, [rows]);

  const resolveMut = useMutation({
    mutationFn: (args: { id: string; resolution: Exclude<Resolution, "pending">; notes?: string }) =>
      syncService.resolveConflict(args.id, args.resolution, args.notes),
    onSuccess: (r) => {
      toast.success(`Résolution appliquée : ${RESOLUTION_LABELS[r.data.conflict.resolution]}`);
      qc.invalidateQueries({ queryKey: ["sync", "conflicts"] });
      setSelected(null);
    },
    onError: (e: any) => toast.error(e?.response?.data?.error || "Erreur"),
  });

  return (
    <div>
      <PageHeader
        title="Conflits de synchronisation"
        subtitle="Divergences détectées entre les données Edge (gateway offline) et Cloud."
        icon={<GitPullRequestArrow size={20} />}
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

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {/* Colonne gauche : liste */}
        <div className="lg:col-span-1 space-y-3">
          <Card padded>
            <div className="flex flex-wrap items-center gap-2 mb-3">
              {RESOLUTIONS.map((r) => (
                <button
                  key={r}
                  onClick={() => setFilter(r)}
                  className={cn(
                    "px-2.5 py-1.5 rounded-lg text-[11px] font-medium transition-colors",
                    filter === r
                      ? "bg-ink text-white"
                      : "bg-ink/5 text-ink hover:bg-ink/10",
                  )}
                >
                  {RESOLUTION_LABELS[r]}
                </button>
              ))}
            </div>
            <div className="relative">
              <Search size={14} className="absolute left-3 top-1/2 -translate-y-1/2 text-ink-muted" />
              <Input
                value={q}
                onChange={(e) => setQ(e.target.value)}
                placeholder="Filtrer entity / gateway / batch…"
                className="pl-8 text-sm"
              />
            </div>
          </Card>

          <div className="space-y-2 max-h-[calc(100vh-360px)] overflow-y-auto pr-1">
            {isLoading && (
              <div className="rounded-2xl bg-surface-soft/60 h-24 animate-pulse" />
            )}
            {!isLoading && filtered.length === 0 && (
              <div className="rounded-2xl bg-surface-soft/60 p-8 text-center text-ink-muted text-sm">
                Aucun conflit à afficher.
              </div>
            )}
            {filtered.map((c) => (
              <button
                key={c.id}
                onClick={() => setSelected(c)}
                className={cn(
                  "w-full text-left rounded-2xl p-3 transition-colors",
                  selected?.id === c.id
                    ? "bg-ink text-white"
                    : "bg-surface-card hover:bg-surface-soft/60 text-ink",
                )}
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="text-sm font-semibold truncate max-w-[220px]">
                    {c.entity_type} · {c.entity_key}
                  </span>
                  <Badge tone={RESOLUTION_TONES[c.resolution]}>
                    {RESOLUTION_LABELS[c.resolution]}
                  </Badge>
                </div>
                <div className={cn(
                  "text-[11px] mt-1 truncate",
                  selected?.id === c.id ? "text-white/70" : "text-ink-muted",
                )}>
                  {c.gateway_label || "—"} · batch {c.batch_batch_id.slice(0, 8)}
                </div>
                <div className={cn(
                  "text-[10px] mt-0.5",
                  selected?.id === c.id ? "text-white/60" : "text-ink-muted",
                )}>
                  Créé {fmtRelative(c.created_at)}
                </div>
              </button>
            ))}
          </div>
        </div>

        {/* Colonne droite : diff + actions */}
        <div className="lg:col-span-2">
          {selected ? (
            <ConflictInspector
              conflict={selected}
              onResolve={(resolution, notes) =>
                resolveMut.mutate({ id: selected.id, resolution, notes })
              }
              busy={resolveMut.isPending}
            />
          ) : (
            <Card padded>
              <div className="py-16 text-center text-ink-muted">
                <ArrowLeftRight className="mx-auto mb-2 opacity-40" size={28} />
                <p className="text-sm">Sélectionne un conflit à gauche pour voir la comparaison.</p>
              </div>
            </Card>
          )}
        </div>
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════
// Panneau détail — diff edge vs cloud + boutons résolution
// ═══════════════════════════════════════════════════════════════
function ConflictInspector({
  conflict, onResolve, busy,
}: {
  conflict: SyncConflictDTO;
  onResolve: (r: Exclude<Resolution, "pending">, notes?: string) => void;
  busy: boolean;
}) {
  const [notes, setNotes] = useState("");
  const isResolved = conflict.resolution !== "pending";

  return (
    <div className="space-y-3">
      <Card
        title={
          <span className="inline-flex items-center gap-2 flex-wrap">
            <span>{conflict.entity_type}</span>
            <code className="font-mono text-xs text-ink-muted">{conflict.entity_key}</code>
            <Badge tone={RESOLUTION_TONES[conflict.resolution]}>
              {RESOLUTION_LABELS[conflict.resolution]}
            </Badge>
          </span>
        }
        subtitle={`Batch ${conflict.batch_batch_id} · Gateway ${conflict.gateway_label || "?"} · créé ${fmtRelative(conflict.created_at)}`}
        padded
      >
        <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
          <PayloadPane
            side="edge"
            version={conflict.edge_version}
            payload={conflict.edge_payload}
          />
          <PayloadPane
            side="cloud"
            version={conflict.cloud_version}
            payload={conflict.cloud_payload}
          />
        </div>
      </Card>

      {!isResolved && (
        <Card title="Résolution" padded>
          <p className="text-xs text-ink-muted mb-3">
            Choisis la version qui doit être appliquée dans le cloud (et rejouée
            si nécessaire vers les gateways).
          </p>

          <input
            value={notes}
            onChange={(e) => setNotes(e.target.value)}
            placeholder="Notes de résolution (optionnel, audit RGPD)…"
            className="w-full rounded-xl border border-surface-border bg-white px-3 py-2 text-sm mb-3"
          />

          <div className="flex flex-wrap items-center gap-2">
            <Button
              variant="dark" leftIcon={<Cloud size={14} />}
              loading={busy} onClick={() => onResolve("cloud_wins", notes)}
            >
              Cloud gagne
            </Button>
            <Button
              variant="primary" leftIcon={<Server size={14} />}
              loading={busy} onClick={() => onResolve("edge_wins", notes)}
            >
              Edge gagne
            </Button>
            <Button
              variant="secondary" leftIcon={<Merge size={14} />}
              loading={busy} onClick={() => onResolve("merge", notes)}
            >
              Fusion
            </Button>
            <Button
              variant="ghost" leftIcon={<Ban size={14} />}
              loading={busy} onClick={() => onResolve("ignore", notes)}
            >
              Ignorer
            </Button>
            <Button
              variant="danger" leftIcon={<AlertOctagon size={14} />}
              loading={busy} onClick={() => onResolve("escalated", notes)}
            >
              Escalader
            </Button>
          </div>
        </Card>
      )}

      {isResolved && (
        <Card padded>
          <div className="flex items-center gap-2 text-sm">
            <CheckCircle2 className="text-ok" size={16} />
            <span>
              Résolu par <span className="font-mono">{conflict.resolved_by || "?"}</span>
              {conflict.resolved_at && (
                <> · {fmtRelative(conflict.resolved_at)}</>
              )}
            </span>
          </div>
          {conflict.resolution_notes && (
            <div className="mt-2 text-xs text-ink-muted italic">
              « {conflict.resolution_notes} »
            </div>
          )}
        </Card>
      )}
    </div>
  );
}

function PayloadPane({
  side, version, payload,
}: {
  side: "edge" | "cloud";
  version: string;
  payload: any;
}) {
  const isEdge = side === "edge";
  return (
    <div className={cn(
      "rounded-2xl p-4",
      isEdge ? "bg-brand-500/5 border border-brand-500/20"
             : "bg-info/5 border border-info/20",
    )}>
      <div className="flex items-center justify-between mb-2">
        <div className="inline-flex items-center gap-2 font-semibold text-sm">
          {isEdge ? <Server size={14} /> : <Cloud size={14} />}
          {isEdge ? "Edge (gateway)" : "Cloud"}
        </div>
        <span className="text-[11px] text-ink-muted font-mono">v{version || "?"}</span>
      </div>
      <pre className="max-h-72 overflow-auto rounded-xl bg-white/60 p-3 text-[11px] font-mono text-ink whitespace-pre-wrap break-words">
        {typeof payload === "string"
          ? payload
          : JSON.stringify(payload ?? {}, null, 2)}
      </pre>
    </div>
  );
}

export default SyncConflictsPage;
