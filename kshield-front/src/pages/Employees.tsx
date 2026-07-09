import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { PageHeader } from "@/components/PageHeader";
import { Card } from "@/components/ui/Card";
import { DataTable, Column } from "@/components/ui/DataTable";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Modal } from "@/components/ui/Modal";
import { employeesService, companiesService } from "@/services";
import { toApiError } from "@/lib/api";
import { parseApiErrors, omitEmpty, FieldErrors } from "@/lib/formErrors";
import { FormErrorBanner } from "@/components/FormErrorBanner";
import { fmtDate, initials } from "@/lib/format";
import { Plus, Search, Edit3, Trash2, Users, Mail, Phone, Briefcase } from "lucide-react";
import toast from "react-hot-toast";

type EmployeeForm = {
  matricule: string;
  first_name: string;
  last_name: string;
  email: string;
  phone: string;
  company: number | "";
  department: string;
  job_title: string;
  contract_type: string;
  work_location: string;
  status: string;
  hired_at: string;
};

const emptyForm: EmployeeForm = {
  matricule: "",
  first_name: "",
  last_name: "",
  email: "",
  phone: "",
  company: "",
  department: "",
  job_title: "",
  contract_type: "cdi",
  work_location: "office",
  status: "active",
  hired_at: "",
};

