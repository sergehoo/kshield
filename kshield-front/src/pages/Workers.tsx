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
import {
  workersService, subcontractorsService, tradesService, sitesService, zonesService,
} from "@/services";
import { toApiError } from "@/lib/api";
import { parseApiErrors, omitEmpty, FieldErrors, fieldLabel } from "@/lib/formErrors";
import { FormErrorBanner } from "@/components/FormErrorBanner";
import { initials, fmtDate } from "@/lib/format";
import {
  Plus, Search, Edit3, Trash2, HardHat, CreditCard, Phone,
  Filter, Users as UsersIcon, ShieldOff, ShieldCheck, Ban, UploadCloud,
} from "lucide-react";
import { Link } from "react-router-dom";
import toast from "react-hot-toast";

type WorkerForm = {
  matricule: string;
  first_name: string; last_name: string;
  date_of_birth: string;
  gender: string;
  marital_status: string;
  nationality: string;
  country_of_residence: string;
  city: string;
  neighborhood: string;
  address: string;
  id_type: string;
  id_document_number: string;
  id_issue_date: string;
  id_expiry_date: string;
  phone: string;
  email: string;
  emergency_contact_name: string;
  emergency_contact_phone: string;
  emergency_contact_relation: string;
  trade: number | "";
  subcontractor: number | "";
  helmet_size: string;
  hired_at: string;
  status: string;
};

const emptyForm: WorkerForm = {
  matricule: "", first_name: "", last_name: "",
  date_of_birth: "", gender: "", marital_status: "",
  nationality: "Ivoirien", country_of_residence: "Côte d'Ivoire",
  city: "", neighborhood: "", address: "",
  id_type: "cni", id_document_number: "", id_issue_date: "", id_expiry_date: "",
  phone: "", email: "",
  emergency_contact_name: "", emergency_contact_phone: "", emergency_contact_relation: "",
  trade: "", subcontractor: "",
  helmet_size: "M", hired_at: "",
  status: "active",
};

