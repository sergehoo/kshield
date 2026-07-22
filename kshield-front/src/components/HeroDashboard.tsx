/**
 * HeroDashboard — Hero principal en tête du Dashboard (style Dappr).
 *
 * Deux modes automatiques :
 *
 *   MODE NOTIFICATIONS : si des alertes non-lues critiques/warning existent,
 *     on affiche une card noire proéminente avec la notif la plus prioritaire,
 *     un compteur "+ N autres" et des CTAs (voir toutes, marquer lu, résoudre).
 *
 *   MODE STATS : par défaut, on affiche un panel gris clair avec le greeting
 *     personnalisé de l'utilisateur + 4 mini-tuiles inline (devices, sites,
 *     employés, alertes 24h) + petit graph des events des 24 dernières heures.
 *
 * Le switch est automatique — pas de prop nécessaire.
 */
import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import {
  Bell, ShieldAlert, TrendingUp, Cpu, MapPin, Users,
  ArrowRight, Check, Activity, Radio, Clock, Sun, Moon,
} from "lucide-react";

import { Button } from "@/components/ui/Button";
import { useAuthStore } from "@/lib/auth";
import {
  notificationsService,
  devicesService,
  sitesService,
  employeesService,
} from "@/services";
import { cn } from "@/lib/cn";
import { fmtRelative } from "@/lib/format";

// ═══════════════════════════════════════════════════════════════════
// HeroDashboard — point d'entrée
// ═══════════════════════════════════════════════════════════════════
export function HeroDashboard() {
  const user = useAuthStore((s) => s.user);

  // ─── Charge les notifications critiques non-lues ───────────
  const { data: alertsData } = useQuery({
    queryKey: ["hero-alerts"],
    queryFn: async () =>
      (await notificationsService.list({
        page_size: 5,
        unread: true,
        ordering: "-created_at",
      })).data,
    refetchInterval: 30_000,
    retry: 1,
  });

  const notifications = (alertsData?.results ?? []).filter(
    (n: any) => n.level === "danger" || n.level === "warning",
  );

  // Si au moins une alerte critique/warning → mode notifications
  if (notifications.length > 0) {
    return <NotificationsHero notifications={notifications} greeting={getGreeting(user)} />;
  }

  return <StatsHero greeting={getGreeting(user)} />;
}

