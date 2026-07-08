import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { PageHeader } from "@/components/PageHeader";
import { Card } from "@/components/ui/Card";
import { DataTable, Column } from "@/components/ui/DataTable";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Modal } from "@/components/ui/Modal";
import { sitesService } from "@/services";
import { toApiError } from "@/lib/api";
import { fmtDate } from "@/lib/format";
import type { Site } from "@/types/api";
import { Plus, MapPin, Search, Trash2 } from "lucide-react";
import toast from "react-hot-toast";

export function SitesPage() {
  const [q, setQ] = useState("");
  const [openNew, setOpenNew] = useState(false);
  const [name, setName] = useState("");
  const [code, setCode] = useState("");
  const [address, setAddress] = useState("");
  const qc = useQueryClient();

  const { data, isLoading } = useQuery({
    queryKey: ["sites", q],
    queryFn: async () =>
      (await sitesService.list({ page_size: 200, search: q || undefined })).data,
  });

  const createMut = useMutation({
    mutationFn: () => sitesService.create({ name, code, address }),
    onSuccess: () => {
      toast.success("Site créé");
      setOpenNew(false);
      setName("");
      setCode("");
      setAddress("");
      qc.invalidateQueries({ queryKey: ["sites"] });
    },
    onError: (e) => toast.error(toApiError(e).message),
  });

  const removeMut = useMutation({
    mutationFn: (id: number) => sitesService.remove(id),
    onSuccess: () => {
      toast.success("Site supprimé");
      qc.invalidateQueries({ queryKey: ["sites"] });
    },
    onError: (e) => toast.error(toApiError(e).message),
  });

  const columns: Column<Site>[] = [
    {
      key: "name",
      header: "Nom",
      render: (s) => (
        <div className="flex items-center gap-2.5">
          <div className="w-8 h-8 rounded-lg bg-brand-500/10 text-brand-400 grid place-items-center">
            <MapPin className="w-4 h-4" />
          </div>
          <div>
            <div className="text-sm font-medium text-ink">{s.name}</div>
            {s.code && <div className="text-xs text-ink-soft font-mono">{s.code}</div>}
          </div>
        </div>
      ),
    },
    {
      key: "address",
      header: "Adresse",
      render: (s) => <span className="text-sm text-ink-muted">{s.address || "—"}</span>,
    },
    {
      key: "company",
      header: "Société",
      render: (s) =>
        typeof s.company === "object" ? s.company?.name : s.company ? `#${s.company}` : "—",
    },
    {
      key: "active",
      header: "Statut",
      render: (s) => (
        <Badge tone={s.is_active !== false ? "ok" : "muted"}>
          {s.is_active !== false ? "Actif" : "Inactif"}
        </Badge>
      ),
    },
    {
      key: "created",
      header: "Créé le",
      render: (s) => <span className="text-xs text-ink-muted">{fmtDate(s.created_at)}</span>,
    },
    {
      key: "actions",
      header: "",
      className: "text-right",
      render: (s) => (
        <button
          onClick={() => {
            if (confirm(`Supprimer le site "${s.name}" ?`)) removeMut.mutate(s.id);
          }}
          className="p-1.5 rounded-md hover:bg-danger/10 text-ink-muted hover:text-danger"
          title="Supprimer"
        >
          <Trash2 className="w-3.5 h-3.5" />
        </button>
      ),
    },
  ];

  return (
    <div>
      <PageHeader
        title="Sites / Chantiers"
        subtitle={`${data?.count ?? 0} sites enregistrés`}
        actions={
          <Button leftIcon={<Plus className="w-4 h-4" />} onClick={() => setOpenNew(true)}>
            Nouveau site
          </Button>
        }
      />

      <Card padded={false}>
        <div className="p-4 border-b border-surface-border">
          <Input
            placeholder="Rechercher un site…"
            leftIcon={<Search className="w-4 h-4" />}
            value={q}
            onChange={(e) => setQ(e.target.value)}
          />
        </div>
        <DataTable
          columns={columns}
          rows={data?.results || []}
          loading={isLoading}
          rowKey={(s) => s.id}
          emptyLabel="Aucun site — cliquez sur 'Nouveau site' pour commencer"
        />
      </Card>

      <Modal
        open={openNew}
        onClose={() => setOpenNew(false)}
        title="Nouveau site"
        footer={
          <>
            <Button variant="ghost" onClick={() => setOpenNew(false)}>
              Annuler
            </Button>
            <Button
              onClick={() => name && createMut.mutate()}
              loading={createMut.isPending}
              disabled={!name}
            >
              Créer
            </Button>
          </>
        }
      >
        <div className="space-y-4">
          <Input label="Nom du site *" value={name} onChange={(e) => setName(e.target.value)} required />
          <Input label="Code" hint="Ex: KRE-01" value={code} onChange={(e) => setCode(e.target.value)} />
          <Input label="Adresse" value={address} onChange={(e) => setAddress(e.target.value)} />
        </div>
      </Modal>
    </div>
  );
}