export function WorkersPage() {
  const [q, setQ] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [tradeFilter, setTradeFilter] = useState<number | "">("");
  // subFilter peut être un ID number OU la string spéciale "__internal__"
  const [subFilter, setSubFilter] = useState<number | string>("");
  const [siteFilter, setSiteFilter] = useState<number | "">("");
  const [zoneFilter, setZoneFilter] = useState<number | "">("");
  const [ageRange, setAgeRange] = useState("");           // "18-25", "26-35", "36-50", "50+"
  const [seniorityRange, setSeniorityRange] = useState(""); // "0-30", "31-180", "181-365", "365+"
  const [cityFilter, setCityFilter] = useState("");
  const [nationalityFilter, setNationalityFilter] = useState("");
  const [showAdvanced, setShowAdvanced] = useState(false);

  const [page, setPage] = useState(1);
  const [modalOpen, setModalOpen] = useState(false);
  const [editId, setEditId] = useState<number | null>(null);
  const [form, setForm] = useState<WorkerForm>(emptyForm);
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({});
  const [globalError, setGlobalError] = useState<string>("");

  const navigate = useNavigate();
  const qc = useQueryClient();
  const pageSize = 30;

  // ─── Data listes ─────────────────────────────
  const listParams = {
    page_size: pageSize, page,
    search: q || undefined,
    status: statusFilter || undefined,
    trade: tradeFilter || undefined,
    // Envoi conditionnel : ID number → filtre par sous-traitant, "__internal__" → sans sous-traitant
    subcontractor: typeof subFilter === "number" ? subFilter : undefined,
    subcontractor_isnull: subFilter === "__internal__" ? true : undefined,
    site: siteFilter || undefined,
    zone: zoneFilter || undefined,
    city: cityFilter || undefined,
    nationality: nationalityFilter || undefined,
    age_range: ageRange || undefined,
    seniority_range: seniorityRange || undefined,
  };

  const { data, isLoading } = useQuery({
    queryKey: ["workers", listParams],
    queryFn: async () => (await workersService.list(listParams)).data,
  });

  const { data: allStats } = useQuery({
    queryKey: ["workers", "stats"],
    queryFn: async () => (await workersService.list({ page_size: 1000 })).data,
    staleTime: 60_000,
  });

  const stats = useMemo(() => {
    const list = allStats?.results || [];
    return {
      total: allStats?.count || 0,
      active: list.filter((w: any) => w.status === "active").length,
      suspended: list.filter((w: any) => w.status === "suspended").length,
      blacklisted: list.filter((w: any) => w.status === "blacklisted").length,
      withBadge: list.filter((w: any) => typeof w.badge === "object" && w.badge).length,
      subs: new Set(list.map((w: any) => typeof w.subcontractor === "object" ? w.subcontractor?.id : w.subcontractor).filter(Boolean)).size,
    };
  }, [allStats]);

  // Data pour selects
  const { data: trades } = useQuery({
    queryKey: ["trades", "all"],
    queryFn: async () => (await tradesService.list({ page_size: 100 })).data,
  });
  const { data: subs } = useQuery({
    queryKey: ["subs", "all"],
    queryFn: async () => (await subcontractorsService.list({ page_size: 100 })).data,
  });
  const { data: sites } = useQuery({
    queryKey: ["sites", "all-workers"],
    queryFn: async () => (await sitesService.list({ page_size: 200 })).data,
  });
  const { data: zones } = useQuery({
    queryKey: ["zones", "all", siteFilter],
    queryFn: async () => (await zonesService.list({ page_size: 100, site: siteFilter || undefined })).data,
    enabled: !!siteFilter,
  });

  // ─── Mutations ─────────────────────────────
  const createMut = useMutation({
    mutationFn: () => workersService.create(omitEmpty(form)),
    onSuccess: () => {
      toast.success("Ouvrier créé");
      closeModal();
      qc.invalidateQueries({ queryKey: ["workers"] });
    },
    onError: (e) => {
      const parsed = parseApiErrors(e);
      setFieldErrors(parsed.fieldErrors);
      setGlobalError(parsed.globalMessage);
      // Toast court avec compteur, détails visibles dans la modale
      const nb = Object.keys(parsed.fieldErrors).length;
      toast.error(nb > 0 ? `${nb} champ(s) à corriger` : parsed.globalMessage);
    },
  });
  const updateMut = useMutation({
    mutationFn: () => workersService.update(editId!, omitEmpty(form)),
    onSuccess: () => {
      toast.success("Ouvrier modifié");
      closeModal();
      qc.invalidateQueries({ queryKey: ["workers"] });
    },
    onError: (e) => {
      const parsed = parseApiErrors(e);
      setFieldErrors(parsed.fieldErrors);
      setGlobalError(parsed.globalMessage);
      const nb = Object.keys(parsed.fieldErrors).length;
      toast.error(nb > 0 ? `${nb} champ(s) à corriger` : parsed.globalMessage);
    },
  });
  const deleteMut = useMutation({
    mutationFn: (id: number) => workersService.remove(id),
    onSuccess: () => { toast.success("Supprimé"); qc.invalidateQueries({ queryKey: ["workers"] }); },
    onError: (e) => toast.error(toApiError(e).message),
  });

  const openCreate = () => {
    setEditId(null); setForm(emptyForm);
    setFieldErrors({}); setGlobalError("");
    setModalOpen(true);
  };
  const openEdit = (w: any) => {
    setEditId(w.id);
    setForm({
      matricule: w.matricule || "", first_name: w.first_name || "", last_name: w.last_name || "",
      date_of_birth: w.date_of_birth || "", gender: w.gender || "", marital_status: w.marital_status || "",
      nationality: w.nationality || "", country_of_residence: w.country_of_residence || "Côte d'Ivoire",
      city: w.city || "", neighborhood: w.neighborhood || "", address: w.address || "",
      id_type: w.id_type || "cni", id_document_number: w.id_document_number || "",
      id_issue_date: w.id_issue_date || "", id_expiry_date: w.id_expiry_date || "",
      phone: w.phone || "", email: w.email || "",
      emergency_contact_name: w.emergency_contact_name || "",
      emergency_contact_phone: w.emergency_contact_phone || "",
      emergency_contact_relation: w.emergency_contact_relation || "",
      trade: typeof w.trade === "object" ? w.trade?.id : w.trade || "",
      subcontractor: typeof w.subcontractor === "object" ? w.subcontractor?.id : w.subcontractor || "",
      helmet_size: w.helmet_size || "M", hired_at: w.hired_at || "",
      status: w.status || "active",
    });
    setFieldErrors({});
    setGlobalError("");
    setModalOpen(true);
  };
  const closeModal = () => {
    setModalOpen(false); setEditId(null); setForm(emptyForm);
    setFieldErrors({}); setGlobalError("");
  };

  const onSubmit = () => {
    // Validation client rapide — messages en français humain
    const missing: string[] = [];
    if (!form.matricule) missing.push("Matricule");
    if (!form.first_name) missing.push("Prénom");
    if (!form.last_name) missing.push("Nom");
    if (missing.length > 0) {
      const fe: FieldErrors = {};
      if (!form.matricule) fe.matricule = "Ce champ est obligatoire.";
      if (!form.first_name) fe.first_name = "Ce champ est obligatoire.";
      if (!form.last_name) fe.last_name = "Ce champ est obligatoire.";
      setFieldErrors(fe);
      setGlobalError(`Merci de compléter : ${missing.join(", ")}.`);
      toast.error(`Champs obligatoires manquants : ${missing.join(", ")}`);
      return;
    }
    setFieldErrors({}); setGlobalError("");
    if (editId) updateMut.mutate(); else createMut.mutate();
  };

  const resetFilters = () => {
    setStatusFilter(""); setTradeFilter(""); setSubFilter(""); setSiteFilter("");
    setZoneFilter(""); setAgeRange(""); setSeniorityRange(""); setCityFilter("");
    setNationalityFilter(""); setQ(""); setPage(1);
  };

  const columns: Column<any>[] = [
    {
      key: "person", header: "Ouvrier",
      render: (w) => (
        <div className="flex items-center gap-2.5">
          {w.photo ? (
            <img src={w.photo} alt="" className="w-9 h-9 rounded-full object-cover" />
          ) : (
            <div className="w-9 h-9 rounded-full bg-warn/20 text-warn grid place-items-center text-xs font-semibold">
              {initials(`${w.first_name} ${w.last_name}`)}
            </div>
          )}
          <div className="min-w-0">
            <div className="text-sm font-medium truncate">{w.first_name} {w.last_name}</div>
            <div className="text-xs text-ink-soft font-mono">{w.matricule}</div>
          </div>
        </div>
      ),
    },
    { key: "trade", header: "Métier", render: (w) => (
      <div className="text-xs">
        <div>{typeof w.trade === "object" ? w.trade?.name : "—"}</div>
        {w.age != null && <div className="text-ink-soft">{w.age} ans</div>}
      </div>
    )},
    { key: "sub", header: "Rattachement", render: (w) => (
      <div className="text-xs">
        <div>{typeof w.subcontractor === "object" ? w.subcontractor?.name : "Interne KAYDAN"}</div>
        {w.nationality && <div className="text-ink-soft">🇮 {w.nationality}</div>}
      </div>
    )},
    { key: "location", header: "Localisation", render: (w) => (
      <div className="text-xs">
        {w.city && <div>{w.city}</div>}
        {w.neighborhood && <div className="text-ink-soft">{w.neighborhood}</div>}
        {!w.city && !w.neighborhood && "—"}
      </div>
    )},
    { key: "phone", header: "Téléphone", render: (w) => (
      w.phone ? <span className="text-xs font-mono flex items-center gap-1">
        <Phone className="w-3 h-3 text-ink-soft" />{w.phone}
      </span> : "—"
    )},
    { key: "equipment", header: "Équipement", render: (w) => {
      const badge = typeof w.badge === "object" ? w.badge : null;
      const helmet = typeof badge?.paired_helmet === "object" ? badge?.paired_helmet : null;
      return (
        <div className="flex flex-col gap-0.5">
          {badge ? (
            <span className="inline-flex items-center gap-1 text-xs">
              <CreditCard className="w-3 h-3 text-info" />
              <code className="font-mono text-[11px]">{badge.uid}</code>
            </span>
          ) : <span className="text-[11px] text-ink-soft">Sans badge</span>}
          {helmet ? (
            <span className="inline-flex items-center gap-1 text-xs">
              <HardHat className="w-3 h-3 text-warn" />
              <code className="font-mono text-[11px] text-ink-soft">{helmet.ble_beacon_uid || helmet.serial_number}</code>
            </span>
          ) : <span className="text-[11px] text-ink-soft">Sans casque</span>}
        </div>
      );
    }},
    { key: "seniority", header: "Ancienneté", render: (w) => {
      if (w.seniority_days == null) return "—";
      const days = w.seniority_days;
      if (days < 30) return <Badge tone="info">{days}j</Badge>;
      if (days < 180) return <Badge tone="info">{Math.floor(days/30)} mois</Badge>;
      if (days < 365) return <Badge tone="ok">{Math.floor(days/30)} mois</Badge>;
      return <Badge tone="ok">{Math.floor(days/365)} an{days >= 730 ? "s" : ""}</Badge>;
    }},
    { key: "status", header: "Statut", render: (w) => (
      <Badge tone={
        w.status === "active" ? "ok" :
        w.status === "suspended" ? "warn" :
        w.status === "blacklisted" ? "danger" : "muted"
      } dot>{w.status || "actif"}</Badge>
    )},
    { key: "actions", header: "", className: "text-right whitespace-nowrap", render: (w) => (
      <div className="inline-flex gap-1">
        <button onClick={(e) => { e.stopPropagation(); openEdit(w); }}
                className="p-1.5 rounded-md hover:bg-surface-soft text-ink-muted hover:text-ink" title="Modifier">
          <Edit3 className="w-3.5 h-3.5" />
        </button>
        <button onClick={(e) => {
          e.stopPropagation();
          if (confirm(`Supprimer ${w.first_name} ${w.last_name} ?`)) deleteMut.mutate(w.id);
        }} className="p-1.5 rounded-md hover:bg-danger/10 text-ink-muted hover:text-danger" title="Supprimer">
          <Trash2 className="w-3.5 h-3.5" />
        </button>
      </div>
    )},
  ];

  return (
    <div>
      <PageHeader
        title="Ouvriers"
        subtitle={`${data?.count ?? 0} résultats · ${stats.total} au total`}
        actions={
          <div className="flex gap-2">
            <Link to="/bulk-import" className="btn-ghost inline-flex">
              <UploadCloud className="w-4 h-4" /> Import CSV
            </Link>
            <Button leftIcon={<Plus className="w-4 h-4" />} onClick={openCreate}>
              Nouvel ouvrier
            </Button>
          </div>
        }
      />

      <StatsRow stats={[
        { label: "Total", value: stats.total, icon: <UsersIcon className="w-4 h-4" />, tone: "brand" },
        { label: "Actifs", value: stats.active, icon: <ShieldCheck className="w-4 h-4" />, tone: "ok",
          onClick: () => setStatusFilter("active") },
        { label: "Suspendus", value: stats.suspended, icon: <ShieldOff className="w-4 h-4" />, tone: "warn",
          onClick: () => setStatusFilter("suspended") },
        { label: "Liste rouge", value: stats.blacklisted, icon: <Ban className="w-4 h-4" />, tone: "danger",
          onClick: () => setStatusFilter("blacklisted") },
        { label: "Avec badge", value: stats.withBadge, icon: <CreditCard className="w-4 h-4" />, tone: "info" },
        { label: "Sous-traitants", value: stats.subs, icon: <HardHat className="w-4 h-4" />, tone: "muted" },
      ]} />

      <Card padded={false}>
        {/* ─── Barre de filtres ─── */}
        <div className="p-4 border-b border-surface-border space-y-3">
          {/* Ligne 1 : search + status + toggle avancé */}
          <div className="grid grid-cols-1 sm:grid-cols-6 gap-2">
            <div className="sm:col-span-3">
              <Input
                placeholder="Rechercher par nom, matricule, téléphone…"
                leftIcon={<Search className="w-4 h-4" />}
                value={q}
                onChange={(e) => { setQ(e.target.value); setPage(1); }}
              />
            </div>
            <select value={tradeFilter} onChange={(e) => { setTradeFilter(e.target.value ? Number(e.target.value) : ""); setPage(1); }} className="field">
              <option value="">Tous métiers</option>
              {trades?.results?.map((t: any) => <option key={t.id} value={t.id}>{t.name}</option>)}
            </select>
            <select value={statusFilter} onChange={(e) => { setStatusFilter(e.target.value); setPage(1); }} className="field">
              <option value="">Tous statuts</option>
              <option value="active">Actifs</option>
              <option value="suspended">Suspendus</option>
              <option value="blacklisted">Liste rouge</option>
              <option value="terminated">Sortis</option>
            </select>
            <button onClick={() => setShowAdvanced(!showAdvanced)}
                    className="flex items-center justify-center gap-1 px-3 rounded-lg border border-surface-border text-xs text-ink-muted hover:text-ink hover:bg-surface-soft transition">
              <Filter className="w-3.5 h-3.5" />
              Filtres {showAdvanced ? "▲" : "▼"}
            </button>
          </div>

          {/* Ligne 2-3 : filtres avancés */}
          {showAdvanced && (
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 pt-2 border-t border-surface-border/60">
              <label className="block">
                <span className="text-[10px] uppercase tracking-wider text-ink-soft">Sous-traitant</span>
                <select value={subFilter as any}
                        onChange={(e) => {
                          const v = e.target.value;
                          // Special value "__internal__" reste en string, sinon → number
                          if (!v) setSubFilter("");
                          else if (v === "__internal__") setSubFilter("__internal__");
                          else setSubFilter(Number(v));
                          setPage(1);
                        }}
                        className="field w-full mt-0.5">
                  <option value="">Tous</option>
                  <option value="__internal__">Interne KAYDAN</option>
                  {subs?.results?.map((s: any) => <option key={s.id} value={s.id}>{s.name}</option>)}
                </select>
              </label>
              <label className="block">
                <span className="text-[10px] uppercase tracking-wider text-ink-soft">Chantier</span>
                <select value={siteFilter} onChange={(e) => { setSiteFilter(e.target.value ? Number(e.target.value) : ""); setZoneFilter(""); setPage(1); }} className="field w-full mt-0.5">
                  <option value="">Tous</option>
                  {sites?.results?.map((s: any) => <option key={s.id} value={s.id}>{s.name}</option>)}
                </select>
              </label>
              <label className="block">
                <span className="text-[10px] uppercase tracking-wider text-ink-soft">Zone</span>
                <select value={zoneFilter} onChange={(e) => { setZoneFilter(e.target.value ? Number(e.target.value) : ""); setPage(1); }}
                        disabled={!siteFilter} className="field w-full mt-0.5">
                  <option value="">{siteFilter ? "Toutes zones" : "Sélectionner un chantier"}</option>
                  {zones?.results?.map((z: any) => <option key={z.id} value={z.id}>{z.name}</option>)}
                </select>
              </label>
              <label className="block">
                <span className="text-[10px] uppercase tracking-wider text-ink-soft">Tranche d'âge</span>
                <select value={ageRange} onChange={(e) => { setAgeRange(e.target.value); setPage(1); }} className="field w-full mt-0.5">
                  <option value="">Toutes</option>
                  <option value="18-25">18-25 ans</option>
                  <option value="26-35">26-35 ans</option>
                  <option value="36-50">36-50 ans</option>
                  <option value="50+">50+ ans</option>
                </select>
              </label>
              <label className="block">
                <span className="text-[10px] uppercase tracking-wider text-ink-soft">Ancienneté</span>
                <select value={seniorityRange} onChange={(e) => { setSeniorityRange(e.target.value); setPage(1); }} className="field w-full mt-0.5">
                  <option value="">Toutes</option>
                  <option value="0-30">Moins d'1 mois</option>
                  <option value="31-180">1-6 mois</option>
                  <option value="181-365">6-12 mois</option>
                  <option value="365+">Plus d'1 an</option>
                </select>
              </label>
              <Input label="Ville" placeholder="Abidjan"
                     value={cityFilter} onChange={(e) => { setCityFilter(e.target.value); setPage(1); }} />
              <Input label="Nationalité" placeholder="Ivoirien"
                     value={nationalityFilter} onChange={(e) => { setNationalityFilter(e.target.value); setPage(1); }} />
              <div className="flex items-end">
                <button onClick={resetFilters}
                        className="w-full h-10 px-3 rounded-lg text-xs text-ink-muted hover:text-ink border border-surface-border hover:bg-surface-soft transition">
                  Réinitialiser
                </button>
              </div>
            </div>
          )}
        </div>

        <DataTable
          columns={columns}
          rows={data?.results || []}
          loading={isLoading}
          rowKey={(w) => w.id}
          onRowClick={(w) => navigate(`/workers/${w.id}`)}
          emptyLabel="Aucun ouvrier trouvé"
          pagination={{ count: data?.count ?? 0, pageSize, page, onPageChange: setPage }}
        />
      </Card>

      <WorkerFormModal
        open={modalOpen} onClose={closeModal}
        editId={editId} form={form} setForm={setForm}
        onSubmit={onSubmit}
        submitting={createMut.isPending || updateMut.isPending}
        trades={trades?.results || []} subs={subs?.results || []}
        fieldErrors={fieldErrors} globalError={globalError}
      />
    </div>
  );
}

