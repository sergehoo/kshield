/**
 * KAYDAN SHIELD — Topologie réseau (Vague 8).
 *
 * Vue hiérarchique Tenant → Sites → Zones → Devices + Agents.
 * SVG basique (pas de D3 pour rester léger). Refresh WS instantané.
 */
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import {
  Network, Building2, MapPin, Cpu, Server, Wifi, WifiOff,
} from "lucide-react";

import { PageHeader } from "@/components/PageHeader";
import { Card } from "@/components/ui/Card";
import { topologyService } from "@/services/enrollment";
import { useDeviceStatusChannel } from "@/hooks/useDeviceStatusChannel";
import { cn } from "@/lib/cn";

export function TopologyPage() {
  const qc = useQueryClient();
  const { data, isLoading } = useQuery({
    queryKey: ["topology"],
    queryFn: async () => (await topologyService.get()).data,
    refetchInterval: 30_000,
  });

  useDeviceStatusChannel({
    onEvent: (evt: any) => {
      const t = evt?.event;
      if (t && (t.startsWith("device.") || t.startsWith("agent."))) {
        qc.invalidateQueries({ queryKey: ["topology"] });
      }
    },
  });

  if (isLoading || !data) {
    return (
      <div>
        <PageHeader title="Topologie réseau" subtitle="Chargement…" />
      </div>
    );
  }

  return (
    <div>
      <PageHeader
        title="Topologie réseau"
        subtitle={`${data.tenant.name} · ${data.tenant.devices_total} équipements · ${data.tenant.agents_total} agents`}
        live
      />

      {/* Tenant root */}
      <Card padded>
        <div className="flex items-center gap-3 mb-4">
          <div className="w-11 h-11 rounded-lg bg-brand-500/10 text-brand-500 grid place-items-center">
            <Network className="w-5 h-5" />
          </div>
          <div>
            <div className="text-lg font-semibold text-ink">{data.tenant.name}</div>
            <div className="text-xs text-ink-muted">
              {data.tenant.devices_total} devices · {data.tenant.agents_total} agents
            </div>
          </div>
        </div>

        {/* Sites → Zones grid */}
        <div className="space-y-3">
          {data.sites.map((site) => {
            const online_ratio = site.devices_total > 0
              ? Math.round(site.devices_online * 100 / site.devices_total)
              : 0;
            return (
              <div key={site.id} className="rounded-lg border border-surface-border p-3">
                <Link to={`/sites/${site.id}`}
                      className="flex items-center gap-2 hover:underline">
                  <Building2 className="w-4 h-4 text-info" />
                  <span className="text-sm font-semibold text-ink">{site.name}</span>
                  {site.code && <code className="text-xs text-ink-soft font-mono">{site.code}</code>}
                  <span className="ml-auto text-xs">
                    <span className={cn(
                      online_ratio >= 90 ? "text-success"
                      : online_ratio >= 70 ? "text-warning" : "text-danger",
                    )}>
                      {site.devices_online}/{site.devices_total} en ligne · {online_ratio}%
                    </span>
                  </span>
                </Link>
                {site.company && (
                  <div className="ml-6 text-xs text-ink-muted mb-2">
                    Filiale : {site.company.name}
                  </div>
                )}

                {/* Zones */}
                {site.zones.length > 0 && (
                  <div className="ml-6 grid grid-cols-1 md:grid-cols-3 lg:grid-cols-4 gap-2 mt-2">
                    {site.zones.map((z) => (
                      <div key={z.id}
                           className="rounded border border-surface-border bg-surface-soft p-2">
                        <div className="flex items-center gap-1 text-xs text-ink">
                          <MapPin className="w-3 h-3 text-info" />
                          <span className="font-medium truncate">{z.name}</span>
                        </div>
                        <div className="text-[10px] text-ink-muted mt-0.5">
                          {z.devices_online}/{z.devices_total} devices
                        </div>
                      </div>
                    ))}
                  </div>
                )}

                {/* Agents rattachés au site */}
                {data.agents.filter((a) => a.site_id === site.id).length > 0 && (
                  <div className="ml-6 mt-2 flex flex-wrap gap-1">
                    {data.agents.filter((a) => a.site_id === site.id).map((a) => (
                      <span key={a.id}
                            className={cn(
                              "text-[10px] px-1.5 py-0.5 rounded border inline-flex items-center gap-1",
                              a.connected
                                ? "border-success/30 bg-success/5 text-success"
                                : "border-surface-border text-ink-muted",
                            )}>
                        {a.connected ? <Wifi className="w-2.5 h-2.5" /> : <WifiOff className="w-2.5 h-2.5" />}
                        <Server className="w-2.5 h-2.5" />
                        {a.label}
                      </span>
                    ))}
                  </div>
                )}
              </div>
            );
          })}
        </div>

        {/* Devices par type — flat */}
        <div className="mt-6">
          <div className="text-xs uppercase tracking-wider text-ink-muted mb-2">
            Devices ({data.devices.length})
          </div>
          <div className="grid grid-cols-2 md:grid-cols-4 lg:grid-cols-6 gap-2">
            {data.devices.slice(0, 60).map((d: any) => {
              const reachable = d.twin?.reachable ?? false;
              const score = d.twin?.health_score;
              return (
                <Link key={d.id} to={`/devices/${d.id}`}
                      className={cn(
                        "rounded border p-1.5 text-[10px] hover:bg-surface-soft transition",
                        reachable
                          ? "border-success/30 bg-success/5"
                          : "border-danger/30 bg-danger/5",
                      )}
                      title={`${d.brand} ${d.model} · ${d.serial}`}>
                  <div className="flex items-center gap-1">
                    <Cpu className="w-3 h-3" />
                    <span className="truncate font-medium">{d.serial}</span>
                  </div>
                  <div className="text-ink-muted mt-0.5 flex items-center justify-between">
                    <span className="truncate">{d.brand}</span>
                    {score != null && (
                      <span className={cn(
                        score >= 70 ? "text-success"
                        : score >= 40 ? "text-warning" : "text-danger",
                      )}>{score}</span>
                    )}
                  </div>
                </Link>
              );
            })}
            {data.devices.length > 60 && (
              <div className="col-span-full text-center text-xs text-ink-muted">
                … +{data.devices.length - 60} autres
              </div>
            )}
          </div>
        </div>
      </Card>
    </div>
  );
}
