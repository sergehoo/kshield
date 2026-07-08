import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { PageHeader } from "@/components/PageHeader";
import { Card } from "@/components/ui/Card";
import { DataTable, Column } from "@/components/ui/DataTable";
import { Badge } from "@/components/ui/Badge";
import { Input } from "@/components/ui/Input";
import { firmwaresService } from "@/services";
import { fmtDateTime, fmtNumber } from "@/lib/format";
import { Search, Package, Cpu, Clock, CheckCircle2 } from "lucide-react";
import { cn } from "@/lib/cn";

/**
 * Page Firmwares & OTA — 2 blocs :
 *  1. Firmwares disponibles (versions publiées)
 *  2. Updates OTA planifiés/en cours
 */
export function FirmwaresPage() {
  const [tab, setTab] = useState<"firmwares" | "ota">("firmwares");

  return (
    <div>
      <PageHeader
        title="Firmwares & OTA"
        subtitle="Gestion des versions de firmware et mises à jour Over-The-Air"
      />

      <div className="mb-4 border-b border-surface-border flex gap-1">
        {(
          [
            { key: "firmwares", label: "Firmwares" },
            { key: "ota", label: "Updates OTA" },
          ] as const
        ).map((t) => (
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            className={cn(
              "px-4 py-2 text-sm",
              tab === t.key
                ? "font-medium text-brand-500 border-b-2 border-brand-500 -mb-px"
                : "text-ink-muted hover:text-ink",
            )}
          >
            {t.label}
          </button>
        ))}
      </div>

      {tab === "firmwares" ? <FirmwaresList /> : <OtaList />}
    </div>
  );
}

function FirmwaresList() {
  const [q, setQ] = useState("");
  const { data, isLoading } = useQuery({
    queryKey: ["firmwares", q],
    queryFn: async () =>
      (await firmwaresService.list({ page_size: 200, search: q || undefined })).data,
  });

  const columns: Column<any>[] = [
    {
      key: "version",
      header: "Version",
      render: (f) => (
        <div className="flex items-center gap-2.5">
          <div className="w-8 h-8 rounded-lg bg-brand-500/10 text-brand-400 grid place-items-center">
            <Package className="w-4 h-4" />
          </div>
          <div>
            <div className="text-sm font-medium text-ink">{f.version}</div>
            <div className="text-xs text-ink-soft">{f.model_name || f.device_model || "—"}</div>
          </div>
        </div>
      ),
    },
    { key: "brand", header: "Marque", render: (f) => f.brand || "—" },
    { key: "size", header: "Taille", render: (f) => f.size_bytes ? `${(f.size_bytes / 1024 / 1024).toFixed(1)} MB` : "—" },
    {
      key: "released",
      header: "Publiée",
      render: (f) => f.released_at ? fmtDateTime(f.released_at) : "—",
    },
    {
      key: "status",
      header: "Statut",
      render: (f) => (
        <Badge tone={f.is_stable ? "ok" : "warn"}>
          {f.is_stable ? "Stable" : "Beta"}
        </Badge>
      ),
    },
  ];

  return (
    <Card padded={false}>
      <div className="p-4 border-b border-surface-border">
        <Input
          placeholder="Rechercher un firmware…"
          leftIcon={<Search className="w-4 h-4" />}
          value={q}
          onChange={(e) => setQ(e.target.value)}
        />
      </div>
      <DataTable
        columns={columns}
        rows={data?.results || []}
        loading={isLoading}
        rowKey={(f) => f.id}
        emptyLabel="Aucun firmware enregistré"
      />
    </Card>
  );
}

function OtaList() {
  const { data, isLoading } = useQuery({
    queryKey: ["ota", "list"],
    queryFn: async () =>
      (await firmwaresService.otaList({ page_size: 200, ordering: "-created_at" })).data,
  });

  const columns: Column<any>[] = [
    {
      key: "device",
      header: "Équipement",
      render: (o) => (
        <div className="flex items-center gap-2.5">
          <Cpu className="w-4 h-4 text-info" />
          <div>
            <div className="text-sm font-medium text-ink">
              {o.device_name || `Device #${o.device}`}
            </div>
            <div className="text-xs text-ink-soft font-mono">{o.device_serial || "—"}</div>
          </div>
        </div>
      ),
    },
    { key: "from", header: "Depuis", render: (o) => o.current_version || "—" },
    { key: "to", header: "Vers", render: (o) => o.target_version || "—" },
    {
      key: "status",
      header: "État",
      render: (o) => {
        const tone =
          o.status === "completed"
            ? "ok"
            : o.status === "failed"
            ? "danger"
            : o.status === "in_progress"
            ? "warn"
            : "muted";
        return (
          <Badge tone={tone} dot>
            {o.status}
          </Badge>
        );
      },
    },
    {
      key: "progress",
      header: "Progrès",
      render: (o) => (
        <div className="flex items-center gap-2 w-32">
          <div className="flex-1 h-1.5 bg-surface-soft rounded-full overflow-hidden">
            <div
              className={cn(
                "h-full transition-all",
                o.status === "failed" ? "bg-danger" : "bg-brand-500",
              )}
              style={{ width: `${o.progress || 0}%` }}
            />
          </div>
          <span className="text-xs text-ink-muted tabular-nums w-8 text-right">
            {o.progress || 0}%
          </span>
        </div>
      ),
    },
    {
      key: "scheduled",
      header: "Planifiée",
      render: (o) => (o.scheduled_at ? fmtDateTime(o.scheduled_at) : "—"),
    },
  ];

  return (
    <Card padded={false}>
      <DataTable
        columns={columns}
        rows={data?.results || []}
        loading={isLoading}
        rowKey={(o) => o.id}
        emptyLabel="Aucune mise à jour OTA planifiée"
      />
    </Card>
  );
}
