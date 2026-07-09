import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { PageHeader } from "@/components/PageHeader";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Modal } from "@/components/ui/Modal";
import { DataTable, Column } from "@/components/ui/DataTable";
import { Plus, Search, Trash2, Edit3 } from "lucide-react";
import { toApiError } from "@/lib/api";
import toast from "react-hot-toast";

export type FieldSpec = {
  key: string;
  label: string;
  type?: "text" | "email" | "number" | "date" | "textarea" | "select" | "checkbox" | "url";
  required?: boolean;
  hint?: string;
  placeholder?: string;
  options?: { value: string | number; label: string }[]; // pour select
  span?: 1 | 2; // colspan dans la grille (1 par défaut, 2 = full width)
};

export type CrudService = {
  list: (params?: any) => Promise<{ data: any }>;
  create: (body: any) => Promise<{ data: any }>;
  update?: (id: any, body: any) => Promise<{ data: any }>;
  remove?: (id: any) => Promise<any>;
};

type Props = {
  /** Titre de la page (ex: "Sous-traitants") */
  title: string;
  subtitle?: string;
  /** Service CRUD (des services/index.ts) */
  service: CrudService;
  /** Colonnes du tableau */
  columns: Column<any>[];
  /** Spec des champs du formulaire modal */
  fields: FieldSpec[];
  /** Query key pour TanStack Query */
  queryKey: string;
  /** Placeholder de la recherche */
  searchPlaceholder?: string;
  /** Fonction rowKey — par défaut row.id */
  rowKey?: (row: any) => string | number;
  /** Callback clic sur ligne — override */
  onRowClick?: (row: any) => void;
  /** Champs par défaut d'un nouveau (pré-remplis à l'ouverture du modal) */
  defaultValues?: Record<string, any>;
  /** Empty state label custom */
  emptyLabel?: string;
  /** Label bouton "Nouveau" custom */
  createLabel?: string;
  /** Actions custom (rendues à droite du header) */
  extraActions?: React.ReactNode;
  /** Filtres additionnels rendus à côté de la barre de recherche */
  extraFilters?: React.ReactNode;
  /** Extra params passés à la liste (ex. status, ordering) */
  extraListParams?: Record<string, any>;
  /** Actions par ligne — rendues dans la colonne actions */
  rowActions?: (row: any) => React.ReactNode;
  /** Cacher la colonne actions (delete/edit) par défaut */
  hideDefaultActions?: boolean;
  /** Bande de stats rendue au-dessus du tableau (utiliser <StatsRow stats={...} />) */
  stats?: React.ReactNode;
};

/**
 * Composant CRUD générique — génère list + modal create/edit + delete.
 *
 * Usage minimal :
 *   <CrudPage
 *     title="Sous-traitants"
 *     service={subcontractorsService}
 *     queryKey="subcontractors"
 *     columns={[{ key: "name", header: "Nom", render: r => r.name }]}
 *     fields={[{ key: "name", label: "Nom", required: true }]}
 *   />
 */
