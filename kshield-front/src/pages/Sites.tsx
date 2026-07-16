import { useState, useMemo } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { PageHeader } from "@/components/PageHeader";
import { Card } from "@/components/ui/Card";
import { DataTable, Column } from "@/components/ui/DataTable";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Modal } from "@/components/ui/Modal";
import { StatsRow } from "@/components/StatsRow";
import { sitesService, companiesService } from "@/services";
import { toApiError } from "@/lib/api";
import { fmtDate } from "@/lib/format";
import { Plus, MapPin, Search, Trash2, Edit3, Building2, HardHat, Warehouse, Home } from "lucide-react";
import toast from "react-hot-toast";
import { MapLocationPicker } from "@/components/MapLocationPicker";

type SiteForm = {
  name: string; code: string; type: string; status: string;
  company: number | ""; latitude: string; longitude: string;
  project_manager_name: string; risk_level: string; timezone: string;
};

const emptyForm: SiteForm = {
  name: "", code: "", type: "office", status: "active",
  company: "", latitude: "", longitude: "",
  project_manager_name: "", risk_level: "", timezone: "Africa/Abidjan",
};

export function SitesPage() {
  const [q, setQ] = useState("");
  const [typeFilter, setTypeFilter] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [companyFilter, setCompanyFilter] = useState<number | "">("");
  const [page, setPage] = useState(1);
  const [modalOpen, setModalOpen] = useState(false);
  const [editId, setEditId] = useState<number | null>(null);
  const [form, setForm] = useState<SiteForm>(emptyForm);
  const qc = useQueryClient();
  const navigate = useNavigate();
  const pageSize = 30;

  const { data, isLoading } = useQuery({
    queryKey: ["sites", q, typeFilter, statusFilter, companyFilter, page],
    queryFn: async () =>
      (await sitesService.list({
        page_size: pageSize, page,
        search: q || undefined,
        type: typeFilter || undefined,
        status: statusFilter || undefined,
        company: companyFilter || undefined,
      })).data,
  });

  // Stats globales (indépendantes des filtres) — 1 seul appel léger
  const { data: allSites } = useQuery({
    queryKey: ["sites", "all-stats"],
    queryFn: async () => (await sitesService.list({ page_size: 500 })).data,
    staleTime: 30_000,
  });

  const { data: companies } = useQuery({
    queryKey: ["companies", "all-for-sites"],
    queryFn: async () => (await companiesService.list({ page_size: 200 })).data,
  });

  const stats = useMemo(() => {
    const list = allSites?.results || [];
    return {
      total: allSites?.count || 0,
      active: list.filter((s: any) => s.status === "active").length,
      construction: list.filter((s: any) => s.type === "construction").length,
      office: list.filter((s: any) => s.type === "office").length,
      warehouse: list.filter((s: any) => s.type === "warehouse").length,
    };
  }, [allSites]);

  const createMut = useMutation({
    mutationFn: () => sitesService.create(cleanForm(form)),
    onSuccess: () => { toast.success("Site créé"); closeModal(); qc.invalidateQueries({ queryKey: ["sites"] }); },
    onError: (e) => toast.error(toApiError(e).message),
  });
  const updateMut = useMutation({
    mutationFn: () => sitesService.update(editId!, cleanForm(form)),
    onSuccess: () => { toast.success("Site modifié"); closeModal(); qc.invalidateQueries({ queryKey: ["sites"] }); },
    onError: (e) => toast.error(toApiError(e).message),
  });
  const removeMut = useMutation({
    mutationFn: (id: number) => sitesService.remove(id),
    onSuccess: () => { toast.success("Supprimé"); qc.invalidateQueries({ queryKey: ["sites"] }); },
    onError: (e) => toast.error(toApiError(e).message),
  });

  const openCreate = () => { setEditId(null); setForm(emptyForm); setModalOpen(true); };
  const openEdit = (s: any) => {
    setEditId(s.id);
    setForm({
      name: s.name || "", code: s.code || "", type: s.type || "office", status: s.status || "active",
      company: typeof s.company === "object" ? s.company?.id : s.company || "",
      latitude: s.latitude?.toString() || "", longitude: s.longitude?.toString() || "",
      project_manager_name: s.project_manager_name || "", risk_level: s.risk_level || "",
      timezone: s.timezone || "Africa/Abidjan",
    });
    setModalOpen(true);
  };
  const closeModal = () => { setModalOpen(false); setEditId(null); setForm(emptyForm); };
  const onSubmit = () => {
    if (!form.name || !form.code) return toast.error("Nom et code obligatoires");
    const lat = Number(form.latitude), lng = Number(form.longitude);
    if (!Number.isFinite(lat) || !Number.isFinite(lng)) {
      return toast.error("Position GPS requise — clique sur la carte ou utilise la recherche");
    }
    if (lat < -90 || lat > 90 || lng < -180 || lng > 180) {
      return toast.error("Coordonnées GPS hors bornes");
    }
    if (editId) updateMut.mutate(); else createMut.mutate();
  };

  const typeIcon = (t: string) =>
    t === "construction" ? <HardHat className="w-4 h-4" /> :
    t === "warehouse" ? <Warehouse className="w-4 h-4" /> :
    t === "office" ? <Building2 className="w-4 h-4" /> :
    <Home className="w-4 h-4" />;

  const columns: Column<any>[] = [
    { key: "name", header: "Site", render: (s) => (
      <div className="flex items-center gap-2.5">
        <div className="w-8 h-8 rounded-lg bg-brand-500/10 text-brand-400 grid place-items-center">
          {typeIcon(s.type)}
        </div>
        <div>
          <div className="text-sm font-medium text-ink">{s.name}</div>
          {s.code && <code className="text-xs text-ink-soft font-mono">{s.code}</code>}
        </div>
      </div>
    )},
    { key: "type", header: "Type", render: (s) => <Badge tone="info">{s.type || "—"}</Badge> },
    { key: "company", header: "Filiale", render: (s) =>
      typeof s.company === "object" ? s.company?.name : s.company ? `#${s.company}` : "—",
    },
    { key: "risk", header: "Risque", render: (s) =>
      s.risk_level ? <Badge tone={
        s.risk_level === "extreme" ? "danger" : s.risk_level === "high" ? "warn" :
        s.risk_level === "medium" ? "info" : "muted"
      }>{s.risk_level}</Badge> : <span className="text-ink-soft text-xs">—</span>
    },
    { key: "geo", header: "GPS", render: (s) =>
      s.latitude && s.longitude ?
        <Badge tone="ok">📍 Localisé</Badge> :
        <Badge tone="muted">Sans coords</Badge>
    },
    { key: "status", header: "Statut", render: (s) => (
      <Badge tone={s.status === "active" ? "ok" : s.status === "archived" ? "muted" : "warn"} dot>
        {s.status || "actif"}
      </Badge>
    )},
    { key: "created", header: "Créé", render: (s) => <span className="text-xs text-ink-muted">{fmtDate(s.created_at)}</span> },
    { key: "actions", header: "", className: "text-right whitespace-nowrap", render: (s) => (
      <div className="inline-flex items-center gap-1">
        <button onClick={(e) => { e.stopPropagation(); openEdit(s); }}
                className="p-1.5 rounded-md hover:bg-surface-soft text-ink-muted hover:text-ink" title="Modifier">
          <Edit3 className="w-3.5 h-3.5" />
        </button>
        <button onClick={(e) => { e.stopPropagation(); if (confirm(`Supprimer "${s.name}" ?`)) removeMut.mutate(s.id); }}
                className="p-1.5 rounded-md hover:bg-danger/10 text-ink-muted hover:text-danger" title="Supprimer">
          <Trash2 className="w-3.5 h-3.5" />
        </button>
      </div>
    )},
  ];

  return (
    <div>
      <PageHeader
        title="Sites / Chantiers"
        subtitle={`${data?.count ?? 0} sites — total flotte : ${stats.total}`}
        actions={<Button leftIcon={<Plus className="w-4 h-4" />} onClick={openCreate}>Nouveau site</Button>}
      />

      <StatsRow stats={[
        { label: "Total sites",   value: stats.total,        icon: <MapPin className="w-4 h-4" />,     tone: "brand" },
        { label: "Actifs",        value: stats.active,       icon: <Building2 className="w-4 h-4" />,  tone: "ok",
          onClick: () => setStatusFilter("active") },
        { label: "Chantiers",     value: stats.construction, icon: <HardHat className="w-4 h-4" />,    tone: "warn",
          onClick: () => setTypeFilter("construction") },
        { label: "Bureaux",       value: stats.office,       icon: <Building2 className="w-4 h-4" />,  tone: "info",
          onClick: () => setTypeFilter("office") },
        { label: "Entrepôts",     value: stats.warehouse,    icon: <Warehouse className="w-4 h-4" />,  tone: "muted",
          onClick: () => setTypeFilter("warehouse") },
      ]} />

      <Card padded={false}>
        <div className="p-4 border-b border-surface-border grid grid-cols-1 sm:grid-cols-4 gap-2">
          <div className="sm:col-span-2">
            <Input placeholder="Rechercher un site…" leftIcon={<Search className="w-4 h-4" />}
                   value={q} onChange={(e) => { setQ(e.target.value); setPage(1); }} />
          </div>
          <select value={typeFilter} onChange={(e) => { setTypeFilter(e.target.value); setPage(1); }} className="field">
            <option value="">Tous types</option>
            <option value="office">Bureau</option>
            <option value="construction">Chantier</option>
            <option value="warehouse">Entrepôt</option>
            <option value="mixed">Mixte</option>
          </select>
          <select value={companyFilter} onChange={(e) => { setCompanyFilter(e.target.value ? Number(e.target.value) : ""); setPage(1); }} className="field">
            <option value="">Toutes filiales</option>
            {companies?.results?.map((c: any) => <option key={c.id} value={c.id}>{c.name}</option>)}
          </select>
        </div>
        <DataTable
          columns={columns} rows={data?.results || []} loading={isLoading}
          rowKey={(s) => s.id} onRowClick={(s) => navigate(`/sites/${s.id}`)}
          emptyLabel="Aucun site trouvé"
          pagination={{ count: data?.count ?? 0, pageSize, page, onPageChange: setPage }}
        />
      </Card>

      <Modal open={modalOpen} onClose={closeModal} title={editId ? "Modifier le site" : "Nouveau site"} size="lg"
        footer={<>
          <Button variant="ghost" onClick={closeModal}>Annuler</Button>
          <Button onClick={onSubmit} loading={createMut.isPending || updateMut.isPending}>
            {editId ? "Enregistrer" : "Créer"}
          </Button>
        </>}>
        <div className="grid grid-cols-2 gap-3">
          <Input label="Nom *" value={form.name} onChange={(e) => setForm({...form, name: e.target.value})} />
          <Input label="Code *" placeholder="KRE-01" value={form.code} onChange={(e) => setForm({...form, code: e.target.value})} />
          <label className="block">
            <span className="text-xs font-medium text-ink-muted">Type</span>
            <select value={form.type} onChange={(e) => setForm({...form, type: e.target.value})} className="field w-full mt-1.5">
              <option value="office">Bureau</option><option value="construction">Chantier</option>
              <option value="warehouse">Entrepôt</option><option value="mixed">Mixte</option>
            </select>
          </label>
          <label className="block">
            <span className="text-xs font-medium text-ink-muted">Filiale</span>
            <select value={form.company} onChange={(e) => setForm({...form, company: e.target.value ? Number(e.target.value) : ""})} className="field w-full mt-1.5">
              <option value="">— Sélectionner —</option>
              {companies?.results?.map((c: any) => <option key={c.id} value={c.id}>{c.name}</option>)}
            </select>
          </label>
          <div className="col-span-2">
            <label className="block text-xs font-medium text-ink-muted mb-1.5">
              Position GPS <span className="text-danger">*</span>
            </label>
            <MapLocationPicker
              latitude={form.latitude ? Number(form.latitude) : null}
              longitude={form.longitude ? Number(form.longitude) : null}
              onChange={({ latitude, longitude }) =>
                setForm((f) => ({
                  ...f,
                  latitude: String(latitude),
                  longitude: String(longitude),
                }))
              }
            />
          </div>
          <Input label="Chef de projet" value={form.project_manager_name} onChange={(e) => setForm({...form, project_manager_name: e.target.value})} />
          <label className="block">
            <span className="text-xs font-medium text-ink-muted">Niveau de risque</span>
            <select value={form.risk_level} onChange={(e) => setForm({...form, risk_level: e.target.value})} className="field w-full mt-1.5">
              <option value="">—</option><option value="low">Faible</option><option value="medium">Moyen</option>
              <option value="high">Élevé</option><option value="extreme">Critique</option>
            </select>
          </label>
          <label className="block">
            <span className="text-xs font-medium text-ink-muted">Statut</span>
            <select value={form.status} onChange={(e) => setForm({...form, status: e.target.value})} className="field w-full mt-1.5">
              <option value="active">Actif</option><option value="inactive">Inactif</option><option value="archived">Archivé</option>
            </select>
          </label>
          <Input label="Fuseau horaire" value={form.timezone} onChange={(e) => setForm({...form, timezone: e.target.value})} />
        </div>
      </Modal>
    </div>
  );
}

function cleanForm(f: SiteForm): any {
  const out: any = { ...f };
  if (out.company === "") delete out.company;
  if (out.latitude) out.latitude = Number(out.latitude); else delete out.latitude;
  if (out.longitude) out.longitude = Number(out.longitude); else delete out.longitude;
  Object.keys(out).forEach(k => { if (out[k] === "") out[k] = null; });
  return out;
}
