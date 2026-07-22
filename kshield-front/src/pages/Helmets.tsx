import { useState, useMemo, useRef, useEffect } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import Papa from "papaparse";
import { PageHeader } from "@/components/PageHeader";
import { Card } from "@/components/ui/Card";
import { DataTable, Column } from "@/components/ui/DataTable";
import { Badge } from "@/components/ui/Badge";
import { Input } from "@/components/ui/Input";
import { Button } from "@/components/ui/Button";
import { Modal } from "@/components/ui/Modal";
import { StatsRow } from "@/components/StatsRow";
import { LivePulse } from "@/components/LivePulse";
import {
  helmetsService, workersService, sitesService,
} from "@/services";
import { toApiError } from "@/lib/api";
import { parseApiErrors, omitEmpty, FieldErrors } from "@/lib/formErrors";
import { fmtDate, fmtRelative, initials } from "@/lib/format";
import { cn } from "@/lib/cn";
import {
  Search, HardHat, Radio, Battery, Signal, Plus, Upload, Edit3, Trash2,
  LayoutGrid, List as ListIcon, LinkIcon, Unlink, Zap, Filter, Radar, X,
  CheckCircle2, MapPin, AlertTriangle, User as UserIcon, Wrench, BatteryLow,
} from "lucide-react";
import toast from "react-hot-toast";

type Mode = "grid" | "list";
type EnrollMode = "manual" | "live" | "csv";

