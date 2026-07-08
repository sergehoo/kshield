import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { PageHeader } from "@/components/PageHeader";
import { Card } from "@/components/ui/Card";
import { DataTable, Column } from "@/components/ui/DataTable";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Modal } from "@/components/ui/Modal";
import { visitorsService } from "@/services";
import { toApiError } from "@/lib/api";
import { fmtDateTime, initials } from "@/lib/format";
import { Plus, Search, LogIn, LogOut, UserPlus } from "lucide-react";
import toast from "react-hot-toast";

export function VisitorsPage() {
  const [q, setQ] = useState("");
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({
    full_name: "",
    company_name: "",
    phone: "",
    reason: "",
    host_email: "",
  });
  const qc = useQueryClient();

  const { data, isLoading } = useQuery({
    queryKey: ["visitors", q],
    queryFn: async () =>
      (await visitorsService.list({ page_size: 200, search: q || undefined, ordering: "-created_at" })).data,
  });

  const createMut = useMutation({
    mutationFn: () => visitorsService.create(form),
    onSuccess: () => {
      toast.success("Visiteur enregistré");
      setOpen(false);
      setForm({ full_name: "", company_name: "", phone: "", reason: "", host_email: "" });
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

  const columns: Column<any>[] = [
    {
      key: "name",
      header: "Visiteur",
      render: (v) => (
        <div className="flex items-center gap-2.5">
          <div className="w-8 h-8 rounded-full bg-info/20 text-info grid place-items-center text-xs font-semibold">
            {initials(v.full_name)}
          </div>
          <div>
            <div className="text-sm font-medium text-ink">{v.full_name}</div>
            {v.company_name && (
              <div className="text-xs text-ink-soft">{v.company_name}</div>
            )}
          </div>
        </div>
      ),
    },
    { key: "reason", header: "Motif", render: (v) => v.reason || "—" },
    { key: "host", header: "Hôte", render: (v) => v.host_email || v.host_name || "—" },
    { key: "phone", header: "Téléphone", render: (v) => v.phone || "—" },
    {
      key: "status",
      header: "Statut",
      render: (v) => {
        if (v.checked_out_at)
          return <Badge tone="muted">Sorti — {fmtDateTime(v.checked_out_at)}</Badge>;
        if (v.checked_in_at)
          return <Badge tone="ok" dot>Sur site depuis {fmtDateTime(v.checked_in_at)}</Badge>;
        return <Badge tone="info">Enregistré</Badge>;
      },
    },
    {
      key: "actions",
      header: "",
      className: "text-right",
      render: (v) => (
        <div className="inline-flex gap-1">
          {!v.checked_in_at && (
            <button
              onClick={() => checkInMut.mutate(v.id)}
              className="p-1.5 rounded-md hover:bg-ok/10 text-ink-muted hover:text-ok"
              title="Check-in"
            >
              <LogIn className="w-3.5 h-3.5" />
            </button>
          )}
          {v.checked_in_at && !v.checked_out_at && (
            <button
              onClick={() => checkOutMut.mutate(v.id)}
              className="p-1.5 rounded-md hover:bg-danger/10 text-ink-muted hover:text-danger"
              title="Check-out"
            >
              <LogOut className="w-3.5 h-3.5" />
            </button>
          )}
        </div>
      ),
    },
  ];

  return (
    <div>
      <PageHeader
        title="Visiteurs"
        subtitle={`${data?.count ?? 0} visiteurs enregistrés`}
        actions={
          <Button leftIcon={<Plus className="w-4 h-4" />} onClick={() => setOpen(true)}>
            Nouveau visiteur
          </Button>
        }
      />

      <Card padded={false}>
        <div className="p-4 border-b border-surface-border">
          <Input
            placeholder="Rechercher un visiteur…"
            leftIcon={<Search className="w-4 h-4" />}
            value={q}
            onChange={(e) => setQ(e.target.value)}
          />
        </div>
        <DataTable
          columns={columns}
          rows={data?.results || []}
          loading={isLoading}
          rowKey={(v) => v.id}
        />
      </Card>

      <Modal
        open={open}
        onClose={() => setOpen(false)}
        title="Nouveau visiteur"
        size="md"
        footer={
          <>
            <Button variant="ghost" onClick={() => setOpen(false)}>Annuler</Button>
            <Button
              leftIcon={<UserPlus className="w-4 h-4" />}
              onClick={() => form.full_name && createMut.mutate()}
              loading={createMut.isPending}
              disabled={!form.full_name}
            >
              Enregistrer
            </Button>
          </>
        }
      >
        <div className="space-y-3">
          <Input
            label="Nom complet *"
            value={form.full_name}
            onChange={(e) => setForm({ ...form, full_name: e.target.value })}
            required
          />
          <div className="grid grid-cols-2 gap-3">
            <Input
              label="Entreprise"
              value={form.company_name}
              onChange={(e) => setForm({ ...form, company_name: e.target.value })}
            />
            <Input
              label="Téléphone"
              value={form.phone}
              onChange={(e) => setForm({ ...form, phone: e.target.value })}
            />
          </div>
          <Input
            label="Motif de la visite"
            value={form.reason}
            onChange={(e) => setForm({ ...form, reason: e.target.value })}
          />
          <Input
            label="Email de l'hôte"
            type="email"
            value={form.host_email}
            onChange={(e) => setForm({ ...form, host_email: e.target.value })}
            placeholder="prenom.nom@kaydangroupe.com"
          />
        </div>
      </Modal>
    </div>
  );
}
