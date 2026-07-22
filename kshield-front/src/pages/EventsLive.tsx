/**
 * EventsLive — Vue supervision temps réel refondue (Phase 2, cahier §1).
 *
 * Fonctionnalités :
 *   - Filtres URL persistants (?site=&type=&severity=…)
 *   - 6 modes d'affichage : liste, compact, cartes, timeline, mur, full-screen
 *   - Toolbar : pause/reprise, son alertes, export CSV, refresh manuel
 *   - Panel latéral détail événement (payload + acknowledgements + actions)
 *   - WS status indicator (connecté / reconnexion / polling fallback)
 *   - Badge pending count si pause activée
 *   - Alertes visuelles + son configurable pour severity=critical
 */
import { useEffect, useMemo, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import toast from "react-hot-toast";
import {
  Search, Pause, Play, VolumeX, Volume2, Download, RefreshCw,
  X, ShieldCheck, Wifi, WifiOff, ChevronRight,
  LayoutList, LayoutGrid, Rows3, Clock,
  Tv2, Expand,
} from "lucide-react";

import { PageHeader } from "@/components/PageHeader";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Badge } from "@/components/ui/Badge";
import { StatsRow } from "@/components/StatsRow";
import { useEventsLive } from "@/hooks/useEventsLive";
import {
  eventsService, type DeviceEventDTO, type EventCategory,
  type EventSeverity, type EventTypeDTO,
} from "@/services/events";
import { fmtRelative } from "@/lib/format";
import { cn } from "@/lib/cn";

// ═══════════════════════════════════════════════════════════════════
// Types locaux
// ═══════════════════════════════════════════════════════════════════
type ViewMode = "list" | "compact" | "cards" | "timeline" | "wall" | "fullscreen";

const VIEW_MODES: { id: ViewMode; label: string; icon: React.ReactNode }[] = [
  { id: "list",       label: "Liste",       icon: <LayoutList className="w-3.5 h-3.5" /> },
  { id: "compact",    label: "Compact",     icon: <Rows3 className="w-3.5 h-3.5" /> },
  { id: "cards",      label: "Cartes",      icon: <LayoutGrid className="w-3.5 h-3.5" /> },
  { id: "timeline",   label: "Timeline",    icon: <Clock className="w-3.5 h-3.5" /> },
  { id: "wall",       label: "Mur",         icon: <Tv2 className="w-3.5 h-3.5" /> },
  { id: "fullscreen", label: "Plein écran", icon: <Expand className="w-3.5 h-3.5" /> },
];