export function CrudPage({
  title,
  subtitle,
  service,
  columns,
  fields,
  queryKey,
  searchPlaceholder = "Rechercher…",
  rowKey = (r) => r.id,
  onRowClick,
  defaultValues = {},
  emptyLabel,
  createLabel = "Nouveau",
  extraActions,
  extraFilters,
  extraListParams,
  rowActions,
  hideDefaultActions = false,
  stats,
}: Props) {
  const [q, setQ] = useState("");
  const [page, setPage] = useState(1);
  const [modalOpen, setModalOpen] = useState(false);
  const [editRow, setEditRow] = useState<any | null>(null);
  const [form, setForm] = useState<Record<string, any>>(defaultValues);
  const qc = useQueryClient();
  const pageSize = 30;

  const { data, isLoading } = useQuery({
    queryKey: [queryKey, q, page, JSON.stringify(extraListParams || {})],
    queryFn: async () =>
      (
        await service.list({
          page_size: pageSize,
          page,
          search: q || undefined,
          ...(extraListParams || {}),
        })
      ).data,
  });

  const createMut = useMutation({
    mutationFn: () => service.create(form),
    onSuccess: () => {
      toast.success("Créé");
      setModalOpen(false);
      setForm(defaultValues);
      qc.invalidateQueries({ queryKey: [queryKey] });
    },
    onError: (e) => toast.error(toApiError(e).message),
  });

  const updateMut = useMutation({
    mutationFn: () => {
      if (!editRow || !service.update) throw new Error("Update non supporté");
      return service.update(editRow.id, form);
    },
    onSuccess: () => {
      toast.success("Modifié");
      setModalOpen(false);
      setEditRow(null);
      setForm(defaultValues);
      qc.invalidateQueries({ queryKey: [queryKey] });
    },
    onError: (e) => toast.error(toApiError(e).message),
  });

  const removeMut = useMutation({
    mutationFn: (id: any) => {
      if (!service.remove) throw new Error("Remove non supporté");
      return service.remove(id);
    },
    onSuccess: () => {
      toast.success("Supprimé");
      qc.invalidateQueries({ queryKey: [queryKey] });
    },
    onError: (e) => toast.error(toApiError(e).message),
  });

  const openCreate = () => {
    setEditRow(null);
    setForm({ ...defaultValues });
    setModalOpen(true);
  };
  const openEdit = (row: any) => {
    setEditRow(row);
    // Copie uniquement les champs déclarés dans fields (évite les propriétés lues seules)
    const initial: Record<string, any> = {};
    fields.forEach((f) => {
      const v = row[f.key];
      initial[f.key] = v !== undefined && v !== null ? v : (defaultValues[f.key] ?? "");
    });
    setForm(initial);
    setModalOpen(true);
  };

  const submit = () => {
    // Validation basique required
    const missing = fields
      .filter((f) => f.required)
      .filter((f) => !form[f.key] && form[f.key] !== 0 && form[f.key] !== false);
    if (missing.length > 0) {
      toast.error(`Champ requis : ${missing.map((f) => f.label).join(", ")}`);
      return;
    }
    if (editRow) updateMut.mutate();
    else createMut.mutate();
  };

  // Actions par ligne : combine extra + edit + delete (si supportés)
  const allColumns: Column<any>[] = [
    ...columns,
    ...(hideDefaultActions
      ? []
      : [
          {
            key: "__actions",
            header: "",
            className: "text-right whitespace-nowrap",
            render: (row: any) => (
              <div className="inline-flex items-center gap-1">
                {rowActions?.(row)}
                {service.update && (
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      openEdit(row);
                    }}
                    className="p-1.5 rounded-md hover:bg-surface-soft text-ink-muted hover:text-ink"
                    title="Modifier"
                  >
                    <Edit3 className="w-3.5 h-3.5" />
                  </button>
                )}
                {service.remove && (
                  <button
                    onClick={(e) => {
                      e.stopPropagation();
                      if (confirm(`Supprimer cet élément ?`)) removeMut.mutate(row.id);
                    }}
                    className="p-1.5 rounded-md hover:bg-danger/10 text-ink-muted hover:text-danger"
                    title="Supprimer"
                  >
                    <Trash2 className="w-3.5 h-3.5" />
                  </button>
                )}
              </div>
            ),
          },
        ]),
  ];

  return (
    <div>
      <PageHeader
        title={title}
        subtitle={subtitle || `${data?.count ?? 0} éléments`}
        actions={
          <div className="flex items-center gap-2">
            {extraActions}
            <Button leftIcon={<Plus className="w-4 h-4" />} onClick={openCreate}>
              {createLabel}
            </Button>
          </div>
        }
      />

      {stats}

      <Card padded={false}>
        <div className="p-4 border-b border-surface-border flex flex-col sm:flex-row gap-2">
          <div className="flex-1">
            <Input
              placeholder={searchPlaceholder}
              leftIcon={<Search className="w-4 h-4" />}
              value={q}
              onChange={(e) => {
                setQ(e.target.value);
                setPage(1);
              }}
            />
          </div>
          {extraFilters}
        </div>
        <DataTable
          columns={allColumns}
          rows={data?.results || []}
          loading={isLoading}
          rowKey={rowKey}
          onRowClick={onRowClick}
          emptyLabel={emptyLabel || "Aucun élément"}
          pagination={{
            count: data?.count ?? 0,
            pageSize,
            page,
            onPageChange: setPage,
          }}
        />
      </Card>

      {/* Modal Create/Edit */}
      <Modal
        open={modalOpen}
        onClose={() => setModalOpen(false)}
        title={editRow ? `Modifier` : `${createLabel}`}
        size={fields.length > 6 ? "lg" : "md"}
        footer={
          <>
            <Button variant="ghost" onClick={() => setModalOpen(false)}>
              Annuler
            </Button>
            <Button
              onClick={submit}
              loading={createMut.isPending || updateMut.isPending}
            >
              {editRow ? "Enregistrer" : "Créer"}
            </Button>
          </>
        }
      >
        <div className={fields.length > 3 ? "grid grid-cols-1 sm:grid-cols-2 gap-3" : "space-y-3"}>
          {fields.map((f) => (
            <FieldInput
              key={f.key}
              field={f}
              value={form[f.key]}
              onChange={(v) => setForm({ ...form, [f.key]: v })}
              span={f.span || 1}
            />
          ))}
        </div>
      </Modal>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────
// Champ de formulaire dynamique
// ─────────────────────────────────────────────────────────────
function FieldInput({
  field,
  value,
  onChange,
  span,
}: {
  field: FieldSpec;
  value: any;
  onChange: (v: any) => void;
  span: number;
}) {
  const wrapper = span === 2 ? "sm:col-span-2" : "";
  const label = (
    <span className="text-xs font-medium text-ink-muted">
      {field.label}
      {field.required && <span className="text-danger ml-0.5">*</span>}
    </span>
  );

  if (field.type === "textarea") {
    return (
      <label className={`block ${wrapper}`}>
        {label}
        <textarea
          rows={4}
          className="field w-full mt-1.5"
          value={value ?? ""}
          onChange={(e) => onChange(e.target.value)}
          placeholder={field.placeholder}
        />
        {field.hint && <span className="text-[11px] text-ink-soft mt-1 block">{field.hint}</span>}
      </label>
    );
  }
  if (field.type === "select") {
    return (
      <label className={`block ${wrapper}`}>
        {label}
        <select
          className="field w-full mt-1.5"
          value={value ?? ""}
          onChange={(e) => onChange(e.target.value)}
        >
          <option value="">— Sélectionner —</option>
          {field.options?.map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </select>
        {field.hint && <span className="text-[11px] text-ink-soft mt-1 block">{field.hint}</span>}
      </label>
    );
  }
  if (field.type === "checkbox") {
    return (
      <label className={`flex items-center gap-2 ${wrapper}`}>
        <input
          type="checkbox"
          checked={!!value}
          onChange={(e) => onChange(e.target.checked)}
          className="w-4 h-4 accent-brand-500"
        />
        <span className="text-sm text-ink">{field.label}</span>
      </label>
    );
  }

  return (
    <label className={`block ${wrapper}`}>
      {label}
      <input
        type={field.type || "text"}
        className="field w-full mt-1.5"
        value={value ?? ""}
        onChange={(e) => onChange(e.target.value)}
        placeholder={field.placeholder}
      />
      {field.hint && <span className="text-[11px] text-ink-soft mt-1 block">{field.hint}</span>}
    </label>
  );
}