// ─────────────────────────────────────────────────────────────
// Modal Create/Edit ouvrier — form multi-sections KYC
// ─────────────────────────────────────────────────────────────
function WorkerFormModal({
  open, onClose, editId, form, setForm, onSubmit, submitting, trades, subs,
  fieldErrors, globalError,
}: any) {
  // Alias pour raccourcir l'affichage de l'erreur par champ dans le JSX
  const err = (k: string) => fieldErrors?.[k];
  return (
    <Modal open={open} onClose={onClose} size="xl"
      title={editId ? "Modifier l'ouvrier" : "Nouvel ouvrier"}
      footer={<>
        <Button variant="ghost" onClick={onClose}>Annuler</Button>
        <Button onClick={onSubmit} loading={submitting}
                leftIcon={editId ? <Edit3 className="w-4 h-4" /> : <Plus className="w-4 h-4" />}>
          {editId ? "Enregistrer" : "Créer l'ouvrier"}
        </Button>
      </>}>
      <div className="space-y-5 max-h-[70vh] overflow-y-auto pr-2">
        <FormErrorBanner message={globalError} fieldErrors={fieldErrors} />
        <p className="text-[11px] text-ink-soft">
          Les champs marqués <span className="text-danger">*</span> sont obligatoires.
        </p>

        <Section title="Identité">
          <div className="grid grid-cols-2 gap-3">
            <Input label="Matricule" requiredMark placeholder="OV-001" value={form.matricule}
                   onChange={(e: any) => setForm({ ...form, matricule: e.target.value })}
                   error={err("matricule")} />
            <Input label="Date de naissance" type="date" value={form.date_of_birth}
                   onChange={(e: any) => setForm({ ...form, date_of_birth: e.target.value })}
                   error={err("date_of_birth")} />
            <Input label="Prénom" requiredMark value={form.first_name}
                   onChange={(e: any) => setForm({ ...form, first_name: e.target.value })}
                   error={err("first_name")} />
            <Input label="Nom" requiredMark value={form.last_name}
                   onChange={(e: any) => setForm({ ...form, last_name: e.target.value })}
                   error={err("last_name")} />
            <Select label="Sexe" value={form.gender} onChange={(v: string) => setForm({ ...form, gender: v })}
                    options={[{value:"",label:"—"},{value:"male",label:"Homme"},{value:"female",label:"Femme"},{value:"other",label:"Autre"}]}
                    error={err("gender")} />
            <Select label="État civil" value={form.marital_status} onChange={(v: string) => setForm({ ...form, marital_status: v })}
                    options={[{value:"",label:"—"},{value:"single",label:"Célibataire"},{value:"married",label:"Marié(e)"},{value:"divorced",label:"Divorcé(e)"},{value:"widowed",label:"Veuf/veuve"}]}
                    error={err("marital_status")} />
          </div>
        </Section>

        <Section title="Résidence & origine">
          <div className="grid grid-cols-2 gap-3">
            <Input label="Nationalité" placeholder="Ivoirien" value={form.nationality}
                   onChange={(e: any) => setForm({ ...form, nationality: e.target.value })}
                   error={err("nationality")} />
            <Input label="Pays de résidence" value={form.country_of_residence}
                   onChange={(e: any) => setForm({ ...form, country_of_residence: e.target.value })} />
            <Input label="Ville" placeholder="Abidjan" value={form.city}
                   onChange={(e: any) => setForm({ ...form, city: e.target.value })} />
            <Input label="Quartier / commune" placeholder="Yopougon" value={form.neighborhood}
                   onChange={(e: any) => setForm({ ...form, neighborhood: e.target.value })} />
            <div className="col-span-2">
              <Input label="Adresse complète" value={form.address}
                     onChange={(e: any) => setForm({ ...form, address: e.target.value })} />
            </div>
          </div>
        </Section>

        <Section title="Pièce d'identité">
          <div className="grid grid-cols-2 gap-3">
            <Select label="Type" value={form.id_type} onChange={(v: string) => setForm({ ...form, id_type: v })}
                    options={[{value:"cni",label:"CNI"},{value:"passport",label:"Passeport"},{value:"driver",label:"Permis"},{value:"cedeao",label:"CEDEAO"},{value:"other",label:"Autre"}]} />
            <Input label="Numéro" value={form.id_document_number}
                   onChange={(e: any) => setForm({ ...form, id_document_number: e.target.value })} />
            <Input label="Date de délivrance" type="date" value={form.id_issue_date}
                   onChange={(e: any) => setForm({ ...form, id_issue_date: e.target.value })} />
            <Input label="Date d'expiration" type="date" value={form.id_expiry_date}
                   onChange={(e: any) => setForm({ ...form, id_expiry_date: e.target.value })} />
          </div>
        </Section>

        <Section title="Contact">
          <div className="grid grid-cols-2 gap-3">
            <Input label="Téléphone" placeholder="+225 07 00 00 00 00" value={form.phone}
                   onChange={(e: any) => setForm({ ...form, phone: e.target.value })} />
            <Input label="Email" type="email" value={form.email}
                   onChange={(e: any) => setForm({ ...form, email: e.target.value })} />
            <Input label="Contact d'urgence (nom)" value={form.emergency_contact_name}
                   onChange={(e: any) => setForm({ ...form, emergency_contact_name: e.target.value })} />
            <Input label="Contact d'urgence (téléphone)" value={form.emergency_contact_phone}
                   onChange={(e: any) => setForm({ ...form, emergency_contact_phone: e.target.value })} />
            <Input label="Relation" placeholder="Épouse, frère, mère…" value={form.emergency_contact_relation}
                   onChange={(e: any) => setForm({ ...form, emergency_contact_relation: e.target.value })} />
          </div>
        </Section>

        <Section title="Métier & emploi">
          <div className="grid grid-cols-2 gap-3">
            <Select label="Métier" value={form.trade ? String(form.trade) : ""}
                    onChange={(v: string) => setForm({ ...form, trade: v ? Number(v) : "" })}
                    options={[{value:"",label:"— Sélectionner —"}, ...trades.map((t: any) => ({ value: String(t.id), label: t.name }))]} />
            <Select label="Sous-traitant" value={form.subcontractor ? String(form.subcontractor) : ""}
                    onChange={(v: string) => setForm({ ...form, subcontractor: v ? Number(v) : "" })}
                    options={[{value:"",label:"Interne KAYDAN"}, ...subs.map((s: any) => ({ value: String(s.id), label: s.name }))]} />
            <Select label="Taille casque" value={form.helmet_size} onChange={(v: string) => setForm({ ...form, helmet_size: v })}
                    options={[{value:"S",label:"S"},{value:"M",label:"M"},{value:"L",label:"L"},{value:"XL",label:"XL"}]} />
            <Input label="Date d'embauche" type="date" value={form.hired_at}
                   onChange={(e: any) => setForm({ ...form, hired_at: e.target.value })} />
            <Select label="Statut" value={form.status} onChange={(v: string) => setForm({ ...form, status: v })}
                    options={[{value:"active",label:"Actif"},{value:"suspended",label:"Suspendu"},{value:"blacklisted",label:"Liste rouge"},{value:"terminated",label:"Sorti"}]} />
          </div>
        </Section>
      </div>
    </Modal>
  );
}

