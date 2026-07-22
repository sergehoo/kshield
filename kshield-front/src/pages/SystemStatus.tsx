import { useLive } from "@/hooks/useLive";
import { PageHeader } from "@/components/PageHeader";
import { Card } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { KpiCard } from "@/components/KpiCard";
import { LivePulse } from "@/components/LivePulse";
import { systemService, devicesService } from "@/services";
import { fmtRelative } from "@/lib/format";
import type { Device } from "@/types/api";
import {
  Activity, Database, Cpu, Server, HeartPulse, AlertTriangle, CheckCircle2,
} from "lucide-react";
import { cn } from "@/lib/cn";

/**
 * Page /system/ — santé technique de la plateforme.
 * Reproduit l'esprit de la page Django /system/ mentionnée dans les specs.
 */
export function SystemStatusPage() {
  const status = useLive(
    ["system", "status"],
    async () => (await systemService.status()).data,
    { intervalMs: 10_000 },
  );

  const devices = useLive(
    ["system", "devices-hb"],
    async () => (await devicesService.list({ page_size: 500 })).data,
    { intervalMs: 30_000 },
  );

  const s = status.data || {};

  return (
    <div>
      <PageHeader
        title="État système"
        subtitle="Santé technique en temps réel — services, workers, terminaux"
        live
      />

      {/* KPIs services core */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-5">
        <ServiceCard
          label="Base de données"
          ok={s.database?.ok !== false}
          detail={s.database?.detail || "PostgreSQL"}
          icon={<Database className="w-5 h-5" />}
          loading={status.isLoading}
        />
        <ServiceCard
          label="Cache Redis"
          ok={s.redis?.ok !== false}
          detail={s.redis?.detail || "Redis"}
          icon={<Server className="w-5 h-5" />}
          loading={status.isLoading}
        />
        <ServiceCard
          label="Celery workers"
          ok={(s.celery?.workers_count ?? 0) > 0}
          detail={
            s.celery?.workers_count !== undefined
              ? `${s.celery.workers_count} worker(s) actifs`
              : "Statut inconnu"
          }
          icon={<Cpu className="w-5 h-5" />}
          loading={status.isLoading}
        />
        <ServiceCard
          label="Celery beat"
          ok={s.celery?.beat_running !== false}
          detail={
            s.celery?.next_task_in
              ? `Prochaine tâche dans ${s.celery.next_task_in}s`
              : "Scheduler"
          }
          icon={<Activity className="w-5 h-5" />}
          loading={status.isLoading}
        />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {/* Heartbeats terminaux */}
        <Card
          className="lg:col-span-2"
          title={
            <span className="flex items-center gap-2">
              <HeartPulse className="w-4 h-4 text-brand-ink" /> Heartbeats terminaux
            </span>
          }
          subtitle={
            devices.data?.results
              ? `${devices.data.results.length} terminaux surveillés`
              : ""
          }
          actions={<LivePulse />}
        >
          <div className="space-y-1.5 max-h-[420px] overflow-y-auto -mx-2 px-2">
            {devices.data?.results?.length === 0 && (
              <div className="text-center py-6 text-ink-muted text-sm">
                Aucun terminal enregistré
              </div>
            )}
            {devices.data?.results
              ?.slice()
              .sort((a: Device, b: Device) => {
                const aTs = a.last_heartbeat_at ? new Date(a.last_heartbeat_at).getTime() : 0;
                const bTs = b.last_heartbeat_at ? new Date(b.last_heartbeat_at).getTime() : 0;
                return bTs - aTs;
              })
              .map((d: Device) => {
                const age = d.last_heartbeat_at
                  ? Math.round((Date.now() - new Date(d.last_heartbeat_at).getTime()) / 1000)
                  : null;
                const tone =
                  age === null ? "muted" : age < 90 ? "ok" : age < 600 ? "warn" : "danger";
                return (
                  <div
                    key={d.id}
                    className="flex items-center gap-3 px-2 py-2 rounded-lg hover:bg-surface-soft/40"
                  >
                    <div
                      className={cn(
                        "w-1.5 h-8 rounded-full shrink-0",
                        tone === "ok" && "bg-ok animate-pulse-dot",
                        tone === "warn" && "bg-warn",
                        tone === "danger" && "bg-danger",
                        tone === "muted" && "bg-ink-soft",
                      )}
                    />
                    <div className="flex-1 min-w-0">
                      <div className="text-sm font-medium text-ink truncate">
                        {d.name}
                      </div>
                      <div className="text-[11px] text-ink-soft font-mono truncate">
                        {d.serial_number || d.ip_address || "—"}
                      </div>
                    </div>
                    <div className="text-right shrink-0">
                      <Badge tone={tone}>
                        {age === null
                          ? "Jamais vu"
                          : age < 90
                          ? `${age}s`
                          : fmtRelative(d.last_heartbeat_at!)}
                      </Badge>
                    </div>
                  </div>
                );
              })}
          </div>
        </Card>

        {/* Tâches récentes + errors */}
        <div className="space-y-4">
          <Card title="Tâches Celery récentes">
            {s.celery?.recent_tasks?.length ? (
              <ul className="space-y-2">
                {s.celery.recent_tasks.slice(0, 6).map((t: any, i: number) => (
                  <li
                    key={i}
                    className="flex items-center justify-between text-xs p-2 rounded bg-surface-soft/40"
                  >
                    <div className="min-w-0">
                      <div className="text-ink font-medium truncate">{t.name}</div>
                      <div className="text-ink-soft">
                        {t.duration_ms ? `${t.duration_ms} ms` : t.state}
                      </div>
                    </div>
                    <Badge tone={t.state === "SUCCESS" ? "ok" : t.state === "FAILURE" ? "danger" : "muted"}>
                      {t.state}
                    </Badge>
                  </li>
                ))}
              </ul>
            ) : (
              <div className="text-xs text-ink-muted text-center py-4">
                Aucune donnée
              </div>
            )}
          </Card>

          <Card title="Environnement">
            <dl className="space-y-2 text-xs">
              <Row label="Django" value={s.env?.django_version} />
              <Row label="Python" value={s.env?.python_version} />
              <Row label="DB" value={s.env?.database_engine} />
              <Row label="Tenant" value={s.env?.current_tenant} />
              <Row label="Version" value={s.env?.app_version} />
              <Row label="Uptime" value={s.env?.uptime} />
            </dl>
          </Card>
        </div>
      </div>
    </div>
  );
}

function ServiceCard({
  label, ok, detail, icon, loading,
}: {
  label: string;
  ok: boolean;
  detail?: string;
  icon: React.ReactNode;
  loading?: boolean;
}) {
  return (
    <KpiCard
      label={label}
      value={
        <span className="flex items-center gap-2 text-base">
          {ok ? (
            <CheckCircle2 className="w-5 h-5 text-ok" />
          ) : (
            <AlertTriangle className="w-5 h-5 text-danger" />
          )}
          <span className={ok ? "text-ok" : "text-danger"}>
            {ok ? "OK" : "KO"}
          </span>
        </span>
      }
      icon={icon}
      accent={ok ? "ok" : "danger"}
      hint={detail}
      loading={loading}
    />
  );
}

function Row({ label, value }: { label: string; value?: string | number }) {
  return (
    <div className="flex items-center justify-between gap-3">
      <dt className="text-ink-muted uppercase tracking-wider">{label}</dt>
      <dd className="font-mono text-ink truncate">{value || "—"}</dd>
    </div>
  );
}