export function HelmetsPage() {
  const [mode, setMode] = useState<Mode>("list");
  const [q, setQ] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [siteFilter, setSiteFilter] = useState<number | "">("");
  const [associatedFilter, setAssociatedFilter] = useState("");
  const [batteryFilter, setBatteryFilter] = useState("");
  const [signalFilter, setSignalFilter] = useState("");
  const [staleFilter, setStaleFilter] = useState("");
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [page, setPage] = useState(1);
  const [enrollOpen, setEnrollOpen] = useState(false);
  const [bulkOpen, setBulkOpen] = useState(false);
  const [editHelmet, setEditHelmet] = useState<any | null>(null);
  const [assocHelmet, setAssocHelmet] = useState<any | null>(null);
  const qc = useQueryClient();
  const pageSize = 30;

  const listParams = {
    page_size: pageSize, page,
    search: q || undefined,
    status: statusFilter || undefined,
    site: siteFilter || undefined,
    associated: associatedFilter || undefined,
    battery_lt: batteryFilter || undefined,
    signal_lt: signalFilter || undefined,
    stale: staleFilter || undefined,
  };

  const { data, isLoading } = useQuery({
    queryKey: ["helmets", listParams],
    queryFn: async () => (await helmetsService.list(listParams)).data,
  });

  const { data: allHelmets } = useQuery({
    queryKey: ["helmets", "all-stats"],
    queryFn: async () => (await helmetsService.list({ page_size: 1000 })).data,
    staleTime: 60_000,
  });

  const stats = useMemo(() => {
    const list = allHelmets?.results || [];
    return {
      total: allHelmets?.count || 0,
      active: list.filter((h: any) => h.status === "active" || !h.status).length,
      paired: list.filter((h: any) => h.worker_id || h.worker_name || h.worker).length,
      unpaired: list.filter((h: any) => !(h.worker_id || h.worker_name || h.worker)).length,
      lowBattery: list.filter((h: any) => h.battery_pct != null && h.battery_pct < 20).length,
      lost: list.filter((h: any) => h.status === "lost").length,
      stale: list.filter((h: any) => {
        if (!h.last_seen_at) return true;
        return (Date.now() - new Date(h.last_seen_at).getTime()) > 7 * 86400_000;
      }).length,
    };
  }, [allHelmets]);

  const { data: sites } = useQuery({
    queryKey: ["sites", "for-helmets"],
    queryFn: async () => (await sitesService.list({ page_size: 200 })).data,
  });

  // ─── Mutations ─────────────────────────
  const deleteMut = useMutation({
    mutationFn: (id: number) => helmetsService.remove(id),
    onSuccess: () => { toast.success("Casque supprimé"); qc.invalidateQueries({ queryKey: ["helmets"] }); },
    onError: (e) => toast.error(toApiError(e).message),
  });
  const dissocMut = useMutation({
    mutationFn: (id: number) => helmetsService.dissociate(id),
    onSuccess: () => { toast.success("Dissocié"); qc.invalidateQueries({ queryKey: ["helmets"] }); },
    onError: (e) => toast.error(toApiError(e).message),
  });
  const suspendMut = useMutation({
    mutationFn: (id: number) => helmetsService.update(id, { status: "maintenance" }),
    onSuccess: () => { toast.success("Mis en maintenance"); qc.invalidateQueries({ queryKey: ["helmets"] }); },
    onError: (e) => toast.error(toApiError(e).message),
  });
  const reactMut = useMutation({
    mutationFn: (id: number) => helmetsService.update(id, { status: "active" }),
    onSuccess: () => { toast.success("Réactivé"); qc.invalidateQueries({ queryKey: ["helmets"] }); },
    onError: (e) => toast.error(toApiError(e).message),
  });

  const resetFilters = () => {
    setQ(""); setStatusFilter(""); setSiteFilter(""); setAssociatedFilter("");
    setBatteryFilter(""); setSignalFilter(""); setStaleFilter(""); setPage(1);
  };

  const columns: Column<any>[] = [
    { key: "uid", header: "Casque", render: (h) => (
      <div className="flex items-center gap-2.5">
        <div className="w-8 h-8 rounded-lg bg-warn/10 text-warn grid place-items-center">
          <HardHat className="w-4 h-4" />
        </div>
        <div>
          <code className="text-xs font-mono text-ink">{h.serial_number || h.uid}</code>
          {h.ble_beacon_uid && (
            <div className="text-[10px] text-ink-soft font-mono flex items-center gap-1">
              <Radio className="w-2.5 h-2.5" /> {h.ble_beacon_uid}
            </div>
          )}
        </div>
      </div>
    )},
    { key: "uhf", header: "Tag UHF", render: (h) =>
      h.uhf_tag_uid ? <code className="text-[11px] font-mono text-ink-muted">{h.uhf_tag_uid}</code>
                    : <span className="text-ink-soft text-xs">—</span>
    },
    { key: "worker", header: "Ouvrier", render: (h) => (
      (h.worker_id || h.worker_name || h.worker) ? (
        <div className="flex items-center gap-1.5 text-xs">
          <UserIcon className="w-3 h-3 text-ink-soft" />
          <span>{h.worker_name || (typeof h.worker === "object" ? h.worker.full_name : `#${h.worker}`)}</span>
        </div>
      ) : <span className="text-ink-soft text-xs">Non apparié</span>
    )},
    { key: "battery", header: "Batterie", render: (h) => {
      if (h.battery_pct == null) return <span className="text-ink-soft text-xs">—</span>;
      const tone = h.battery_pct > 30 ? "ok" : h.battery_pct > 15 ? "warn" : "danger";
      return (
        <div className="flex items-center gap-1.5">
          <Battery className={cn("w-3.5 h-3.5",
            tone === "danger" ? "text-danger" : tone === "warn" ? "text-warn" : "text-ok")} />
          <Badge tone={tone}>{h.battery_pct}%</Badge>
        </div>
      );
    }},
    { key: "signal", header: "Signal RSSI", render: (h) => {
      if (h.rssi == null && h.signal_level == null) return <span className="text-ink-soft text-xs">—</span>;
      const v = h.rssi || h.signal_level;
      return (
        <div className="flex items-center gap-1 text-xs">
          <Signal className="w-3 h-3 text-ink-soft" />
          <span className="font-mono">{v}</span>
        </div>
      );
    }},
    { key: "site", header: "Site", render: (h) =>
      typeof h.site === "object" ? h.site?.name :
      <span className="text-ink-soft text-xs">—</span>
    },
    { key: "status", header: "Statut", render: (h) => (
      <Badge tone={
        h.status === "active" || !h.status ? "ok" :
        h.status === "maintenance" ? "warn" :
        h.status === "lost" ? "danger" : "muted"
      } dot>{h.status || "actif"}</Badge>
    )},
    { key: "last", header: "Dernière détection", render: (h) => (
      h.last_seen_at ? (
        <span className="text-xs text-ink-muted">{fmtRelative(h.last_seen_at)}</span>
      ) : <span className="text-ink-soft text-xs">—</span>
    )},
    { key: "actions", header: "", className: "text-right whitespace-nowrap", render: (h) => (
      <div className="inline-flex gap-0.5">
        {!(h.worker_id || h.worker) && (
          <button onClick={(e) => { e.stopPropagation(); setAssocHelmet(h); }}
                  className="p-1.5 rounded-md hover:bg-info/10 text-ink-muted hover:text-info"
                  title="Associer">
            <LinkIcon className="w-3.5 h-3.5" />
          </button>
        )}
        {(h.worker_id || h.worker) && (
          <button onClick={(e) => {
            e.stopPropagation();
            if (confirm("Dissocier ce casque ?")) dissocMut.mutate(h.id);
          }} className="p-1.5 rounded-md hover:bg-warn/10 text-ink-muted hover:text-warn"
             title="Dissocier">
            <Unlink className="w-3.5 h-3.5" />
          </button>
        )}
        {h.status === "active" && (
          <button onClick={(e) => { e.stopPropagation(); suspendMut.mutate(h.id); }}
                  className="p-1.5 rounded-md hover:bg-warn/10 text-ink-muted hover:text-warn"
                  title="Maintenance">
            <Wrench className="w-3.5 h-3.5" />
          </button>
        )}
        {h.status === "maintenance" && (
          <button onClick={(e) => { e.stopPropagation(); reactMut.mutate(h.id); }}
                  className="p-1.5 rounded-md hover:bg-ok/10 text-ink-muted hover:text-ok"
                  title="Réactiver">
            <CheckCircle2 className="w-3.5 h-3.5" />
          </button>
        )}
        <button onClick={(e) => { e.stopPropagation(); setEditHelmet(h); }}
                className="p-1.5 rounded-md hover:bg-surface-soft text-ink-muted hover:text-ink"
                title="Modifier">
          <Edit3 className="w-3.5 h-3.5" />
        </button>
        <button onClick={(e) => {
          e.stopPropagation();
          if (confirm(`Supprimer casque ${h.serial_number || h.uid} ?`)) deleteMut.mutate(h.id);
        }} className="p-1.5 rounded-md hover:bg-danger/10 text-ink-muted hover:text-danger"
           title="Supprimer">
          <Trash2 className="w-3.5 h-3.5" />
        </button>
      </div>
    )},
  ];

  return (
    <div>
      <PageHeader
        title="Casques BLE"
        subtitle={`${data?.count ?? 0} casques affichés — ${stats.total} au total`}
        actions={
          <div className="flex gap-2">
            <Button variant="ghost" leftIcon={<Upload className="w-4 h-4" />}
                    onClick={() => setBulkOpen(true)}>
              Enrôlement multiple
            </Button>
            <Button leftIcon={<Plus className="w-4 h-4" />} onClick={() => setEnrollOpen(true)}>
              Nouveau casque
            </Button>
          </div>
        }
      />

      <StatsRow stats={[
        { label: "Total", value: stats.total, icon: <HardHat className="w-4 h-4" />, tone: "brand" },
        { label: "Appariés", value: stats.paired, icon: <LinkIcon className="w-4 h-4" />, tone: "ok" },
        { label: "Non appariés", value: stats.unpaired, icon: <Unlink className="w-4 h-4" />, tone: "warn",
          onClick: () => setAssociatedFilter("false") },
        { label: "Batterie faible", value: stats.lowBattery, icon: <BatteryLow className="w-4 h-4" />, tone: "warn",
          onClick: () => setBatteryFilter("20") },
        { label: "Non vus 7j+", value: stats.stale, icon: <AlertTriangle className="w-4 h-4" />, tone: "danger",
          onClick: () => setStaleFilter("7d") },
        { label: "Perdus", value: stats.lost, icon: <AlertTriangle className="w-4 h-4" />, tone: "danger",
          onClick: () => setStatusFilter("lost") },
      ]} />

      <Card padded={false}>
        <div className="p-4 border-b border-surface-border space-y-3">
          <div className="flex flex-col sm:flex-row gap-2">
            <div className="flex-1">
              <Input placeholder="Serial, BLE UID, UHF UID, ouvrier…" leftIcon={<Search className="w-4 h-4" />}
                     value={q} onChange={(e) => { setQ(e.target.value); setPage(1); }} />
            </div>
            <select value={statusFilter} onChange={(e) => { setStatusFilter(e.target.value); setPage(1); }} className="field sm:w-40">
              <option value="">Tous statuts</option>
              <option value="active">Actifs</option>
              <option value="maintenance">Maintenance</option>
              <option value="lost">Perdus</option>
              <option value="retired">Retirés</option>
            </select>
            <button onClick={() => setShowAdvanced(!showAdvanced)}
                    className="flex items-center gap-1 px-3 rounded-lg border border-surface-border text-xs text-ink-muted hover:text-ink hover:bg-surface-soft">
              <Filter className="w-3.5 h-3.5" /> Filtres {showAdvanced ? "▲" : "▼"}
            </button>
            <div className="inline-flex rounded-lg bg-surface-soft p-0.5 border border-surface-border">
              <button onClick={() => setMode("list")}
                      className={cn("flex items-center gap-1 px-2.5 py-1.5 rounded text-xs",
                        mode === "list" ? "bg-brand-500 text-white" : "text-ink-muted")}>
                <ListIcon className="w-3.5 h-3.5" /> Liste
              </button>
              <button onClick={() => setMode("grid")}
                      className={cn("flex items-center gap-1 px-2.5 py-1.5 rounded text-xs",
                        mode === "grid" ? "bg-brand-500 text-white" : "text-ink-muted")}>
                <LayoutGrid className="w-3.5 h-3.5" /> Grille
              </button>
            </div>
          </div>

          {showAdvanced && (
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 pt-2 border-t border-surface-border/60">
              <select value={siteFilter} onChange={(e) => { setSiteFilter(e.target.value ? Number(e.target.value) : ""); setPage(1); }} className="field">
                <option value="">Tous sites</option>
                {sites?.results?.map((s: any) => <option key={s.id} value={s.id}>{s.name}</option>)}
              </select>
              <select value={associatedFilter} onChange={(e) => { setAssociatedFilter(e.target.value); setPage(1); }} className="field">
                <option value="">Tous</option>
                <option value="true">Appariés</option>
                <option value="false">Non appariés</option>
              </select>
              <select value={batteryFilter} onChange={(e) => { setBatteryFilter(e.target.value); setPage(1); }} className="field">
                <option value="">Batterie</option>
                <option value="20">{"<"} 20%</option>
                <option value="40">{"<"} 40%</option>
              </select>
              <select value={signalFilter} onChange={(e) => { setSignalFilter(e.target.value); setPage(1); }} className="field">
                <option value="">Signal RSSI</option>
                <option value="-80">Faible ({"<"} -80 dBm)</option>
                <option value="-90">Très faible ({"<"} -90 dBm)</option>
              </select>
              <button onClick={resetFilters}
                      className="col-span-full sm:col-span-1 h-10 rounded-lg border border-surface-border text-xs hover:bg-surface-soft">
                Réinitialiser
              </button>
            </div>
          )}
        </div>

        {mode === "list" ? (
          <DataTable
            columns={columns} rows={data?.results || []} loading={isLoading}
            rowKey={(h) => h.id}
            emptyLabel="Aucun casque trouvé"
            pagination={{ count: data?.count ?? 0, pageSize, page, onPageChange: setPage }}
          />
        ) : (
          <HelmetGrid helmets={data?.results || []} onEdit={setEditHelmet} onAssoc={setAssocHelmet}
                     onDissoc={(id) => dissocMut.mutate(id)}
                     onDelete={(id) => deleteMut.mutate(id)} />
        )}
      </Card>

      <HelmetEnrollModal open={enrollOpen} onClose={() => setEnrollOpen(false)} />
      <HelmetBulkModal open={bulkOpen} onClose={() => setBulkOpen(false)} />
      <HelmetEditModal helmet={editHelmet} onClose={() => setEditHelmet(null)} />
      <HelmetAssocModal helmet={assocHelmet} onClose={() => setAssocHelmet(null)} />
    </div>
  );
}

