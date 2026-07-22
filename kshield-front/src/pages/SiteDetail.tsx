import { useParams, useNavigate, Link } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import { useLive } from "@/hooks/useLive";
import { PageHeader } from "@/components/PageHeader";
import { Card } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { KpiCard } from "@/components/KpiCard";
import { sitesService, devicesService, workersService, accessEventsService } from "@/services";
import { fmtTime, fmtRelative } from "@/lib/format";
import { ArrowLeft, MapPin, Cpu, HardHat, Activity, Users } from "lucide-react";

export function SiteDetailPage() {
  const params = useParams<{ id: string }>();
  const navigate = useNavigate();
  const id = Number(params.id);

  const site = useQuery({
    queryKey: ["site", id],
    queryFn: async () => (await (sitesService as any).get(id)).data,
    enabled: !!id,
  });

  const devices = useQuery({
    queryKey: ["site", id, "devices"],
    queryFn: async () =>
      (await devicesService.list({ site: id, page_size: 100 })).data,
    enabled: !!id,
  });

  const workers = useQuery({
    queryKey: ["site", id, "workers"],
    queryFn: async () =>
      (await workersService.list({ site: id, page_size: 100 })).data,
    enabled: !!id,
  });

  const events = useLive(
    ["site", id, "events"],
    async () =>
      (
        await accessEventsService.list({
          site: id,
          page_size: 15,
          ordering: "-timestamp",
        })
      ).data,
    { intervalMs: 10_000, enabled: !!id },
  );

  const s = site.data;
  if (!s && site.isLoading)
    return <div className="text-center py-16 text-ink-muted">Chargement…</div>;
  if (!s)
    return (
      <div className="text-center py-16">
        <p className="text-ink-muted mb-3">Chantier introuvable</p>
        <Link to="/sites" className="btn-ghost inline-flex">
          <ArrowLeft className="w-4 h-4" /> Retour
        </Link>
      </div>
    );

  const onlineDevicesCount =
    devices.data?.results?.filter((d: any) => d.is_online || d.status === "active").length ?? 0;

  return (
    <div>
      <PageHeader
        title={s.name}
        subtitle={
          <span className="flex items-center gap-2 text-xs">
            {s.code && <code className="font-mono">{s.code}</code>}
            {s.address && (
              <>
                <span>·</span>
                <span>{s.address}</span>
              </>
            )}
          </span>
        }
        live
        actions={
          <Button
            variant="ghost"
            size="sm"
            leftIcon={<ArrowLeft className="w-3.5 h-3.5" />}
            onClick={() => navigate("/sites")}
          >
            Retour
          </Button>
        }
      />

      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-5">
        <KpiCard
          label="Ouvriers"
          value={workers.data?.count ?? 0}
          icon={<HardHat className="w-5 h-5" />}
          accent="warn"
        />
        <KpiCard
          label="Équipements"
          value={`${onlineDevicesCount}/${devices.data?.count ?? 0}`}
          icon={<Cpu className="w-5 h-5" />}
          accent={onlineDevicesCount === devices.data?.count ? "ok" : "warn"}
        />
        <KpiCard
          label="Événements récents"
          value={events.data?.count ?? 0}
          icon={<Activity className="w-5 h-5" />}
          accent="info"
        />
        <KpiCard
          label="Filiale"
          value={typeof s.company === "object" ? s.company?.name?.slice(0, 20) : "—"}
          icon={<MapPin className="w-5 h-5" />}
          accent="brand"
        />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-4">
        <Card
          title={
            <span className="flex items-center gap-2">
              <Cpu className="w-4 h-4" /> Équipements du site
            </span>
          }
          padded={false}
        >
          {devices.data?.results?.length === 0 && (
            <div className="p-6 text-center text-ink-muted text-sm">
              Aucun équipement sur ce site
            </div>
          )}
          <ul className="divide-y divide-surface-border/50">
            {devices.data?.results?.slice(0, 10).map((d: any) => (
              <li key={d.id} className="px-4 py-2.5 flex items-center gap-3">
                <Badge tone={d.is_online || d.status === "active" ? "ok" : "danger"} dot>
                  {d.is_online || d.status === "active" ? "OK" : "Off"}
                </Badge>
                <div className="flex-1 min-w-0">
                  <Link
                    to={`/devices/${d.id}`}
                    className="text-sm font-medium text-ink hover:text-brand-ink"
                  >
                    {d.name}
                  </Link>
                  <div className="text-[11px] text-ink-soft">
                    {d.type} · {d.ip_address || "—"}
                  </div>
                </div>
              </li>
            ))}
          </ul>
        </Card>

        <Card
          title={
            <span className="flex items-center gap-2">
              <Activity className="w-4 h-4" /> Événements récents
            </span>
          }
          padded={false}
        >
          <ul className="divide-y divide-surface-border/50 max-h-[420px] overflow-y-auto">
            {events.data?.results?.length === 0 && (
              <li className="p-6 text-center text-ink-muted text-sm">Aucun événement</li>
            )}
            {events.data?.results?.map((ev: any) => (
              <li key={ev.id} className="px-4 py-2.5 flex items-center gap-3">
                <Badge tone={ev.decision === "granted" ? "ok" : "danger"}>
                  {ev.decision === "granted" ? "OK" : "Refus"}
                </Badge>
                <div className="flex-1 min-w-0">
                  <div className="text-sm text-ink truncate">
                    {ev.holder_name || ev.badge_uid}
                  </div>
                </div>
                <div className="text-xs text-ink-soft">{fmtTime(ev.timestamp)}</div>
              </li>
            ))}
          </ul>
        </Card>

        {/* Ouvriers du site */}
        <Card
          className="lg:col-span-2"
          title={
            <span className="flex items-center gap-2">
              <Users className="w-4 h-4" /> Ouvriers affectés ({workers.data?.count ?? 0})
            </span>
          }
          padded={false}
        >
          {workers.data?.results?.length === 0 && (
            <div className="p-6 text-center text-ink-muted text-sm">
              Aucun ouvrier affecté à ce site
            </div>
          )}
          <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-4 gap-2 p-4">
            {workers.data?.results?.slice(0, 24).map((w: any) => (
              <Link
                key={w.id}
                to={`/workers/${w.id}`}
                className="flex items-center gap-2 p-2 rounded-lg bg-surface-soft/40 hover:bg-surface-soft"
              >
                <div className="w-7 h-7 rounded-full bg-warn/20 text-warn grid place-items-center text-[10px] font-semibold shrink-0">
                  {w.full_name?.split(" ").slice(0, 2).map((s: string) => s[0]).join("")}
                </div>
                <div className="min-w-0">
                  <div className="text-xs text-ink truncate">{w.full_name}</div>
                  <div className="text-[10px] text-ink-soft truncate">{w.trade || "—"}</div>
                </div>
              </Link>
            ))}
          </div>
        </Card>
      </div>
    </div>
  );
}
