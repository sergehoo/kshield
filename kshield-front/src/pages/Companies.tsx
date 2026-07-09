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
import { companiesService } from "@/services";
import { toApiError } from "@/lib/api";
import { fmtDate } from "@/lib/format";
import type { Company } from "@/types/api";
import { Plus, Building2, Search, Trash2, Truck, Factory, Store, Package } from "lucide-react";
import toast from "react-hot-toast";

export function CompaniesPage() {
  const [q, setQ] = useState("");
  const [sectorFilter, setSectorFilter] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [openNew, setOpenNew] = useState(false);
  const [form, setForm] = useState({ name: "", code: "", legal_form: "", sector: "services" });
  const qc = useQueryClient();
  const navigate = useNavigate();

  const { data, isLoading } = useQuery({
    queryKey: ["companies", q, sectorFilter, statusFilter],
    queryFn: async () =>
      (await companiesService.list({
        page_size: 200,
        search: q || undefined,
        sector: sectorFilter || undefined,
        is_active: statusFilter === "active" ? true : statusFilter === "inactive" ? false : undefined,
      })).data,
  });

  const { data: allCompanies } = useQuery({
    queryKey: ["companies", "all-stats"],
    queryFn: async () => (await companiesService.list({ page_size: 500 })).data,
    staleTime: 30_000,
  });

  const stats = useMemo(() => {
    const list = allCompanies?.results || [];
    return {
      total: allCompanies?.count || 0,
      active: list.filter((c: any) => c.is_active !== false).length,
      btp: list.filter((c: any) => c.sector === "btp").length,
      logistics: list.filter((c: any) => c.sector === "logistics").length,
      industry: list.filter((c: any) => c.sector === "industry").length,
    };
  }, [allCompanies]);

  const createMut = useMutation({
    mutationFn: () => companiesService.create(form),
    onSuccess: () => {
      toast.success("Filiale créée");
      setOpenNew(false);
      setForm({ name: "", code: "", legal_form: "", sector: "services" });
      qc.invalidateQueries({ queryKey: ["companies"] });
    },
    onError: (e) => toast.error(toApiError(e).message),
  });

  const removeMut = useMutation({
    mutationFn: (id: number) => companiesService.remove(id),
    onSuccess: () => {
      toast.success("Filiale supprimée");
      qc.invalidateQueries({ queryKey: ["companies"] });
    },
    onError: (e) => toast.error(toApiError(e).message),
  });

  const columns: Column<Company>[] = [
    {
      key: "name",
      header: "Filiale",
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
        title="Filiales"
        subtitle={`${data?.count ?? 0} filiale${(data?.count ?? 0) > 1 ? "s" : ""} enregistrée${(data?.count ?? 0) > 1 ? "s" : ""}`}
        actions={
          <Button leftIcon={<Plus className="w-4 h-4" />} onClick={() => setOpenNew(true)}>
            Nouvelle filiale
          </Button>
        }
      />

      <StatsRow stats={[
        { label: "Total filiales", value: stats.total,    icon: <Building2 className="w-4 h-4" />, tone: "brand" },
        { label: "Actives",        value: stats.active,   icon: <Building2 className="w-4 h-4" />, tone: "ok",
          onClick: () => setStatusFilter("active") },
        { label: "BTP",            value: stats.btp,      icon: <Package className="w-4 h-4" />,   tone: "warn",
          onClick: () => setSectorFilter("btp") },
        { label: "Logistique",     value: stats.logistics,icon: <Truck className="w-4 h-4" />,     tone: "info",
          onClick: () => setSectorFilter("logistics") },
        { label: "Industrie",      value: stats.industry, icon: <Factory className="w-4 h-4" />,   tone: "muted",
          onClick: () => setSectorFilter("industry") },
      ]} />

      <Card padded={false}>
        <div className="p-4 border-b border-surface-border flex flex-col sm:flex-row gap-2">
          <div className="flex-1">
            <Input
              placeholder="Rechercher…"
              leftIcon={<Search className="w-4 h-4" />}
              value={q}
              onChange={(e) => setQ(e.target.value)}
            />
          </div>
          <select value={sectorFilter} onChange={(e) => setSectorFilter(e.target.value)} className="field sm:w-40">
            <option value="">Tous secteurs</option>
            <option value="btp">BTP</option>
            <option value="logistics">Logistique</option>
            <option value="industry">Industrie</option>
            <option value="services">Services</option>
            <option value="trading">Commerce</option>
            <option value="other">Autre</option>
          </select>
          <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)} className="field sm:w-40">
            <option value="">Tous statuts</option>
            <option value="active">Actives</option>
            <option value="inactive">Inactives</option>
          </select>
        </div>
        <DataTable
          columns={columns}
          rows={data?.results || []}
          loading={isLoading}
          rowKey={(c) => c.id}
          onRowClick={(c) => navigate(`/companies/${c.id}`)}
        />
      </Card>

      <Modal
        open={openNew}
        onClose={() => setOpenNew(false)}
        title="Nouvelle filiale"
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
        </div>
      </Modal>
    </div>
  );
}
