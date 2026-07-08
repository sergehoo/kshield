import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { PageHeader } from "@/components/PageHeader";
import { Card } from "@/components/ui/Card";
import { DataTable, Column } from "@/components/ui/DataTable";
import { Badge } from "@/components/ui/Badge";
import { Input } from "@/components/ui/Input";
import { Button } from "@/components/ui/Button";
import { helmetsService } from "@/services";
import { fmtRelative } from "@/lib/format";
import { Search, HardHat, UploadCloud } from "lucide-react";
import { Link } from "react-router-dom";

export function HelmetsPage() {
  const [q, setQ] = useState("");

  const { data, isLoading } = useQuery({
    queryKey: ["helmets", q],
    queryFn: async () =>
      (await helmetsService.list({ page_size: 200, search: q || undefined })).data,
  });

  const columns: Column<any>[] = [
    {
      key: "uid",
      header: "UID casque",
      render: (h) => (
        <div className="flex items-center gap-2">
          <HardHat className="w-4 h-4 text-warn" />
          <code className="text-xs font-mono text-ink">{h.uid}</code>
        </div>
      ),
    },
    {
      key: "ble",
      header: "BLE beacon",
      render: (h) =>
        h.ble_uid ? (
          <code className="text-xs font-mono text-ink-muted">{h.ble_uid}</code>
        ) : (
          <span className="text-ink-soft text-xs">—</span>
        ),
    },
    {
      key: "worker",
      header: "Ouvrier",
      render: (h) =>
        h.worker_name || (typeof h.worker === "object" ? h.worker?.full_name : "—"),
    },
    {
      key: "status",
      header: "État",
      render: (h) => (
        <Badge tone={h.status === "active" ? "ok" : h.status === "lost" ? "danger" : "muted"}>
          {h.status || "actif"}
        </Badge>
      ),
    },
    {
      key: "battery",
      header: "Batterie",
      render: (h) =>
        h.battery_pct != null ? (
          <Badge tone={h.battery_pct > 30 ? "ok" : h.battery_pct > 15 ? "warn" : "danger"}>
            {h.battery_pct}%
          </Badge>
        ) : (
          "—"
        ),
    },
    {
      key: "last",
      header: "Dernière détection",
      render: (h) => h.last_seen_at ? fmtRelative(h.last_seen_at) : "—",
    },
  ];

  return (
    <div>
      <PageHeader
        title="Casques BLE"
        subtitle={`${data?.count ?? 0} casques (UHF + BLE beacon MOKO H7)`}
        actions={
          <Link to="/badges/bulk-enroll" className="btn-primary inline-flex">
            <UploadCloud className="w-4 h-4" /> Enrôler des casques
          </Link>
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
          rowKey={(h) => h.id}
        />
      </Card>
    </div>
  );
}
