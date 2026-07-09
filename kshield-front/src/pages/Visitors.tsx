import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { PageHeader } from "@/components/PageHeader";
import { Card } from "@/components/ui/Card";
import { DataTable, Column } from "@/components/ui/DataTable";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Modal } from "@/components/ui/Modal";
import {
  visitorsService, visitPurposesService, watchlistsService, sitesService,
} from "@/services";
import { toApiError } from "@/lib/api";
import { fmtDateTime, initials, fmtRelative } from "@/lib/format";
import {
  Plus, Search, Edit3, Trash2, LogIn, LogOut, Shield, UserCheck, Mail, Phone,
} from "lucide-react";
import toast from "react-hot-toast";
import { cn } from "@/lib/cn";

type VisitorForm = {
  first_name: string;
  last_name: string;
  full_name: string;
  email: string;
  phone: string;
  company_name: string;
  id_type: string;
  id_number: string;
  purpose: number | "";
  purpose_label: string;
  host_email: string;
  host_name: string;
  reason: string;
  site: number | "";
};

const emptyForm: VisitorForm = {
  first_name: "",
  last_name: "",
  full_name: "",
  email: "",
  phone: "",
  company_name: "",
  id_type: "cni",
  id_number: "",
  purpose: "",
  purpose_label: "",
  host_email: "",
  host_name: "",
  reason: "",
  site: "",
};

