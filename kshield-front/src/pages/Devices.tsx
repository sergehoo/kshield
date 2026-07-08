import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useLive } from "@/hooks/useLive";
import { PageHeader } from "@/components/PageHeader";
import { Card } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { DataTable, Column } from "@/components/ui/DataTable";
import { Input } from "@/components/ui/Input";
import { LivePulse } from "@/components/LivePulse";
import { devicesService } from "@/services";
import { toApiError } from "@/lib/api";
import { fmtRelative } from "@/lib/format";
import type { Device } from "@/types/api";
import { useMutation, useQueryClient } from "@tanstack/react-query";
import {
  Cpu, RefreshCw, PlugZap, Search, Zap, Wifi, WifiOff, Activity,
} from "lucide-react";
import toast from "react-hot-toast";

function deviceTone(d: Device) {
  if (d.status === "offline" || d.is_online === false) return "danger" as const;
  if (d.status === "maintenance") return "warn" as const;
  if (d.status === "active" || d.is_online) return "ok" as const;
  return "muted" as const;
}

export function DevicesPage() {
  const [q, setQ] = useState("");
  const [statusFilter, setStatusFilter] = useState<string>("");
  const qc = useQueryClient();
  const navigate = useNavigate();

  const { data, isLoading, isFetching, refetch } = useLive(
    ["devices", "list", q, statusFilter],
    async () =>
      (
        await devicesService.list({
          page_size: 200,
          search: q || undefined,
          status: statusFilter || undefined,
        })
      ).data,
    { intervalMs: 20_000 },
  );

  const testConn = useMutation({
    mutationFn: (id: number) => devicesService.testConnection(id).then((r) => r.data),
    onSuccess: (r) => {
      toast.success(
        r?.reachable ? "Équipement joignable ✓" : "Équipement injoignable ✗",
      );
      qc.invalidateQueries({ queryKey: ["devices"] });
    },
    onError: (err) => toast.error(toApiError(err).message),
  });

  const syncNow = useMutation({
    mutationFn: (id: number) => devicesService.zkSyncNow(id).then((r) => r.data),
    onSuccess: () => toast.success("Sync ZKTeco lancée"),
    onError: (err) => toast.error(toApiError(err).message),
  });

  const columns: Column<Device>[] = [
    {
      key: "name",
      header: "Équipement",
      render: (d) => (
        <div className="flex items-center gap-2.5">
          <div className="w-8 h-8 rounded-lg bg-brand-500/10 text-brand-400 grid place-items-center shrink-0">
            <Cpu className="w-4 h-4" />
          </div>
          <div className="min-w-0">
            <div className="text-sm font-medium text-ink truncate">{d.name}</div>
            <div className="text-[11px] text-ink-soft font-mono truncate">
              {d.serial_number || "—"}
            </div>
          </div>
        </div>
      ),
    },
    {
      key: "type",
      header: "Type",
      render: (d) => (
        <span className="text-xs text-ink-muted">{d.type || "—"}</span>
      ),
    },
    {
      key: "ip",
      header: "Adresse",
      render: (d) => (
        <div className="text-xs font-mono">
          {d.ip_address ? (
            <>
              {d.ip_address}
              {d.port ? <span className="text-ink-soft">:{d.port}</span> : null}
            </>
          ) : (
            <span className="text-ink-soft">—</span>
          )}
        </div>
      ),
    },
    {
      key: "status",
      header: "Statut",
      render: (d) => {
        const tone = deviceTone(d);
        return (
          <Badge tone={tone} dot>
            {tone === "ok" ? (
              <><Wifi className="w-3 h-3" /> En ligne</>
            ) : tone === "danger" ? (
              <><WifiOff className="w-3 h-3" /> Offline</>
            ) : tone === "warn" ? (
              "Maintenance"
            ) : (
              d.status || "Inconnu"
            )}
          </Badge>
        );
      },
    },
    {
      key: "hb",
      header: "Dernier signal",
      render: (d) => (
        <span className="text-xs text-ink-muted">
          {d.last_heartbeat_at ? fmtRelative(d.last_heartbeat_at) : "Jamais"}
        </span>
      ),
    },
    {
      key: "actions",
      header: "",
      className: "text-right",
      render: (d) => (
        <div className="inline-flex items-center gap-1">
          <button
            onClick={(e) => {
              e.stopPropagation();
              testConn.mutate(d.id);
            }}
            className="p-1.5 rounded-md hover:bg-surface-soft text-ink-muted hover:text-ink"
            title="Test connexion"
          >
            <PlugZap className="w-3.5 h-3.5" />
          </button>
          {(d.type === "attendance" || d.type?.includes("zk")) && (
            <button
              onClick={(e) => {
                e.stopPropagation();
                syncNow.mutate(d.id);
              }}
              className="p-1.5 rounded-md hover:bg-surface-soft text-ink-muted hover:text-ink"
              title="Sync ZK"
            >
              <Zap className="w-3.5 h-3.5" />
            </button>
          )}
        </div>
      ),
    },
  ];

  const stats = {
    total: data?.count ?? 0,
    online: data?.results?.filter((d) => d.is_online || d.status === "active").length ?? 0,
    offline: data?.results?.filter((d) => d.status === "offline").length ?? 0,
  };

  return (
    <div>
      <PageHeader
        title="Équipements"
        subtitle={`${stats.total} équipements — ${stats.online} en ligne, ${stats.offline} offline`}
        live
        actions={
          <Button
            variant="ghost"
            size="sm"
            leftIcon={<RefreshCw className={`w-3.5 h-3.5 ${isFetching ? "animate-spin" : ""}`} />}
            onClick={() => refetch()}
          >
            Rafraîchir
          </Button>
        }
      />

      <Card padded={false}>
        {/* Filtres */}
        <div className="flex flex-col sm:flex-row gap-2 p-4 border-b border-surface-border">
          <div className="flex-1">
            <Input
              placeholder="Rechercher par nom, IP, serial…"
              leftIcon={<Search className="w-4 h-4" />}
              value={q}
              onChange={(e) => setQ(e.target.value)}
            />
          </div>
          <select
            value={statusFilter}
            onChange={(e) => setStatusFilter(e.target.value)}
            className="field sm:w-48"
          >
            <option value="">Tous statuts</option>
            <option value="active">En ligne</option>
            <option value="offline">Offline</option>
            <option value="maintenance">Maintenance</option>
          </select>
        </div>

        <DataTable
          columns={columns}
          rows={data?.results || []}
          loading={isLoading}
          rowKey={(d) => d.id}
          onRowClick={(d) => navigate(`/devices/${d.id}`)}
          emptyLabel="Aucun équipement trouvé"
        />
      </Card>
    </div>
  );
}
