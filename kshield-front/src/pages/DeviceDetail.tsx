import { useState, useMemo } from "react";
import { useParams, useNavigate, Link } from "react-router-dom";
import { useMutation, useQueryClient, useQuery } from "@tanstack/react-query";
import { useLive } from "@/hooks/useLive";
import { PageHeader } from "@/components/PageHeader";
import { Card } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Modal } from "@/components/ui/Modal";
import { KpiCard } from "@/components/KpiCard";
import { LivePulse } from "@/components/LivePulse";
import { RealtimeDeviceStatus } from "@/components/RealtimeDeviceStatus";
import { DeviceCommandConsole } from "@/components/DeviceCommandConsole";
import { DigitalTwinPanel } from "@/components/DigitalTwinPanel";
import { devicesService, accessEventsService, sitesService, zonesService } from "@/services";
import { toApiError } from "@/lib/api";
import { fmtDateTime, fmtRelative, fmtTime } from "@/lib/format";
import { cn } from "@/lib/cn";
import {
  ArrowLeft, Cpu, PlugZap, Zap, RefreshCw, Activity, Wifi, WifiOff,
  Terminal, Copy, Battery, Signal, Thermometer, Cpu as CpuIcon,
  HardDrive, Network, Server, Shield, Radar, MapPin, Layers, DoorClosed,
  Calendar, User, Package, Info, Settings, History, Trash2, Edit3,
  Play, Square, Download, ClipboardList, AlertTriangle, ChevronRight,
} from "lucide-react";
import toast from "react-hot-toast";