function Section({ title, children }: { title: string; children: React.ReactNode }) {
  return (
    <div>
      <div className="text-xs uppercase tracking-wider text-ink-soft font-semibold mb-2">{title}</div>
      {children}
    </div>
  );
}
function Select({ label, value, onChange, options, error, required }: {
  label: string; value: string; onChange: (v: string) => void;
  options: { value: string; label: string }[];
  error?: string; required?: boolean;
}) {
  return (
    <label className="block">
      <span className="text-xs font-medium text-ink-muted flex items-center gap-0.5">
        {label}
        {required && <span className="text-danger">*</span>}
      </span>
      <select value={value} onChange={(e) => onChange(e.target.value)}
              className={`field w-full mt-1.5 ${error ? "border-danger/60" : ""}`}>
        {options.map((o) => <option key={o.value} value={o.value}>{o.label}</option>)}
      </select>
      {error && (
        <span className="text-xs text-danger mt-1 flex items-start gap-1">
          <span className="w-1 h-1 rounded-full bg-danger mt-1.5 shrink-0" />
          {error}
        </span>
      )}
    </label>
  );
}
// cleanForm remplacé par omitEmpty() de lib/formErrors — supprime toutes les clés
// vides plutôt que d'envoyer null (Django rejette null sur champs blank=True).