// ─────────────────────────────────────────────────────────────
// Grille miniature
// ─────────────────────────────────────────────────────────────
function HelmetGrid({ helmets, onEdit, onAssoc, onDissoc, onDelete }: {
  helmets: any[]; onEdit: (h: any) => void; onAssoc: (h: any) => void;
  onDissoc: (id: number) => void; onDelete: (id: number) => void;
}) {
  if (helmets.length === 0)
    return <div className="p-8 text-center text-ink-muted text-sm">Aucun casque</div>;
  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-3 p-4">
      {helmets.map((h) => {
        const paired = h.worker_id || h.worker_name || h.worker;
        const lowBat = h.battery_pct != null && h.battery_pct < 20;
        return (
          <div key={h.id}
               className={cn("rounded-2xl border p-4 hover:border-brand-500/40 transition",
                 lowBat ? "border-warn/40 bg-warn/5" : "border-surface-border bg-surface-card/60"
               )}>
            <div className="flex items-start justify-between mb-3">
              <div className="w-10 h-10 rounded-xl bg-warn/10 text-warn grid place-items-center">
                <HardHat className="w-5 h-5" />
              </div>
              <Badge tone={
                h.status === "active" || !h.status ? "ok" :
                h.status === "maintenance" ? "warn" :
                h.status === "lost" ? "danger" : "muted"
              } dot>{h.status || "actif"}</Badge>
            </div>

            <code className="text-sm font-mono text-ink block truncate">
              {h.serial_number || h.uid}
            </code>
            {h.ble_beacon_uid && (
              <div className="text-[10px] text-ink-soft font-mono flex items-center gap-1 mt-0.5">
                <Radio className="w-2.5 h-2.5" /> BLE {h.ble_beacon_uid}
              </div>
            )}
            {h.uhf_tag_uid && (
              <div className="text-[10px] text-ink-soft font-mono">
                UHF {h.uhf_tag_uid}
              </div>
            )}

            <div className="mt-3 pt-3 border-t border-surface-border/60 space-y-1.5 text-xs">
              {paired ? (
                <div className="flex items-center gap-1">
                  <UserIcon className="w-3 h-3 text-ink-soft" />
                  <span className="text-ink truncate">
                    {h.worker_name || (typeof h.worker === "object" ? h.worker.full_name : `#${h.worker}`)}
                  </span>
                </div>
              ) : (
                <div className="text-warn">⚠ Non apparié</div>
              )}
              {h.battery_pct != null && (
                <div className="flex items-center gap-1">
                  <Battery className={cn("w-3 h-3",
                    h.battery_pct < 20 ? "text-danger" : h.battery_pct < 40 ? "text-warn" : "text-ok")} />
                  <span>{h.battery_pct}%</span>
                </div>
              )}
              {typeof h.site === "object" && h.site?.name && (
                <div className="flex items-center gap-1 text-ink-muted">
                  <MapPin className="w-3 h-3" />
                  <span className="truncate">{h.site.name}</span>
                </div>
              )}
              {h.last_seen_at && (
                <div className="text-ink-soft">Vu {fmtRelative(h.last_seen_at)}</div>
              )}
            </div>

            <div className="mt-3 flex gap-1 justify-end">
              {!paired ? (
                <button onClick={() => onAssoc(h)} title="Apparier"
                        className="p-1.5 rounded hover:bg-info/10 text-ink-muted hover:text-info">
                  <LinkIcon className="w-3.5 h-3.5" />
                </button>
              ) : (
                <button onClick={() => confirm("Dissocier ?") && onDissoc(h.id)} title="Dissocier"
                        className="p-1.5 rounded hover:bg-warn/10 text-ink-muted hover:text-warn">
                  <Unlink className="w-3.5 h-3.5" />
                </button>
              )}
              <button onClick={() => onEdit(h)} title="Modifier"
                      className="p-1.5 rounded hover:bg-surface-soft text-ink-muted hover:text-ink">
                <Edit3 className="w-3.5 h-3.5" />
              </button>
              <button onClick={() => confirm(`Supprimer ${h.serial_number || h.uid} ?`) && onDelete(h.id)}
                      title="Supprimer"
                      className="p-1.5 rounded hover:bg-danger/10 text-ink-muted hover:text-danger">
                <Trash2 className="w-3.5 h-3.5" />
              </button>
            </div>
          </div>
        );
      })}
    </div>
  );
}

