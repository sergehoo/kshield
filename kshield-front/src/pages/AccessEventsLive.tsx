import { useEffect, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import {
  ArrowDownToLine,
  ArrowUpFromLine,
  Ban,
  CheckCircle2,
  ChevronRight,
  CircleAlert,
  Clock3,
  ContactRound,
  Cpu,
  ExternalLink,
  Fingerprint,
  Loader2,
  MapPin,
  Pause,
  Play,
  Radio,
  ScanLine,
  ShieldCheck,
  UserRound,
} from "lucide-react";

import { PageHeader } from "@/components/PageHeader";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Modal } from "@/components/ui/Modal";
import { useLive } from "@/hooks/useLive";
import { cn } from "@/lib/cn";
import { fmtDate, fmtDateTime, fmtRelative, fmtTime, initials } from "@/lib/format";
import { accessEventsService } from "@/services";
import type { AccessDoorCommand, AccessEvent } from "@/types/api";

type EventFilter = "all" | "granted" | "denied" | "review";

const FILTERS: Array<{ value: EventFilter; label: string }> = [
  { value: "all", label: "Tous" },
  { value: "granted", label: "Autorisés" },
  { value: "denied", label: "Refusés" },
  { value: "review", label: "À vérifier" },
];

export function AccessEventsLivePage() {
  const [paused, setPaused] = useState(false);
  const [filter, setFilter] = useState<EventFilter>("all");
  const [selectedEventId, setSelectedEventId] = useState<number | null>(null);
  const seenIds = useRef<Set<number>>(new Set());
  const initialized = useRef(false);
  const [flashIds, setFlashIds] = useState<Set<number>>(new Set());

  const { data, isLoading, isFetching } = useLive(
    ["events", "live", filter],
    async () => {
      const params: Record<string, string | number> = {
        page_size: 40,
        ordering: "-timestamp",
      };
      if (filter !== "all") params.decision = filter;
      return (await accessEventsService.list(params)).data;
    },
    { intervalMs: 5_000, paused: paused || selectedEventId !== null },
  );

  useEffect(() => {
    if (!data?.results) return;

    if (!initialized.current) {
      data.results.forEach((event) => seenIds.current.add(event.id));
      initialized.current = true;
      return;
    }

    const fresh = new Set<number>();
    data.results.forEach((event) => {
      if (!seenIds.current.has(event.id)) fresh.add(event.id);
      seenIds.current.add(event.id);
    });

    if (fresh.size === 0) return;
    setFlashIds(fresh);
    const timeout = window.setTimeout(() => setFlashIds(new Set()), 2_000);
    return () => window.clearTimeout(timeout);
  }, [data]);

  return (
    <div>
      <PageHeader
        title="Événements en direct"
        subtitle="Flux temps réel des passages et décisions de contrôle d’accès"
        live={!paused}
        actions={
          <div className="flex flex-wrap items-center justify-end gap-2">
            <div className="inline-flex max-w-full overflow-x-auto rounded-lg border border-surface-border bg-surface-soft p-0.5">
              {FILTERS.map(({ value, label }) => (
                <button
                  key={value}
                  type="button"
                  onClick={() => setFilter(value)}
                  className={cn(
                    "shrink-0 rounded-md px-3 py-1 text-xs font-medium transition-colors",
                    filter === value
                      ? "bg-brand-500 text-white"
                      : "text-ink-muted hover:bg-surface-card hover:text-ink",
                  )}
                >
                  {label}
                </button>
              ))}
            </div>
            <Button
              variant={paused ? "primary" : "ghost"}
              size="sm"
              leftIcon={paused ? <Play className="h-3.5 w-3.5" /> : <Pause className="h-3.5 w-3.5" />}
              onClick={() => setPaused((current) => !current)}
            >
              {paused ? "Reprendre" : "Pause"}
            </Button>
          </div>
        }
      />

      <Card padded={false}>
        <div className="flex min-h-12 items-center justify-between gap-3 border-b border-surface-border/60 px-5 py-3">
          <div className="flex min-w-0 items-center gap-2 text-xs text-ink-muted">
            <Radio className={cn("h-4 w-4 shrink-0", !paused && "text-ok")} />
            <span className="truncate">
              {data ? `${data.count} événement${data.count > 1 ? "s" : ""}` : "Connexion au flux"}
            </span>
          </div>
          <span className="flex shrink-0 items-center gap-1.5 text-[11px] text-ink-soft">
            {isFetching && !paused && <Loader2 className="h-3 w-3 animate-spin" />}
            {paused ? "Actualisation suspendue" : "Actualisation 5 s"}
          </span>
        </div>

        <div className="max-h-[70vh] overflow-y-auto">
          {isLoading && !data && (
            <div className="grid min-h-52 place-items-center text-sm text-ink-muted">
              <span className="flex items-center gap-2">
                <Loader2 className="h-4 w-4 animate-spin" /> Chargement des événements
              </span>
            </div>
          )}
          {data?.results?.length === 0 && (
            <div className="grid min-h-52 place-items-center px-5 text-center">
              <div>
                <ScanLine className="mx-auto mb-3 h-6 w-6 text-ink-soft" />
                <p className="text-sm font-medium text-ink">Aucun événement</p>
                <p className="mt-1 text-xs text-ink-muted">Le flux correspondant à ce filtre est vide.</p>
              </div>
            </div>
          )}
          <ul className="divide-y divide-surface-border/60">
            {data?.results?.map((event) => (
              <EventRow
                key={event.id}
                event={event}
                flash={flashIds.has(event.id)}
                onOpen={() => setSelectedEventId(event.id)}
              />
            ))}
          </ul>
        </div>
      </Card>

      {selectedEventId !== null && (
        <EventDetailModal eventId={selectedEventId} onClose={() => setSelectedEventId(null)} />
      )}
    </div>
  );
}

