import { useState, useMemo } from "react";
import { useNavigate } from "react-router-dom";
import { useQuery, useMutation } from "@tanstack/react-query";
import { PageHeader } from "@/components/PageHeader";
import { Card } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { DataTable, Column } from "@/components/ui/DataTable";
import { StatsRow } from "@/components/StatsRow";
import { camerasService, sitesService } from "@/services";
import { toApiError } from "@/lib/api";
import { Search, Radar, Camera, Wifi, WifiOff, LayoutGrid, VideoOff } from "lucide-react";
import { Link } from "react-router-dom";
import toast from "react-hot-toast";

export function CamerasPage() {
  const [q, setQ] = useState("");
  const [siteFilter, setSiteFilter] = useState<number | "">("");
  const [onlineFilter, setOnlineFilter] = useState<string>("");
  const navigate = useNavigate();

  const { data, isLoading, refetch } = useQuery({
    queryKey: ["cameras", q, siteFilter, onlineFilter],
    queryFn: async () =>
      (await camerasService.list({
        page_size: 200,
        search: q || undefined,
        site: siteFilter || undefined,
        is_online: onlineFilter === "online" ? true : onlineFilter === "offline" ? false : undefined,
      })).data,
  });

  const { data: allCams } = useQuery({
    queryKey: ["cameras", "all-stats"],
    queryFn: async () => (await camerasService.list({ page_size: 300 })).data,
    staleTime: 30_000,
  });

  const { data: sites } = useQuery({
    queryKey: ["sites", "all-cam"],
    queryFn: async () => (await sitesService.list({ page_size: 200 })).data,
  });

  const stats = useMemo(() => {
    const list = allCams?.results || [];
    const online = list.filter((c: any) => c.is_online).length;
    return {
      total: allCams?.count || 0,
      online,
      offline: list.length - online,
      hikvision: list.filter((c: any) => (c.brand || "").toLowerCase().includes("hikvision")).length,
    };
  }, [allCams]);

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
        subtitle={`${data?.count ?? 0} caméras · ${stats.online}/${stats.total} en ligne`}
        actions={
          <div className="flex items-center gap-2">
            <Link to="/cameras/live" className="btn-ghost inline-flex">
              <LayoutGrid className="w-4 h-4" /> Mur live
            </Link>
            <Button
              variant="ghost"
              leftIcon={<Radar className="w-4 h-4" />}
              onClick={() => discoverMut.mutate()}
              loading={discoverMut.isPending}
            >
              Auto-détection ONVIF
            </Button>
          </div>
        }
      />

      <StatsRow stats={[
        { label: "Total caméras", value: stats.total,   icon: <Camera className="w-4 h-4" />,   tone: "brand" },
        { label: "En ligne",      value: stats.online,  icon: <Wifi className="w-4 h-4" />,     tone: "ok",
          onClick: () => setOnlineFilter("online") },
        { label: "Offline",       value: stats.offline, icon: <VideoOff className="w-4 h-4" />, tone: "danger",
          onClick: () => setOnlineFilter("offline") },
        { label: "Hikvision",     value: stats.hikvision, icon: <Camera className="w-4 h-4" />, tone: "info" },
      ]} />

      <Card padded={false}>
        <div className="p-4 border-b border-surface-border flex flex-col sm:flex-row gap-2">
          <div className="flex-1">
            <Input
              placeholder="Rechercher par nom, IP…"
              leftIcon={<Search className="w-4 h-4" />}
              value={q}
              onChange={(e) => setQ(e.target.value)}
            />
          </div>
          <select value={siteFilter} onChange={(e) => setSiteFilter(e.target.value ? Number(e.target.value) : "")} className="field sm:w-48">
            <option value="">Tous sites</option>
            {sites?.results?.map((s: any) => <option key={s.id} value={s.id}>{s.name}</option>)}
          </select>
          <select value={onlineFilter} onChange={(e) => setOnlineFilter(e.target.value)} className="field sm:w-36">
            <option value="">Tous statuts</option>
            <option value="online">En ligne</option>
            <option value="offline">Offline</option>
          </select>
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
