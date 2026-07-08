import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { PageHeader } from "@/components/PageHeader";
import { Card } from "@/components/ui/Card";
import { DataTable, Column } from "@/components/ui/DataTable";
import { Badge } from "@/components/ui/Badge";
import { Input } from "@/components/ui/Input";
import { employeesService } from "@/services";
import { initials } from "@/lib/format";
import type { Employee } from "@/types/api";
import { Search } from "lucide-react";

export function EmployeesPage() {
  const [q, setQ] = useState("");
  const navigate = useNavigate();

  const { data, isLoading } = useQuery({
    queryKey: ["employees", q],
    queryFn: async () =>
      (await employeesService.list({ page_size: 200, search: q || undefined })).data,
  });

  const columns: Column<Employee>[] = [
    {
      key: "name",
      header: "Employé",
      render: (e) => (
        <div className="flex items-center gap-2.5">
          {e.photo ? (
            <img src={e.photo} alt="" className="w-8 h-8 rounded-full object-cover" />
          ) : (
            <div className="w-8 h-8 rounded-full bg-brand-500/20 text-brand-400 grid place-items-center text-xs font-semibold">
              {initials(e.full_name)}
            </div>
          )}
          <div>
            <div className="text-sm font-medium text-ink">{e.full_name}</div>
            <div className="text-xs text-ink-soft font-mono">{e.matricule || "—"}</div>
          </div>
        </div>
      ),
    },
    { key: "job", header: "Poste", render: (e) => e.job_title || "—" },
    { key: "dept", header: "Département", render: (e) => e.department || "—" },
    {
      key: "contact",
      header: "Contact",
      render: (e) => (
        <div className="text-xs">
          {e.email && <div className="text-ink">{e.email}</div>}
          {e.phone && <div className="text-ink-muted font-mono">{e.phone}</div>}
        </div>
      ),
    },
    {
      key: "company",
      header: "Société",
      render: (e) =>
        typeof e.company === "object" ? e.company?.name : e.company ? `#${e.company}` : "—",
    },
    {
      key: "active",
      header: "Statut",
      render: (e) => (
        <Badge tone={e.is_active !== false ? "ok" : "muted"}>
          {e.is_active !== false ? "Actif" : "Inactif"}
        </Badge>
      ),
    },
  ];

  return (
    <div>
      <PageHeader title="Employés" subtitle={`${data?.count ?? 0} employés`} />
      <Card padded={false}>
        <div className="p-4 border-b border-surface-border">
          <Input
            placeholder="Rechercher un employé…"
            leftIcon={<Search className="w-4 h-4" />}
            value={q}
            onChange={(e) => setQ(e.target.value)}
          />
        </div>
        <DataTable
          columns={columns}
          rows={data?.results || []}
          loading={isLoading}
          rowKey={(e) => e.id}
          onRowClick={(e) => navigate(`/employees/${e.id}`)}
        />
      </Card>
    </div>
  );
}