// ─────────────────────────────────────────────────────────────
// Modal enrôlement unitaire
// ─────────────────────────────────────────────────────────────
function HelmetEnrollModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [enrollMode, setEnrollMode] = useState<"manual" | "live">("manual");
  const [form, setForm] = useState({
    serial_number: "", ble_beacon_uid: "", uhf_tag_uid: "",
    mac_address: "", uuid: "", major: "", minor: "",
    worker: "" as any, site: "" as any, status: "active",
  });
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({});
  const [duplicate, setDuplicate] = useState<any | null>(null);
  const seenIds = useRef<Set<string>>(new Set());
  const qc = useQueryClient();

  const { data: inbox } = useQuery({
    queryKey: ["helmet-scan-inbox"],
    queryFn: async () => (await helmetsService.scanInbox()).data,
    refetchInterval: enrollMode === "live" ? 1500 : false,
    enabled: open && enrollMode === "live",
    retry: false,
  });

  useEffect(() => {
    if (enrollMode !== "live" || !inbox?.scans) return;
    for (const s of (inbox.scans || [])) {
      const id = s.ble_beacon_uid || s.uid || s.mac_address;
      if (id && !seenIds.current.has(id)) {
        seenIds.current.add(id);
        setForm((f) => ({
          ...f,
          ble_beacon_uid: s.ble_beacon_uid || f.ble_beacon_uid,
          mac_address: s.mac_address || f.mac_address,
          uuid: s.uuid || f.uuid,
          major: s.major || f.major,
          minor: s.minor || f.minor,
          serial_number: f.serial_number || `HLM-${id.slice(-6)}`,
        }));
        toast.success(`Casque BLE détecté : ${id}`);
        break;
      }
    }
  }, [inbox, enrollMode]);

  const { data: workers } = useQuery({
    queryKey: ["workers", "for-helmet-enroll"],
    queryFn: async () => (await workersService.list({ page_size: 200 })).data,
    enabled: open,
  });
  const { data: sites } = useQuery({
    queryKey: ["sites", "for-helmet-enroll"],
    queryFn: async () => (await sitesService.list({ page_size: 200 })).data,
    enabled: open,
  });

  const submitMut = useMutation({
    mutationFn: () => helmetsService.create(omitEmpty({
      ...form,
      worker: form.worker ? Number(form.worker) : undefined,
      site: form.site ? Number(form.site) : undefined,
    })),
    onSuccess: () => {
      toast.success("Casque enrôlé");
      qc.invalidateQueries({ queryKey: ["helmets"] });
      onClose();
      resetLocal();
    },
    onError: (e) => {
      const p = parseApiErrors(e);
      setFieldErrors(p.fieldErrors);
      toast.error(p.globalMessage);
    },
  });

  const resetLocal = () => {
    setForm({
      serial_number: "", ble_beacon_uid: "", uhf_tag_uid: "",
      mac_address: "", uuid: "", major: "", minor: "",
      worker: "", site: "", status: "active",
    });
    setFieldErrors({}); setDuplicate(null); seenIds.current.clear();
  };

  return (
    <Modal open={open} onClose={() => { onClose(); resetLocal(); }} size="lg"
      title="Enrôler un casque BLE"
      footer={<>
        <Button variant="ghost" onClick={() => { onClose(); resetLocal(); }}>Annuler</Button>
        <Button onClick={() => {
          if (!form.serial_number) { setFieldErrors({ serial_number: "Requis" }); return; }
          submitMut.mutate();
        }} loading={submitMut.isPending}>
          Enrôler le casque
        </Button>
      </>}>
      <div className="space-y-4">
        <div className="flex gap-2">
          <button onClick={() => setEnrollMode("manual")}
                  className={cn("flex-1 p-3 rounded-lg border text-sm",
                    enrollMode === "manual" ? "border-brand-500 bg-brand-500/5" : "border-surface-border")}>
            <Edit3 className="w-4 h-4 mx-auto mb-1 text-brand-ink" />
            Saisie manuelle
          </button>
          <button onClick={() => setEnrollMode("live")}
                  className={cn("flex-1 p-3 rounded-lg border text-sm",
                    enrollMode === "live" ? "border-brand-500 bg-brand-500/5" : "border-surface-border")}>
            <Radar className="w-4 h-4 mx-auto mb-1 text-info" />
            Scan BLE à proximité
            <LivePulse label="LIVE" />
          </button>
        </div>

        {enrollMode === "live" && (
          <div className="p-3 rounded-lg bg-info/5 border border-info/20 text-xs text-ink flex gap-2">
            <Radar className="w-4 h-4 text-info shrink-0" />
            <div>
              <strong>Placez le casque BLE près d'un gateway configuré</strong>.
              Les beacons détectés remplissent automatiquement le formulaire.
            </div>
          </div>
        )}

        <div className="grid grid-cols-2 gap-3">
          <Input label="Numéro série" requiredMark placeholder="HLM-001"
                 value={form.serial_number} onChange={(e) => setForm({...form, serial_number: e.target.value})}
                 error={fieldErrors.serial_number} />
          <Input label="Tag BLE (beacon UID)" placeholder="AC:BC:32:..."
                 value={form.ble_beacon_uid} onChange={(e) => setForm({...form, ble_beacon_uid: e.target.value})} />
          <Input label="Tag UHF (Xerafy)" placeholder="UHF-..."
                 value={form.uhf_tag_uid} onChange={(e) => setForm({...form, uhf_tag_uid: e.target.value})} />
          <Input label="Adresse MAC" placeholder="AC:BC:32:XX:XX:XX"
                 value={form.mac_address} onChange={(e) => setForm({...form, mac_address: e.target.value})} />
          <Input label="UUID (iBeacon)" placeholder="F7826DA6-4FA2-4E98..."
                 value={form.uuid} onChange={(e) => setForm({...form, uuid: e.target.value})} />
          <Input label="Major" type="number"
                 value={form.major} onChange={(e) => setForm({...form, major: e.target.value})} />
          <Input label="Minor" type="number"
                 value={form.minor} onChange={(e) => setForm({...form, minor: e.target.value})} />

          <label className="block">
            <span className="text-xs font-medium text-ink-muted">Site</span>
            <select value={form.site} onChange={(e) => setForm({...form, site: e.target.value})} className="field w-full mt-1.5">
              <option value="">— Aucun —</option>
              {sites?.results?.map((s: any) => <option key={s.id} value={s.id}>{s.name}</option>)}
            </select>
          </label>

          <label className="block col-span-2">
            <span className="text-xs font-medium text-ink-muted">Apparier immédiatement à un ouvrier</span>
            <select value={form.worker} onChange={(e) => setForm({...form, worker: e.target.value})} className="field w-full mt-1.5">
              <option value="">— Aucun (apparier plus tard) —</option>
              {workers?.results?.map((w: any) => (
                <option key={w.id} value={w.id}>
                  {w.matricule} — {w.first_name} {w.last_name}
                </option>
              ))}
            </select>
          </label>
        </div>
      </div>
    </Modal>
  );
}

