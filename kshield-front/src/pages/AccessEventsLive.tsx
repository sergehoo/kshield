import { useEffect, useRef, useState } from "react";
import { useLive } from "@/hooks/useLive";
import { PageHeader } from "@/components/PageHeader";
import { Card } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { LivePulse } from "@/components/LivePulse";
import { Button } from "@/components/ui/Button";
import { accessEventsService } from "@/services";
import { fmtTime, fmtRelative } from "@/lib/format";
import type { AccessEvent } from "@/types/api";
import {
  ArrowDownToLine, ArrowUpFromLine, Ban, CheckCircle2, Filter, Pause, Play, ShieldAlert,
} from "lucide-react";
import { cn } from "@/lib/cn";

/**
 * Vue "console de contrôle" — flux en temps réel des AccessEvents.
 * Polling 5s, avec pause/play, filtre décision, et animation d'entrée.
 */
export function AccessEventsLivePage() {
  const [paused, setPaused] = useState(false);
  const [filter, setFilter] = useState<"all" | "granted" | "denied">("all");
  const seenIds = useRef<Set<number>>(new Set());
  const [flashIds, setFlashIds] = useState<Set<number>>(new Set());

  const { data, isLoading } = useLive(
    ["events", "live", filter],
    async () => {
      const params: any = { page_size: 40, ordering: "-timestamp" };
      if (filter !== "all") params.decision = filter;
      return (await accessEventsService.list(params)).data;
    },
    { intervalMs: 5_000, paused },
  );

  // Détecte les nouveaux events pour flash animation
  useEffect(() => {
    if (!data?.results) return;
    const fresh = new Set<number>();
    data.results.forEach((e) => {
      if (!seenIds.current.has(e.id)) {
        fresh.add(e.id);
        seenIds.current.add(e.id);
      }
    });
    if (fresh.size > 0 && seenIds.current.size > fresh.size) {
      // Pas le premier chargement — flash
      setFlashIds(fresh);
      setTimeout(() => setFlashIds(new Set()), 2000);
    }
  }, [data]);

  return (
    <div>
      <PageHeader
        title="Événements en direct"
        subtitle="Flux temps réel des scans (badge, face, RFID)"
        live={!paused}
        actions={
          <div className="flex items-center gap-2">
            <div className="inline-flex rounded-lg bg-surface-soft p-0.5 border border-surface-border">
              {(["all", "granted", "denied"] as const).map((f) => (
                <button
                  key={f}
                  onClick={() => setFilter(f)}
                  className={cn(
                    "px-3 py-1 rounded-md text-xs font-medium transition-all",
                    filter === f ? "bg-brand-500 text-white" : "text-ink-muted hover:text-ink",
                  )}
                >
                  {f === "all" ? "Tous" : f === "granted" ? "Autorisés" : "Refusés"}
                </button>
              ))}
            </div>
            <Button
              variant={paused ? "primary" : "ghost"}
              size="sm"
              leftIcon={paused ? <Play className="w-3.5 h-3.5" /> : <Pause className="w-3.5 h-3.5" />}
              onClick={() => setPaused((p) => !p)}
            >
              {paused ? "Reprendre" : "Pause"}
            </Button>
          </div>
        }
      />

      <Card padded={false}>
        <div className="max-h-[70vh] overflow-y-auto">
          {isLoading && !data && (
            <div className="p-10 text-center text-ink-muted text-sm">Chargement…</div>
          )}
          {data?.results?.length === 0 && (
            <div className="p-10 text-center text-ink-muted text-sm">
              Aucun événement pour l'instant
            </div>
          )}
          <ul className="divide-y divide-surface-border/50">
            {data?.results?.map((e) => (
              <EventRow key={e.id} event={e} flash={flashIds.has(e.id)} />
            ))}
          </ul>
        </div>
      </Card>

      <p className="mt-3 text-xs text-ink-soft text-center">
        {paused ? "Flux mis en pause" : "Rafraîchissement toutes les 5 secondes"}
      </p>
    </div>
  );
}

function EventRow({ event, flash }: { event: AccessEvent; flash: boolean }) {
  const granted = event.decision === "granted";
  const direction = event.direction === "in" ? "in" : event.direction === "out" ? "out" : "?";
  const deviceName =
    typeof event.device === "object" ? event.device?.name : event.device ? `Device #${event.device}` : "";
  const siteName =
    typeof event.site === "object" ? event.site?.name : event.site ? `Site #${event.site}` : "";

  return (
    <li
      className={cn(
        "flex items-center gap-4 px-5 py-3 transition-colors",
        flash && "bg-brand-500/10 animate-pulse",
        !flash && "hover:bg-surface-soft/40",
      )}
    >
      <div
        className={cn(
          "w-10 h-10 rounded-xl grid place-items-center shrink-0",
          granted ? "bg-ok/10 text-ok" : "bg-danger/10 text-danger",
        )}
      >
        {granted ? <CheckCircle2 className="w-5 h-5" /> : <Ban className="w-5 h-5" />}
      </div>

      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 flex-wrap">
          <span className="text-sm font-medium text-ink truncate">
            {event.holder_name || event.badge_uid || "Inconnu"}
          </span>
          {event.badge_uid && (
            <span className="text-[11px] font-mono text-ink-soft">
              {event.badge_uid}
            </span>
          )}
          <Badge tone={granted ? "ok" : "danger"}>
            {granted ? "Autorisé" : "Refusé"}
          </Badge>
          <Badge tone={direction === "in" ? "info" : "muted"}>
            {direction === "in" ? (
              <><ArrowDownToLine className="w-3 h-3" /> Entrée</>
            ) : direction === "out" ? (
              <><ArrowUpFromLine className="w-3 h-3" /> Sortie</>
            ) : (
              "—"
            )}
          </Badge>
        </div>
        <div className="text-xs text-ink-muted mt-0.5 truncate">
          {deviceName}
          {siteName && ` · ${siteName}`}
        </div>
      </div>

      <div className="text-right shrink-0">
        <div className="text-sm font-mono text-ink">{fmtTime(event.timestamp)}</div>
        <div className="text-[11px] text-ink-soft">{fmtRelative(event.timestamp)}</div>
      </div>
    </li>
  );
}
