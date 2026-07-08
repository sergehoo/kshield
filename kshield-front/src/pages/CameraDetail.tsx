import { useState } from "react";
import { useParams, useNavigate, Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { PageHeader } from "@/components/PageHeader";
import { Card } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { camerasService } from "@/services";
import { fmtDateTime } from "@/lib/format";
import { ArrowLeft, Camera, Play, Pause, Maximize2, Wifi, WifiOff } from "lucide-react";

export function CameraDetailPage() {
  const params = useParams<{ id: string }>();
  const navigate = useNavigate();
  const id = Number(params.id);
  const [playing, setPlaying] = useState(true);

  const { data, isLoading } = useQuery({
    queryKey: ["camera", id],
    queryFn: async () => (await camerasService.get(id)).data,
    enabled: !!id,
  });

  if (isLoading && !data) {
    return <div className="text-center py-16 text-ink-muted">Chargement…</div>;
  }
  if (!data) {
    return (
      <div className="text-center py-16">
        <p className="text-ink-muted mb-3">Caméra introuvable</p>
        <Link to="/cameras" className="btn-ghost inline-flex">
          <ArrowLeft className="w-4 h-4" /> Retour
        </Link>
      </div>
    );
  }

  const streamSrc = camerasService.streamUrl(id);

  return (
    <div>
      <PageHeader
        title={data.name}
        subtitle={data.model_name || data.brand || ""}
        actions={
          <Button
            variant="ghost"
            size="sm"
            leftIcon={<ArrowLeft className="w-3.5 h-3.5" />}
            onClick={() => navigate("/cameras")}
          >
            Retour
          </Button>
        }
      />

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {/* Flux vidéo */}
        <Card
          className="lg:col-span-2"
          title={
            <span className="flex items-center gap-2">
              <Camera className="w-4 h-4" /> Flux MJPEG live
            </span>
          }
          padded={false}
          actions={
            <div className="flex items-center gap-2">
              <Badge tone={data.is_online ? "ok" : "danger"} dot>
                {data.is_online ? "En ligne" : "Offline"}
              </Badge>
              <button
                onClick={() => setPlaying((p) => !p)}
                className="p-1.5 rounded-md hover:bg-surface-soft"
                title={playing ? "Pause" : "Reprendre"}
              >
                {playing ? (
                  <Pause className="w-4 h-4" />
                ) : (
                  <Play className="w-4 h-4" />
                )}
              </button>
              <button
                onClick={() =>
                  window.open(streamSrc, "_blank", "width=1280,height=720")
                }
                className="p-1.5 rounded-md hover:bg-surface-soft"
                title="Plein écran"
              >
                <Maximize2 className="w-4 h-4" />
              </button>
            </div>
          }
        >
          <div className="aspect-video bg-black flex items-center justify-center overflow-hidden">
            {playing ? (
              <img
                src={streamSrc}
                alt="Flux caméra"
                className="w-full h-full object-contain"
                onError={(e) => {
                  (e.target as HTMLImageElement).style.display = "none";
                }}
              />
            ) : (
              <div className="text-ink-soft text-sm">Flux en pause</div>
            )}
          </div>
        </Card>

        {/* Infos */}
        <Card title="Informations">
          <dl className="space-y-3 text-sm">
            <Row label="Marque" value={data.brand} />
            <Row label="Modèle" value={data.model_name} />
            <Row label="Serial" value={data.serial_number} mono />
            <Row label="IP" value={data.ip_address} mono />
            <Row label="RTSP" value={data.rtsp_url} mono />
            <Row
              label="Site"
              value={typeof data.site === "object" ? data.site?.name : "—"}
            />
            <Row
              label="État"
              value={
                <Badge tone={data.is_online ? "ok" : "danger"} dot>
                  {data.is_online ? "Online" : "Offline"}
                </Badge>
              }
            />
            <Row
              label="Dernier heartbeat"
              value={data.last_heartbeat_at ? fmtDateTime(data.last_heartbeat_at) : "Jamais"}
            />
          </dl>
        </Card>
      </div>
    </div>
  );
}

function Row({
  label, value, mono,
}: {
  label: string;
  value: React.ReactNode;
  mono?: boolean;
}) {
  return (
    <div className="flex items-center justify-between gap-3">
      <dt className="text-xs uppercase tracking-wider text-ink-soft">{label}</dt>
      <dd className={mono ? "font-mono text-xs text-ink truncate max-w-[220px]" : "text-ink"}>
        {value || <span className="text-ink-soft">—</span>}
      </dd>
    </div>
  );
}