// ─────────────────────────────────────────────────────────────
// Modal enrôlement en masse (BLE)
// ─────────────────────────────────────────────────────────────
function HelmetBulkModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [mode, setMode] = useState<EnrollMode>("manual");
  const [text, setText] = useState("");
  const [items, setItems] = useState<{ serial: string; ble?: string; status?: "ok" | "error"; msg?: string }[]>([]);
  const seen = useRef<Set<string>>(new Set());
  const fileRef = useRef<HTMLInputElement>(null);
  const qc = useQueryClient();

  const { data: inbox } = useQuery({
    queryKey: ["helmet-bulk-inbox"],
    queryFn: async () => (await helmetsService.scanInbox()).data,
    refetchInterval: mode === "live" ? 1500 : false,
    enabled: open && mode === "live",
    retry: false,
  });

  useEffect(() => {
    if (mode !== "live" || !inbox?.scans) return;
    const fresh: any[] = [];
    for (const s of (inbox.scans || [])) {
      const bleId = s.ble_beacon_uid || s.uid;
      if (bleId && !seen.current.has(bleId)) {
        seen.current.add(bleId);
        fresh.push({
          serial: `HLM-${bleId.slice(-6)}`,
          ble: bleId,
        });
      }
    }
    if (fresh.length > 0) {
      setItems((p) => [...fresh, ...p]);
      toast.success(`${fresh.length} casque(s) détecté(s)`);
    }
  }, [inbox, mode]);

  const parseBatch = () => {
    const lines = text.split(/\r?\n/).map((l) => l.trim()).filter(Boolean);
    const fresh = lines.map((l) => {
      const parts = l.split(/[,;\t]/);
      return { serial: parts[0], ble: parts[1] };
    }).filter((i) => i.serial && !seen.current.has(i.serial));
    fresh.forEach((i) => seen.current.add(i.serial));
    setItems((p) => [...fresh, ...p]);
    setText("");
    toast.success(`${fresh.length} ajouté(s)`);
  };

  const parseCsv = (file: File) => {
    Papa.parse(file, {
      header: false, skipEmptyLines: true,
      complete: (r) => {
        const fresh = (r.data as any[][])
          .map((row) => ({
            serial: (row[0] || "").toString().trim(),
            ble: (row[1] || "").toString().trim() || undefined,
          }))
          .filter((i) => i.serial && !seen.current.has(i.serial));
        fresh.forEach((i) => seen.current.add(i.serial));
        setItems((p) => [...fresh, ...p]);
        toast.success(`${fresh.length} importé(s)`);
      },
    });
    if (fileRef.current) fileRef.current.value = "";
  };

  const bulkMut = useMutation({
    mutationFn: () => helmetsService.bulkEnroll({
      items: items.filter((i) => !i.status).map((i) => ({
        serial_number: i.serial, ble_beacon_uid: i.ble,
      })),
    }),
    onSuccess: (r: any) => {
      const created = r.data?.created_count ?? 0;
      const errors = r.data?.errors || [];
      toast.success(`${created} casque(s) créé(s)`);
      setItems((p) => p.map((it) => {
        const e = errors.find((x: any) => x.serial_number === it.serial);
        if (e) return { ...it, status: "error", msg: e.error };
        return { ...it, status: "ok" };
      }));
      qc.invalidateQueries({ queryKey: ["helmets"] });
    },
    onError: (e) => toast.error(toApiError(e).message),
  });

  return (
    <Modal open={open} onClose={onClose} size="xl"
      title="Enrôlement multiple de casques BLE"
      footer={<>
        <Button variant="ghost" onClick={onClose}>Fermer</Button>
        <Button onClick={() => bulkMut.mutate()} loading={bulkMut.isPending}
                disabled={items.filter(i => !i.status).length === 0}
                leftIcon={<Zap className="w-4 h-4" />}>
          Enrôler {items.filter(i => !i.status).length} casques
        </Button>
      </>}>
      <div className="space-y-4">
        <div className="grid grid-cols-3 gap-2">
          {[{k:"manual",l:"Coller",icon:Edit3},{k:"csv",l:"CSV",icon:Upload},{k:"live",l:"Scan BLE",icon:Radar}].map(m => (
            <button key={m.k} onClick={() => setMode(m.k as EnrollMode)}
                    className={cn("p-2 rounded-lg border text-xs",
                      mode === m.k ? "border-brand-500 bg-brand-500/5" : "border-surface-border")}>
              <m.icon className="w-4 h-4 mx-auto mb-1" />
              {m.l}
            </button>
          ))}
        </div>

        {mode === "manual" && (
          <div>
            <textarea rows={4} value={text} onChange={(e) => setText(e.target.value)}
                      placeholder="Format: serial[,ble_uid] par ligne&#10;HLM-001,AC:BC:32:11&#10;HLM-002,AC:BC:32:12"
                      className="field w-full font-mono text-xs" />
            <Button size="sm" className="mt-2" onClick={parseBatch} disabled={!text.trim()}>
              Ajouter à la liste
            </Button>
          </div>
        )}

        {mode === "csv" && (
          <div>
            <input ref={fileRef} type="file" accept=".csv,.txt" className="hidden"
                   onChange={(e) => e.target.files?.[0] && parseCsv(e.target.files[0])} />
            <Button onClick={() => fileRef.current?.click()}
                    leftIcon={<Upload className="w-4 h-4" />}>Choisir un CSV</Button>
            <p className="mt-2 text-[11px] text-ink-soft">
              Format : serial,ble_uid (une ligne par casque)
            </p>
          </div>
        )}

        {mode === "live" && (
          <div className="p-3 rounded-lg bg-info/5 border border-info/20 text-xs flex gap-2">
            <Radar className="w-4 h-4 text-info shrink-0" />
            <div>
              <strong>Placez les casques BLE près d'un gateway</strong>.
              Chaque beacon détecté est automatiquement ajouté à la liste.
              <LivePulse label="Live" />
            </div>
          </div>
        )}

        {items.length > 0 && (
          <Card padded={false}>
            <div className="p-3 border-b border-surface-border text-xs">
              <strong>{items.length}</strong> casques ·{" "}
              {items.filter(i => i.status === "ok").length} OK ·{" "}
              {items.filter(i => i.status === "error").length} erreurs
            </div>
            <ul className="max-h-64 overflow-y-auto">
              {items.map((it) => (
                <li key={it.serial} className={cn("px-3 py-1.5 flex items-center gap-2 text-xs border-b border-surface-border/30",
                  it.status === "ok" && "bg-ok/5",
                  it.status === "error" && "bg-danger/5")}>
                  <HardHat className="w-3.5 h-3.5 text-warn" />
                  <code className="font-mono flex-1">
                    {it.serial}
                    {it.ble && <span className="ml-2 text-ink-soft">· {it.ble}</span>}
                  </code>
                  {it.status === "ok" && <Badge tone="ok"><CheckCircle2 className="w-3 h-3" /> Créé</Badge>}
                  {it.status === "error" && <span className="text-danger text-[10px]">{it.msg}</span>}
                </li>
              ))}
            </ul>
          </Card>
        )}
      </div>
    </Modal>
  );
}

