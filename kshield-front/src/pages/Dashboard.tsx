import { useLive } from "@/hooks/useLive";
import { KpiCard } from "@/components/KpiCard";
import { Card } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { LivePulse } from "@/components/LivePulse";
import { SystemAlertsBanner } from "@/components/SystemAlertsBanner";
import { RealtimeStatsWidget } from "@/components/RealtimeStatsWidget";
import { HeroDashboard } from "@/components/HeroDashboard";
import { accessEventsService, devicesService, attendanceService, notificationsService } from "@/services";
import { fmtRelative, fmtNumber, fmtTime } from "@/lib/format";
import { Users, Cpu, ShieldAlert, Activity, Radar, HardHat } from "lucide-react";
import { Link } from "react-router-dom";
import {
  Area,
  AreaChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
  CartesianGrid,
} from "recharts";
import { useMemo } from "react";

export function DashboardPage() {
  // ─── Devices ─────────────────────────────────────────────
  const devices = useLive(
    ["devices", "kpi"],
    async () =>
      (await devicesService.list({ page_size: 500 })).data,
    { intervalMs: 30_000 },
  );

  // ─── Attendance today ────────────────────────────────────
  const today = useLive(
    ["attendance", "today"],
    async () => (await attendanceService.todaySummary()).data,
    { intervalMs: 30_000 },
  );

  // ─── Access events récents ───────────────────────────────
  const events = useLive(
    ["events", "recent"],
    async () =>
      (await accessEventsService.list({ page_size: 12, ordering: "-timestamp" })).data,
    { intervalMs: 8_000 },
  );

  // ─── Notifications alertes ───────────────────────────────
  const alerts = useLive(
    ["notifications", "recent"],
    async () =>
      (
        await notificationsService.list({
          page_size: 5,
          level: "danger",
          ordering: "-created_at",
        })
      ).data,
    { intervalMs: 30_000 },
  );

  // Stats devices
  const totalDevices = devices.data?.count ?? 0;
  const deviceList = devices.data?.results ?? [];
  const onlineDevices = deviceList.filter(
    (d) => d.is_online || d.status === "active",
  ).length;
  const offlineDevices = deviceList.filter(
    (d) => d.status === "offline" || (!d.is_online && d.status !== "maintenance"),
  ).length;

  // Chart data — événements par heure (approximation à partir des 12 derniers)
  const chartData = useMemo(() => {
    const buckets: Record<string, number> = {};
    events.data?.results?.forEach((e) => {
      const h = new Date(e.timestamp).getHours();
      const key = `${h.toString().padStart(2, "0")}h`;
      buckets[key] = (buckets[key] || 0) + 1;
    });
    return Object.entries(buckets)
      .sort()
      .map(([hour, count]) => ({ hour, count }));
  }, [events.data]);

  return (
    <div>
      {/* Hero principal : notifications si dispo, sinon greeting + stats équipements */}
      <HeroDashboard />

      {/* Bannière alertes système compact (secondaire — le hero prend la priorité) */}
      <SystemAlertsBanner />

      {/* Widget métriques temps réel (devices/agents/sessions/commandes/alertes) */}
      <RealtimeStatsWidget />

      {/* KPIs */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <KpiCard
          label="Présents chantier"
          value={fmtNumber(today.data?.present_count)}
          icon={<Users className="w-5 h-5" />}
          accent="brand"
          hint={
            today.data?.total_workers
              ? `${today.data?.present_count}/${today.data?.total_workers} ouvriers`
              : undefined
          }
          loading={today.isLoading}
        />
        <KpiCard
          label="Équipements en ligne"
          value={`${onlineDevices}/${totalDevices}`}
          icon={<Cpu className="w-5 h-5" />}
          accent={offlineDevices === 0 ? "ok" : "warn"}
          hint={offlineDevices > 0 ? `${offlineDevices} offline` : "Tous OK"}
          loading={devices.isLoading}
        />
        <KpiCard
          label="Événements 24h"
          value={fmtNumber(today.data?.events_24h ?? events.data?.count)}
          icon={<Activity className="w-5 h-5" />}
          accent="info"
          loading={events.isLoading}
        />
        <KpiCard
          label="Alertes actives"
          value={fmtNumber(alerts.data?.count)}
          icon={<ShieldAlert className="w-5 h-5" />}
          accent={alerts.data?.count ? "danger" : "ok"}
          loading={alerts.isLoading}
        />
      </div>

      {/* Layout 2 colonnes */}
      <div className="mt-6 grid grid-cols-1 lg:grid-cols-3 gap-4">
        {/* Live feed */}
        <Card
          className="lg:col-span-2"
          title={
            <span className="flex items-center gap-2">
              <Radar className="w-4 h-4 text-brand-ink" /> Événements récents
            </span>
          }
          subtitle="Actualisé toutes les 8 secondes"
          actions={<LivePulse />}
        >
          <div className="space-y-2 max-h-[420px] overflow-y-auto -mx-2 px-2">
            {events.data?.results?.length === 0 && (
              <div className="text-center py-8 text-ink-muted text-sm">
                Aucun événement récent
              </div>
            )}
            {events.data?.results?.map((e) => (
              <div
                key={e.id}
                className="flex items-center gap-3 p-3 rounded-lg bg-surface-soft/40 hover:bg-surface-soft/70 transition-colors"
              >
                <div
                  className={`w-8 h-8 rounded-full grid place-items-center shrink-0 ${
                    e.decision === "granted"
                      ? "bg-ok/10 text-ok"
                      : "bg-danger/10 text-danger"
                  }`}
                >
                  <HardHat className="w-4 h-4" />
                </div>
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2">
                    <span className="text-sm font-medium text-ink truncate">
                      {e.holder_name || e.badge_uid || "Inconnu"}
                    </span>
                    <Badge tone={e.direction === "in" ? "ok" : "info"}>
                      {e.direction === "in" ? "Entrée" : e.direction === "out" ? "Sortie" : "—"}
                    </Badge>
                  </div>
                  <div className="text-xs text-ink-muted truncate">
                    {typeof e.device === "object" ? e.device?.name : `Device #${e.device}`}
                    {" · "}
                    {typeof e.site === "object" ? e.site?.name : e.site ? `Site #${e.site}` : ""}
                  </div>
                </div>
                <div className="text-right shrink-0">
                  <div className="text-xs text-ink font-mono">{fmtTime(e.timestamp)}</div>
                  <div className="text-[10px] text-ink-soft">{fmtRelative(e.timestamp)}</div>
                </div>
              </div>
            ))}
          </div>
          <div className="mt-3 flex justify-end">
            <Link
              to="/events"
              className="text-xs text-brand-ink hover:text-brand-ink font-medium"
            >
              Voir tous les événements →
            </Link>
          </div>
        </Card>

        {/* Chart + alertes */}
        <div className="space-y-4">
          <Card title="Trafic par heure" subtitle="Événements des dernières heures">
            <div className="h-40 -mx-2">
              <ResponsiveContainer width="100%" height="100%">
                <AreaChart data={chartData} margin={{ top: 8, right: 8, bottom: 0, left: -18 }}>
                  <defs>
                    <linearGradient id="fillCount" x1="0" y1="0" x2="0" y2="1">
                      <stop offset="0%" stopColor="rgb(var(--c-brand-ink))" stopOpacity={0.38} />
                      <stop offset="100%" stopColor="rgb(var(--c-brand-ink))" stopOpacity={0} />
                    </linearGradient>
                  </defs>
                  <CartesianGrid strokeDasharray="3 3" stroke="rgb(var(--c-surface-border))" strokeOpacity={0.65} />
                  <XAxis dataKey="hour" tick={{ fill: "rgb(var(--c-ink-muted))", fontSize: 11 }} />
                  <YAxis tick={{ fill: "rgb(var(--c-ink-muted))", fontSize: 11 }} />
                  <Tooltip
                    contentStyle={{
                      background: "rgb(var(--c-surface-card))",
                      color: "rgb(var(--c-ink))",
                      border: "1px solid rgb(var(--c-surface-border))",
                      borderRadius: 8,
                      fontSize: 12,
                    }}
                  />
                  <Area
                    type="monotone"
                    dataKey="count"
                    stroke="rgb(var(--c-brand-ink))"
                    strokeWidth={2}
                    fill="url(#fillCount)"
                  />
                </AreaChart>
              </ResponsiveContainer>
            </div>
          </Card>

          <Card title="Alertes actives">
            {alerts.data?.results?.length === 0 && (
              <div className="text-sm text-ink-muted text-center py-4">
                🎉 Aucune alerte
              </div>
            )}
            <div className="space-y-2">
              {alerts.data?.results?.map((n) => (
                <div key={n.id} className="p-2.5 rounded-lg bg-danger/5 border border-danger/10">
                  <div className="flex items-center gap-2">
                    <ShieldAlert className="w-3.5 h-3.5 text-danger shrink-0" />
                    <div className="text-xs font-medium text-ink truncate">{n.title}</div>
                  </div>
                  {n.body && (
                    <div className="mt-1 text-[11px] text-ink-muted line-clamp-2">
                      {n.body}
                    </div>
                  )}
                  <div className="mt-1 text-[10px] text-ink-soft">
                    {fmtRelative(n.created_at)}
                  </div>
                </div>
              ))}
            </div>
          </Card>
        </div>
      </div>
    </div>
  );
}
