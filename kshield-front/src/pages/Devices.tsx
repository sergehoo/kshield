import { useState, useMemo } from "react";
import { useNavigate } from "react-router-dom";
import { useQueryClient, useMutation } from "@tanstack/react-query";
import { useLive } from "@/hooks/useLive";
import { PageHeader } from "@/components/PageHeader";
import { Card } from "@/components/ui/Card";
import { DataTable, Column } from "@/components/ui/DataTable";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Modal } from "@/components/ui/Modal";
import { StatsRow } from "@/components/StatsRow";
import { LivePulse } from "@/components/LivePulse";
import { devicesService, sitesService, zonesService } from "@/services";
import { useQuery } from "@tanstack/react-query";
import { toApiError } from "@/lib/api";
import { fmtRelative, fmtDateTime } from "@/lib/format";
import { cn } from "@/lib/cn";
import {
  Cpu, RefreshCw, PlugZap, Zap, Wifi, WifiOff, Activity, Search,
  Radar, LayoutGrid, List as ListIcon, Map as MapIcon, Network,
  Camera, ScanFace, CreditCard, HardHat, Radio, Package, DoorClosed,
  Lock, KeyRound, AlertTriangle, ShieldAlert, Battery, Signal,
  Filter, Layers, Plus, Terminal, Zap as ZapIcon, ChevronRight,
  Server, X, Download, FileText,
} from "lucide-react";
import toast from "react-hot-toast";
import { Link } from "react-router-dom";

/**
 * Types d'équipements — chaque type a icône + couleur + label.
 */
const DEVICE_TYPES = [
  { key: "face_terminal",      label: "Terminal face",     icon: ScanFace,    color: "brand" },
  { key: "biometric",          label: "Terminal biométrique", icon: ScanFace, color: "brand" },
  { key: "reader_uhf_fixed",   label: "Lecteur UHF fixe",  icon: Radio,       color: "info" },
  { key: "reader_uhf_mobile",  label: "Lecteur UHF mobile", icon: Radio,      color: "info" },
  { key: "reader_nfc_fixed",   label: "Lecteur NFC fixe",  icon: CreditCard,  color: "info" },
  { key: "reader_nfc_mobile",  label: "Lecteur NFC mobile", icon: CreditCard, color: "info" },
  { key: "tag_uhf",            label: "Tag UHF",           icon: Radio,       color: "muted" },
  { key: "tag_nfc",            label: "Tag NFC",           icon: CreditCard,  color: "muted" },
  { key: "beacon_ble",         label: "Beacon BLE",        icon: Radio,       color: "info" },
  { key: "helmet_ble",         label: "Casque BLE",        icon: HardHat,     color: "warn" },
  { key: "camera",             label: "Caméra IP",         icon: Camera,      color: "info" },
  { key: "portique",           label: "Portique UHF",      icon: DoorClosed,  color: "warn" },
  { key: "door_lock",          label: "Serrure connectée", icon: Lock,        color: "warn" },
  { key: "qr_reader",          label: "Lecteur QR",        icon: KeyRound,    color: "info" },
  { key: "gateway",            label: "Gateway réseau",    icon: Network,     color: "brand" },
  { key: "iot_sensor",         label: "Capteur IoT",       icon: Activity,    color: "muted" },
  { key: "punch_clock",        label: "Borne pointage",    icon: Terminal,    color: "info" },
];

function typeMeta(t?: string) {
  return DEVICE_TYPES.find((d) => d.key === t) ||
    { key: t, label: t || "Inconnu", icon: Cpu, color: "muted" };
}

const PROTOCOLS = ["TCP/IP", "OSDP", "Wiegand", "BLE", "NFC", "RFID", "ONVIF", "RTSP", "ADMS", "LLRP"];

type View = "list" | "grid" | "sites" | "topology";