// ─────────────────────────────────────────────────────────────
// Modal édition helmet
// ─────────────────────────────────────────────────────────────
function HelmetEditModal({ helmet, onClose }: { helmet: any | null; onClose: () => void }) {
  const [ble, setBle] = useState("");
  const [uhf, setUhf] = useState("");
  const [status, setStatus] = useState("active");
  const qc = useQueryClient();

  useEffect(() => {
    setBle(helmet?.ble_beacon_uid || "");
    setUhf(helmet?.uhf_tag_uid || "");
    setStatus(helmet?.status || "active");
  }, [helmet]);

  const saveMut = useMutation({
    mutationFn: () => helmetsService.update(helmet.id, {
      ble_beacon_uid: ble, uhf_tag_uid: uhf, status,
    }),
    onSuccess: () => {
      toast.success("Casque modifié");
      qc.invalidateQueries({ queryKey: ["helmets"] });
      onClose();
    },
    onError: (e) => toast.error(toApiError(e).message),
  });

  if (!helmet) return null;
  return (
    <Modal open={!!helmet} onClose={onClose}
      title={`Modifier ${helmet.serial_number || helmet.uid}`}
      footer={<>
        <Button variant="ghost" onClick={onClose}>Annuler</Button>
        <Button onClick={() => saveMut.mutate()} loading={saveMut.isPending}>Enregistrer</Button>
      </>}>
      <div className="space-y-3">
        <Input label="Tag BLE" value={ble} onChange={(e) => setBle(e.target.value)} />
        <Input label="Tag UHF" value={uhf} onChange={(e) => setUhf(e.target.value)} />
        <label className="block">
          <span className="text-xs font-medium text-ink-muted">Statut</span>
          <select value={status} onChange={(e) => setStatus(e.target.value)} className="field w-full mt-1.5">
            <option value="active">Actif</option>
            <option value="maintenance">Maintenance</option>
            <option value="lost">Perdu</option>
            <option value="retired">Retiré</option>
          </select>
        </label>
      </div>
    </Modal>
  );
}

