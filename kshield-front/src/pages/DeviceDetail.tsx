import { useMemo, useState } from "react";
import { useParams, useNavigate, Link } from "react-router-dom";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useLive } from "@/hooks/useLive";
import { PageHeader } from "@/components/PageHeader";
import { Card } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { KpiCard } from "@/components/KpiCard";
import { LivePulse } from "@/components/LivePulse";
import { devicesService, accessEventsService } from "@/services";
import { toApiError } from "@/lib/api";
import { fmtDateTime, fmtRelative, fmtTime } from "@/lib/format";
import {
  ArrowLeft, Cpu, PlugZap, Zap, Users, RefreshCw, Activity,
  Wifi, WifiOff, Terminal, Copy, ExternalLink,
} from "lucide-react";
import toast from "react-hot-toast";

export function DeviceDetailPage() {
  const params = useParams<{ id: string }>();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const id = Number(params.id);
  const [tab, setTab] = useState<"overview" | "events" | "debug">("overview");

  // ─── Device (polling 15s pour heartbeat live) ────────────
  const device = useLive(
    ["device", id],
    async () => (await devicesService.get(id)).data,
    { intervalMs: 15_000, enabled: !!id },
  );

  // ─── Events récents pour ce device ────────────────────────
  const events = useLive(
    ["device", id, "events"],
    async () =>
      (
        await accessEventsService.list({
          device: id,
          page_size: 30,
          ordering: "-timestamp",
        })
      ).data,
    { intervalMs: 10_000, enabled: !!id },
  );

  // ─── Debug iclock (dernier POST bruts) ────────────────────
  const debug = useLive(
    ["device", id, "iclock-debug"],
    async () => (await devicesService.iclockDebug(id)).data,
    { intervalMs: 15_000, enabled: tab === "debug" && !!id },
  );

  // ─── Actions ──────────────────────────────────────────────
  const testConn = useMutation({
    mutationFn: () => devicesService.testConnection(id).then((r) => r.data),
    onSuccess: (r) => {
      toast.success(r?.reachable ? "Équipement joignable ✓" : "Injoignable ✗");
      qc.invalidateQueries({ queryKey: ["device", id] });
    },
    onError: (e) => toast.error(toApiError(e).message),
  });

  const zkSync = useMutation({
    mutationFn: () => devicesService.zkSyncNow(id).then((r) => r.data),
    onSuccess: () => toast.success("Sync ZKTeco lancée en arrière-plan"),
    onError: (e) => toast.error(toApiError(e).message),
  });

  const zkPushUsers = useMutation({
    mutationFn: () => devicesService.zkPushUsers(id).then((r) => r.data),
    onSuccess: () => toast.success("Push utilisateurs → terminal lancé"),
    onError: (e) => toast.error(toApiError(e).message),
  });

  // ─── Statut computed ──────────────────────────────────────
  const d = device.data;
  const online = d?.is_online || d?.status === "active";
  const heartbeatAgeSec = useMemo(() => {
    if (!d?.last_heartbeat_at) return null;
    return Math.round((Date.now() - new Date(d.last_heartbeat_at).getTime()) / 1000);
  }, [d?.last_heartbeat_at]);

  if (device.isLoading && !d) {
    return (
      <div className="text-center py-16 text-ink-muted">Chargement de l'équipement…</div>
    );
  }
  if (!d) {
    return (
      <div className="text-center py-16">
        <p className="text-ink-muted mb-3">Équipement introuvable</p>
        <Link to="/devices" className="btn-ghost inline-flex">
          <ArrowLeft className="w-4 h-4" /> Retour aux équipements
        </Link>
      </div>
    );
  }

  return (
    <div>
      <PageHeader
        title={d.name}
        subtitle={
          <div className="flex items-center gap-2 text-xs">
            {d.serial_number && (
              <code className="font-mono text-ink-soft">{d.serial_number}</code>
            )}
            {d.type && (
              <>
                <span className="text-ink-soft">·</span>
                <span>{d.type}</span>
              </>
            )}
          </div>
        }
        live
        actions={
          <div className="flex items-center gap-2">
            <Button
              variant="ghost"
              size="sm"
              leftIcon={<ArrowLeft className="w-3.5 h-3.5" />}
              onClick={() => navigate("/devices")}
            >
              Retour
            </Button>
            <Button
              variant="ghost"
              size="sm"
              leftIcon={<PlugZap className="w-3.5 h-3.5" />}
              onClick={() => testConn.mutate()}
              loading={testConn.isPending}
            >
              Tester connexion
            </Button>
            {(d.type?.includes("zk") || d.type === "attendance") && (
              <>
                <Button
                  variant="ghost"
                  size="sm"
                  leftIcon={<Zap className="w-3.5 h-3.5" />}
                  onClick={() => zkSync.mutate()}
                  loading={zkSync.isPending}
                >
                  Sync events
                </Button>
                <Button
                  variant="ghost"
                  size="sm"
                  leftIcon={<Users className="w-3.5 h-3.5" />}
                  onClick={() => zkPushUsers.mutate()}
                  loading={zkPushUsers.isPending}
                >
                  Push users
                </Button>
              </>
            )}
          </div>
        }
      />

      {/* Bandeau statut */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-5">
        <KpiCard
          label="Statut"
          value={
            <Badge tone={online ? "ok" : "danger"} dot>
              {online ? (
                <>
                  <Wifi className="w-3 h-3" /> En ligne
                </>
              ) : (
                <>
                  <WifiOff className="w-3 h-3" /> Offline
                </>
              )}
            </Badge>
          }
          icon={<Cpu className="w-5 h-5" />}
          accent={online ? "ok" : "danger"}
        />
        <KpiCard
          label="Dernier signal"
          value={d.last_heartbeat_at ? fmtRelative(d.last_heartbeat_at) : "Jamais"}
          hint={
            heartbeatAgeSec !== null && heartbeatAgeSec < 60
              ? `${heartbeatAgeSec}s`
              : undefined
          }
          icon={<Activity className="w-5 h-5" />}
          accent={
            heartbeatAgeSec !== null && heartbeatAgeSec < 60
              ? "ok"
              : heartbeatAgeSec !== null && heartbeatAgeSec < 300
              ? "warn"
              : "danger"
          }
        />
        <KpiCard
          label="Événements récents"
          value={events.data?.count ?? 0}
          icon={<Activity className="w-5 h-5" />}
          accent="info"
        />
        <KpiCard
          label="Firmware"
          value={d.firmware_version || "—"}
          icon={<Terminal className="w-5 h-5" />}
          accent="brand"
        />
      </div>

      {/* Tabs */}
      <div className="mb-4 border-b border-surface-border flex gap-1">
        {(
          [
            { key: "overview", label: "Aperçu" },
            { key: "events", label: `Événements (${events.data?.count ?? 0})` },
            { key: "debug", label: "Debug iclock" },
          ] as const
        ).map((t) => (
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            className={
              tab === t.key
                ? "px-4 py-2 text-sm font-medium text-brand-500 border-b-2 border-brand-500 -mb-px"
                : "px-4 py-2 text-sm text-ink-muted hover:text-ink"
            }
          >
            {t.label}
          </button>
        ))}
      </div>

      {/* Contenu selon tab */}
      {tab === "overview" && <OverviewTab device={d} />}
      {tab === "events" && (
        <Card padded={false}>
          <ul className="divide-y divide-surface-border/50 max-h-[60vh] overflow-y-auto">
            {events.data?.results?.length === 0 && (
              <li className="p-8 text-center text-ink-muted text-sm">
                Aucun événement pour ce terminal
              </li>
            )}
            {events.data?.results?.map((e) => (
              <li
                key={e.id}
                className="px-5 py-3 flex items-center gap-4 hover:bg-surface-soft/40"
              >
                <div
                  className={
                    e.decision === "granted"
                      ? "w-8 h-8 rounded-lg bg-ok/10 text-ok grid place-items-center shrink-0"
                      : "w-8 h-8 rounded-lg bg-danger/10 text-danger grid place-items-center shrink-0"
                  }
                >
                  <Activity className="w-4 h-4" />
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-medium text-ink truncate">
                      {e.holder_name || e.badge_uid || "Inconnu"}
                    </span>
                    <Badge tone={e.direction === "in" ? "info" : "muted"}>
                      {e.direction === "in" ? "Entrée" : e.direction === "out" ? "Sortie" : "—"}
                    </Badge>
                  </div>
                  <div className="text-[11px] text-ink-soft font-mono truncate">
                    {e.badge_uid || "—"}
                  </div>
                </div>
                <div className="text-right text-xs">
                  <div className="font-mono">{fmtTime(e.timestamp)}</div>
                  <div className="text-ink-soft">{fmtRelative(e.timestamp)}</div>
                </div>
              </li>
            ))}
          </ul>
        </Card>
      )}
      {tab === "debug" && <DebugTab debug={debug.data} loading={debug.isLoading} />}
    </div>
  );
}

// ─────────────────────────────────────────────────────────────
// Overview tab — infos techniques + config réseau
// ─────────────────────────────────────────────────────────────
function OverviewTab({ device }: { device: any }) {
  const info = [
    { label: "ID", value: device.id },
    { label: "Type", value: device.type },
    { label: "Serial", value: device.serial_number, mono: true },
    {
      label: "IP:Port",
      value: device.ip_address ? `${device.ip_address}${device.port ? `:${device.port}` : ""}` : null,
      mono: true,
    },
    { label: "Firmware", value: device.firmware_version, mono: true },
    {
      label: "Modèle",
      value:
        typeof device.model === "object"
          ? `${device.model?.brand || ""} ${device.model?.model_name || ""}`
          : null,
    },
    {
      label: "Site",
      value: typeof device.site === "object" ? device.site?.name : null,
    },
    {
      label: "Créé le",
      value: device.created_at ? fmtDateTime(device.created_at) : null,
    },
    {
      label: "Dernier heartbeat",
      value: device.last_heartbeat_at ? fmtDateTime(device.last_heartbeat_at) : null,
    },
  ];

  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
      <Card title="Informations techniques">
        <dl className="grid grid-cols-2 gap-x-4 gap-y-3 text-sm">
          {info.map((i) => (
            <div key={i.label} className="min-w-0">
              <dt className="text-[11px] uppercase tracking-wider text-ink-soft">
                {i.label}
              </dt>
              <dd
                className={
                  i.mono
                    ? "font-mono text-xs text-ink mt-0.5 break-all"
                    : "text-ink mt-0.5 truncate"
                }
              >
                {i.value || <span className="text-ink-soft">—</span>}
              </dd>
            </div>
          ))}
        </dl>
      </Card>

      <Card title="Configuration ADMS / push">
        <p className="text-xs text-ink-muted mb-3">
          Pour un terminal push-mode (ZKTeco K14, AiFace), configurer sur le
          terminal l'URL suivante (menu COMM / Cloud Server) :
        </p>
        <div className="bg-surface-soft/60 border border-surface-border rounded-lg p-3 font-mono text-xs text-ink break-all">
          https://api.kaydanshield.com/iclock/cdata
        </div>
        <div className="mt-3 flex gap-2">
          <Button
            size="sm"
            variant="ghost"
            leftIcon={<Copy className="w-3.5 h-3.5" />}
            onClick={() => {
              navigator.clipboard.writeText("https://api.kaydanshield.com/iclock/cdata");
              toast.success("URL copiée");
            }}
          >
            Copier l'URL
          </Button>
        </div>
        <p className="mt-4 text-[11px] text-ink-soft">
          Le terminal doit envoyer son heartbeat sur{" "}
          <code className="font-mono">/iclock/getrequest?SN={device.serial_number || "…"}</code>
          {" "}et ses events sur{" "}
          <code className="font-mono">POST /iclock/cdata</code>.
        </p>
      </Card>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────
// Debug tab — dernières requêtes iclock brutes (pour reverse eng)
// ─────────────────────────────────────────────────────────────
function DebugTab({ debug, loading }: { debug: any; loading: boolean }) {
  if (loading) return <div className="text-center py-10 text-ink-muted">Chargement…</div>;

  return (
    <Card
      title="Dernières requêtes /iclock/cdata reçues"
      subtitle={
        debug?.entries_count
          ? `${debug.entries_count} entrées en cache Redis`
          : "Aucune requête POST reçue de ce terminal"
      }
      actions={<LivePulse />}
    >
      {!debug?.entries?.length && (
        <div className="text-center py-8 text-ink-muted text-sm">
          Aucun POST /iclock/cdata pour ce SN.<br />
          <span className="text-xs">
            Si le terminal envoie du heartbeat mais aucun event : configurer l'upload
            temps réel dans les paramètres du terminal (Realtime=1).
          </span>
        </div>
      )}
      <ul className="space-y-3 max-h-[60vh] overflow-y-auto">
        {debug?.entries?.map((e: any, i: number) => (
          <li
            key={i}
            className="p-3 rounded-lg bg-surface-soft/40 border border-surface-border"
          >
            <div className="flex items-center gap-2 text-xs">
              <Badge tone="info">{e.table || "no-table"}</Badge>
              <span className="text-ink-soft">{fmtDateTime(e.at)}</span>
              <span className="ml-auto text-ink-soft">{e.content_type}</span>
            </div>
            {e.query && Object.keys(e.query).length > 0 && (
              <pre className="mt-2 text-[11px] font-mono text-info bg-surface p-2 rounded overflow-x-auto">
                {JSON.stringify(e.query, null, 2)}
              </pre>
            )}
            <pre className="mt-2 text-[11px] font-mono text-ink bg-surface p-2 rounded overflow-x-auto whitespace-pre-wrap break-all">
              {e.body_preview || <span className="text-ink-soft">(body vide)</span>}
            </pre>
          </li>
        ))}
      </ul>
    </Card>
  );
}
