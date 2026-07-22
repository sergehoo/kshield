import { useQuery } from "@tanstack/react-query";
import { PageHeader } from "@/components/PageHeader";
import { Card } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { LivePulse } from "@/components/LivePulse";
import { camerasService } from "@/services";
import { Camera, Maximize2, WifiOff } from "lucide-react";
import { Link } from "react-router-dom";

/**
 * Mur de caméras — grille N×N avec streams MJPEG live de toutes les caméras.
 * Utile pour un écran de PC de sécurité / poste de contrôle.
 */
export function CamerasLivePage() {
  const { data } = useQuery({
    queryKey: ["cameras", "live-grid"],
    queryFn: async () =>
      (await camerasService.list({ page_size: 30 })).data,
    refetchInterval: 60_000, // refresh la liste 1×/min (les streams sont continus)
  });

  const cameras = data?.results || [];
  const onlineCount = cameras.filter((c: any) => c.is_online).length;

  return (
    <div>
      <PageHeader
        title="Mur de caméras — live"
        subtitle={`${onlineCount}/${cameras.length} caméras en ligne · streams MJPEG continus`}
        live
        actions={<LivePulse label="STREAMS ACTIFS" />}
      />

      {cameras.length === 0 ? (
        <Card>
          <div className="p-8 text-center text-ink-muted text-sm">
            Aucune caméra enregistrée. Ajoute des caméras depuis la page{" "}
            <Link to="/cameras" className="text-brand-ink hover:underline">
              Caméras
            </Link>{" "}
            ou lance une auto-détection ONVIF.
          </div>
        </Card>
      ) : (
        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
          {cameras.map((cam: any) => (
            <CameraTile key={cam.id} camera={cam} />
          ))}
        </div>
      )}
    </div>
  );
}

function CameraTile({ camera }: { camera: any }) {
  const streamSrc = camerasService.streamUrl(camera.id);
  const openFullscreen = () => {
    window.open(streamSrc, "_blank", "width=1280,height=720,noopener");
  };

  return (
    <div className="rounded-2xl border border-surface-border bg-surface-card/60 overflow-hidden flex flex-col">
      {/* Video */}
      <div className="relative aspect-video bg-black overflow-hidden">
        {camera.is_online ? (
          <img
            src={streamSrc}
            alt={camera.name}
            className="w-full h-full object-cover"
            onError={(e) => {
              (e.target as HTMLImageElement).style.display = "none";
            }}
          />
        ) : (
          <div className="w-full h-full flex flex-col items-center justify-center text-ink-soft">
            <WifiOff className="w-8 h-8" />
            <span className="text-xs mt-2">Caméra offline</span>
          </div>
        )}

        {/* Overlay statut + fullscreen */}
        <div className="absolute top-2 left-2">
          <Badge tone={camera.is_online ? "ok" : "danger"} dot>
            {camera.is_online ? "LIVE" : "OFF"}
          </Badge>
        </div>
        <button
          onClick={openFullscreen}
          className="absolute top-2 right-2 p-1.5 rounded-md bg-black/50 text-white hover:bg-black/70"
          title="Plein écran"
        >
          <Maximize2 className="w-3.5 h-3.5" />
        </button>
      </div>

      {/* Footer */}
      <div className="p-3 flex items-center justify-between gap-2">
        <div className="min-w-0 flex-1">
          <Link
            to={`/cameras/${camera.id}`}
            className="text-sm font-medium text-ink hover:text-brand-ink truncate block"
          >
            <Camera className="inline w-3.5 h-3.5 mr-1 -mt-0.5" />
            {camera.name}
          </Link>
          {(camera.site_name || (typeof camera.site === "object" && camera.site?.name)) && (
            <div className="text-xs text-ink-soft truncate">
              📍{" "}
              {camera.site_name ||
                (typeof camera.site === "object" ? camera.site?.name : "")}
            </div>
          )}
        </div>
      </div>
    </div>
  );
}