export function EmployeesPage() {
  const [q, setQ] = useState("");
  const [statusFilter, setStatusFilter] = useState<string>("");
  const [companyFilter, setCompanyFilter] = useState<number | "">("");
  const [page, setPage] = useState(1);
  const [modalOpen, setModalOpen] = useState(false);
  const [editId, setEditId] = useState<number | null>(null);
  const [form, setForm] = useState<EmployeeForm>(emptyForm);
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({});
  const [globalError, setGlobalError] = useState<string>("");

  const navigate = useNavigate();
  const qc = useQueryClient();
  const pageSize = 30;

  // ─── Liste ──────────────────────────────────
  const { data, isLoading } = useQuery({
    queryKey: ["employees", q, statusFilter, companyFilter, page],
    queryFn: async () =>
      (
        await employeesService.list({
          page_size: pageSize,
          page,
          search: q || undefined,
          status: statusFilter || undefined,
          company: companyFilter || undefined,
        })
      ).data,
  });

  // ─── Sociétés (pour le filtre + select modal) ──
  const { data: companies } = useQuery({
    queryKey: ["companies", "all-for-emp"],
    queryFn: async () => (await companiesService.list({ page_size: 200 })).data,
  });

  // ─── Mutations ─────────────────────────────
  const handleApiError = (e: unknown) => {
    const parsed = parseApiErrors(e);
    setFieldErrors(parsed.fieldErrors);
    setGlobalError(parsed.globalMessage);
    const nb = Object.keys(parsed.fieldErrors).length;
    toast.error(nb > 0 ? `${nb} champ(s) à corriger` : parsed.globalMessage);
  };

  const createMut = useMutation({
    mutationFn: () => employeesService.create(omitEmpty(form)),
    onSuccess: () => {
      toast.success("Employé créé");
      closeModal();
      qc.invalidateQueries({ queryKey: ["employees"] });
    },
    onError: handleApiError,
  });

  const updateMut = useMutation({
    mutationFn: () => {
      if (!editId) throw new Error("no id");
      return employeesService.update(editId, omitEmpty(form));
    },
    onSuccess: () => {
      toast.success("Employé modifié");
      closeModal();
      qc.invalidateQueries({ queryKey: ["employees"] });
    },
    onError: handleApiError,
  });

  const deleteMut = useMutation({
    mutationFn: (id: number) => employeesService.remove(id),
    onSuccess: () => {
      toast.success("Supprimé");
      qc.invalidateQueries({ queryKey: ["employees"] });
    },
    onError: (e) => toast.error(toApiError(e).message),
  });

  // ─── Ouverture modal ────────────────────────
  const openCreate = () => {
    setEditId(null);
    setForm(emptyForm);
    setFieldErrors({}); setGlobalError("");
    setModalOpen(true);
  };
  const openEdit = (e: any) => {
    setEditId(e.id);
    setForm({
      matricule: e.matricule || "",
      first_name: e.first_name || "",
      last_name: e.last_name || "",
      email: e.email || "",
      phone: e.phone || "",
      company: typeof e.company === "object" ? e.company?.id : e.company || "",
      department: typeof e.department === "object" ? e.department?.name : "",
      job_title: e.job_title || "",
      contract_type: e.contract_type || "cdi",
      work_location: e.work_location || "office",
      status: e.status || "active",
      hired_at: e.hired_at || "",
    });
    setFieldErrors({}); setGlobalError("");
    setModalOpen(true);
  };
  const closeModal = () => {
    setModalOpen(false);
    setEditId(null);
    setForm(emptyForm);
    setFieldErrors({}); setGlobalError("");
  };

  const onSubmit = () => {
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
    if (editId) updateMut.mutate();
    else createMut.mutate();
  };

  // ─── Colonnes tableau ──────────────────────
  const columns: Column<any>[] = [
    {
      key: "person",
      header: "Employé",
      render: (e) => (
        <div className="flex items-center gap-2.5">
          {e.photo ? (
            <img src={e.photo} alt="" className="w-9 h-9 rounded-full object-cover border border-surface-border" />
          ) : (
            <div className="w-9 h-9 rounded-full bg-brand-500/20 text-brand-400 grid place-items-center text-xs font-semibold">
              {initials(`${e.first_name} ${e.last_name}`)}
            </div>
          )}
          <div className="min-w-0">
            <div className="text-sm font-medium text-ink truncate">
              {e.first_name} {e.last_name}
            </div>
            <div className="text-xs text-ink-soft font-mono">{e.matricule || "—"}</div>
          </div>
        </div>
      ),
    },
    {
      key: "contact",
      header: "Contact",
      render: (e) => (
        <div className="text-xs space-y-0.5">
          {e.email && (
            <div className="flex items-center gap-1 text-ink">
              <Mail className="w-3 h-3 text-ink-soft" />
              <span className="truncate max-w-[180px]">{e.email}</span>
            </div>
          )}
          {e.phone && (
            <div className="flex items-center gap-1 text-ink-muted font-mono">
              <Phone className="w-3 h-3 text-ink-soft" />
              {e.phone}
            </div>
          )}
        </div>
      ),
    },
    {
      key: "job",
      header: "Poste",
      render: (e) => (
        <div className="text-xs">
          <div className="text-ink flex items-center gap-1">
            <Briefcase className="w-3 h-3 text-ink-soft" />
            {e.job_title || "—"}
          </div>
          {e.department && (
            <div className="text-ink-soft mt-0.5">
              {typeof e.department === "object" ? e.department.name : e.department}
            </div>
          )}
        </div>
      ),
    },
    {
      key: "company",
      header: "Filiale",
      render: (e) => (typeof e.company === "object" ? e.company?.name : e.company ? `#${e.company}` : "—"),
    },
    {
      key: "contract",
      header: "Contrat",
      render: (e) => <Badge tone="info">{(e.contract_type || "").toUpperCase()}</Badge>,
    },
    {
      key: "status",
      header: "Statut",
      render: (e) => (
        <Badge
          tone={
            e.status === "active" ? "ok" :
            e.status === "on_leave" ? "warn" :
            e.status === "suspended" ? "danger" : "muted"
          }
          dot
        >
          {e.status || "actif"}
        </Badge>
      ),
    },
    {
      key: "actions",
      header: "",
      className: "text-right whitespace-nowrap",
      render: (e) => (
        <div className="inline-flex items-center gap-1">
          <button
            onClick={(ev) => {
              ev.stopPropagation();
              openEdit(e);
            }}
            className="p-1.5 rounded-md hover:bg-surface-soft text-ink-muted hover:text-ink"
            title="Modifier"
          >
            <Edit3 className="w-3.5 h-3.5" />
          </button>
          <button
            onClick={(ev) => {
              ev.stopPropagation();
              if (confirm(`Supprimer ${e.first_name} ${e.last_name} ?`)) deleteMut.mutate(e.id);
            }}
            className="p-1.5 rounded-md hover:bg-danger/10 text-ink-muted hover:text-danger"
            title="Supprimer"
          >
            <Trash2 className="w-3.5 h-3.5" />
          </button>
        </div>
      ),
    },
  ];

  return (
    <div>
      <PageHeader
        title="Employés"
        subtitle={`${data?.count ?? 0} employés enregistrés`}
        actions={
          <Button leftIcon={<Plus className="w-4 h-4" />} onClick={openCreate}>
            Nouvel employé
          </Button>
        }
      />

      <Card padded={false}>
        <div className="p-4 border-b border-surface-border flex flex-col sm:flex-row gap-2">
          <div className="flex-1">
            <Input
              placeholder="Rechercher par nom, matricule, email…"
              leftIcon={<Search className="w-4 h-4" />}
              value={q}
              onChange={(e) => {
                setQ(e.target.value);
                setPage(1);
              }}
            />
          </div>
          <select
            value={companyFilter}
            onChange={(e) => {
              setCompanyFilter(e.target.value ? Number(e.target.value) : "");
              setPage(1);
            }}
            className="field sm:w-48"
          >
            <option value="">Toutes filiales</option>
            {companies?.results?.map((c: any) => (
              <option key={c.id} value={c.id}>
                {c.name}
              </option>
            ))}
          </select>
          <select
            value={statusFilter}
            onChange={(e) => {
              setStatusFilter(e.target.value);
              setPage(1);
            }}
            className="field sm:w-40"
          >
            <option value="">Tous statuts</option>
            <option value="active">Actifs</option>
            <option value="on_leave">En congé</option>
            <option value="suspended">Suspendus</option>
            <option value="terminated">Sortis</option>
          </select>
        </div>
        <DataTable
          columns={columns}
          rows={data?.results || []}
          loading={isLoading}
          rowKey={(e) => e.id}
          onRowClick={(e) => navigate(`/employees/${e.id}`)}
          emptyLabel="Aucun employé — cliquez sur 'Nouvel employé' pour commencer"
          emptyIcon={<Users className="w-8 h-8 mx-auto text-ink-soft mb-2" />}
          pagination={{
            count: data?.count ?? 0,
            pageSize,
            page,
            onPageChange: setPage,
          }}
        />
      </Card>

      {/* ─── Modal Create/Edit ─── */}
      <Modal
        open={modalOpen}
        onClose={closeModal}
        title={editId ? "Modifier l'employé" : "Nouvel employé"}
        size="lg"
        footer={
          <>
            <Button variant="ghost" onClick={closeModal}>Annuler</Button>
            <Button
              onClick={onSubmit}
              loading={createMut.isPending || updateMut.isPending}
            >
              {editId ? "Enregistrer" : "Créer l'employé"}
            </Button>
          </>
        }
      >
        <div className="space-y-5">
          <FormErrorBanner message={globalError} fieldErrors={fieldErrors} />
          <p className="text-[11px] text-ink-soft">
            Les champs marqués <span className="text-danger">*</span> sont obligatoires.
          </p>

          {/* Section identité */}
          <div>
            <div className="text-xs uppercase tracking-wider text-ink-soft font-semibold mb-2">
              Identité
            </div>
            <div className="grid grid-cols-2 gap-3">
              <Input
                label="Matricule" requiredMark
                placeholder="EMP-001"
                value={form.matricule}
                onChange={(e) => setForm({ ...form, matricule: e.target.value })}
                error={fieldErrors.matricule}
              />
              <div />
              <Input
                label="Prénom" requiredMark
                value={form.first_name}
                onChange={(e) => setForm({ ...form, first_name: e.target.value })}
                error={fieldErrors.first_name}
              />
              <Input
                label="Nom" requiredMark
                value={form.last_name}
                onChange={(e) => setForm({ ...form, last_name: e.target.value })}
                error={fieldErrors.last_name}
              />
            </div>
          </div>

          {/* Section contact */}
          <div>
            <div className="text-xs uppercase tracking-wider text-ink-soft font-semibold mb-2">
              Contact
            </div>
            <div className="grid grid-cols-2 gap-3">
              <Input
                label="Email"
                type="email"
                value={form.email}
                onChange={(e) => setForm({ ...form, email: e.target.value })}
                error={fieldErrors.email}
              />
              <Input
                label="Téléphone"
                value={form.phone}
                onChange={(e) => setForm({ ...form, phone: e.target.value })}
                placeholder="+225 07 00 00 00 00"
                error={fieldErrors.phone}
              />
            </div>
          </div>

          {/* Section pro */}
          <div>
            <div className="text-xs uppercase tracking-wider text-ink-soft font-semibold mb-2">
              Poste & rattachement
            </div>
            <div className="grid grid-cols-2 gap-3">
              <label className="block">
                <span className="text-xs font-medium text-ink-muted">Filiale</span>
                <select
                  value={form.company}
                  onChange={(e) => setForm({ ...form, company: e.target.value ? Number(e.target.value) : "" })}
                  className="field w-full mt-1.5"
                >
                  <option value="">— Sélectionner —</option>
                  {companies?.results?.map((c: any) => (
                    <option key={c.id} value={c.id}>{c.name}</option>
                  ))}
                </select>
              </label>
              <Input
                label="Département"
                value={form.department}
                onChange={(e) => setForm({ ...form, department: e.target.value })}
                placeholder="RH, Finance, Tech…"
              />
              <Input
                label="Poste"
                value={form.job_title}
                onChange={(e) => setForm({ ...form, job_title: e.target.value })}
                placeholder="Chef de projet, Comptable…"
              />
              <label className="block">
                <span className="text-xs font-medium text-ink-muted">Type de contrat</span>
                <select
                  value={form.contract_type}
                  onChange={(e) => setForm({ ...form, contract_type: e.target.value })}
                  className="field w-full mt-1.5"
                >
                  <option value="cdi">CDI</option>
                  <option value="cdd">CDD</option>
                  <option value="internship">Stage</option>
                  <option value="freelance">Indépendant</option>
                  <option value="temp">Intérim</option>
                </select>
              </label>
              <label className="block">
                <span className="text-xs font-medium text-ink-muted">Lieu de travail</span>
                <select
                  value={form.work_location}
                  onChange={(e) => setForm({ ...form, work_location: e.target.value })}
                  className="field w-full mt-1.5"
                >
                  <option value="office">Bureau (badge seul)</option>
                  <option value="field">Chantier (badge + casque)</option>
                  <option value="both">Bureau + chantiers</option>
                </select>
              </label>
              <Input
                label="Date d'embauche"
                type="date"
                value={form.hired_at}
                onChange={(e) => setForm({ ...form, hired_at: e.target.value })}
              />
            </div>
          </div>

          {/* Statut */}
          <label className="block">
            <span className="text-xs font-medium text-ink-muted">Statut</span>
            <select
              value={form.status}
              onChange={(e) => setForm({ ...form, status: e.target.value })}
              className="field w-full mt-1.5"
            >
              <option value="active">Actif</option>
              <option value="on_leave">En congé</option>
              <option value="suspended">Suspendu</option>
              <option value="terminated">Sorti</option>
            </select>
          </label>
        </div>
      </Modal>
    </div>
  );
}

// cleanForm remplacé par omitEmpty() de lib/formErrors — supprime toutes les clés
// vides plutôt que d'envoyer null (Django rejette null sur champs blank=True).