export function VisitorsPage() {
  const [q, setQ] = useState("");
  const [statusFilter, setStatusFilter] = useState<string>("");
  const [page, setPage] = useState(1);
  const [modalOpen, setModalOpen] = useState(false);
  const [editId, setEditId] = useState<number | null>(null);
  const [form, setForm] = useState<VisitorForm>(emptyForm);
  const [watchlistTarget, setWatchlistTarget] = useState<any | null>(null);
  const [wlReason, setWlReason] = useState("");
  const [wlSeverity, setWlSeverity] = useState<"warn" | "block">("warn");

  const qc = useQueryClient();
  const pageSize = 30;

  // ─── Liste ──────────────────────────────────
  const { data, isLoading } = useQuery({
    queryKey: ["visitors", q, statusFilter, page],
    queryFn: async () => {
      const params: any = {
        page_size: pageSize,
        page,
        search: q || undefined,
        ordering: "-created_at",
      };
      // Filtre statut : sur site / sorti / enregistré
      if (statusFilter === "on_site") params.status = "on_site";
      else if (statusFilter === "checked_out") params.status = "checked_out";
      else if (statusFilter === "registered") params.status = "registered";
      return (await visitorsService.list(params)).data;
    },
  });

  const { data: purposes } = useQuery({
    queryKey: ["visit-purposes", "all"],
    queryFn: async () => (await visitPurposesService.list({ page_size: 100 })).data,
  });
  const { data: sites } = useQuery({
    queryKey: ["sites", "all-for-visitors"],
    queryFn: async () => (await sitesService.list({ page_size: 200 })).data,
  });

  // ─── Mutations ─────────────────────────────
  const createMut = useMutation({
    mutationFn: () => visitorsService.create(cleanForm(form)),
    onSuccess: () => {
      toast.success("Visiteur enregistré");
      closeModal();
      qc.invalidateQueries({ queryKey: ["visitors"] });
    },
    onError: (e) => toast.error(toApiError(e).message),
  });

  const updateMut = useMutation({
    mutationFn: () => {
      if (!editId) throw new Error("no id");
      return visitorsService.update(editId, cleanForm(form));
    },
    onSuccess: () => {
      toast.success("Visiteur modifié");
      closeModal();
      qc.invalidateQueries({ queryKey: ["visitors"] });
    },
    onError: (e) => toast.error(toApiError(e).message),
  });

  const deleteMut = useMutation({
    mutationFn: (id: number) => visitorsService.remove(id),
    onSuccess: () => {
      toast.success("Supprimé");
      qc.invalidateQueries({ queryKey: ["visitors"] });
    },
    onError: (e) => toast.error(toApiError(e).message),
  });

  const checkInMut = useMutation({
    mutationFn: (id: number) => visitorsService.checkIn(id),
    onSuccess: () => {
      toast.success("Visiteur enregistré à l'entrée");
      qc.invalidateQueries({ queryKey: ["visitors"] });
    },
    onError: (e) => toast.error(toApiError(e).message),
  });

  const checkOutMut = useMutation({
    mutationFn: (id: number) => visitorsService.checkOut(id),
    onSuccess: () => {
      toast.success("Visiteur sorti");
      qc.invalidateQueries({ queryKey: ["visitors"] });
    },
    onError: (e) => toast.error(toApiError(e).message),
  });

  const addToWatchlistMut = useMutation({
    mutationFn: () => {
      if (!watchlistTarget) throw new Error("no target");
      return watchlistsService.create({
        full_name: `${watchlistTarget.first_name || ""} ${watchlistTarget.last_name || watchlistTarget.full_name || ""}`.trim(),
        id_number: watchlistTarget.id_number,
        reason: wlReason,
        severity: wlSeverity,
      });
    },
    onSuccess: () => {
      toast.success("Ajouté à la liste rouge");
      setWatchlistTarget(null);
      setWlReason("");
    },
    onError: (e) => toast.error(toApiError(e).message),
  });

  const openCreate = () => {
    setEditId(null);
    setForm(emptyForm);
    setModalOpen(true);
  };
  const openEdit = (v: any) => {
    setEditId(v.id);
    setForm({
      first_name: v.first_name || "",
      last_name: v.last_name || "",
      full_name: v.full_name || "",
      email: v.email || "",
      phone: v.phone || "",
      company_name: v.company_name || v.company || "",
      id_type: v.id_type || "cni",
      id_number: v.id_number || "",
      purpose: typeof v.purpose === "object" ? v.purpose?.id : v.purpose || "",
      purpose_label: v.purpose_label || "",
      host_email: v.host_email || "",
      host_name: v.host_name || "",
      reason: v.reason || "",
      site: typeof v.site === "object" ? v.site?.id : v.site || "",
    });
    setModalOpen(true);
  };
  const closeModal = () => {
    setModalOpen(false);
    setEditId(null);
    setForm(emptyForm);
  };

  const onSubmit = () => {
    const name = form.full_name || `${form.first_name} ${form.last_name}`.trim();
    if (!name) {
      toast.error("Nom du visiteur obligatoire");
      return;
    }
    if (editId) updateMut.mutate();
    else createMut.mutate();
  };

  const statusOf = (v: any) => {
    if (v.checked_out_at) return { label: "Sorti", tone: "muted" as const };
    if (v.checked_in_at) return { label: "Sur site", tone: "ok" as const };
    return { label: "Enregistré", tone: "info" as const };
  };

  // ─── Colonnes tableau ──────────────────────
  const columns: Column<any>[] = [
    {
      key: "person",
      header: "Visiteur",
      render: (v) => {
        const displayName = v.full_name || `${v.first_name || ""} ${v.last_name || ""}`.trim();
        return (
          <div className="flex items-center gap-2.5">
            <div className="w-9 h-9 rounded-full bg-info/20 text-info grid place-items-center text-xs font-semibold">
              {initials(displayName)}
            </div>
            <div className="min-w-0">
              <div className="text-sm font-medium text-ink truncate">{displayName || "—"}</div>
              <div className="text-xs text-ink-soft truncate">
                {v.company_name || "—"}
              </div>
            </div>
          </div>
        );
      },
    },
    {
      key: "contact",
      header: "Contact",
      render: (v) => (
        <div className="text-xs space-y-0.5">
          {v.email && (
            <div className="flex items-center gap-1 text-ink">
              <Mail className="w-3 h-3 text-ink-soft" />
              <span className="truncate max-w-[180px]">{v.email}</span>
            </div>
          )}
          {v.phone && (
            <div className="flex items-center gap-1 text-ink-muted font-mono">
              <Phone className="w-3 h-3 text-ink-soft" />
              {v.phone}
            </div>
          )}
        </div>
      ),
    },
    { key: "reason", header: "Motif", render: (v) => v.purpose_label || v.reason || "—" },
    { key: "host", header: "Hôte", render: (v) => v.host_email || v.host_name || "—" },
    {
      key: "status",
      header: "Statut",
      render: (v) => {
        const s = statusOf(v);
        return (
          <div className="flex flex-col gap-0.5">
            <Badge tone={s.tone} dot>{s.label}</Badge>
            {v.checked_in_at && !v.checked_out_at && (
              <span className="text-[10px] text-ink-soft">
                Entrée {fmtRelative(v.checked_in_at)}
              </span>
            )}
            {v.checked_out_at && (
              <span className="text-[10px] text-ink-soft">
                Sortie {fmtRelative(v.checked_out_at)}
              </span>
            )}
          </div>
        );
      },
    },
    {
      key: "actions",
      header: "",
      className: "text-right whitespace-nowrap",
      render: (v) => (
        <div className="inline-flex items-center gap-0.5">
          {!v.checked_in_at && !v.checked_out_at && (
            <button
              onClick={(e) => {
                e.stopPropagation();
                checkInMut.mutate(v.id);
              }}
              className="p-1.5 rounded-md hover:bg-ok/10 text-ink-muted hover:text-ok"
              title="Enregistrer l'entrée"
            >
              <LogIn className="w-3.5 h-3.5" />
            </button>
          )}
          {v.checked_in_at && !v.checked_out_at && (
            <button
              onClick={(e) => {
                e.stopPropagation();
                checkOutMut.mutate(v.id);
              }}
              className="p-1.5 rounded-md hover:bg-danger/10 text-ink-muted hover:text-danger"
              title="Enregistrer la sortie"
            >
              <LogOut className="w-3.5 h-3.5" />
            </button>
          )}
          <button
            onClick={(e) => {
              e.stopPropagation();
              setWatchlistTarget(v);
              setWlReason("");
              setWlSeverity("warn");
            }}
            className="p-1.5 rounded-md hover:bg-warn/10 text-ink-muted hover:text-warn"
            title="Ajouter à la liste rouge"
          >
            <Shield className="w-3.5 h-3.5" />
          </button>
          <button
            onClick={(e) => {
              e.stopPropagation();
              openEdit(v);
            }}
            className="p-1.5 rounded-md hover:bg-surface-soft text-ink-muted hover:text-ink"
            title="Modifier"
          >
            <Edit3 className="w-3.5 h-3.5" />
          </button>
          <button
            onClick={(e) => {
              e.stopPropagation();
              const name = v.full_name || `${v.first_name} ${v.last_name}`;
              if (confirm(`Supprimer le visiteur ${name} ?`)) deleteMut.mutate(v.id);
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
        title="Visiteurs"
        subtitle={`${data?.count ?? 0} visiteurs enregistrés · workflow check-in / check-out`}
        actions={
          <Button leftIcon={<Plus className="w-4 h-4" />} onClick={openCreate}>
            Nouveau visiteur
          </Button>
        }
      />

      <Card padded={false}>
        <div className="p-4 border-b border-surface-border flex flex-col sm:flex-row gap-2">
          <div className="flex-1">
            <Input
              placeholder="Rechercher par nom, société, email…"
              leftIcon={<Search className="w-4 h-4" />}
              value={q}
              onChange={(e) => {
                setQ(e.target.value);
                setPage(1);
              }}
            />
          </div>
          <div className="inline-flex rounded-lg bg-surface-soft p-0.5 border border-surface-border">
            {(
              [
                { key: "", label: "Tous" },
                { key: "registered", label: "Enregistrés" },
                { key: "on_site", label: "Sur site" },
                { key: "checked_out", label: "Sortis" },
              ] as const
            ).map((f) => (
              <button
                key={f.key}
                onClick={() => {
                  setStatusFilter(f.key);
                  setPage(1);
                }}
                className={cn(
                  "px-3 py-1.5 rounded-md text-xs font-medium transition",
                  statusFilter === f.key
                    ? "bg-brand-500 text-white"
                    : "text-ink-muted hover:text-ink",
                )}
              >
                {f.label}
              </button>
            ))}
          </div>
        </div>
        <DataTable
          columns={columns}
          rows={data?.results || []}
          loading={isLoading}
          rowKey={(v) => v.id}
          emptyLabel="Aucun visiteur — cliquez sur 'Nouveau visiteur' pour commencer"
          emptyIcon={<UserCheck className="w-8 h-8 mx-auto text-ink-soft mb-2" />}
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
        title={editId ? "Modifier le visiteur" : "Nouveau visiteur"}
        size="lg"
        footer={
          <>
            <Button variant="ghost" onClick={closeModal}>Annuler</Button>
            <Button
              onClick={onSubmit}
              loading={createMut.isPending || updateMut.isPending}
              leftIcon={editId ? <Edit3 className="w-4 h-4" /> : <Plus className="w-4 h-4" />}
            >
              {editId ? "Enregistrer" : "Créer le visiteur"}
            </Button>
          </>
        }
      >
        <div className="space-y-5">
          {/* Identité */}
          <div>
            <div className="text-xs uppercase tracking-wider text-ink-soft font-semibold mb-2">
              Identité
            </div>
            <div className="grid grid-cols-2 gap-3">
              <Input
                label="Prénom"
                value={form.first_name}
                onChange={(e) => setForm({ ...form, first_name: e.target.value })}
              />
              <Input
                label="Nom"
                value={form.last_name}
                onChange={(e) => setForm({ ...form, last_name: e.target.value })}
              />
              <label className="block">
                <span className="text-xs font-medium text-ink-muted">Type de pièce</span>
                <select
                  value={form.id_type}
                  onChange={(e) => setForm({ ...form, id_type: e.target.value })}
                  className="field w-full mt-1.5"
                >
                  <option value="cni">CNI</option>
                  <option value="passport">Passeport</option>
                  <option value="driver_license">Permis</option>
                  <option value="other">Autre</option>
                </select>
              </label>
              <Input
                label="Numéro de pièce"
                value={form.id_number}
                onChange={(e) => setForm({ ...form, id_number: e.target.value })}
                placeholder="CNI-1234567"
              />
            </div>
          </div>

          {/* Contact & société */}
          <div>
            <div className="text-xs uppercase tracking-wider text-ink-soft font-semibold mb-2">
              Contact & entreprise
            </div>
            <div className="grid grid-cols-2 gap-3">
              <Input
                label="Email"
                type="email"
                value={form.email}
                onChange={(e) => setForm({ ...form, email: e.target.value })}
              />
              <Input
                label="Téléphone"
                value={form.phone}
                onChange={(e) => setForm({ ...form, phone: e.target.value })}
                placeholder="+225 07 00 00 00 00"
              />
              <Input
                label="Entreprise"
                value={form.company_name}
                onChange={(e) => setForm({ ...form, company_name: e.target.value })}
                placeholder="ETS Bâtir+"
              />
              <label className="block">
                <span className="text-xs font-medium text-ink-muted">Site visité</span>
                <select
                  value={form.site}
                  onChange={(e) => setForm({ ...form, site: e.target.value ? Number(e.target.value) : "" })}
                  className="field w-full mt-1.5"
                >
                  <option value="">— Sélectionner —</option>
                  {sites?.results?.map((s: any) => (
                    <option key={s.id} value={s.id}>{s.name}</option>
                  ))}
                </select>
              </label>
            </div>
          </div>

          {/* Visite */}
          <div>
            <div className="text-xs uppercase tracking-wider text-ink-soft font-semibold mb-2">
              Motif & hôte
            </div>
            <div className="grid grid-cols-2 gap-3">
              <label className="block">
                <span className="text-xs font-medium text-ink-muted">Motif</span>
                <select
                  value={form.purpose}
                  onChange={(e) => setForm({ ...form, purpose: e.target.value ? Number(e.target.value) : "" })}
                  className="field w-full mt-1.5"
                >
                  <option value="">— Sélectionner —</option>
                  {purposes?.results?.map((p: any) => (
                    <option key={p.id} value={p.id}>{p.label}</option>
                  ))}
                </select>
              </label>
              <Input
                label="Email de l'hôte"
                type="email"
                value={form.host_email}
                onChange={(e) => setForm({ ...form, host_email: e.target.value })}
                placeholder="prenom.nom@kaydangroupe.com"
              />
              <Input
                label="Nom de l'hôte"
                value={form.host_name}
                onChange={(e) => setForm({ ...form, host_name: e.target.value })}
              />
              <div />
              <label className="block col-span-2">
                <span className="text-xs font-medium text-ink-muted">Détails / notes</span>
                <textarea
                  rows={3}
                  value={form.reason}
                  onChange={(e) => setForm({ ...form, reason: e.target.value })}
                  className="field w-full mt-1.5"
                  placeholder="Livraison matériel, réunion projet X, audit HSE…"
                />
              </label>
            </div>
          </div>
        </div>
      </Modal>

      {/* ─── Modal Ajouter à Watchlist ─── */}
      <Modal
        open={!!watchlistTarget}
        onClose={() => setWatchlistTarget(null)}
        title="Ajouter à la liste rouge"
        footer={
          <>
            <Button variant="ghost" onClick={() => setWatchlistTarget(null)}>Annuler</Button>
            <Button
              variant="danger"
              onClick={() => wlReason && addToWatchlistMut.mutate()}
              loading={addToWatchlistMut.isPending}
              disabled={!wlReason}
              leftIcon={<Shield className="w-4 h-4" />}
            >
              Ajouter à la liste rouge
            </Button>
          </>
        }
      >
        <div className="space-y-3">
          <div className="p-3 rounded-lg bg-warn/10 border border-warn/20 text-xs text-ink">
            Vous êtes sur le point d'ajouter{" "}
            <strong>
              {watchlistTarget?.full_name ||
                `${watchlistTarget?.first_name || ""} ${watchlistTarget?.last_name || ""}`.trim()}
            </strong>{" "}
            à la liste rouge. Les prochaines tentatives d'accès de cette personne{" "}
            {wlSeverity === "block" ? "seront bloquées automatiquement" : "généreront une alerte"}.
          </div>
          <label className="block">
            <span className="text-xs font-medium text-ink-muted">Sévérité</span>
            <select
              value={wlSeverity}
              onChange={(e) => setWlSeverity(e.target.value as any)}
              className="field w-full mt-1.5"
            >
              <option value="warn">Alerter (autoriser mais notifier)</option>
              <option value="block">Bloquer (refuser l'accès)</option>
            </select>
          </label>
          <label className="block">
            <span className="text-xs font-medium text-ink-muted">Motif (obligatoire)</span>
            <textarea
              value={wlReason}
              onChange={(e) => setWlReason(e.target.value)}
              rows={3}
              className="field w-full mt-1.5"
              placeholder="Comportement inapproprié, incident du..., refus d'identification..."
            />
          </label>
        </div>
      </Modal>
    </div>
  );
}

function cleanForm(f: VisitorForm): any {
  const out: any = { ...f };
  if (out.purpose === "") delete out.purpose;
  if (out.site === "") delete out.site;
  // Compat back : si le back attend "full_name" ou "first_name/last_name" séparés
  if (!out.full_name && (out.first_name || out.last_name)) {
    out.full_name = `${out.first_name} ${out.last_name}`.trim();
  }
  Object.keys(out).forEach((k) => {
    if (out[k] === "") out[k] = null;
  });
  return out;
}