function EventRow({
  event,
  flash,
  onOpen,
}: {
  event: AccessEvent;
  flash: boolean;
  onOpen: () => void;
}) {
  const presentation = getDecisionPresentation(event);
  const holderName = event.holder_detail?.name || event.holder_name || "Porteur non identifié";
  const holderReference = event.holder_detail?.reference;
  const siteName = event.site_detail?.name || relationName(event.site, "Site");
  const checkpointName = event.checkpoint_detail?.name || relationName(event.checkpoint, "Point");
  const deviceName = event.device_detail?.name || relationName(event.device, "Terminal");
  const deviceSerial = event.device_detail?.serial_number;

  return (
    <li className={cn("transition-colors", flash && "bg-brand-500/10")}>
      <button
        type="button"
        onClick={onOpen}
        className={cn(
          "group grid w-full grid-cols-[2.75rem_minmax(0,1fr)_auto] gap-3 px-4 py-4 text-left transition-colors",
          "hover:bg-surface-soft/50 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-inset focus-visible:ring-brand-500",
          "sm:grid-cols-[3rem_minmax(0,1fr)_8.5rem] sm:gap-4 sm:px-5",
        )}
        aria-label={`Voir le détail de l’événement ${event.id}`}
      >
        <div
          className={cn(
            "grid h-11 w-11 place-items-center rounded-lg",
            presentation.iconBackground,
            presentation.iconColor,
          )}
        >
          <presentation.Icon className="h-5 w-5" />
        </div>

        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <span className="max-w-full truncate text-sm font-semibold text-ink">{holderName}</span>
            {holderReference && <span className="text-xs text-ink-muted">{holderReference}</span>}
            <Badge tone={presentation.tone}>{event.decision_label || presentation.label}</Badge>
            <DirectionBadge event={event} />
          </div>

          <div className="mt-2 grid gap-x-5 gap-y-1.5 text-xs text-ink-muted md:grid-cols-3">
            <EventInfo icon={MapPin} value={[checkpointName, siteName].filter(Boolean).join(" · ") || "Lieu non renseigné"} />
            <EventInfo
              icon={Cpu}
              value={[deviceName, deviceSerial].filter(Boolean).join(" · ") || "Terminal non renseigné"}
            />
            <EventInfo
              icon={Fingerprint}
              value={[event.method_label || event.method?.toUpperCase(), event.badge_uid].filter(Boolean).join(" · ") || "Identifiant non renseigné"}
              mono={Boolean(event.badge_uid)}
            />
          </div>

          {event.decision === "denied" && event.denial_reason && (
            <p className="mt-2 flex items-start gap-1.5 text-xs text-danger">
              <CircleAlert className="mt-0.5 h-3.5 w-3.5 shrink-0" />
              <span className="line-clamp-2">{event.denial_reason}</span>
            </p>
          )}
        </div>

        <div className="flex min-w-0 items-center justify-end gap-2 self-start sm:self-center">
          <div className="hidden text-right sm:block">
            <div className="text-xs text-ink-muted">{fmtDate(event.timestamp)}</div>
            <div className="font-mono text-sm text-ink">{fmtTime(event.timestamp)}</div>
            <div className="mt-0.5 text-[11px] text-ink-soft">{fmtRelative(event.timestamp)}</div>
          </div>
          <ChevronRight className="h-4 w-4 shrink-0 text-ink-soft transition-transform group-hover:translate-x-0.5 group-hover:text-ink" />
        </div>

        <div className="col-start-2 text-[11px] text-ink-soft sm:hidden">
          {fmtDate(event.timestamp)} à {fmtTime(event.timestamp)} · {fmtRelative(event.timestamp)}
        </div>
      </button>
    </li>
  );
}