// ═══════════════════════════════════════════════════════════════════
// EventsLive page
// ═══════════════════════════════════════════════════════════════════
export default function EventsLivePage() {
  const [searchParams, setSearchParams] = useSearchParams();
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const [soundOn, setSoundOn] = useState(false);
  const [viewMode, setViewMode] = useState<ViewMode>(
    (searchParams.get("view") as ViewMode) || "list",
  );

  // Filtres extraits de l'URL — reflétés en cours de session
  const filters = useMemo(() => {
    const f: any = {};
    ["period", "date_from", "date_to", "gateway", "agent", "holder",
     "badge", "has_helmet", "transmission", "is_offline", "is_synced",
     "q"].forEach((k) => {
      const v = searchParams.get(k);
      if (v) f[k] = v;
    });
    ["site", "zone", "checkpoint", "device"].forEach((k) => {
      const v = searchParams.get(k);
      if (v) f[k] = Number(v);
    });
    ["category", "severity", "result"].forEach((k) => {
      const v = searchParams.get(k);
      if (v) f[k] = v;
    });
    const types = searchParams.getAll("type");
    if (types.length) f.type = types;
    return f;
  }, [searchParams]);

  // Hook temps réel
  const {
    events, wsStatus, pendingCount, isPaused,
    pause, resume, clear, stats24h, loading, error, totalCount, refetch,
  } = useEventsLive(filters);

  // Catalogue nomenclature (pour selects)
  const { data: catalogRaw } = useQuery({
    queryKey: ["event-types-catalog"],
    queryFn: async () => (await eventsService.types()).data,
    staleTime: 5 * 60_000,
  });

  // Son alertes critiques
  const audioRef = useRef<HTMLAudioElement | null>(null);
  const lastAlertedRef = useRef<string | null>(null);
  useEffect(() => {
    if (!soundOn || events.length === 0) return;
    const latest = events[0];
    if (latest.id === lastAlertedRef.current) return;
    if (latest.severity === "critical" || latest.severity === "emergency") {
      lastAlertedRef.current = latest.id;
      audioRef.current?.play().catch(() => {});
    }
  }, [events, soundOn]);

  // Fullscreen auto
  const rootRef = useRef<HTMLDivElement>(null);
  useEffect(() => {
    if (viewMode === "fullscreen" && rootRef.current) {
      rootRef.current.requestFullscreen?.().catch(() => {});
    } else if (document.fullscreenElement) {
      document.exitFullscreen?.().catch(() => {});
    }
  }, [viewMode]);

  // ─── Handlers ───────────────────────────────────────────────
  const updateFilter = (key: string, value: string | number | null) => {
    const next = new URLSearchParams(searchParams);
    if (value === null || value === "" || value === undefined) {
      next.delete(key);
    } else {
      next.set(key, String(value));
    }
    setSearchParams(next);
  };

  const changeViewMode = (mode: ViewMode) => {
    setViewMode(mode);
    updateFilter("view", mode === "list" ? null : mode);
  };

  const handleExport = () => {
    const url = eventsService.exportCsvUrl(filters);
    window.open(url, "_blank");
    toast.success("Export CSV lancé");
  };

  const selectedEvent = useMemo(
    () => events.find((e) => e.id === selectedId),
    [selectedId, events],
  );

  const activeFilterCount = Object.keys(filters).length;

  // ═══════════════════════════════════════════════════════════════
  // Render
  // ═══════════════════════════════════════════════════════════════
  return (
    <div ref={rootRef} className={cn(
      viewMode === "fullscreen" && "min-h-screen bg-surface p-6",
    )}>
      <PageHeader
        icon={<ShieldCheck className="w-5 h-5" />}
        title="Événements en direct"
        subtitle={
          <div className="flex items-center gap-3">
            <WsStatusPill status={wsStatus} />
            <span className="text-xs text-ink-muted">
              {totalCount.toLocaleString("fr-FR")} événement{totalCount > 1 ? "s" : ""}
              {activeFilterCount > 0 && ` — ${activeFilterCount} filtre${activeFilterCount > 1 ? "s" : ""} actif${activeFilterCount > 1 ? "s" : ""}`}
            </span>
          </div>
        }
      />

      {/* Stats 24h */}
      {stats24h && (
        <StatsRow stats={[
          {
            label: "Total 24h",
            value: stats24h.total.toString(),
            hint: "événements",
            tone: "info",
          },
          {
            label: "Critiques",
            value: stats24h.by_severity.critical.toString(),
            hint: stats24h.by_severity.emergency > 0
              ? `+${stats24h.by_severity.emergency} urgences`
              : "24h",
            tone: stats24h.by_severity.critical + stats24h.by_severity.emergency > 0
              ? "danger" : "ok",
          },
          {
            label: "Refusés",
            value: (stats24h.by_result.denied || 0).toString(),
            hint: "accès",
            tone: (stats24h.by_result.denied || 0) > 0 ? "warn" : "ok",
          },
          {
            label: "Anomalies",
            value: ((stats24h.by_result.anomaly || 0) + (stats24h.by_result.alert || 0)).toString(),
            hint: "détectées",
            tone: "warn",
          },
        ]} />
      )}

      {/* Toolbar */}
      <div className="flex flex-wrap items-center gap-2 mb-4">
        {/* Recherche */}
        <div className="flex-1 min-w-[240px]">
          <Input
            leftIcon={<Search className="w-4 h-4" />}
            placeholder="Rechercher (badge, message, code, holder)…"
            value={searchParams.get("q") || ""}
            onChange={(e) => updateFilter("q", e.target.value)}
          />
        </div>

        {/* Période */}
        <select
          className="h-11 px-3 rounded-2xl bg-surface-soft text-sm"
          value={searchParams.get("period") || ""}
          onChange={(e) => updateFilter("period", e.target.value)}
        >
          <option value="">Toute période</option>
          <option value="last_hour">Dernière heure</option>
          <option value="today">Aujourd'hui</option>
          <option value="last_24h">Dernières 24h</option>
          <option value="last_7d">7 derniers jours</option>
        </select>

        {/* Catégorie */}
        <select
          className="h-11 px-3 rounded-2xl bg-surface-soft text-sm"
          value={searchParams.get("category") || ""}
          onChange={(e) => updateFilter("category", e.target.value)}
        >
          <option value="">Toutes catégories</option>
          {catalogRaw && Object.keys(catalogRaw.categories).map((cat) => (
            <option key={cat} value={cat}>
              {CATEGORY_LABELS[cat as EventCategory] || cat}
            </option>
          ))}
        </select>

        {/* Sévérité */}
        <select
          className="h-11 px-3 rounded-2xl bg-surface-soft text-sm"
          value={searchParams.get("severity") || ""}
          onChange={(e) => updateFilter("severity", e.target.value)}
        >
          <option value="">Toutes sévérités</option>
          <option value="info">Info</option>
          <option value="warning">Warning</option>
          <option value="critical">Critique</option>
          <option value="emergency">Urgence</option>
        </select>

        {/* Résultat */}
        <select
          className="h-11 px-3 rounded-2xl bg-surface-soft text-sm"
          value={searchParams.get("result") || ""}
          onChange={(e) => updateFilter("result", e.target.value)}
        >
          <option value="">Tous résultats</option>
          <option value="granted">Autorisé</option>
          <option value="denied">Refusé</option>
          <option value="pending">En attente</option>
          <option value="anomaly">Anomalie</option>
          <option value="alert">Alerte</option>
        </select>

        {/* Actions */}
        {isPaused ? (
          <Button
            variant="dark"
            onClick={resume}
            leftIcon={<Play className="w-4 h-4" />}
          >
            Reprendre {pendingCount > 0 && (
              <Badge className="ml-1">{pendingCount}</Badge>
            )}
          </Button>
        ) : (
          <Button
            variant="ghost"
            onClick={pause}
            leftIcon={<Pause className="w-4 h-4" />}
          >
            Pause
          </Button>
        )}

        <Button
          variant="ghost"
          onClick={() => setSoundOn((s) => !s)}
          title={soundOn ? "Couper le son" : "Activer le son des alertes critiques"}
        >
          {soundOn ? <Volume2 className="w-4 h-4" /> : <VolumeX className="w-4 h-4" />}
        </Button>

        <Button variant="ghost" onClick={refetch} title="Rafraîchir">
          <RefreshCw className="w-4 h-4" />
        </Button>

        <Button
          variant="ghost"
          onClick={handleExport}
          leftIcon={<Download className="w-4 h-4" />}
        >
          Export
        </Button>

        {activeFilterCount > 0 && (
          <Button
            variant="ghost"
            onClick={() => setSearchParams(new URLSearchParams())}
          >
            <X className="w-4 h-4" /> Reset
          </Button>
        )}
      </div>

      {/* Sélecteur mode d'affichage */}
      <div className="flex items-center gap-1 mb-3">
        {VIEW_MODES.map((m) => (
          <button
            key={m.id}
            onClick={() => changeViewMode(m.id)}
            className={cn(
              "px-3 py-1.5 rounded-xl text-xs font-medium flex items-center gap-1.5 transition",
              viewMode === m.id
                ? "bg-ink text-surface-card"
                : "bg-surface-soft text-ink-muted hover:text-ink",
            )}
          >
            {m.icon}
            {m.label}
          </button>
        ))}
      </div>

      {/* Corps — 2 colonnes si détail ouvert, sinon pleine largeur */}
      <div className={cn(
        "grid gap-4",
        selectedId ? "grid-cols-1 lg:grid-cols-[1fr_400px]" : "grid-cols-1",
      )}>
        {/* Liste selon mode */}
        <div className="min-w-0">
          {loading && (
            <Card padded>
              <div className="animate-pulse space-y-2">
                {[...Array(8)].map((_, i) => (
                  <div key={i} className="h-14 bg-ink/5 rounded-xl" />
                ))}
              </div>
            </Card>
          )}

          {error && (
            <Card padded className="border-2 border-danger/30">
              <div className="text-danger text-sm">Erreur : {error}</div>
            </Card>
          )}

          {!loading && !error && events.length === 0 && (
            <Card padded>
              <div className="text-center py-16 text-ink-muted">
                <ShieldCheck className="w-12 h-12 mx-auto mb-3 opacity-20" />
                <p className="text-sm font-medium mb-1">Aucun événement</p>
                <p className="text-xs">
                  {activeFilterCount > 0
                    ? "Essayez d'élargir les filtres."
                    : "Les événements apparaîtront ici en temps réel."}
                </p>
              </div>
            </Card>
          )}

          {!loading && !error && events.length > 0 && (
            <>
              {viewMode === "list" && (
                <ListView events={events} selectedId={selectedId} onSelect={setSelectedId} />
              )}
              {viewMode === "compact" && (
                <CompactView events={events} selectedId={selectedId} onSelect={setSelectedId} />
              )}
              {viewMode === "cards" && (
                <CardsView events={events} onSelect={setSelectedId} />
              )}
              {viewMode === "timeline" && (
                <TimelineView events={events} onSelect={setSelectedId} />
              )}
              {(viewMode === "wall" || viewMode === "fullscreen") && (
                <WallView events={events} onSelect={setSelectedId} />
              )}
            </>
          )}
        </div>

        {/* Panneau latéral détail */}
        {selectedId && selectedEvent && (
          <EventDetailPanel
            eventId={selectedId}
            initialData={selectedEvent}
            onClose={() => setSelectedId(null)}
          />
        )}
      </div>

      {/* Audio pour alertes critiques */}
      <audio
        ref={audioRef}
        src="data:audio/wav;base64,UklGRnoGAABXQVZFZm10IBAAAAABAAEAQB8AAEAfAAABAAgAZGF0YQ=="
        preload="auto"
      />
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════
// WsStatusPill — indicateur WebSocket
// ═══════════════════════════════════════════════════════════════════
function WsStatusPill({ status }: { status: string }) {
  const meta: Record<string, { icon: React.ReactNode; label: string; cls: string }> = {
    connected:    { icon: <Wifi className="w-3 h-3" />,    label: "Live",     cls: "bg-success/15 text-success" },
    connecting:   { icon: <RefreshCw className="w-3 h-3 animate-spin" />, label: "Connexion", cls: "bg-info/15 text-info" },
    reconnecting: { icon: <RefreshCw className="w-3 h-3 animate-spin" />, label: "Reconnexion", cls: "bg-warning/15 text-warning" },
    polling:      { icon: <RefreshCw className="w-3 h-3" />, label: "Polling", cls: "bg-warning/15 text-warning" },
    disconnected: { icon: <WifiOff className="w-3 h-3" />,  label: "Hors ligne", cls: "bg-danger/15 text-danger" },
  };
  const m = meta[status] || meta.disconnected;
  return (
    <span className={cn(
      "inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-semibold",
      m.cls,
    )}>
      {m.icon} {m.label}
    </span>
  );
}

// ═══════════════════════════════════════════════════════════════════
// Vues (list / compact / cards / timeline / wall)
// ═══════════════════════════════════════════════════════════════════
const CATEGORY_LABELS: Record<EventCategory, string> = {
  access: "Contrôle d'accès",
  attendance: "Pointage",
  rfid: "RFID / NFC",
  ble: "BLE / Casques",
  device: "Équipements",
  gateway: "Gateway & Agents",
  security: "Sécurité",
  system: "Système",
};

const SEVERITY_COLOR: Record<EventSeverity, string> = {
  info: "bg-info/15 text-info",
  warning: "bg-warning/15 text-warning",
  critical: "bg-danger/15 text-danger",
  emergency: "bg-danger/25 text-danger animate-pulse",
};

function EventRow({
  event, isSelected, onSelect, compact,
}: {
  event: DeviceEventDTO;
  isSelected?: boolean;
  onSelect: (id: string) => void;
  compact?: boolean;
}) {
  return (
    <button
      onClick={() => onSelect(event.id)}
      className={cn(
        "w-full text-left px-3 py-2.5 hover:bg-ink/5 transition flex items-center gap-3 border-b border-surface-border/40",
        isSelected && "bg-ink/5",
      )}
    >
      <div className={cn(
        "px-2 py-0.5 rounded-full text-[10px] font-bold shrink-0",
        SEVERITY_COLOR[event.severity],
      )}>
        {event.severity.toUpperCase()}
      </div>
      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-2 text-sm text-ink">
          <span className="font-medium truncate">{event.label}</span>
          <span className="font-mono text-[10px] text-ink-muted opacity-60">{event.code}</span>
        </div>
        {!compact && (
          <div className="text-xs text-ink-muted truncate mt-0.5">
            {event.site_label && `${event.site_label} · `}
            {event.device_label && `${event.device_label} · `}
            {event.badge_uid && `Badge ${event.badge_uid} · `}
            {event.message}
          </div>
        )}
      </div>
      <div className="text-[11px] text-ink-muted font-mono shrink-0">
        {fmtRelative(event.occurred_at)}
      </div>
      <ChevronRight className="w-3.5 h-3.5 text-ink-muted shrink-0" />
    </button>
  );
}

function ListView({ events, selectedId, onSelect }: {
  events: DeviceEventDTO[]; selectedId: string | null; onSelect: (id: string) => void;
}) {
  return (
    <Card padded={false}>
      {events.map((e) => (
        <EventRow key={e.id} event={e} isSelected={e.id === selectedId} onSelect={onSelect} />
      ))}
    </Card>
  );
}

function CompactView({ events, selectedId, onSelect }: {
  events: DeviceEventDTO[]; selectedId: string | null; onSelect: (id: string) => void;
}) {
  return (
    <Card padded={false}>
      {events.map((e) => (
        <EventRow key={e.id} event={e} compact isSelected={e.id === selectedId} onSelect={onSelect} />
      ))}
    </Card>
  );
}

function CardsView({ events, onSelect }: {
  events: DeviceEventDTO[]; onSelect: (id: string) => void;
}) {
  return (
    <div className="grid grid-cols-1 md:grid-cols-2 xl:grid-cols-3 gap-3">
      {events.map((e) => (
        <button
          key={e.id}
          onClick={() => onSelect(e.id)}
          className="text-left rounded-3xl bg-surface-soft/60 p-4 hover:bg-surface-soft transition"
        >
          <div className="flex items-center justify-between mb-2">
            <span className={cn(
              "px-2 py-0.5 rounded-full text-[10px] font-bold",
              SEVERITY_COLOR[e.severity],
            )}>
              {e.severity.toUpperCase()}
            </span>
            <span className="text-[11px] text-ink-muted font-mono">
              {fmtRelative(e.occurred_at)}
            </span>
          </div>
          <div className="text-sm font-semibold text-ink mb-1">{e.label}</div>
          <div className="text-xs text-ink-muted truncate">
            {e.device_label || e.gateway_label || e.site_label || "—"}
          </div>
          {e.message && (
            <div className="text-xs text-ink-muted mt-2 line-clamp-2">{e.message}</div>
          )}
        </button>
      ))}
    </div>
  );
}

function TimelineView({ events, onSelect }: {
  events: DeviceEventDTO[]; onSelect: (id: string) => void;
}) {
  return (
    <Card padded>
      <div className="relative pl-6">
        <div className="absolute left-2 top-2 bottom-2 w-px bg-surface-border" />
        {events.map((e) => (
          <button
            key={e.id}
            onClick={() => onSelect(e.id)}
            className="relative w-full text-left py-2 pl-4 hover:bg-ink/5 rounded-xl transition"
          >
            <div className={cn(
              "absolute -left-[1px] top-4 w-3 h-3 rounded-full border-2 border-white",
              SEVERITY_COLOR[e.severity].split(" ")[0].replace("bg-", "bg-").replace("/15", ""),
            )} />
            <div className="text-xs text-ink-muted font-mono mb-0.5">
              {new Date(e.occurred_at).toLocaleTimeString("fr-FR")}
            </div>
            <div className="text-sm font-medium text-ink">{e.label}</div>
            <div className="text-xs text-ink-muted truncate">
              {e.device_label} · {e.site_label}
            </div>
          </button>
        ))}
      </div>
    </Card>
  );
}

function WallView({ events, onSelect }: {
  events: DeviceEventDTO[]; onSelect: (id: string) => void;
}) {
  return (
    <div className="grid grid-cols-2 md:grid-cols-3 xl:grid-cols-5 gap-2">
      {events.slice(0, 30).map((e) => (
        <button
          key={e.id}
          onClick={() => onSelect(e.id)}
          className={cn(
            "rounded-2xl p-3 min-h-[100px] text-left transition",
            "hover:brightness-110",
            e.severity === "critical" || e.severity === "emergency"
              ? "bg-danger text-on-danger"
              : e.severity === "warning"
                ? "bg-warning text-on-warn"
                : "bg-obsidian text-white",
          )}
        >
          <div className="text-[10px] uppercase tracking-widest opacity-70">
            {e.severity}
          </div>
          <div className="text-sm font-bold mt-1 line-clamp-2">{e.label}</div>
          <div className="text-[10px] opacity-70 mt-1 truncate">
            {e.device_label || e.site_label}
          </div>
          <div className="text-[10px] opacity-60 mt-1 font-mono">
            {new Date(e.occurred_at).toLocaleTimeString("fr-FR")}
          </div>
        </button>
      ))}
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════
// EventDetailPanel — panneau latéral
// ═══════════════════════════════════════════════════════════════════
function EventDetailPanel({
  eventId, initialData, onClose,
}: {
  eventId: string;
  initialData: DeviceEventDTO;
  onClose: () => void;
}) {
  const { data: full, refetch } = useQuery({
    queryKey: ["event-detail", eventId],
    queryFn: async () => (await eventsService.detail(eventId)).data,
    initialData: initialData,
  });

  const [notes, setNotes] = useState("");
  const [busy, setBusy] = useState(false);

  const handleAction = async (action: "acknowledge" | "resolve" | "comment") => {
    if (action === "comment" && !notes) {
      toast.error("Ajouter un commentaire d'abord");
      return;
    }
    setBusy(true);
    try {
      if (action === "acknowledge") {
        await eventsService.acknowledge(eventId, notes);
        toast.success("Événement acquitté");
      } else if (action === "resolve") {
        await eventsService.resolve(eventId, notes);
        toast.success("Événement résolu");
      } else {
        await eventsService.comment(eventId, notes);
        toast.success("Commentaire ajouté");
      }
      setNotes("");
      refetch();
    } catch (e: any) {
      toast.error(e?.response?.data?.error ?? "Erreur");
    } finally {
      setBusy(false);
    }
  };

  return (
    <Card padded={false} className="sticky top-3 max-h-[calc(100vh-2rem)] overflow-auto">
      {/* Header */}
      <div className="p-4 border-b border-surface-border/40 flex items-start justify-between">
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-1">
            <span className={cn(
              "px-2 py-0.5 rounded-full text-[10px] font-bold",
              SEVERITY_COLOR[full.severity],
            )}>
              {full.severity.toUpperCase()}
            </span>
            <span className="font-mono text-[10px] text-ink-muted">{full.code}</span>
          </div>
          <h3 className="font-semibold text-sm text-ink line-clamp-2">{full.label}</h3>
        </div>
        <button onClick={onClose} className="p-1 hover:bg-ink/5 rounded-lg">
          <X className="w-4 h-4 text-ink-muted" />
        </button>
      </div>

      {/* Métadonnées */}
      <div className="p-4 space-y-3 text-xs">
        <MetaRow label="Occurred" value={new Date(full.occurred_at).toLocaleString("fr-FR")} />
        <MetaRow label="Received" value={new Date(full.received_at).toLocaleString("fr-FR")} />
        <MetaRow label="Site" value={full.site_label} />
        <MetaRow label="Zone" value={full.zone_id?.toString()} />
        <MetaRow label="Device" value={full.device_label} />
        <MetaRow label="Gateway" value={full.gateway_label || full.gateway_id?.slice(0, 8)} />
        <MetaRow label="Badge" value={full.badge_uid} mono />
        <MetaRow label="Casque" value={full.helmet_uid} mono />
        <MetaRow label="Titulaire" value={`${full.holder_kind} · ${full.holder_ref}`} />
        <MetaRow label="Transmission" value={full.transmission_mode} />
        <MetaRow label="Offline" value={full.is_offline ? "Oui" : "Non"} />
        {full.message && (
          <div className="pt-2 border-t border-surface-border/40">
            <div className="text-[10px] uppercase tracking-widest text-ink-muted mb-1">
              Message
            </div>
            <div className="text-ink">{full.message}</div>
          </div>
        )}
      </div>

      {/* Payload JSON */}
      {full.payload && Object.keys(full.payload).length > 0 && (
        <details className="border-t border-surface-border/40">
          <summary className="p-4 cursor-pointer text-xs font-semibold text-ink-muted uppercase tracking-widest">
            Payload technique
          </summary>
          <pre className="p-4 bg-obsidian text-white text-[10px] font-mono overflow-auto max-h-64">
            {JSON.stringify(full.payload, null, 2)}
          </pre>
        </details>
      )}

      {/* Actions */}
      <div className="p-4 border-t border-surface-border/40 space-y-2">
        <textarea
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
          placeholder="Notes (obligatoire pour commentaire)"
          rows={2}
          className="w-full text-xs p-2 rounded-xl bg-surface-soft resize-none focus:outline-none"
        />
        <div className="grid grid-cols-3 gap-2">
          <Button
            size="sm"
            variant="ghost"
            onClick={() => handleAction("acknowledge")}
            disabled={busy || full.is_acknowledged}
          >
            {full.is_acknowledged ? "Acquitté" : "Acquitter"}
          </Button>
          <Button
            size="sm"
            variant="dark"
            onClick={() => handleAction("resolve")}
            disabled={busy || full.is_resolved}
          >
            {full.is_resolved ? "Résolu" : "Résoudre"}
          </Button>
          <Button
            size="sm"
            variant="ghost"
            onClick={() => handleAction("comment")}
            disabled={busy || !notes}
          >
            Commenter
          </Button>
        </div>
      </div>

      {/* Historique acks */}
      {full.acknowledgements && full.acknowledgements.length > 0 && (
        <div className="p-4 border-t border-surface-border/40">
          <div className="text-[10px] uppercase tracking-widest text-ink-muted mb-2 font-semibold">
            Historique
          </div>
          <div className="space-y-2">
            {full.acknowledgements.map((a) => (
              <div key={a.id} className="text-xs bg-surface-soft/60 rounded-xl p-2">
                <div className="flex items-center justify-between mb-0.5">
                  <span className="font-semibold text-ink">{a.action}</span>
                  <span className="text-ink-muted text-[10px]">
                    {fmtRelative(a.created_at)}
                  </span>
                </div>
                <div className="text-ink-muted">{a.user}</div>
                {a.notes && <div className="text-ink mt-1">{a.notes}</div>}
              </div>
            ))}
          </div>
        </div>
      )}
    </Card>
  );
}

function MetaRow({ label, value, mono }: {
  label: string; value?: string | null; mono?: boolean;
}) {
  if (!value) return null;
  return (
    <div className="flex items-baseline gap-3">
      <div className="text-[10px] uppercase tracking-widest text-ink-muted w-24 shrink-0">
        {label}
      </div>
      <div className={cn("text-ink flex-1", mono && "font-mono text-[11px]")}>
        {value}
      </div>
    </div>
  );
}
