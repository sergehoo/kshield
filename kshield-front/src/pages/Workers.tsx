import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { PageHeader } from "@/components/PageHeader";
import { Card } from "@/components/ui/Card";
import { DataTable, Column } from "@/components/ui/DataTable";
import { Badge } from "@/components/ui/Badge";
import { Input } from "@/components/ui/Input";
import { workersService } from "@/services";
import { initials } from "@/lib/format";
import type { Worker } from "@/types/api";
import { Search, HardHat, CreditCard, Zap } from "lucide-react";

export function WorkersPage() {
  const [q, setQ] = useState("");
  const navigate = useNavigate();

  const { data, isLoading } = useQuery({
    queryKey: ["workers", q],
    queryFn: async () =>
      (await workersService.list({ page_size: 300, search: q || undefined })).data,
  });

  const columns: Column<Worker>[] = [
    {
      key: "name",
      header: "Ouvrier",
      render: (w) => (
        <div className="flex items-center gap-2.5">
          {w.photo ? (
            <img src={w.photo} alt="" className="w-8 h-8 rounded-full object-cover" />
          ) : (
            <div className="w-8 h-8 rounded-full bg-warn/20 text-warn grid place-items-center text-xs font-semibold">
              {initials(w.full_name)}
            </div>
          )}
          <div>
            <div className="text-sm font-medium text-ink">{w.full_name}</div>
            <div className="text-xs text-ink-soft font-mono">{w.matricule || "—"}</div>
          </div>
        </div>
      ),
    },
    { key: "trade", header: "Métier", render: (w) => w.trade || "—" },
    {
      key: "site",
      header: "Chantier",
      render: (w) =>
        typeof w.site === "object" ? (
          <Badge tone="brand">{w.site?.name}</Badge>
        ) : (
          "—"
        ),
    },
    {
      key: "badge",
      header: "Badge",
      render: (w) =>
        typeof w.badge === "object" && w.badge?.uid ? (
          <span className="inline-flex items-center gap-1.5 text-xs">
            <CreditCard className="w-3.5 h-3.5 text-info" />
            <code className="font-mono">{w.badge.uid}</code>
          </span>
        ) : (
          <span className="text-ink-soft text-xs">Aucun</span>
        ),
    },
    {
      key: "helmet",
      header: "Casque",
      render: (w) =>
        typeof w.helmet === "object" && w.helmet?.uid ? (
          <span className="inline-flex items-center gap-1.5 text-xs">
            <HardHat className="w-3.5 h-3.5 text-warn" />
            <code className="font-mono">{w.helmet.uid}</code>
          </span>
        ) : (
          <span className="text-ink-soft text-xs">—</span>
        ),
    },
  ];

  return (
    <div>
      <PageHeader
        title="Ouvriers"
        subtitle={`${data?.count ?? 0} ouvriers enregistrés`}
      />
      <Card padded={false}>
        <div className="p-4 border-b border-surface-border">
          <Input
            placeholder="Rechercher un ouvrier…"
            leftIcon={<Search className="w-4 h-4" />}
            value={q}
            onChange={(e) => setQ(e.target.value)}
          />
        </div>
        <DataTable
          columns={columns}
          rows={data?.results || []}
          loading={isLoading}
          rowKey={(w) => w.id}
          onRowClick={(w) => navigate(`/workers/${w.id}`)}
        />
      </Card>
    </div>
  );
}
