import { useState } from "react";
import { useLive } from "@/hooks/useLive";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { PageHeader } from "@/components/PageHeader";
import { Card } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { LivePulse } from "@/components/LivePulse";
import { antifraudService } from "@/services";
import { toApiError } from "@/lib/api";
import { fmtRelative, fmtDateTime } from "@/lib/format";
import { ShieldAlert, CheckCircle2, XCircle, AlertTriangle } from "lucide-react";
import { cn } from "@/lib/cn";
import toast from "react-hot-toast";

/**
 * Page /antifraud — alertes fraude en temps réel.
 * Détecte : badges dupliqués, tailgating, tentatives hors horaires, etc.
 */
export function AntifraudPage() {
  const [filter, setFilter] = useState<"open" | "resolved" | "all">("open");
  const qc = useQueryClient();

  const { data, isLoading } = useLive(
    ["antifraud", "alerts", filter],
    async () =>
      (
        await antifraudService.alertsList({
          status: filter === "all" ? undefined : filter,
          ordering: "-created_at",
          page_size: 100,
        })
      ).data,
    { intervalMs: 15_000 },
  );

  const resolveMut = useMutation({
    mutationFn: (id: number) => antifraudService.alertResolve(id),
    onSuccess: () => {
      toast.success("Alerte résolue");
      qc.invalidateQueries({ queryKey: ["antifraud"] });
    },
    onError: (e) => toast.error(toApiError(e).message),
  });

  const dismissMut = useMutation({
    mutationFn: (id: number) => antifraudService.alertDismiss(id),
    onSuccess: () => {
      toast.success("Alerte ignorée");
      qc.invalidateQueries({ queryKey: ["antifraud"] });
    },
    onError: (e) => toast.error(toApiError(e).message),
  });

  return (
    <div>
      <PageHeader
        title="Anti-fraude"
        subtitle="Alertes en temps réel — badges dupliqués, tailgating, tentatives suspectes"
        live
        actions={
          <div className="inline-flex rounded-lg bg-surface-soft p-0.5 border border-surface-border">
            {(["open", "resolved", "all"] as const).map((f) => (
              <button
                key={f}
                onClick={() => setFilter(f)}
                className={cn(
                  "px-3 py-1.5 rounded-md text-xs font-medium transition",
                  filter === f
                    ? "bg-brand-500 text-white"
                    : "text-ink-muted hover:text-ink",
                )}
              >
                {f === "open" ? "Ouvertes" : f === "resolved" ? "Résolues" : "Toutes"}
              </button>
            ))}
          </div>
        }
      />

      <Card padded={false}>
        {isLoading && !data && (
          <div className="p-10 text-center text-ink-muted">Chargement…</div>
        )}
        {data?.results?.length === 0 && (
          <div className="p-10 text-center">
            <CheckCircle2 className="w-12 h-12 mx-auto text-ok mb-3" />
            <div className="text-sm font-medium text-ink">Aucune alerte {filter === "open" ? "ouverte" : ""}</div>
            <div className="text-xs text-ink-soft mt-1">Tout va bien.</div>
          </div>
        )}
        <ul className="divide-y divide-surface-border/50">
          {data?.results?.map((a: any) => (
            <li key={a.id} className="p-4 hover:bg-surface-soft/40">
              <div className="flex items-start gap-3">
                <div
                  className={cn(
                    "w-10 h-10 rounded-xl grid place-items-center shrink-0",
                    a.severity === "critical"
                      ? "bg-danger/10 text-danger"
                      : a.severity === "high"
                      ? "bg-warn/10 text-warn"
                      : "bg-info/10 text-info",
                  )}
                >
                  <ShieldAlert className="w-5 h-5" />
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="text-sm font-semibold text-ink">
                      {a.rule_name || a.rule?.name || a.type}
                    </span>
                    <Badge
                      tone={
                        a.severity === "critical"
                          ? "danger"
                          : a.severity === "high"
                          ? "warn"
                          : "info"
                      }
                    >
                      {a.severity || "info"}
                    </Badge>
                    {a.status && (
                      <Badge
                        tone={
                          a.status === "resolved"
                            ? "ok"
                            : a.status === "dismissed"
                            ? "muted"
                            : "warn"
                        }
                      >
                        {a.status}
                      </Badge>
                    )}
                  </div>
                  {a.description && (
                    <p className="mt-1 text-sm text-ink-muted">{a.description}</p>
                  )}
                  <div className="mt-2 flex items-center gap-3 text-xs text-ink-soft">
                    <span>{fmtDateTime(a.created_at)}</span>
                    <span>·</span>
                    <span>{fmtRelative(a.created_at)}</span>
                    {a.badge_uid && (
                      <>
                        <span>·</span>
                        <code className="font-mono">{a.badge_uid}</code>
                      </>
                    )}
                    {a.site_name && (
                      <>
                        <span>·</span>
                        <span>📍 {a.site_name}</span>
                      </>
                    )}
                  </div>
                </div>
                {a.status !== "resolved" && a.status !== "dismissed" && (
                  <div className="flex items-center gap-1 shrink-0">
                    <Button
                      size="sm"
                      variant="ghost"
                      leftIcon={<CheckCircle2 className="w-3.5 h-3.5" />}
                      onClick={() => resolveMut.mutate(a.id)}
                      loading={resolveMut.isPending && resolveMut.variables === a.id}
                    >
                      Résoudre
                    </Button>
                    <Button
                      size="sm"
                      variant="ghost"
                      leftIcon={<XCircle className="w-3.5 h-3.5" />}
                      onClick={() => dismissMut.mutate(a.id)}
                    >
                      Ignorer
                    </Button>
                  </div>
                )}
              </div>
            </li>
          ))}
        </ul>
      </Card>
    </div>
  );
}