function EventDetailModal({ eventId, onClose }: { eventId: number; onClose: () => void }) {
  const { data: response, isLoading, isError } = useQuery({
    queryKey: ["access-event", eventId],
    queryFn: () => accessEventsService.get(eventId),
  });
  const event = response?.data;

  return (
    <Modal
      open
      onClose={onClose}
      size="xl"
      title={<span>Événement #{eventId}</span>}
      footer={<Button variant="secondary" onClick={onClose}>Fermer</Button>}
    >
      {isLoading && (
        <div className="grid min-h-80 place-items-center text-sm text-ink-muted">
          <span className="flex items-center gap-2">
            <Loader2 className="h-4 w-4 animate-spin" /> Chargement du détail
          </span>
        </div>
      )}

      {isError && (
        <div className="grid min-h-80 place-items-center px-6 text-center">
          <div>
            <CircleAlert className="mx-auto mb-3 h-7 w-7 text-danger" />
            <p className="text-sm font-medium text-ink">Détail indisponible</p>
            <p className="mt-1 text-xs text-ink-muted">L’événement n’a pas pu être chargé.</p>
          </div>
        </div>
      )}

      {event && <EventDetail event={event} />}
    </Modal>
  );
}

function EventDetail({ event }: { event: AccessEvent }) {
  const presentation = getDecisionPresentation(event);
  const holder = event.holder_detail;
  const holderPath = holder?.kind === "employee"
    ? `/employees/${holder.id}`
    : holder?.kind === "worker"
      ? `/workers/${holder.id}`
      : null;

  return (
    <div>
      <div className="flex flex-col justify-between gap-4 border-b border-surface-border pb-5 sm:flex-row sm:items-center">
        <div className="flex min-w-0 items-center gap-3">
          <div className={cn("grid h-12 w-12 shrink-0 place-items-center rounded-lg", presentation.iconBackground, presentation.iconColor)}>
            <presentation.Icon className="h-6 w-6" />
          </div>
          <div className="min-w-0">
            <div className="flex flex-wrap items-center gap-2">
              <h4 className="truncate text-base font-semibold text-ink">{event.decision_label || presentation.label}</h4>
              <DirectionBadge event={event} />
            </div>
            <p className="mt-1 text-xs text-ink-muted">
              {fmtDate(event.timestamp)} à <span className="font-mono text-ink">{fmtTime(event.timestamp)}</span>
              {` · ${fmtRelative(event.timestamp)}`}
            </p>
          </div>
        </div>
        <span className="font-mono text-[11px] text-ink-soft">{event.uuid || `ID ${event.id}`}</span>
      </div>

      <DetailSection title="Porteur et identifiants" icon={UserRound}>
        <div className="flex flex-col gap-5 sm:flex-row sm:items-start">
          <div className="flex min-w-0 flex-1 items-center gap-3">
            {holder?.photo_url ? (
              <img src={holder.photo_url} alt="" className="h-14 w-14 shrink-0 rounded-lg object-cover" />
            ) : (
              <div className="grid h-14 w-14 shrink-0 place-items-center rounded-lg bg-surface-soft text-sm font-semibold text-ink-muted">
                {initials(holder?.name || event.holder_name)}
              </div>
            )}
            <div className="min-w-0">
              <p className="truncate text-sm font-semibold text-ink">{holder?.name || event.holder_name || "Porteur non identifié"}</p>
              <p className="mt-0.5 text-xs text-ink-muted">
                {[holder?.kind_label || event.holder_kind_label, holder?.reference, holder?.role].filter(Boolean).join(" · ") || "Aucune identité associée"}
              </p>
              {holder?.organization && <p className="mt-0.5 text-xs text-ink-soft">{holder.organization}</p>}
              {holderPath && (
                <Link to={holderPath} className="mt-2 inline-flex items-center gap-1 text-xs font-medium text-brand-ink hover:text-brand-ink">
                  Voir le dossier <ExternalLink className="h-3 w-3" />
                </Link>
              )}
            </div>
          </div>
          <dl className="grid min-w-0 flex-1 grid-cols-1 gap-3 sm:grid-cols-2">
            <DetailValue label="Badge" value={event.badge_uid} mono />
            <DetailValue label="Casque" value={event.helmet_uid} mono />
          </dl>
        </div>
      </DetailSection>

      <DetailSection title="Passage" icon={MapPin}>
        <dl className="grid grid-cols-1 gap-x-6 gap-y-4 sm:grid-cols-2 lg:grid-cols-3">
          <DetailValue label="Site" value={event.site_detail?.name || relationName(event.site, "Site")} />
          <DetailValue label="Point de contrôle" value={event.checkpoint_detail?.name || relationName(event.checkpoint, "Point")} />
          <DetailValue label="Zone" value={event.zone_detail?.name || relationName(event.zone, "Zone")} />
          <DetailValue label="Sens" value={event.direction_label || event.direction} />
          <DetailValue label="Méthode" value={event.method_label || event.method?.toUpperCase()} />
          <DetailValue label="Reçu par le serveur" value={fmtDateTime(event.received_at)} />
        </dl>
      </DetailSection>

      <DetailSection title="Terminal" icon={Cpu}>
        <dl className="grid grid-cols-1 gap-x-6 gap-y-4 sm:grid-cols-2 lg:grid-cols-3">
          <DetailValue label="Modèle" value={event.device_detail?.model || relationName(event.device, "Terminal")} />
          <DetailValue label="Numéro de série" value={event.device_detail?.serial_number} mono />
          <DetailValue label="Type" value={event.device_detail?.type_label} />
          <DetailValue label="État" value={event.device_detail?.status_label} />
          <DetailValue label="Adresse IP" value={event.device_detail?.ip_address} mono />
          <DetailValue label="Dernier heartbeat" value={fmtDateTime(event.device_detail?.last_heartbeat_at)} />
        </dl>
        {event.device_detail && (
          <Link to={`/devices/${event.device_detail.id}`} className="mt-4 inline-flex items-center gap-1 text-xs font-medium text-brand-ink hover:text-brand-ink">
            Voir le terminal <ExternalLink className="h-3 w-3" />
          </Link>
        )}
      </DetailSection>

      <DetailSection title="Décision" icon={ShieldCheck}>
        <dl className="grid grid-cols-1 gap-x-6 gap-y-4 sm:grid-cols-2 lg:grid-cols-3">
          <DetailValue label="Résultat" value={event.decision_label || presentation.label} />
          <DetailValue label="Motif" value={event.denial_reason} />
          <DetailValue label="Règle décisive" value={event.decision_trace?.deciding_rule_code} mono />
          <DetailValue label="Score de risque" value={formatRiskScore(event.decision_trace?.risk_score)} />
          <DetailValue label="Délai de traitement" value={formatDelay(event.processing_delay_ms)} />
          <DetailValue label="Opérateur" value={event.operator_detail?.name} />
        </dl>
        {event.decision_trace?.notes && (
          <p className="mt-4 border-l-2 border-surface-border pl-3 text-xs leading-5 text-ink-muted">{event.decision_trace.notes}</p>
        )}
        {event.decision_trace?.rules_evaluated && (
          <details className="mt-4 border-t border-surface-border/60 pt-3">
            <summary className="cursor-pointer text-xs font-medium text-ink">Règles évaluées</summary>
            <JsonBlock value={event.decision_trace.rules_evaluated} />
          </details>
        )}
      </DetailSection>

      {Boolean(event.door_commands?.length) && (
        <DetailSection title="Commandes de porte" icon={ScanLine}>
          <div className="divide-y divide-surface-border/60">
            {event.door_commands?.map((command) => <DoorCommandLine key={command.id} command={command} />)}
          </div>
        </DetailSection>
      )}

      <DetailSection title="Données techniques" icon={ContactRound} last>
        <dl className="grid grid-cols-1 gap-x-6 gap-y-4 sm:grid-cols-2 lg:grid-cols-3">
          <DetailValue label="Identifiant" value={event.uuid || String(event.id)} mono />
          <DetailValue label="Coordonnées" value={formatCoordinates(event.latitude, event.longitude)} mono />
          <DetailValue label="Horodatage source" value={event.timestamp} mono />
        </dl>
        {event.raw_payload && Object.keys(event.raw_payload).length > 0 && (
          <details className="mt-4 border-t border-surface-border/60 pt-3">
            <summary className="cursor-pointer text-xs font-medium text-ink">Charge utile reçue</summary>
            <JsonBlock value={event.raw_payload} />
          </details>
        )}
      </DetailSection>
    </div>
  );
}

function DetailSection({
  title,
  icon: Icon,
  children,
  last = false,
}: {
  title: string;
  icon: typeof Clock3;
  children: React.ReactNode;
  last?: boolean;
}) {
  return (
    <section className={cn("py-5", !last && "border-b border-surface-border")}>
      <h5 className="mb-4 flex items-center gap-2 text-xs font-semibold text-ink">
        <Icon className="h-4 w-4 text-ink-muted" /> {title}
      </h5>
      {children}
    </section>
  );
}

function DetailValue({ label, value, mono = false }: { label: string; value?: string | number | null; mono?: boolean }) {
  const displayValue = value === null || value === undefined || value === "" ? "—" : String(value);
  return (
    <div className="min-w-0">
      <dt className="text-[11px] text-ink-soft">{label}</dt>
      <dd className={cn("mt-1 break-words text-xs text-ink", mono && "font-mono")}>{displayValue}</dd>
    </div>
  );
}

function EventInfo({ icon: Icon, value, mono = false }: { icon: typeof MapPin; value: string; mono?: boolean }) {
  return (
    <span className="flex min-w-0 items-center gap-1.5">
      <Icon className="h-3.5 w-3.5 shrink-0 text-ink-soft" />
      <span className={cn("truncate", mono && "font-mono")}>{value}</span>
    </span>
  );
}

function DirectionBadge({ event }: { event: AccessEvent }) {
  if (event.direction === "in") {
    return <Badge tone="info"><ArrowDownToLine className="h-3 w-3" />{event.direction_label || "Entrée"}</Badge>;
  }
  if (event.direction === "out") {
    return <Badge tone="muted"><ArrowUpFromLine className="h-3 w-3" />{event.direction_label || "Sortie"}</Badge>;
  }
  return <Badge tone="muted">{event.direction_label || "Passage"}</Badge>;
}

function DoorCommandLine({ command }: { command: AccessDoorCommand }) {
  const tone = command.status === "succeeded"
    ? "ok"
    : command.status === "failed"
      ? "danger"
      : "muted";
  return (
    <div className="flex flex-col justify-between gap-2 py-3 first:pt-0 last:pb-0 sm:flex-row sm:items-center">
      <div>
        <p className="text-xs font-medium text-ink">{command.command_label || command.command}</p>
        <p className="mt-0.5 text-[11px] text-ink-muted">{command.reason || fmtDateTime(command.created_at)}</p>
      </div>
      <div className="flex items-center gap-2">
        {command.latency_ms !== null && command.latency_ms !== undefined && (
          <span className="font-mono text-[11px] text-ink-soft">{command.latency_ms} ms</span>
        )}
        <Badge tone={tone}>{command.status_label || command.status}</Badge>
      </div>
    </div>
  );
}

function JsonBlock({ value }: { value: unknown }) {
  return (
    <pre className="mt-3 max-h-56 overflow-auto rounded-lg bg-surface-soft p-3 font-mono text-[11px] leading-5 text-ink-muted">
      {JSON.stringify(value, null, 2)}
    </pre>
  );
}

function getDecisionPresentation(event: AccessEvent) {
  if (event.decision === "granted") {
    return {
      label: "Autorisé",
      tone: "ok" as const,
      Icon: CheckCircle2,
      iconBackground: "bg-ok/10",
      iconColor: "text-ok",
    };
  }
  if (event.decision === "review") {
    return {
      label: "À vérifier",
      tone: "warn" as const,
      Icon: CircleAlert,
      iconBackground: "bg-warn/10",
      iconColor: "text-warn",
    };
  }
  return {
    label: "Refusé",
    tone: "danger" as const,
    Icon: Ban,
    iconBackground: "bg-danger/10",
    iconColor: "text-danger",
  };
}

function relationName(relation: AccessEvent["site"] | AccessEvent["device"] | AccessEvent["checkpoint"] | AccessEvent["zone"], fallback: string) {
  if (typeof relation === "object" && relation?.name) return relation.name;
  if (typeof relation === "number") return `${fallback} #${relation}`;
  return "";
}

function formatDelay(delay?: number | null) {
  if (delay === null || delay === undefined) return "—";
  if (delay < 1_000) return `${delay} ms`;
  return `${(delay / 1_000).toFixed(2)} s`;
}

function formatRiskScore(score?: number | null) {
  if (score === null || score === undefined) return "—";
  return score.toFixed(2);
}

function formatCoordinates(latitude?: string | number | null, longitude?: string | number | null) {
  if (latitude === null || latitude === undefined || longitude === null || longitude === undefined) return "—";
  return `${latitude}, ${longitude}`;
}
