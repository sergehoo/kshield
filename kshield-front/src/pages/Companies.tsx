import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { PageHeader } from "@/components/PageHeader";
import { Card } from "@/components/ui/Card";
import { DataTable, Column } from "@/components/ui/DataTable";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Modal } from "@/components/ui/Modal";
import { companiesService } from "@/services";
import { toApiError } from "@/lib/api";
import { fmtDate } from "@/lib/format";
import type { Company } from "@/types/api";
import { Plus, Building2, Search, Trash2 } from "lucide-react";
import toast from "react-hot-toast";

export function CompaniesPage() {
  const [q, setQ] = useState("");
  const [openNew, setOpenNew] = useState(false);
  const [form, setForm] = useState({ name: "", code: "", legal_form: "", ncc: "" });
  const qc = useQueryClient();

  const { data, isLoading } = useQuery({
    queryKey: ["companies", q],
    queryFn: async () =>
      (await companiesService.list({ page_size: 200, search: q || undefined })).data,
  });

  const createMut = useMutation({
    mutationFn: () => companiesService.create(form),
    onSuccess: () => {
      toast.success("Société créée");
      setOpenNew(false);
      setForm({ name: "", code: "", legal_form: "", ncc: "" });
      qc.invalidateQueries({ queryKey: ["companies"] });
    },
    onError: (e) => toast.error(toApiError(e).message),
  });

  const removeMut = useMutation({
    mutationFn: (id: number) => companiesService.remove(id),
    onSuccess: () => {
      toast.success("Supprimée");
      qc.invalidateQueries({ queryKey: ["companies"] });
    },
    onError: (e) => toast.error(toApiError(e).message),
  });

  const columns: Column<Company>[] = [
    {
      key: "name",
      header: "Société",
      render: (c) => (
        <div className="flex items-center gap-2.5">
          <div className="w-8 h-8 rounded-lg bg-info/10 text-info grid place-items-center">
            <Building2 className="w-4 h-4" />
          </div>
          <div>
            <div className="text-sm font-medium text-ink">{c.name}</div>
            {c.code && <div className="text-xs text-ink-soft font-mono">{c.code}</div>}
          </div>
        </div>
      ),
    },
    { key: "legal", header: "Forme juridique", render: (c) => c.legal_form || "—" },
    { key: "ncc", header: "N° CC", render: (c) => <span className="font-mono text-xs">{c.ncc || "—"}</span> },
    {
      key: "active",
      header: "Statut",
      render: (c) => (
        <Badge tone={c.is_active !== false ? "ok" : "muted"}>
          {c.is_active !== false ? "Active" : "Inactive"}
        </Badge>
      ),
    },
    { key: "created", header: "Créée le", render: (c) => fmtDate(c.created_at) },
    {
      key: "actions",
      header: "",
      className: "text-right",
      render: (c) => (
        <button
          onClick={() => {
            if (confirm(`Supprimer "${c.name}" ?`)) removeMut.mutate(c.id);
          }}
          className="p-1.5 rounded-md hover:bg-danger/10 text-ink-muted hover:text-danger"
        >
          <Trash2 className="w-3.5 h-3.5" />
        </button>
      ),
    },
  ];

  return (
    <div>
      <PageHeader
        title="Sociétés"
        subtitle={`${data?.count ?? 0} sociétés enregistrées`}
        actions={
          <Button leftIcon={<Plus className="w-4 h-4" />} onClick={() => setOpenNew(true)}>
            Nouvelle société
          </Button>
        }
      />

      <Card padded={false}>
        <div className="p-4 border-b border-surface-border">
          <Input
            placeholder="Rechercher…"
            leftIcon={<Search className="w-4 h-4" />}
            value={q}
            onChange={(e) => setQ(e.target.value)}
          />
        </div>
        <DataTable
          columns={columns}
          rows={data?.results || []}
          loading={isLoading}
          rowKey={(c) => c.id}
        />
      </Card>

      <Modal
        open={openNew}
        onClose={() => setOpenNew(false)}
        title="Nouvelle société"
        footer={
          <>
            <Button variant="ghost" onClick={() => setOpenNew(false)}>
              Annuler
            </Button>
            <Button
              onClick={() => form.name && createMut.mutate()}
              loading={createMut.isPending}
              disabled={!form.name}
            >
              Créer
            </Button>
          </>
        }
      >
        <div className="space-y-4">
          <Input
            label="Nom *"
            value={form.name}
            onChange={(e) => setForm({ ...form, name: e.target.value })}
          />
          <div className="grid grid-cols-2 gap-3">
            <Input
              label="Code"
              value={form.code}
              onChange={(e) => setForm({ ...form, code: e.target.value })}
            />
            <Input
              label="Forme juridique"
              placeholder="SARL, SA…"
              value={form.legal_form}
              onChange={(e) => setForm({ ...form, legal_form: e.target.value })}
            />
          </div>
          <Input
            label="Numéro de compte contribuable"
            value={form.ncc}
            onChange={(e) => setForm({ ...form, ncc: e.target.value })}
          />
        </div>
      </Modal>
    </div>
  );
}