// ─────────────────────────────────────────────────────────────
// Modal apparier à un ouvrier
// ─────────────────────────────────────────────────────────────
function HelmetAssocModal({ helmet, onClose }: { helmet: any | null; onClose: () => void }) {
  const [workerId, setWorkerId] = useState("");
  const qc = useQueryClient();

  const { data: workers } = useQuery({
    queryKey: ["workers", "for-helmet-assoc"],
    queryFn: async () => (await workersService.list({ page_size: 200 })).data,
    enabled: !!helmet,
  });

  const assocMut = useMutation({
    mutationFn: () => helmetsService.associate(helmet.id, Number(workerId)),
    onSuccess: () => {
      toast.success("Casque apparié");
      qc.invalidateQueries({ queryKey: ["helmets"] });
      onClose();
    },
    onError: (e) => toast.error(toApiError(e).message),
  });

  if (!helmet) return null;
  return (
    <Modal open={!!helmet} onClose={onClose}
      title={`Apparier ${helmet.serial_number || helmet.uid} à un ouvrier`}
      footer={<>
        <Button variant="ghost" onClick={onClose}>Annuler</Button>
        <Button onClick={() => workerId && assocMut.mutate()} disabled={!workerId}
                loading={assocMut.isPending} leftIcon={<LinkIcon className="w-4 h-4" />}>
          Apparier
        </Button>
      </>}>
      <label className="block">
        <span className="text-xs font-medium text-ink-muted">Ouvrier</span>
        <select value={workerId} onChange={(e) => setWorkerId(e.target.value)}
                className="field w-full mt-1.5">
          <option value="">— Sélectionner —</option>
          {workers?.results?.map((w: any) => (
            <option key={w.id} value={w.id}>{w.matricule} — {w.first_name} {w.last_name}</option>
          ))}
        </select>
      </label>
    </Modal>
  );
}
