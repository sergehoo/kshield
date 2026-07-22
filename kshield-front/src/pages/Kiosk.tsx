import { useEffect, useState } from "react";
import { useLive } from "@/hooks/useLive";
import { accessEventsService, attendanceService, devicesService } from "@/services";
import { fmtTime, fmtDateTime } from "@/lib/format";
import { LivePulse } from "@/components/LivePulse";
import {
  ShieldCheck, Users, Cpu, Activity, ArrowDownToLine, ArrowUpFromLine,
  CheckCircle2, Ban, Maximize2, Minimize2, LogOut,
} from "lucide-react";
import { Link } from "react-router-dom";
import { cn } from "@/lib/cn";

/**
 * Kiosk mode — écran plein-écran pour hall d'entreprise / poste de garde.
 *
 * Affiche en temps réel :
 *   - Horloge géante
 *   - Compteur présents live
 *   - Flux d'événements récents (dernières 10 entrées/sorties)
 *   - Statut terminaux (online/offline)
 *
 * Interface volontairement épurée, gros contrastes, lisible à 3m.
 */
export function KioskPage() {
  const [now, setNow] = useState(new Date());
  const [isFullscreen, setIsFullscreen] = useState(false);

  // Horloge live
  useEffect(() => {
    const t = setInterval(() => setNow(new Date()), 1000);
    return () => clearInterval(t);
  }, []);

  // Detect fullscreen changes
  useEffect(() => {
    const onFsChange = () => setIsFullscreen(!!document.fullscreenElement);
    document.addEventListener("fullscreenchange", onFsChange);
    return () => document.removeEventListener("fullscreenchange", onFsChange);
  }, []);

  const events = useLive(
    ["kiosk", "events"],
    async () =>
      (
        await accessEventsService.list({
          page_size: 10,
          ordering: "-timestamp",
        })
      ).data,
    { intervalMs: 3_000 },
  );

  const summary = useLive(
    ["kiosk", "summary"],
    async () => (await attendanceService.todaySummary()).data,
    { intervalMs: 15_000 },
  );

  const devices = useLive(
    ["kiosk", "devices"],
    async () => (await devicesService.list({ page_size: 500 })).data,
    { intervalMs: 30_000 },
  );

  const deviceList = devices.data?.results || [];
  const onlineCount = deviceList.filter((d: any) => d.is_online || d.status === "active").length;
  const totalDevices = deviceList.length;

  const toggleFullscreen = () => {
    if (!document.fullscreenElement) {
      document.documentElement.requestFullscreen?.();
    } else {
      document.exitFullscreen?.();
    }
  };

  return (
    <div className="fixed inset-0 bg-surface flex flex-col overflow-hidden">
      {/* Header géant */}
      <header className="flex items-center justify-between px-8 py-6 border-b border-surface-border">
        <div className="flex items-center gap-4">
          <ShieldCheck className="w-14 h-14 text-brand-ink" />
          <div>
            <div className="text-2xl font-black text-ink tracking-tight">
              KAYDAN <span className="text-brand-ink">SHIELD</span>
            </div>
            <div className="text-sm text-ink-muted">Cockpit temps réel</div>
          </div>
        </div>

        <div className="flex items-center gap-6">
          <div className="text-right">
            <div className="text-5xl font-black text-ink font-mono tabular-nums">
              {fmtTime(now.toISOString())}
            </div>
            <div className="text-sm text-ink-muted mt-1">
              {now.toLocaleDateString("fr-FR", {
                weekday: "long",
                day: "numeric",
                month: "long",
                year: "numeric",
              })}
            </div>
          </div>

          <div className="flex items-center gap-2">
            <button
              onClick={toggleFullscreen}
              className="p-3 rounded-xl border border-surface-border hover:bg-surface-soft text-ink-muted hover:text-ink"
              title={isFullscreen ? "Quitter plein écran" : "Plein écran"}
            >
              {isFullscreen ? (
                <Minimize2 className="w-5 h-5" />
              ) : (
                <Maximize2 className="w-5 h-5" />
              )}
            </button>
            <Link
              to="/"
              className="p-3 rounded-xl border border-surface-border hover:bg-surface-soft text-ink-muted hover:text-ink"
              title="Sortir du kiosk mode"
            >
              <LogOut className="w-5 h-5" />
            </Link>
          </div>
        </div>
      </header>

      {/* KPIs géants */}
      <div className="grid grid-cols-3 gap-6 px-8 py-6">
        <KioskStat
          label="Présents sur site"
          value={summary.data?.present_count ?? "—"}
          icon={<Users className="w-10 h-10" />}
          accent="brand"
          hint={
            summary.data?.total_workers
              ? `sur ${summary.data.total_workers} ouvriers enregistrés`
              : undefined
          }
        />
        <KioskStat
          label="Équipements en ligne"
          value={`${onlineCount}/${totalDevices}`}
          icon={<Cpu className="w-10 h-10" />}
          accent={onlineCount === totalDevices ? "ok" : "warn"}
          hint={
            totalDevices - onlineCount > 0
              ? `${totalDevices - onlineCount} hors ligne`
              : "Tous opérationnels"
          }
        />
        <KioskStat
          label="Événements 24h"
          value={summary.data?.events_24h ?? events.data?.count ?? 0}
          icon={<Activity className="w-10 h-10" />}
          accent="info"
        />
      </div>

      {/* Live feed géant */}
      <div className="flex-1 px-8 pb-6 overflow-hidden">
        <div className="h-full rounded-2xl border border-surface-border bg-surface-card/50 flex flex-col overflow-hidden">
          <div className="flex items-center justify-between px-6 py-4 border-b border-surface-border">
            <h2 className="text-xl font-bold text-ink flex items-center gap-3">
              <Activity className="w-6 h-6 text-brand-ink" />
              Événements en direct
            </h2>
            <LivePulse label="temps réel · 3s" />
          </div>

          <ul className="flex-1 overflow-y-auto divide-y divide-surface-border/50">
            {events.data?.results?.length === 0 && (
              <li className="p-12 text-center text-ink-muted text-lg">
                En attente d'événements…
              </li>
            )}
            {events.data?.results?.map((e: any) => (
              <KioskEventRow key={e.id} event={e} />
            ))}
          </ul>
        </div>
      </div>
    </div>
  );
}