// ═══════════════════════════════════════════════════════════════════
// Mode NOTIFICATIONS — card noire proéminente
// ═══════════════════════════════════════════════════════════════════
function NotificationsHero({
  notifications,
  greeting,
}: {
  notifications: any[];
  greeting: { hello: string; name: string; emoji: string };
}) {
  const primary = notifications[0];
  const others = notifications.length - 1;
  const critical = notifications.filter((n) => n.level === "danger").length;

  return (
    <div className="mb-6 rounded-3xl bg-obsidian text-white p-6 md:p-8 relative overflow-hidden border border-white/10 shadow-dappr">
      {/* Décoration : gradient subtil en arrière-plan */}
      <div className="absolute inset-0 opacity-30 pointer-events-none">
        <div className="absolute -top-20 -right-20 w-64 h-64 rounded-full bg-danger/20 blur-3xl" />
        <div className="absolute -bottom-20 -left-10 w-48 h-48 rounded-full bg-brand-500/20 blur-3xl" />
      </div>

      <div className="relative flex flex-col md:flex-row gap-6 md:items-center md:justify-between">
        {/* Left — Alert content */}
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-2">
            <div className="w-10 h-10 rounded-2xl bg-danger/20 text-danger grid place-items-center">
              <ShieldAlert className="w-5 h-5" />
            </div>
            <div className="text-xs uppercase tracking-widest text-white/60 font-semibold">
              {critical > 0
                ? `${critical} alerte${critical > 1 ? "s" : ""} critique${critical > 1 ? "s" : ""}`
                : "Notifications actives"}
            </div>
          </div>

          <h2 className="text-2xl md:text-3xl font-bold tracking-tight mb-2 line-clamp-2">
            {primary.title || primary.message || "Alerte système"}
          </h2>

          {primary.message && primary.title && (
            <p className="text-white/70 text-sm md:text-base mb-3 line-clamp-2">
              {primary.message}
            </p>
          )}

          <div className="flex items-center gap-3 text-xs text-white/60">
            <span className="inline-flex items-center gap-1">
              <Clock className="w-3.5 h-3.5" />
              {primary.created_at ? fmtRelative(primary.created_at) : "à l'instant"}
            </span>
            {others > 0 && (
              <>
                <span>·</span>
                <span className="inline-flex items-center gap-1">
                  <Bell className="w-3.5 h-3.5" />
                  +{others} autre{others > 1 ? "s" : ""} notification{others > 1 ? "s" : ""}
                </span>
              </>
            )}
          </div>
        </div>

        {/* Right — CTAs */}
        <div className="flex flex-col sm:flex-row md:flex-col gap-2 shrink-0">
          <Link to="/notifications">
            <Button variant="invert" size="md" className="w-full sm:w-auto">
              Voir toutes
              <ArrowRight className="w-4 h-4" />
            </Button>
          </Link>
          <Button
            variant="ghost"
            size="md"
            className="w-full sm:w-auto text-white hover:bg-white/10"
            onClick={() => {
              // TODO : mark-as-read via API
              console.log("mark read", primary.id);
            }}
          >
            <Check className="w-4 h-4" />
            Marquer comme lue
          </Button>
        </div>
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════
// Mode STATS — panel greeting + 4 mini-tuiles inline
// ═══════════════════════════════════════════════════════════════════
function StatsHero({
  greeting,
}: {
  greeting: { hello: string; name: string; emoji: string };
}) {
  const { data: devicesRaw } = useQuery({
    queryKey: ["hero-devices"],
    queryFn: async () => (await devicesService.list({ page_size: 500 })).data,
    refetchInterval: 60_000,
  });

  const { data: sitesRaw } = useQuery({
    queryKey: ["hero-sites"],
    queryFn: async () => (await sitesService.list({ page_size: 100 })).data,
    refetchInterval: 300_000,
  });

  const { data: employeesRaw } = useQuery({
    queryKey: ["hero-employees"],
    queryFn: async () => (await employeesService.list({ page_size: 1 })).data,
    refetchInterval: 300_000,
  });

  const devices = devicesRaw?.results ?? [];
  const totalDevices = devicesRaw?.count ?? devices.length;
  const onlineDevices = devices.filter(
    (d: any) => d.is_online || d.status === "active",
  ).length;
  const onlineRatio = totalDevices > 0
    ? Math.round((onlineDevices * 100) / totalDevices)
    : 0;

  const sitesCount = sitesRaw?.count ?? sitesRaw?.results?.length ?? 0;
  const employeesCount = employeesRaw?.count ?? 0;

  // Score de santé général (heuristique simple)
  const healthScore = totalDevices === 0
    ? 100
    : Math.round((onlineDevices * 100) / totalDevices);

  const healthTone =
    healthScore >= 90 ? "text-success"
    : healthScore >= 70 ? "text-warning"
    : "text-danger";

  return (
    // Style Dappr : hero noir profond comme la sidebar
    <div className="mb-6 rounded-3xl bg-obsidian text-white p-6 md:p-8 relative overflow-hidden border border-white/10 shadow-dappr">
      {/* Décoration : gradients subtils orange/bleu comme la sidebar */}
      <div className="absolute inset-0 opacity-40 pointer-events-none">
        <div className="absolute -top-20 -right-20 w-72 h-72 rounded-full bg-brand-500/15 blur-3xl" />
        <div className="absolute -bottom-20 -left-10 w-56 h-56 rounded-full bg-info/10 blur-3xl" />
      </div>

      <div className="relative flex flex-col lg:flex-row gap-6 lg:items-center lg:justify-between">
        {/* Left — Greeting personnalisé */}
        <div className="flex-1 min-w-0">
          <div className="flex items-center gap-2 mb-2">
            <span className="text-2xl">{greeting.emoji}</span>
            <div className="text-xs uppercase tracking-widest text-white/50 font-semibold">
              {greeting.hello}
            </div>
          </div>

          <h1 className="text-3xl md:text-4xl font-bold text-white tracking-tight leading-tight mb-2">
            Bonjour, {greeting.name} !
          </h1>

          <p className="text-white/70 text-sm md:text-base max-w-md">
            Aucune alerte critique.{" "}
            <span className={cn("font-semibold", healthTone)}>
              Score santé {healthScore}%
            </span>{" "}
            — vos équipements sont opérationnels.
          </p>
        </div>

        {/* Right — Mini-tuiles inline (fond translucide sur noir) */}
        <div className="grid grid-cols-2 sm:grid-cols-4 lg:grid-cols-2 xl:grid-cols-4 gap-3 shrink-0">
          <MiniTile
            icon={<Cpu className="w-4 h-4" />}
            label="Terminaux"
            value={`${onlineDevices}/${totalDevices}`}
            hint={`${onlineRatio}% en ligne`}
            trend={onlineRatio >= 90 ? "ok" : onlineRatio >= 70 ? "warn" : "danger"}
          />
          <MiniTile
            icon={<MapPin className="w-4 h-4" />}
            label="Sites"
            value={sitesCount}
            hint="chantiers actifs"
            trend="info"
          />
          <MiniTile
            icon={<Users className="w-4 h-4" />}
            label="Employés"
            value={employeesCount}
            hint="dans le référentiel"
            trend="info"
          />
          <MiniTile
            icon={<Activity className="w-4 h-4" />}
            label="Santé"
            value={`${healthScore}%`}
            hint="score global"
            trend={healthScore >= 90 ? "ok" : healthScore >= 70 ? "warn" : "danger"}
          />
        </div>
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════
// MiniTile — petite tuile inline dans le hero stats
// ═══════════════════════════════════════════════════════════════════
function MiniTile({
  icon,
  label,
  value,
  hint,
  trend,
}: {
  icon: React.ReactNode;
  label: string;
  value: React.ReactNode;
  hint?: string;
  trend?: "ok" | "warn" | "danger" | "info";
}) {
  // Sur fond noir, on utilise des couleurs plus lumineuses avec fond translucide
  const trendColor: Record<string, string> = {
    ok:     "bg-success/25 text-success",
    warn:   "bg-warning/25 text-warning",
    danger: "bg-danger/25 text-danger",
    info:   "bg-info/25 text-info",
  };

  return (
    <div className="rounded-2xl bg-white/10 backdrop-blur-sm p-3 min-w-[130px] border border-white/5">
      <div className="flex items-center gap-1.5 text-xs text-white/60 mb-1">
        <span className={cn(
          "w-6 h-6 rounded-lg grid place-items-center text-[10px]",
          trendColor[trend || "info"],
        )}>
          {icon}
        </span>
        <span className="font-medium truncate">{label}</span>
      </div>
      <div className="text-2xl font-bold text-white tabular-nums tracking-tight">
        {value}
      </div>
      {hint && (
        <div className="text-[10px] text-white/40 mt-0.5 truncate">{hint}</div>
      )}
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════════
// Helpers
// ═══════════════════════════════════════════════════════════════════
function getGreeting(user: any): { hello: string; name: string; emoji: string } {
  const now = new Date();
  const hour = now.getHours();

  let hello = "Bonjour";
  let emoji = "☀️";
  if (hour < 5 || hour >= 22) {
    hello = "Bonsoir";
    emoji = "🌙";
  } else if (hour < 12) {
    hello = "Bonjour";
    emoji = "☀️";
  } else if (hour < 18) {
    hello = "Bon après-midi";
    emoji = "🌤️";
  } else {
    hello = "Bonsoir";
    emoji = "🌆";
  }

  // Extrait le prénom depuis first_name > full_name > email
  let name = "Admin";
  if (user?.first_name) {
    name = user.first_name;
  } else if (user?.full_name) {
    name = user.full_name.split(" ")[0];
  } else if (user?.email) {
    name = user.email.split("@")[0].split(".")[0];
    name = name.charAt(0).toUpperCase() + name.slice(1);
  }

  return { hello, name, emoji };
}
