import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery, useMutation } from "@tanstack/react-query";
import { PageHeader } from "@/components/PageHeader";
import { Card } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { DataTable, Column } from "@/components/ui/DataTable";
import { camerasService } from "@/services";
import { toApiError } from "@/lib/api";
import { Search, Radar, Camera, Wifi, WifiOff } from "lucide-react";
import toast from "react-hot-toast";

export function CamerasPage() {
  const [q, setQ] = useState("");
  const navigate = useNavigate();

  const { data, isLoading, refetch } = useQuery({
    queryKey: ["cameras", q],
    queryFn: async () =>
      (await camerasService.list({ page_size: 200, search: q || undefined })).data,
  });

  const discoverMut = useMutation({
    mutationFn: () => camerasService.discover(),
    onSuccess: (r: any) =>
      toast.success(`${r.data?.discovered ?? 0} caméra(s) détectée(s)`),
    onError: (e) => toast.error(toApiError(e).message),
  });

  const columns: Column<any>[] = [
    {
      key: "name",
      header: "Caméra",
      render: (c) => (
        <div className="flex items-center gap-2.5">
          <div className="w-8 h-8 rounded-lg bg-info/10 text-info grid place-items-center">
            <Camera className="w-4 h-4" />
          </div>
          <div>
            <div className="text-sm font-medium text-ink">{c.name}</div>
            <div className="text-xs text-ink-soft font-mono">{c.serial_number || "—"}</div>
          </div>
        </div>
      ),
    },
    {
      key: "ip",
      header: "IP / RTSP",
      render: (c) => (
        <code className="text-xs font-mono text-ink-muted truncate max-w-xs block">
          {c.rtsp_url || c.ip_address || "—"}
        </code>
      ),
    },
    { key: "model", header: "Modèle", render: (c) => c.model_name || c.brand || "—" },
    {
      key: "site",
      header: "Site",
      render: (c) => (typeof c.site === "object" ? c.site?.name : "—"),
    },
    {
      key: "status",
      header: "État",
      render: (c) => (
        <Badge tone={c.is_online ? "ok" : "danger"} dot>
          {c.is_online ? (
            <>
              <Wifi className="w-3 h-3" /> Online
            </>
          ) : (
            <>
              <WifiOff className="w-3 h-3" /> Offline
            </>
          )}
        </Badge>
      ),
    },
  ];

  return (
    <div>
      <PageHeader
        title="Caméras"
        subtitle={`${data?.count ?? 0} caméras surveillance vidéo`}
        actions={
          <Button
            variant="ghost"
            leftIcon={<Radar className="w-4 h-4" />}
            onClick={() => discoverMut.mutate()}
            loading={discoverMut.isPending}
          >
            Auto-détection ONVIF
          </Button>
        }
      />

      <Card padded={false}>
        <div className="p-4 border-b border-surface-border">
          <Input
            placeholder="Rechercher par nom, IP…"
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
          onRowClick={(c) => navigate(`/cameras/${c.id}`)}
        />
      </Card>
    </div>
  );
}