function KioskStat({
  label, value, icon, accent, hint,
}: {
  label: string;
  value: React.ReactNode;
  icon: React.ReactNode;
  accent: "brand" | "ok" | "warn" | "danger" | "info";
  hint?: string;
}) {
  const accentClass = {
    brand: "bg-brand-500/10 text-brand-ink border-brand-500/30",
    ok:    "bg-ok/10 text-ok border-ok/30",
    warn:  "bg-warn/10 text-warn border-warn/30",
    danger:"bg-danger/10 text-danger border-danger/30",
    info:  "bg-info/10 text-info border-info/30",
  }[accent];
  return (
    <div className="rounded-2xl border border-surface-border bg-surface-card/50 p-6">
      <div className="flex items-start justify-between gap-3">
        <div className={cn("w-16 h-16 rounded-2xl grid place-items-center", accentClass)}>
          {icon}
        </div>
      </div>
      <div className="mt-4 text-6xl font-black text-ink tabular-nums leading-none">
        {value}
      </div>
      <div className="mt-2 text-lg font-semibold text-ink">{label}</div>
      {hint && <div className="text-sm text-ink-muted mt-1">{hint}</div>}
    </div>
  );
}

function KioskEventRow({ event }: { event: any }) {
  const granted = event.decision === "granted";
  const isIn = event.direction === "in";
  const deviceName =
    typeof event.device === "object" ? event.device?.name : `Device #${event.device}`;

  return (
    <li className="px-6 py-4 flex items-center gap-5">
      <div
        className={cn(
          "w-14 h-14 rounded-2xl grid place-items-center shrink-0",
          granted ? "bg-ok/10 text-ok" : "bg-danger/10 text-danger",
        )}
      >
        {granted ? <CheckCircle2 className="w-7 h-7" /> : <Ban className="w-7 h-7" />}
      </div>

      <div className="flex-1 min-w-0">
        <div className="flex items-center gap-3 flex-wrap">
          <span className="text-xl font-bold text-ink">
            {event.holder_name || event.badge_uid || "Inconnu"}
          </span>
          <span
            className={cn(
              "inline-flex items-center gap-1.5 px-3 py-1 rounded-full text-sm font-semibold",
              isIn ? "bg-info/10 text-info" : "bg-warn/10 text-warn",
            )}
          >
            {isIn ? (
              <>
                <ArrowDownToLine className="w-4 h-4" /> ENTRÉE
              </>
            ) : (
              <>
                <ArrowUpFromLine className="w-4 h-4" /> SORTIE
              </>
            )}
          </span>
        </div>
        <div className="mt-1 text-sm text-ink-muted">
          {deviceName}
          {event.site && (
            <>
              {" · "}
              {typeof event.site === "object" ? event.site?.name : `Site #${event.site}`}
            </>
          )}
        </div>
      </div>

      <div className="text-right shrink-0">
        <div className="text-3xl font-mono tabular-nums text-ink">
          {fmtTime(event.timestamp)}
        </div>
      </div>
    </li>
  );
}