export function DevicesPage() {
  const [view, setView] = useState<View>("list");
  const [q, setQ] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [typeFilter, setTypeFilter] = useState("");
  const [siteFilter, setSiteFilter] = useState<number | "">("");
  const [zoneFilter, setZoneFilter] = useState<number | "">("");
  const [brandFilter, setBrandFilter] = useState("");
  const [protocolFilter, setProtocolFilter] = useState("");
  const [ipRange, setIpRange] = useState("");
  const [associatedFilter, setAssociatedFilter] = useState("");
  const [batteryFilter, setBatteryFilter] = useState("");
  const [signalFilter, setSignalFilter] = useState("");
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [scanModalOpen, setScanModalOpen] = useState(false);
  const [page, setPage] = useState(1);

  const navigate = useNavigate();
  const qc = useQueryClient();
  const pageSize = 30;

  // ─── Live query équipements ─────────────────────
  const { data, isLoading, isFetching, refetch } = useLive(
    ["devices", q, statusFilter, typeFilter, siteFilter, zoneFilter, brandFilter, protocolFilter, ipRange, associatedFilter, batteryFilter, signalFilter, page],
    async () => (await devicesService.list({
      page_size: pageSize, page,
      search: q || undefined,
      status: statusFilter || undefined,
      type: typeFilter || undefined,
      site: siteFilter || undefined,
      zone: zoneFilter || undefined,
      brand: brandFilter || undefined,
      protocol: protocolFilter || undefined,
      ip_range: ipRange || undefined,
      associated: associatedFilter || undefined,
      battery_lt: batteryFilter || undefined,
      signal_lt: signalFilter || undefined,
    })).data,
    { intervalMs: 20_000 },
  );

  // ─── Stats globales ─────────────────────
  const { data: allDevices } = useLive(
    ["devices", "all-stats"],
    async () => (await devicesService.list({ page_size: 500 })).data,
    { intervalMs: 60_000 },
  );

  const stats = useMemo(() => {
    const list: any[] = allDevices?.results || [];
    const now = Date.now();
    return {
      total: allDevices?.count || 0,
      online: list.filter((d) => d.is_online || d.status === "active").length,
      offline: list.filter((d) => d.status === "offline" || (!d.is_online && d.status !== "maintenance")).length,
      maintenance: list.filter((d) => d.status === "maintenance").length,
      unassociated: list.filter((d) => !d.site).length,
      newDetected: list.filter((d) => d.created_at &&
        (now - new Date(d.created_at).getTime()) < 7 * 86400_000).length,
      withAnomaly: list.filter((d) =>
        d.status === "error" || d.battery_level < 15 || d.last_error).length,
      lastScanAt: (localStorage.getItem("last-network-scan") || "").slice(0, 19),
    };
  }, [allDevices]);

  // Data pour selects
  const { data: sites } = useQuery({
    queryKey: ["sites", "for-devices"],
    queryFn: async () => (await sitesService.list({ page_size: 200 })).data,
  });
  const { data: zones } = useQuery({
    queryKey: ["zones", siteFilter],
    queryFn: async () => (await zonesService.list({ page_size: 100, site: siteFilter || undefined })).data,
    enabled: !!siteFilter,
  });

  // Marques uniques dérivées de allDevices
  const brands = useMemo(() => {
    const set = new Set<string>();
    (allDevices?.results || []).forEach((d: any) => {
      const b = typeof d.model === "object" ? d.model?.brand : null;
      if (b) set.add(b);
    });
    return Array.from(set).sort();
  }, [allDevices]);

  // ─── Mutations ─────────────────────
  const testMut = useMutation({
    mutationFn: (id: number) => devicesService.testConnection(id).then((r) => r.data),
    onSuccess: (r) => {
      toast.success(r?.reachable ? "Équipement joignable ✓" : "Injoignable ✗");
      qc.invalidateQueries({ queryKey: ["devices"] });
    },
    onError: (e) => toast.error(toApiError(e).message),
  });

  const pingMut = useMutation({
    mutationFn: (id: number) => devicesService.ping(id).then((r) => r.data),
    onSuccess: (r) => toast.success(`Ping ${r?.latency_ms || "?"} ms`),
    onError: (e) => toast.error(toApiError(e).message),
  });

  const syncMut = useMutation({
    mutationFn: (id: number) => devicesService.syncNow(id).then((r) => r.data),
    onSuccess: () => toast.success("Synchronisation lancée"),
    onError: (e) => toast.error(toApiError(e).message),
  });

  const restartMut = useMutation({
    mutationFn: (id: number) => devicesService.restart(id).then((r) => r.data),
    onSuccess: () => toast.success("Redémarrage lancé"),
    onError: (e) => toast.error(toApiError(e).message),
  });

  const maintenanceMut = useMutation({
    mutationFn: ({ id, enabled }: { id: number; enabled: boolean }) =>
      devicesService.setMaintenance(id, enabled),
    onSuccess: (_, v) => {
      toast.success(v.enabled ? "Mis en maintenance" : "Sorti de maintenance");
      qc.invalidateQueries({ queryKey: ["devices"] });
    },
    onError: (e) => toast.error(toApiError(e).message),
  });

  // ─── Colonnes tableau technique ─────────────────────
  const columns: Column<any>[] = [
    { key: "device", header: "Équipement", render: (d) => {
      const meta = typeMeta(d.type);
      const Icon = meta.icon;
      return (
        <div className="flex items-center gap-2.5">
          <div className={cn("w-8 h-8 rounded-lg grid place-items-center shrink-0",
            meta.color === "brand"  ? "bg-brand-500/10 text-brand-400" :
            meta.color === "info"   ? "bg-info/10 text-info" :
            meta.color === "warn"   ? "bg-warn/10 text-warn" :
            meta.color === "danger" ? "bg-danger/10 text-danger" : "bg-white/5 text-ink-muted"
          )}>
            <Icon className="w-4 h-4" />
          </div>
          <div className="min-w-0">
            <div className="text-sm font-medium truncate">{d.name || meta.label}</div>
            <div className="text-[11px] text-ink-soft font-mono truncate">{d.serial_number || "—"}</div>
          </div>
        </div>
      );
    }},
    { key: "type", header: "Type", render: (d) => (
      <Badge tone="info">{typeMeta(d.type).label}</Badge>
    )},
    { key: "brand", header: "Marque / modèle", render: (d) => (
      <div className="text-xs">
        <div>{typeof d.model === "object" ? d.model?.brand : "—"}</div>
        <div className="text-ink-soft">{typeof d.model === "object" ? d.model?.model_name : ""}</div>
      </div>
    )},
    { key: "network", header: "Réseau", render: (d) => (
      <div className="text-xs font-mono">
        <div>{d.ip_address ? `${d.ip_address}${d.port ? `:${d.port}` : ""}` : "—"}</div>
        <div className="text-ink-soft">{d.mac_address || ""}</div>
      </div>
    )},
    { key: "location", header: "Emplacement", render: (d) => (
      <div className="text-xs">
        {typeof d.site === "object" && d.site?.name && (
          <div className="flex items-center gap-1">
            <MapIcon className="w-3 h-3 text-ink-soft" /> {d.site.name}
          </div>
        )}
        {typeof d.zone === "object" && d.zone?.name && (
          <div className="text-ink-soft ml-4">{d.zone.name}</div>
        )}
        {typeof d.checkpoint === "object" && d.checkpoint?.name && (
          <div className="text-ink-soft ml-4">🚪 {d.checkpoint.name}</div>
        )}
        {!d.site && <span className="text-ink-soft">— non associé</span>}
      </div>
    )},
    { key: "status", header: "Statut", render: (d) => {
      const online = d.is_online || d.status === "active";
      const tone = online ? "ok" : d.status === "maintenance" ? "warn" :
                   d.status === "error" ? "danger" : "muted";
      return (
        <div className="flex flex-col gap-0.5">
          <Badge tone={tone} dot>
            {online ? (<><Wifi className="w-3 h-3" /> En ligne</>) :
             d.status === "maintenance" ? "Maintenance" :
             d.status === "error" ? "Erreur" :
             (<><WifiOff className="w-3 h-3" /> Offline</>)}
          </Badge>
          {d.last_heartbeat_at && (
            <span className="text-[10px] text-ink-soft">{fmtRelative(d.last_heartbeat_at)}</span>
          )}
        </div>
      );
    }},
    { key: "protocol", header: "Protocole", render: (d) => (
      <span className="text-[11px] text-ink-muted">
        {d.protocol || (typeof d.model === "object" ? (d.model?.protocol || "TCP/IP") : "—")}
      </span>
    )},
    { key: "firmware", header: "Firmware", render: (d) => (
      <code className="text-[11px] font-mono text-ink-muted">{d.firmware_version || "—"}</code>
    )},
    { key: "health", header: "Santé", render: (d) => (
      <div className="flex items-center gap-2">
        {d.battery_level != null && (
          <div className="flex items-center gap-0.5 text-[11px]">
            <Battery className={cn("w-3 h-3", d.battery_level < 20 ? "text-danger" : d.battery_level < 40 ? "text-warn" : "text-ok")} />
            {d.battery_level}%
          </div>
        )}
        {d.signal_level != null && (
          <div className="flex items-center gap-0.5 text-[11px]">
            <Signal className={cn("w-3 h-3", d.signal_level < 30 ? "text-danger" : "text-ok")} />
            {d.signal_level}%
          </div>
        )}
        {!d.battery_level && !d.signal_level && <span className="text-ink-soft text-[11px]">—</span>}
      </div>
    )},
    { key: "actions", header: "", className: "text-right whitespace-nowrap", render: (d) => (
      <div className="inline-flex gap-0.5">
        <button title="Ping" onClick={(e) => { e.stopPropagation(); pingMut.mutate(d.id); }}
                className="p-1.5 rounded-md hover:bg-surface-soft text-ink-muted hover:text-ink">
          <Activity className="w-3.5 h-3.5" />
        </button>
        <button title="Test connexion" onClick={(e) => { e.stopPropagation(); testMut.mutate(d.id); }}
                className="p-1.5 rounded-md hover:bg-surface-soft text-ink-muted hover:text-ink">
          <PlugZap className="w-3.5 h-3.5" />
        </button>
        <button title="Synchroniser" onClick={(e) => { e.stopPropagation(); syncMut.mutate(d.id); }}
                className="p-1.5 rounded-md hover:bg-surface-soft text-ink-muted hover:text-info">
          <Zap className="w-3.5 h-3.5" />
        </button>
        <button title={d.status === "maintenance" ? "Sortir de maintenance" : "Mettre en maintenance"}
                onClick={(e) => {
                  e.stopPropagation();
                  maintenanceMut.mutate({ id: d.id, enabled: d.status !== "maintenance" });
                }}
                className="p-1.5 rounded-md hover:bg-warn/10 text-ink-muted hover:text-warn">
          🔧
        </button>
        <button title="Redémarrer"
                onClick={(e) => {
                  e.stopPropagation();
                  if (confirm(`Redémarrer ${d.name} ?`)) restartMut.mutate(d.id);
                }}
                className="p-1.5 rounded-md hover:bg-danger/10 text-ink-muted hover:text-danger">
          <RefreshCw className="w-3.5 h-3.5" />
        </button>
      </div>
    )},
  ];

  // Devices groupés par type pour la vue grille
  const byType = useMemo(() => {
    const map = new Map<string, any[]>();
    (data?.results || []).forEach((d: any) => {
      const key = d.type || "unknown";
      if (!map.has(key)) map.set(key, []);
      map.get(key)!.push(d);
    });
    return Array.from(map.entries());
  }, [data]);

  // Devices groupés par site pour la vue Sites
  const bySite = useMemo(() => {
    const map = new Map<string, any[]>();
    (data?.results || []).forEach((d: any) => {
      const key = typeof d.site === "object" ? d.site?.name : "— non associé";
      const k = key || "— non associé";
      if (!map.has(k)) map.set(k, []);
      map.get(k)!.push(d);
    });
    return Array.from(map.entries()).sort();
  }, [data]);

  const resetFilters = () => {
    setQ(""); setStatusFilter(""); setTypeFilter(""); setSiteFilter(""); setZoneFilter("");
    setBrandFilter(""); setProtocolFilter(""); setIpRange(""); setAssociatedFilter("");
    setBatteryFilter(""); setSignalFilter(""); setPage(1);
  };

  return (
    <div>
      <PageHeader
        title="Terminaux & équipements techniques"
        subtitle={`${stats.total} équipements — ${stats.online} en ligne / ${stats.offline} offline`}
        live
        actions={
          <div className="flex items-center gap-2">
            <Button variant="ghost" size="sm"
                    leftIcon={<Radar className={cn("w-3.5 h-3.5", isFetching && "animate-spin")} />}
                    onClick={() => refetch()}>
              Rafraîchir
            </Button>
            <Button size="sm" leftIcon={<Network className="w-3.5 h-3.5" />}
                    onClick={() => setScanModalOpen(true)}>
              Scan réseau
            </Button>
            <Link to="/devices/new" className="btn-primary inline-flex">
              <Plus className="w-4 h-4" /> Ajouter
            </Link>
          </div>
        }
      />

      {/* ═══ 8 KPIs ═══ */}
      <StatsRow stats={[
        { label: "Total", value: stats.total, icon: <Cpu className="w-4 h-4" />, tone: "brand" },
        { label: "En ligne", value: stats.online, icon: <Wifi className="w-4 h-4" />, tone: "ok",
          onClick: () => setStatusFilter("active") },
        { label: "Offline", value: stats.offline, icon: <WifiOff className="w-4 h-4" />, tone: "danger",
          onClick: () => setStatusFilter("offline") },
        { label: "Maintenance", value: stats.maintenance, icon: <Activity className="w-4 h-4" />, tone: "warn",
          onClick: () => setStatusFilter("maintenance") },
        { label: "Non associés", value: stats.unassociated, icon: <Layers className="w-4 h-4" />, tone: "muted",
          onClick: () => setAssociatedFilter("false") },
        { label: "Nouveaux (7j)", value: stats.newDetected, icon: <Plus className="w-4 h-4" />, tone: "info" },
        { label: "Anomalies", value: stats.withAnomaly, icon: <AlertTriangle className="w-4 h-4" />, tone: "danger" },
        { label: "Dernier scan", value: stats.lastScanAt ? fmtRelative(stats.lastScanAt) : "Jamais",
          icon: <Radar className="w-4 h-4" />, tone: "muted" },
      ]} />

      {/* ═══ Vue selector ═══ */}
      <div className="mb-4 flex items-center justify-between">
        <div className="inline-flex rounded-lg bg-surface-soft p-0.5 border border-surface-border">
          {[
            { key: "list",     label: "Liste",       icon: ListIcon },
            { key: "grid",     label: "Par type",    icon: LayoutGrid },
            { key: "sites",    label: "Par site",    icon: MapIcon },
            { key: "topology", label: "Topologie",   icon: Network },
          ].map((v) => (
            <button key={v.key}
                    onClick={() => setView(v.key as View)}
                    className={cn("flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium transition",
                      view === v.key ? "bg-brand-500 text-white" : "text-ink-muted hover:text-ink"
                    )}>
              <v.icon className="w-3.5 h-3.5" />
              {v.label}
            </button>
          ))}
        </div>
        <LivePulse label="Auto-refresh 20s" />
      </div>

      {/* ═══ Barre de filtres ═══ */}
      <Card padded={false} className="mb-4">
        <div className="p-4 border-b border-surface-border space-y-2">
          <div className="grid grid-cols-1 sm:grid-cols-6 gap-2">
            <div className="sm:col-span-2">
              <Input placeholder="Nom, IP, MAC, serial, tag, badge…"
                     leftIcon={<Search className="w-4 h-4" />}
                     value={q} onChange={(e) => { setQ(e.target.value); setPage(1); }} />
            </div>
            <select value={typeFilter} onChange={(e) => { setTypeFilter(e.target.value); setPage(1); }} className="field">
              <option value="">Tous types</option>
              {DEVICE_TYPES.map((t) => <option key={t.key} value={t.key}>{t.label}</option>)}
            </select>
            <select value={statusFilter} onChange={(e) => { setStatusFilter(e.target.value); setPage(1); }} className="field">
              <option value="">Tous statuts</option>
              <option value="active">En ligne</option>
              <option value="offline">Offline</option>
              <option value="maintenance">Maintenance</option>
              <option value="error">Erreur</option>
              <option value="inactive">Inactif</option>
            </select>
            <select value={siteFilter} onChange={(e) => { setSiteFilter(e.target.value ? Number(e.target.value) : ""); setZoneFilter(""); setPage(1); }} className="field">
              <option value="">Tous sites</option>
              {sites?.results?.map((s: any) => <option key={s.id} value={s.id}>{s.name}</option>)}
            </select>
            <button onClick={() => setShowAdvanced(!showAdvanced)}
                    className="flex items-center justify-center gap-1 px-3 rounded-lg border border-surface-border text-xs text-ink-muted hover:text-ink hover:bg-surface-soft transition">
              <Filter className="w-3.5 h-3.5" />
              Filtres {showAdvanced ? "▲" : "▼"}
            </button>
          </div>

          {showAdvanced && (
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 pt-2 border-t border-surface-border/60">
              <label className="block">
                <span className="text-[10px] uppercase tracking-wider text-ink-soft">Zone</span>
                <select value={zoneFilter}
                        onChange={(e) => { setZoneFilter(e.target.value ? Number(e.target.value) : ""); setPage(1); }}
                        disabled={!siteFilter} className="field w-full mt-0.5">
                  <option value="">{siteFilter ? "Toutes zones" : "Choisir un site"}</option>
                  {zones?.results?.map((z: any) => <option key={z.id} value={z.id}>{z.name}</option>)}
                </select>
              </label>
              <label className="block">
                <span className="text-[10px] uppercase tracking-wider text-ink-soft">Marque</span>
                <select value={brandFilter} onChange={(e) => { setBrandFilter(e.target.value); setPage(1); }} className="field w-full mt-0.5">
                  <option value="">Toutes marques</option>
                  {brands.map((b) => <option key={b} value={b}>{b}</option>)}
                </select>
              </label>
              <label className="block">
                <span className="text-[10px] uppercase tracking-wider text-ink-soft">Protocole</span>
                <select value={protocolFilter} onChange={(e) => { setProtocolFilter(e.target.value); setPage(1); }} className="field w-full mt-0.5">
                  <option value="">Tous</option>
                  {PROTOCOLS.map((p) => <option key={p} value={p}>{p}</option>)}
                </select>
              </label>
              <label className="block">
                <span className="text-[10px] uppercase tracking-wider text-ink-soft">Association</span>
                <select value={associatedFilter} onChange={(e) => { setAssociatedFilter(e.target.value); setPage(1); }} className="field w-full mt-0.5">
                  <option value="">Tous</option>
                  <option value="true">Associés</option>
                  <option value="false">Non associés</option>
                </select>
              </label>
              <Input label="Plage IP" placeholder="192.168.1.0/24"
                     value={ipRange} onChange={(e) => { setIpRange(e.target.value); setPage(1); }} />
              <label className="block">
                <span className="text-[10px] uppercase tracking-wider text-ink-soft">Batterie {"<"}</span>
                <select value={batteryFilter} onChange={(e) => { setBatteryFilter(e.target.value); setPage(1); }} className="field w-full mt-0.5">
                  <option value="">—</option>
                  <option value="20">20%</option>
                  <option value="40">40%</option>
                </select>
              </label>
              <label className="block">
                <span className="text-[10px] uppercase tracking-wider text-ink-soft">Signal {"<"}</span>
                <select value={signalFilter} onChange={(e) => { setSignalFilter(e.target.value); setPage(1); }} className="field w-full mt-0.5">
                  <option value="">—</option>
                  <option value="30">30%</option>
                  <option value="50">50%</option>
                </select>
              </label>
              <div className="flex items-end">
                <button onClick={resetFilters}
                        className="w-full h-10 px-3 rounded-lg text-xs text-ink-muted hover:text-ink border border-surface-border hover:bg-surface-soft transition">
                  Réinitialiser
                </button>
              </div>
            </div>
          )}
        </div>

        {/* ═══ Vues ═══ */}
        {view === "list" && (
          <DataTable
            columns={columns} rows={data?.results || []} loading={isLoading}
            rowKey={(d) => d.id}
            onRowClick={(d) => navigate(`/devices/${d.id}`)}
            emptyLabel="Aucun équipement trouvé"
            pagination={{ count: data?.count ?? 0, pageSize, page, onPageChange: setPage }}
          />
        )}

        {view === "grid" && <GridView byType={byType} onOpen={(id) => navigate(`/devices/${id}`)} />}

        {view === "sites" && <SitesView bySite={bySite} onOpen={(id) => navigate(`/devices/${id}`)} />}

        {view === "topology" && <TopologyView devices={data?.results || []} onOpen={(id) => navigate(`/devices/${id}`)} />}
      </Card>

      <NetworkScanModal open={scanModalOpen} onClose={() => setScanModalOpen(false)} />
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────
// Vue grille par type
// ─────────────────────────────────────────────────────────────────
function GridView({ byType, onOpen }: { byType: [string, any[]][]; onOpen: (id: number) => void }) {
  return (
    <div className="p-4 space-y-4">
      {byType.length === 0 && <div className="text-center py-8 text-ink-muted">Aucun équipement</div>}
      {byType.map(([type, list]) => {
        const meta = typeMeta(type);
        const Icon = meta.icon;
        return (
          <div key={type}>
            <div className="flex items-center gap-2 mb-2">
              <Icon className={cn("w-4 h-4",
                meta.color === "brand" ? "text-brand-400" :
                meta.color === "info"  ? "text-info" :
                meta.color === "warn"  ? "text-warn" : "text-ink-muted"
              )} />
              <span className="text-sm font-semibold">{meta.label}</span>
              <Badge tone="muted">{list.length}</Badge>
            </div>
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-2">
              {list.map((d) => (
                <button key={d.id} onClick={() => onOpen(d.id)}
                        className="text-left p-3 rounded-xl border border-surface-border bg-surface-card/50 hover:border-brand-500/40 hover:bg-surface-card transition">
                  <div className="flex items-start gap-2">
                    <div className={cn("w-2 h-2 rounded-full mt-1.5",
                      d.is_online || d.status === "active" ? "bg-ok animate-pulse-dot" :
                      d.status === "maintenance" ? "bg-warn" : "bg-danger")} />
                    <div className="min-w-0 flex-1">
                      <div className="text-sm font-medium truncate">{d.name}</div>
                      <div className="text-[11px] text-ink-soft font-mono truncate">{d.serial_number || d.ip_address}</div>
                    </div>
                  </div>
                </button>
              ))}
            </div>
          </div>
        );
      })}
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────
// Vue par site
// ─────────────────────────────────────────────────────────────────
function SitesView({ bySite, onOpen }: { bySite: [string, any[]][]; onOpen: (id: number) => void }) {
  return (
    <div className="p-4 space-y-4">
      {bySite.map(([site, list]) => (
        <div key={site} className="rounded-xl border border-surface-border p-4 bg-surface-card/40">
          <div className="flex items-center gap-2 mb-3">
            <MapIcon className="w-4 h-4 text-brand-500" />
            <span className="text-sm font-semibold">{site}</span>
            <Badge tone="muted">{list.length} équipement{list.length > 1 ? "s" : ""}</Badge>
          </div>
          <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-2">
            {list.map((d) => {
              const meta = typeMeta(d.type);
              const Icon = meta.icon;
              return (
                <button key={d.id} onClick={() => onOpen(d.id)}
                        className="text-left flex items-center gap-2 p-2 rounded-lg hover:bg-surface-soft/50">
                  <Icon className="w-3.5 h-3.5 text-ink-muted" />
                  <div className="min-w-0 flex-1">
                    <div className="text-xs font-medium truncate">{d.name}</div>
                    <div className="text-[10px] text-ink-soft">{typeMeta(d.type).label}</div>
                  </div>
                  <Badge tone={d.is_online ? "ok" : "danger"} dot>{d.is_online ? "OK" : "Off"}</Badge>
                </button>
              );
            })}
          </div>
        </div>
      ))}
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────
// Vue topologie réseau simple
// ─────────────────────────────────────────────────────────────────
function TopologyView({ devices, onOpen }: { devices: any[]; onOpen: (id: number) => void }) {
  return (
    <div className="p-4">
      <div className="flex items-center justify-center flex-wrap gap-6">
        <div className="rounded-2xl border border-brand-500/40 bg-brand-500/10 p-4 text-center">
          <Server className="w-8 h-8 mx-auto text-brand-400" />
          <div className="mt-2 text-sm font-semibold">KAYDAN SHIELD Cloud</div>
          <div className="text-[10px] text-ink-soft">api.kaydanshield.com</div>
        </div>
      </div>
      <div className="mt-4 grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-2">
        {devices.slice(0, 30).map((d) => {
          const meta = typeMeta(d.type);
          const Icon = meta.icon;
          const online = d.is_online || d.status === "active";
          return (
            <button key={d.id} onClick={() => onOpen(d.id)}
                    className="relative p-3 rounded-xl border border-surface-border bg-surface-card/50 hover:border-brand-500/40 transition text-center">
              <div className={cn("w-8 h-8 mx-auto rounded-lg grid place-items-center",
                online ? "bg-ok/10 text-ok" : "bg-danger/10 text-danger")}>
                <Icon className="w-4 h-4" />
              </div>
              <div className="mt-2 text-[10px] font-medium truncate">{d.name}</div>
              <div className="text-[9px] text-ink-soft font-mono truncate">{d.ip_address}</div>
              {/* Ligne vers le cloud (visuelle) */}
              <div className={cn("absolute -top-3 left-1/2 w-px h-3",
                online ? "bg-ok/40" : "bg-danger/40")} />
            </button>
          );
        })}
      </div>
      {devices.length > 30 && (
        <div className="mt-3 text-center text-xs text-ink-soft">
          Affichage 30 sur {devices.length} — utilisez la vue liste pour voir tous les équipements.
        </div>
      )}
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────
// Modal Scan réseau — plage IP + progression + logs
// ─────────────────────────────────────────────────────────────────
function NetworkScanModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [ipRange, setIpRange] = useState("192.168.1.0/24");
  const [scanId, setScanId] = useState<string | null>(null);
  const [confirmed, setConfirmed] = useState(false);

  const startMut = useMutation({
    mutationFn: () => devicesService.scanStart({
      ip_range: ipRange,
      ports: [80, 443, 4370, 5084, 554, 8000, 8080],
      protocols: ["onvif", "zkteco", "adms", "llrp"],
      timeout_ms: 800,
    }),
    onSuccess: (r) => {
      setScanId(r.data.scan_id);
      localStorage.setItem("last-network-scan", new Date().toISOString());
      toast.success("Scan démarré");
    },
    onError: (e) => toast.error(toApiError(e).message),
  });

  const { data: status } = useQuery({
    queryKey: ["scan", scanId],
    queryFn: async () => (await devicesService.scanStatus(scanId!)).data,
    enabled: !!scanId,
    refetchInterval: scanId ? 2000 : false,
  });

  const cancel = () => {
    if (scanId) devicesService.scanCancel(scanId).catch(() => {});
    setScanId(null);
  };

  const adopt = useMutation({
    mutationFn: (ip: string) => devicesService.scanAdopt(scanId!, ip),
    onSuccess: () => toast.success("Équipement adopté dans Shield"),
    onError: (e) => toast.error(toApiError(e).message),
  });

  const progress = status?.progress || 0;
  const done = status?.done || false;

  return (
    <Modal open={open} onClose={() => { onClose(); setScanId(null); setConfirmed(false); }}
      title="Scan du réseau" size="xl"
      footer={
        !scanId ? (
          <>
            <Button variant="ghost" onClick={onClose}>Annuler</Button>
            <Button leftIcon={<Radar className="w-4 h-4" />}
                    onClick={() => confirmed ? startMut.mutate() : setConfirmed(true)}
                    loading={startMut.isPending}
                    variant={confirmed ? "danger" : "primary"}>
              {confirmed ? "Confirmer et lancer le scan" : "Lancer le scan"}
            </Button>
          </>
        ) : (
          <Button variant="ghost" onClick={cancel}>Annuler le scan</Button>
        )
      }>
      {!scanId ? (
        <div className="space-y-4">
          <div className="p-3 rounded-lg bg-info/5 border border-info/20 text-xs text-ink">
            <div className="font-medium mb-1 flex items-center gap-1">
              <ShieldAlert className="w-3.5 h-3.5 text-info" /> Scan encadré et sécurisé
            </div>
            <ul className="space-y-0.5 text-ink-muted">
              <li>• Non destructif · pas de modification des équipements</li>
              <li>• Détecte ports ouverts : 80, 443, 4370 (ZK), 5084 (LLRP), 554 (RTSP)</li>
              <li>• Identifie ONVIF, ADMS, LLRP automatiquement</li>
              <li>• Rate-limité pour ne pas saturer le réseau</li>
              <li>• Loggé dans l'audit + admin uniquement</li>
            </ul>
          </div>

          <Input label="Plage IP à scanner *" placeholder="192.168.1.0/24 ou 192.168.1.1-254"
                 value={ipRange} onChange={(e) => setIpRange(e.target.value)} />

          {confirmed && (
            <div className="p-3 rounded-lg bg-warn/10 border border-warn/30 text-xs text-warn font-medium">
              ⚠ Prêt à scanner <code className="font-mono">{ipRange}</code>. Continuer ?
            </div>
          )}
        </div>
      ) : (
        <div className="space-y-4">
          {/* Progression */}
          <div>
            <div className="flex items-center justify-between mb-2 text-sm">
              <span className="font-medium">{done ? "Scan terminé" : "Scan en cours…"}</span>
              <Badge tone={done ? "ok" : "info"} dot>{progress}%</Badge>
            </div>
            <div className="h-2 rounded-full bg-surface-soft overflow-hidden">
              <div className={cn("h-full transition-all", done ? "bg-ok" : "bg-brand-500")}
                   style={{ width: `${progress}%` }} />
            </div>
          </div>

          {/* Stats live */}
          <div className="grid grid-cols-4 gap-2 text-center">
            <MiniStat label="IP scannées" value={status?.ips_scanned || 0} />
            <MiniStat label="Détectés" value={status?.devices_found || 0} tone="info" />
            <MiniStat label="Nouveaux" value={status?.new_devices || 0} tone="ok" />
            <MiniStat label="Inconnus" value={status?.unknown || 0} tone="warn" />
          </div>

          {/* Résultats */}
          {status?.results && status.results.length > 0 && (
            <div className="rounded-xl border border-surface-border overflow-hidden max-h-64 overflow-y-auto">
              <table className="w-full text-xs">
                <thead className="sticky top-0 bg-surface-card">
                  <tr className="text-ink-muted">
                    <th className="text-left px-3 py-2">IP</th>
                    <th className="text-left px-3 py-2">MAC</th>
                    <th className="text-left px-3 py-2">Ports</th>
                    <th className="text-left px-3 py-2">Protocole</th>
                    <th className="text-left px-3 py-2">Type détecté</th>
                    <th className="text-right px-3 py-2">Action</th>
                  </tr>
                </thead>
                <tbody>
                  {status.results.map((r: any) => (
                    <tr key={r.ip} className="border-t border-surface-border/50">
                      <td className="px-3 py-2 font-mono">{r.ip}</td>
                      <td className="px-3 py-2 font-mono text-ink-soft">{r.mac || "—"}</td>
                      <td className="px-3 py-2 text-ink-muted">{(r.ports || []).join(", ") || "—"}</td>
                      <td className="px-3 py-2">
                        {r.protocol && <Badge tone="info">{r.protocol}</Badge>}
                      </td>
                      <td className="px-3 py-2">{r.detected_type || "—"}</td>
                      <td className="px-3 py-2 text-right">
                        {r.already_known ? (
                          <Badge tone="muted">Connu</Badge>
                        ) : (
                          <button onClick={() => adopt.mutate(r.ip)}
                                  className="text-brand-500 hover:underline text-xs">
                            + Adopter
                          </button>
                        )}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}

          {/* Logs live */}
          {status?.logs && (
            <div>
              <div className="text-xs font-semibold text-ink-muted mb-1">Logs</div>
              <div className="bg-surface p-2 rounded-lg max-h-40 overflow-y-auto text-[10px] font-mono text-ink-muted">
                {status.logs.map((l: string, i: number) => (
                  <div key={i}>{l}</div>
                ))}
              </div>
            </div>
          )}
        </div>
      )}
    </Modal>
  );
}

function MiniStat({ label, value, tone }: { label: string; value: any; tone?: "info" | "ok" | "warn" }) {
  return (
    <div className={cn("rounded-lg border p-2",
      tone === "info" ? "border-info/30 bg-info/5" :
      tone === "ok"   ? "border-ok/30 bg-ok/5" :
      tone === "warn" ? "border-warn/30 bg-warn/5" :
      "border-surface-border bg-surface-soft"
    )}>
      <div className="text-[10px] uppercase tracking-wider text-ink-soft">{label}</div>
      <div className="text-lg font-bold text-ink">{value}</div>
    </div>
  );
}