export function DeviceDetailPage() {
  const params = useParams<{ id: string }>();
  const navigate = useNavigate();
  const qc = useQueryClient();
  const id = Number(params.id);
  const [tab, setTab] = useState<"info" | "state" | "factory" | "config" | "history" | "logs" | "debug">("info");

  const [assocOpen, setAssocOpen] = useState(false);
  const [assocForm, setAssocForm] = useState({ site: "", zone: "", checkpoint: "" });

  // Device live
  const device = useLive(
    ["device", id],
    async () => (await devicesService.get(id)).data,
    { intervalMs: 15_000, enabled: !!id },
  );

  // Events récents
  const events = useLive(
    ["device", id, "events"],
    async () =>
      (await accessEventsService.list({
        device: id, page_size: 30, ordering: "-timestamp",
      })).data,
    { intervalMs: 10_000, enabled: !!id && tab === "history" },
  );

  // Debug iclock si tab
  const debug = useLive(
    ["device", id, "iclock-debug"],
    async () => (await devicesService.iclockDebug(id)).data,
    { intervalMs: 15_000, enabled: tab === "debug" && !!id },
  );

  // Logs device
  const logs = useQuery({
    queryKey: ["device", id, "logs"],
    queryFn: async () => (await devicesService.logs(id)).data,
    enabled: !!id && tab === "logs",
    retry: false,
  });

  // Sites & zones pour la modale d'association
  const { data: sites } = useQuery({
    queryKey: ["sites", "for-device-assoc"],
    queryFn: async () => (await sitesService.list({ page_size: 200 })).data,
    enabled: assocOpen,
  });
  const { data: zones } = useQuery({
    queryKey: ["zones", "for-device-assoc", assocForm.site],
    queryFn: async () => (await zonesService.list({ page_size: 100, site: assocForm.site })).data,
    enabled: assocOpen && !!assocForm.site,
  });

  // ─── Mutations actions ─────────────────────────
  const testMut = useMutation({
    mutationFn: () => devicesService.testConnection(id).then((r) => r.data),
    onSuccess: (r) => { toast.success(r?.reachable ? "Joignable ✓" : "Injoignable ✗"); qc.invalidateQueries({ queryKey: ["device", id] }); },
    onError: (e) => toast.error(toApiError(e).message),
  });
  const pingMut = useMutation({
    mutationFn: () => devicesService.ping(id).then((r) => r.data),
    onSuccess: (r) => toast.success(`Ping ${r?.latency_ms || "?"} ms`),
    onError: (e) => toast.error(toApiError(e).message),
  });
  const syncMut = useMutation({
    mutationFn: () => devicesService.syncNow(id),
    onSuccess: () => toast.success("Sync lancée"),
    onError: (e) => toast.error(toApiError(e).message),
  });
  const restartMut = useMutation({
    mutationFn: () => devicesService.restart(id),
    onSuccess: () => toast.success("Redémarrage envoyé"),
    onError: (e) => toast.error(toApiError(e).message),
  });
  const resetMut = useMutation({
    mutationFn: () => devicesService.resetConfig(id),
    onSuccess: () => toast.success("Configuration réinitialisée"),
    onError: (e) => toast.error(toApiError(e).message),
  });
  const fwMut = useMutation({
    mutationFn: () => devicesService.updateFirmware(id),
    onSuccess: () => toast.success("Mise à jour firmware planifiée"),
    onError: (e) => toast.error(toApiError(e).message),
  });
  const maintenanceMut = useMutation({
    mutationFn: (enabled: boolean) => devicesService.setMaintenance(id, enabled),
    onSuccess: (_, enabled) => {
      toast.success(enabled ? "Mis en maintenance" : "Sorti de maintenance");
      qc.invalidateQueries({ queryKey: ["device", id] });
    },
    onError: (e) => toast.error(toApiError(e).message),
  });
  const associateMut = useMutation({
    mutationFn: () => devicesService.update(id, {
      site: assocForm.site ? Number(assocForm.site) : null,
      zone: assocForm.zone ? Number(assocForm.zone) : null,
      checkpoint: assocForm.checkpoint ? Number(assocForm.checkpoint) : null,
    }),
    onSuccess: () => {
      toast.success("Association mise à jour");
      setAssocOpen(false);
      qc.invalidateQueries({ queryKey: ["device", id] });
    },
    onError: (e) => toast.error(toApiError(e).message),
  });
  const deleteMut = useMutation({
    mutationFn: () => devicesService.remove(id),
    onSuccess: () => { toast.success("Équipement supprimé"); navigate("/devices"); },
    onError: (e) => toast.error(toApiError(e).message),
  });
  const exportMut = useMutation({
    mutationFn: () => devicesService.exportSpec(id),
    onSuccess: (r: any) => {
      const url = URL.createObjectURL(r.data);
      const a = document.createElement("a");
      a.href = url;
      a.download = `device-${id}-spec.pdf`;
      a.click();
      URL.revokeObjectURL(url);
      toast.success("Fiche technique exportée");
    },
    onError: (e) => toast.error(toApiError(e).message),
  });

  const d = device.data;
  const heartbeatAgeSec = useMemo(() => {
    if (!d?.last_heartbeat_at) return null;
    return Math.round((Date.now() - new Date(d.last_heartbeat_at).getTime()) / 1000);
  }, [d?.last_heartbeat_at]);

  if (device.isLoading && !d)
    return <div className="text-center py-16 text-ink-muted">Chargement…</div>;
  if (!d)
    return (
      <div className="text-center py-16">
        <p className="text-ink-muted mb-3">Équipement introuvable</p>
        <Link to="/devices" className="btn-ghost inline-flex">
          <ArrowLeft className="w-4 h-4" /> Retour
        </Link>
      </div>
    );

  const online = d.is_online || d.status === "active";

  return (
    <div>
      <PageHeader
        title={d.name}
        subtitle={
          <div className="flex items-center gap-2 text-xs">
            {d.serial_number && <code className="font-mono text-ink-soft">{d.serial_number}</code>}
            {d.type && (<><span className="text-ink-soft">·</span><span>{d.type}</span></>)}
            {d.model?.brand && (<><span className="text-ink-soft">·</span><span>{d.model.brand} {d.model.model_name}</span></>)}
          </div>
        }
        live
        actions={
          <div className="flex items-center gap-1 flex-wrap">
            <Button variant="ghost" size="sm" leftIcon={<ArrowLeft className="w-3.5 h-3.5" />} onClick={() => navigate("/devices")}>
              Retour
            </Button>
            <Button variant="ghost" size="sm" leftIcon={<Activity className="w-3.5 h-3.5" />}
                    onClick={() => pingMut.mutate()} loading={pingMut.isPending}>Ping</Button>
            <Button variant="ghost" size="sm" leftIcon={<PlugZap className="w-3.5 h-3.5" />}
                    onClick={() => testMut.mutate()} loading={testMut.isPending}>Test</Button>
            <Button variant="ghost" size="sm" leftIcon={<Zap className="w-3.5 h-3.5" />}
                    onClick={() => syncMut.mutate()} loading={syncMut.isPending}>Sync</Button>
            <Button variant="ghost" size="sm" leftIcon={<Layers className="w-3.5 h-3.5" />}
                    onClick={() => setAssocOpen(true)}>Associer</Button>
            <Button variant="ghost" size="sm"
                    leftIcon={d.status === "maintenance" ? <Play className="w-3.5 h-3.5" /> : <Square className="w-3.5 h-3.5" />}
                    onClick={() => maintenanceMut.mutate(d.status !== "maintenance")}>
              {d.status === "maintenance" ? "Sortir maint." : "Maintenance"}
            </Button>
            <Button variant="ghost" size="sm" leftIcon={<Download className="w-3.5 h-3.5" />}
                    onClick={() => exportMut.mutate()}>Export PDF</Button>
            <Button variant="ghost" size="sm" leftIcon={<RefreshCw className="w-3.5 h-3.5" />}
                    onClick={() => confirm(`Redémarrer ${d.name} ?`) && restartMut.mutate()}>Redémarrer</Button>
            <Button variant="danger" size="sm" leftIcon={<Trash2 className="w-3.5 h-3.5" />}
                    onClick={() => confirm(`Supprimer définitivement ${d.name} ?`) && deleteMut.mutate()}>
              Supprimer
            </Button>
          </div>
        }
      />

      {/* Bandeau statut temps réel (WS + probe TCP) */}
      <div className="mb-4">
        <RealtimeDeviceStatus deviceId={id} />
      </div>

      {/* Digital Twin — jumeau numérique (le front ne parle qu'au twin) */}
      <div className="mb-4 p-3 border border-surface-border rounded-lg">
        <div className="text-xs uppercase tracking-wider text-ink-muted mb-2 flex items-center gap-1">
          <Cpu className="w-3.5 h-3.5" /> Jumeau numérique
        </div>
        <DigitalTwinPanel deviceId={id} />
      </div>

      {/* Bandeau KPIs statut */}
      <div className="grid grid-cols-2 lg:grid-cols-5 gap-3 mb-4">
        <KpiCard label="Statut" accent={online ? "ok" : "danger"} icon={<Cpu className="w-5 h-5" />}
          value={<Badge tone={online ? "ok" : "danger"} dot>{online ? "En ligne" : "Offline"}</Badge>} />
        <KpiCard label="Dernier heartbeat" accent={
          heartbeatAgeSec != null && heartbeatAgeSec < 60 ? "ok" :
          heartbeatAgeSec != null && heartbeatAgeSec < 300 ? "warn" : "danger"
        } icon={<Activity className="w-5 h-5" />}
          value={d.last_heartbeat_at ? fmtRelative(d.last_heartbeat_at) : "Jamais"}
          hint={heartbeatAgeSec != null ? `${heartbeatAgeSec}s` : undefined} />
        <KpiCard label="Batterie" accent={
          d.battery_level == null ? "brand" :
          d.battery_level < 20 ? "danger" : d.battery_level < 40 ? "warn" : "ok"
        } icon={<Battery className="w-5 h-5" />}
          value={d.battery_level != null ? `${d.battery_level}%` : "—"} />
        <KpiCard label="Signal" accent={
          d.signal_level == null ? "brand" :
          d.signal_level < 30 ? "danger" : d.signal_level < 60 ? "warn" : "ok"
        } icon={<Signal className="w-5 h-5" />}
          value={d.signal_level != null ? `${d.signal_level}%` : "—"} />
        <KpiCard label="Firmware" accent="info" icon={<Terminal className="w-5 h-5" />}
          value={d.firmware_version || "—"} hint={d.hardware_version} />
      </div>

      {/* Tabs */}
      <div className="mb-4 border-b border-surface-border flex gap-1 overflow-x-auto">
        {([
          { key: "info",    label: "Informations",  icon: Info },
          { key: "state",   label: "État & santé",   icon: Activity },
          { key: "factory", label: "Données usine",  icon: Package },
          { key: "config",  label: "Configuration",  icon: Settings },
          { key: "history", label: "Historique",     icon: History },
          { key: "logs",    label: "Logs",           icon: ClipboardList },
          { key: "debug",   label: "Debug iclock",   icon: Terminal },
        ] as const).map((t) => (
          <button key={t.key} onClick={() => setTab(t.key)}
                  className={cn("flex items-center gap-1.5 px-4 py-2 text-sm whitespace-nowrap",
                    tab === t.key
                      ? "font-medium text-brand-ink border-b-2 border-brand-500 -mb-px"
                      : "text-ink-muted hover:text-ink")}>
            <t.icon className="w-3.5 h-3.5" />
            {t.label}
          </button>
        ))}
      </div>

      {tab === "info"    && <InfoTab d={d} />}
      {tab === "state"   && <StateTab d={d} heartbeatAgeSec={heartbeatAgeSec} />}
      {tab === "factory" && <FactoryTab d={d} />}
      {tab === "config"  && <ConfigTab d={d} />}
      {tab === "history" && <HistoryTab events={events.data?.results || []} />}
      {tab === "logs"    && (
        <div className="space-y-4">
          <div className="p-3 border border-surface-border rounded-lg">
            <DeviceCommandConsole deviceId={id} />
          </div>
          <LogsTab logs={logs.data} loading={logs.isLoading} />
        </div>
      )}
      {tab === "debug"   && <DebugTab debug={debug.data} loading={debug.isLoading} />}

      {/* Modal association */}
      <Modal open={assocOpen} onClose={() => setAssocOpen(false)}
             title="Associer l'équipement à un site / zone / porte"
             footer={<>
               <Button variant="ghost" onClick={() => setAssocOpen(false)}>Annuler</Button>
               <Button onClick={() => associateMut.mutate()} loading={associateMut.isPending}>
                 Enregistrer
               </Button>
             </>}>
        <div className="space-y-3">
          <label className="block">
            <span className="text-xs font-medium text-ink-muted">Site</span>
            <select value={assocForm.site}
                    onChange={(e) => setAssocForm({ ...assocForm, site: e.target.value, zone: "", checkpoint: "" })}
                    className="field w-full mt-1.5">
              <option value="">— Aucun —</option>
              {sites?.results?.map((s: any) => <option key={s.id} value={s.id}>{s.name}</option>)}
            </select>
          </label>
          <label className="block">
            <span className="text-xs font-medium text-ink-muted">Zone (dans le site)</span>
            <select value={assocForm.zone}
                    onChange={(e) => setAssocForm({ ...assocForm, zone: e.target.value })}
                    disabled={!assocForm.site}
                    className="field w-full mt-1.5">
              <option value="">— Aucune —</option>
              {zones?.results?.map((z: any) => <option key={z.id} value={z.id}>{z.name}</option>)}
            </select>
          </label>
          <label className="block">
            <span className="text-xs font-medium text-ink-muted">Point de contrôle / porte (ID)</span>
            <input type="number" value={assocForm.checkpoint}
                   onChange={(e) => setAssocForm({ ...assocForm, checkpoint: e.target.value })}
                   className="field w-full mt-1.5" placeholder="ID du checkpoint" />
          </label>
        </div>
      </Modal>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────
// TAB 1 — Informations générales
// ─────────────────────────────────────────────────────────────
function InfoTab({ d }: { d: any }) {
  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
      <Card title={<span className="flex items-center gap-2"><Info className="w-4 h-4" /> Informations générales</span>}>
        <dl className="grid grid-cols-2 gap-y-2 text-sm">
          <Row label="Nom" value={d.name} />
          <Row label="Type" value={d.type} />
          <Row label="Marque" value={d.model?.brand} />
          <Row label="Modèle" value={d.model?.model_name} />
          <Row label="Numéro série" value={d.serial_number} mono />
          <Row label="Code tag (BLE/RFID/NFC)" value={d.tag_uid || d.beacon_uid} mono />
          <Row label="Date installation" value={d.commissioned_at ? fmtDateTime(d.commissioned_at) : "—"} />
          <Row label="Responsable technique" value={d.responsible_name} />
        </dl>
      </Card>

      <Card title={<span className="flex items-center gap-2"><Network className="w-4 h-4" /> Réseau</span>}>
        <dl className="grid grid-cols-2 gap-y-2 text-sm">
          <Row label="Adresse IP" value={d.ip_address} mono />
          <Row label="Port" value={d.port ? String(d.port) : "—"} mono />
          <Row label="Adresse MAC" value={d.mac_address} mono />
          <Row label="Protocole" value={d.protocol || d.model?.protocol} />
        </dl>
      </Card>

      <Card title={<span className="flex items-center gap-2"><MapPin className="w-4 h-4" /> Emplacement</span>}>
        <dl className="grid grid-cols-2 gap-y-2 text-sm">
          <Row label="Site" value={typeof d.site === "object" ? d.site?.name : "—"} />
          <Row label="Zone" value={typeof d.zone === "object" ? d.zone?.name : "—"} />
          <Row icon={<DoorClosed className="w-3.5 h-3.5" />} label="Porte / checkpoint"
               value={typeof d.checkpoint === "object" ? d.checkpoint?.name : "—"} span={2} />
        </dl>
      </Card>

      <Card title={<span className="flex items-center gap-2"><Calendar className="w-4 h-4" /> Dates</span>}>
        <dl className="grid grid-cols-2 gap-y-2 text-sm">
          <Row label="Créé le" value={d.created_at ? fmtDateTime(d.created_at) : "—"} />
          <Row label="Mis en service" value={d.commissioned_at ? fmtDateTime(d.commissioned_at) : "—"} />
          <Row label="Dernière activité" value={d.last_heartbeat_at ? fmtRelative(d.last_heartbeat_at) : "Jamais"} span={2} />
        </dl>
      </Card>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────
// TAB 2 — État & santé (temps réel)
// ─────────────────────────────────────────────────────────────
function StateTab({ d, heartbeatAgeSec }: { d: any; heartbeatAgeSec: number | null }) {
  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
      <Card title={<span className="flex items-center gap-2">
        <Activity className="w-4 h-4" /> Connectivité <LivePulse />
      </span>}>
        <dl className="grid grid-cols-2 gap-y-3 text-sm">
          <Row label="Statut" value={
            <Badge tone={d.is_online ? "ok" : "danger"} dot>{d.is_online ? "En ligne" : "Offline"}</Badge>
          } />
          <Row label="Dernier ping" value={heartbeatAgeSec != null ? `${heartbeatAgeSec}s ago` : "—"} />
          <Row label="Latence moyenne" value={d.avg_latency_ms ? `${d.avg_latency_ms} ms` : "—"} />
          <Row label="Uptime" value={d.uptime_hours ? `${d.uptime_hours}h` : "—"} />
        </dl>
      </Card>

      <Card title={<span className="flex items-center gap-2"><Battery className="w-4 h-4" /> Ressources matérielles</span>}>
        <div className="space-y-3">
          <ResourceBar label="Batterie" value={d.battery_level} icon={<Battery className="w-3.5 h-3.5" />}
                       lowThreshold={20} unit="%" />
          <ResourceBar label="Signal" value={d.signal_level} icon={<Signal className="w-3.5 h-3.5" />}
                       lowThreshold={30} unit="%" />
          <ResourceBar label="Charge CPU" value={d.cpu_usage} icon={<CpuIcon className="w-3.5 h-3.5" />}
                       highThreshold={80} unit="%" />
          <ResourceBar label="Mémoire" value={d.memory_usage} icon={<HardDrive className="w-3.5 h-3.5" />}
                       highThreshold={85} unit="%" />
          <ResourceBar label="Stockage" value={d.storage_usage} icon={<HardDrive className="w-3.5 h-3.5" />}
                       highThreshold={90} unit="%" />
          {d.temperature != null && (
            <div className="flex items-center justify-between text-sm">
              <span className="flex items-center gap-1.5 text-ink-muted">
                <Thermometer className="w-3.5 h-3.5" /> Température
              </span>
              <Badge tone={d.temperature > 70 ? "danger" : d.temperature > 55 ? "warn" : "ok"}>
                {d.temperature}°C
              </Badge>
            </div>
          )}
        </div>
      </Card>

      {d.recent_errors?.length > 0 && (
        <Card title={<span className="flex items-center gap-2 text-danger">
          <AlertTriangle className="w-4 h-4" /> Erreurs récentes ({d.recent_errors.length})
        </span>} className="lg:col-span-2">
          <ul className="space-y-2">
            {d.recent_errors.slice(0, 10).map((e: any, i: number) => (
              <li key={i} className="p-2 rounded bg-danger/5 border border-danger/10 text-xs">
                <div className="flex items-center justify-between">
                  <span className="font-medium text-danger">{e.code || "ERROR"}</span>
                  <span className="text-ink-soft">{fmtRelative(e.at)}</span>
                </div>
                <div className="mt-0.5 text-ink-muted">{e.message}</div>
              </li>
            ))}
          </ul>
        </Card>
      )}
    </div>
  );
}

// ─────────────────────────────────────────────────────────────
// TAB 3 — Données usine
// ─────────────────────────────────────────────────────────────
function FactoryTab({ d }: { d: any }) {
  const spec = d.spec || d.model?.spec || {};
  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
      <Card title={<span className="flex items-center gap-2"><Package className="w-4 h-4" /> Identification usine</span>}>
        <dl className="grid grid-cols-2 gap-y-2 text-sm">
          <Row label="Fabricant" value={d.model?.brand} />
          <Row label="Modèle exact" value={d.model?.model_name} />
          <Row label="ID fabricant" value={spec.manufacturer_id || d.manufacturer_id} mono />
          <Row label="Numéro série usine" value={d.serial_number} mono />
          <Row label="Version firmware" value={d.firmware_version} mono />
          <Row label="Version hardware" value={d.hardware_version} mono />
          <Row label="Date fabrication"
               value={spec.manufactured_at ? fmtDateTime(spec.manufactured_at) : "—"} />
          <Row label="Garantie jusqu'à"
               value={spec.warranty_until ? fmtDateTime(spec.warranty_until) : "—"} />
        </dl>
      </Card>

      <Card title="Capacités & protocoles">
        <dl className="grid grid-cols-2 gap-y-2 text-sm">
          <Row label="Capacité utilisateurs" value={spec.users_capacity ? String(spec.users_capacity) : "—"} />
          <Row label="Capacité badges" value={spec.badges_capacity ? String(spec.badges_capacity) : "—"} />
          <Row label="Capacité logs" value={spec.logs_capacity ? String(spec.logs_capacity) : "—"} />
          <Row label="Mémoire flash" value={spec.flash_memory || "—"} />
          <Row label="Protocoles supportés"
               value={(spec.protocols || d.model?.protocols || []).join(", ") || "—"} span={2} />
          <Row label="Ports actifs" value={(spec.active_ports || []).join(", ") || "—"} span={2} />
        </dl>
      </Card>

      {spec && Object.keys(spec).length > 0 && (
        <Card title="Spec technique brute (JSON)" className="lg:col-span-2">
          <pre className="text-[10px] font-mono text-ink-muted bg-surface p-3 rounded-lg overflow-x-auto max-h-64">
            {JSON.stringify(spec, null, 2)}
          </pre>
        </Card>
      )}
    </div>
  );
}

// ─────────────────────────────────────────────────────────────
// TAB 4 — Configuration
// ─────────────────────────────────────────────────────────────
function ConfigTab({ d }: { d: any }) {
  const admsUrl = "https://api.kaydanshield.com/iclock/cdata";
  return (
    <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
      <Card title={<span className="flex items-center gap-2"><Network className="w-4 h-4" /> Configuration réseau</span>}>
        <dl className="grid grid-cols-2 gap-y-2 text-sm">
          <Row label="Mode IP" value={d.ip_config_mode || "DHCP"} />
          <Row label="Adresse IP" value={d.ip_address} mono />
          <Row label="Masque" value={d.netmask || "—"} mono />
          <Row label="Passerelle" value={d.gateway || "—"} mono />
          <Row label="DNS primaire" value={d.dns_primary || "—"} mono />
          <Row label="DNS secondaire" value={d.dns_secondary || "—"} mono />
          <Row label="Port API" value={d.port ? String(d.port) : "—"} mono />
          <Row label="Port RTSP/ONVIF" value={d.rtsp_port ? String(d.rtsp_port) : "—"} mono />
        </dl>
      </Card>

      <Card title={<span className="flex items-center gap-2"><Shield className="w-4 h-4" /> Protocoles & sécurité</span>}>
        <dl className="grid grid-cols-2 gap-y-2 text-sm">
          <Row label="Chiffrement" value={d.encryption_enabled ? "Activé" : "Désactivé"} />
          <Row label="Auth mode" value={d.auth_mode || "Basic"} />
          <Row label="Certificat TLS" value={d.tls_cert_expires ? `Expire ${fmtDateTime(d.tls_cert_expires)}` : "—"} />
          <Row label="Sync interval" value={d.sync_interval_s ? `${d.sync_interval_s}s` : "—"} />
        </dl>
      </Card>

      <Card title="URLs / endpoints à configurer côté terminal" className="lg:col-span-2">
        <div className="space-y-2">
          <URLCopy label="ADMS ZKTeco / AiFace"
                   url={`${admsUrl}?SN=${d.serial_number || ""}`}
                   hint="À configurer dans le menu Cloud/COMM du terminal" />
          <URLCopy label="Webhook événements"
                   url={`https://api.kaydanshield.com/api/v1/devices/face-terminal/${d.serial_number || "SN"}/event/`}
                   hint="Terminaux face reco Hikvision/AiFace" />
        </div>
      </Card>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────
// TAB 5 — Historique événements
// ─────────────────────────────────────────────────────────────
function HistoryTab({ events }: { events: any[] }) {
  return (
    <Card padded={false} title="Événements récents">
      <ul className="divide-y divide-surface-border/50 max-h-[60vh] overflow-y-auto">
        {events.length === 0 && (
          <li className="p-8 text-center text-ink-muted text-sm">Aucun événement récent</li>
        )}
        {events.map((e: any) => (
          <li key={e.id} className="px-5 py-2.5 flex items-center gap-4 hover:bg-surface-soft/40">
            <div className={cn("w-8 h-8 rounded-lg grid place-items-center",
              e.decision === "granted" ? "bg-ok/10 text-ok" : "bg-danger/10 text-danger")}>
              <Activity className="w-4 h-4" />
            </div>
            <div className="flex-1 min-w-0">
              <div className="flex items-center gap-2">
                <span className="text-sm font-medium">
                  {e.holder_name || e.badge_uid || "Inconnu"}
                </span>
                <Badge tone={e.direction === "in" ? "info" : "muted"}>
                  {e.direction === "in" ? "Entrée" : "Sortie"}
                </Badge>
              </div>
              <div className="text-[11px] text-ink-soft font-mono">{e.badge_uid}</div>
            </div>
            <div className="text-right text-xs">
              <div className="font-mono">{fmtTime(e.timestamp)}</div>
              <div className="text-ink-soft">{fmtRelative(e.timestamp)}</div>
            </div>
          </li>
        ))}
      </ul>
    </Card>
  );
}

// ─────────────────────────────────────────────────────────────
// TAB 6 — Logs
// ─────────────────────────────────────────────────────────────
function LogsTab({ logs, loading }: { logs: any; loading: boolean }) {
  if (loading) return <div className="text-center py-8 text-ink-muted">Chargement des logs…</div>;
  const lines = logs?.entries || logs?.logs || [];
  return (
    <Card title={`Logs (${lines.length} entrées)`} padded={false}>
      <pre className="p-4 text-[11px] font-mono text-ink-muted bg-surface max-h-[60vh] overflow-auto whitespace-pre-wrap">
        {lines.length === 0 ? "Aucun log disponible pour cet équipement." :
          lines.map((l: any) => typeof l === "string" ? l : JSON.stringify(l)).join("\n")}
      </pre>
    </Card>
  );
}

// ─────────────────────────────────────────────────────────────
// TAB 7 — Debug iclock
// ─────────────────────────────────────────────────────────────
function DebugTab({ debug, loading }: { debug: any; loading: boolean }) {
  if (loading) return <div className="text-center py-8 text-ink-muted">Chargement…</div>;
  return (
    <Card title="Dernières requêtes /iclock/cdata reçues"
      subtitle={debug?.entries_count ? `${debug.entries_count} entrées en cache` : "Aucune requête POST reçue"}
      actions={<LivePulse />}>
      {!debug?.entries?.length && (
        <div className="text-center py-8 text-ink-muted text-sm">
          Aucun POST /iclock/cdata pour ce SN.
        </div>
      )}
      <ul className="space-y-3 max-h-[60vh] overflow-y-auto">
        {debug?.entries?.map((e: any, i: number) => (
          <li key={i} className="p-3 rounded-lg bg-surface-soft/40 border border-surface-border">
            <div className="flex items-center gap-2 text-xs">
              <Badge tone="info">{e.table || "no-table"}</Badge>
              <span className="text-ink-soft">{fmtDateTime(e.at)}</span>
              <span className="ml-auto text-ink-soft">{e.content_type}</span>
            </div>
            <pre className="mt-2 text-[11px] font-mono text-ink bg-surface p-2 rounded overflow-x-auto whitespace-pre-wrap break-all">
              {e.body_preview || <span className="text-ink-soft">(body vide)</span>}
            </pre>
          </li>
        ))}
      </ul>
    </Card>
  );
}

// ─────────────────────────────────────────────────────────────
// Sous-composants
// ─────────────────────────────────────────────────────────────
function Row({ icon, label, value, mono, span }: {
  icon?: React.ReactNode; label: string; value: React.ReactNode;
  mono?: boolean; span?: number;
}) {
  return (
    <div className={cn("py-1", span === 2 && "col-span-2")}>
      <dt className="flex items-center gap-1.5 text-[10px] uppercase tracking-wider text-ink-soft font-semibold">
        {icon}{label}
      </dt>
      <dd className={cn("mt-0.5 text-ink truncate", mono && "font-mono text-xs")}>
        {value || <span className="text-ink-soft">—</span>}
      </dd>
    </div>
  );
}

function ResourceBar({ label, value, icon, lowThreshold, highThreshold, unit }:
  { label: string; value: number | null; icon?: React.ReactNode; lowThreshold?: number; highThreshold?: number; unit?: string }) {
  if (value == null) return null;
  const isLow = lowThreshold != null && value < lowThreshold;
  const isHigh = highThreshold != null && value > highThreshold;
  const tone = isLow || isHigh ? (value < 20 || value > 90 ? "danger" : "warn") : "ok";
  const barColor = tone === "danger" ? "bg-danger" : tone === "warn" ? "bg-warn" : "bg-ok";

  return (
    <div>
      <div className="flex items-center justify-between mb-1">
        <span className="flex items-center gap-1.5 text-xs text-ink-muted">{icon}{label}</span>
        <span className={cn("text-xs font-mono",
          tone === "danger" ? "text-danger" : tone === "warn" ? "text-warn" : "text-ink")}>
          {value}{unit || ""}
        </span>
      </div>
      <div className="h-1.5 rounded-full bg-surface-soft overflow-hidden">
        <div className={cn("h-full transition-all", barColor)} style={{ width: `${Math.min(100, value)}%` }} />
      </div>
    </div>
  );
}

function URLCopy({ label, url, hint }: { label: string; url: string; hint?: string }) {
  return (
    <div className="p-3 rounded-lg bg-surface-soft/50 border border-surface-border">
      <div className="text-xs font-medium text-ink mb-1">{label}</div>
      <div className="flex items-center gap-2">
        <code className="flex-1 text-[11px] font-mono text-ink-muted break-all">{url}</code>
        <button onClick={() => {
          navigator.clipboard.writeText(url);
          toast.success("Copié");
        }} className="p-1.5 rounded hover:bg-surface-soft text-ink-muted hover:text-ink">
          <Copy className="w-3.5 h-3.5" />
        </button>
      </div>
      {hint && <div className="mt-1 text-[10px] text-ink-soft">{hint}</div>}
    </div>
  );
}
