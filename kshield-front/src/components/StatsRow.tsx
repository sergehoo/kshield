import { ReactNode } from "react";
import { cn } from "@/lib/cn";

export type Stat = {
  label: string;
  value: ReactNode;
  icon?: ReactNode;
  hint?: string;
  tone?: "brand" | "ok" | "warn" | "danger" | "info" | "muted";
  onClick?: () => void;
};

const toneMap = {
  brand:  "text-brand-ink bg-brand-500/10 border-brand-500/20",
  ok:     "text-ok bg-ok/10 border-ok/20",
  warn:   "text-warn bg-warn/10 border-warn/20",
  danger: "text-danger bg-danger/10 border-danger/20",
  info:   "text-info bg-info/10 border-info/20",
  muted:  "text-ink-muted bg-ink/5 border-surface-border",
};

/**
 * StatsRow — bande compacte de 2-6 KPIs alignés au-dessus d'une liste.
 * Chaque stat est optionnellement cliquable (utile pour filtrer la liste).
 *
 * Rend automatiquement grid-cols responsive selon le nombre de stats.
 */
export function StatsRow({
  stats,
  className,
  loading,
}: {
  stats: Stat[];
  className?: string;
  loading?: boolean;
}) {
  const cols =
    stats.length <= 2 ? "grid-cols-2" :
    stats.length === 3 ? "grid-cols-3" :
    stats.length === 4 ? "grid-cols-2 sm:grid-cols-4" :
    stats.length === 5 ? "grid-cols-2 sm:grid-cols-3 lg:grid-cols-5" :
    "grid-cols-2 sm:grid-cols-3 lg:grid-cols-6";

  return (
    <div className={cn(`grid ${cols} gap-3 mb-4`, className)}>
      {stats.map((s, i) => (
        <StatCard key={i} stat={s} loading={loading} />
      ))}
    </div>
  );
}

function StatCard({ stat, loading }: { stat: Stat; loading?: boolean }) {
  const clickable = !!stat.onClick;

  // Tone → couleur de la pastille chip en bas (au lieu d'une bordure)
  const chipTone: Record<string, string> = {
    brand:  "bg-brand-500/15 text-brand-ink",
    ok:     "bg-ok/15 text-ok",
    warn:   "bg-warn/15 text-warn",
    danger: "bg-danger/15 text-danger",
    info:   "bg-info/15 text-info",
    muted:  "bg-ink/5 text-ink-muted",
  };

  return (
    <div
      onClick={stat.onClick}
      className={cn(
        // Style Dappr : rounded-3xl, fond gris uni, icône noire en haut,
        // gros chiffre bold, label petit et pâle
        "relative rounded-3xl bg-surface-soft/60 p-5 min-h-[130px] flex flex-col justify-between transition-all",
        clickable && "cursor-pointer hover:bg-surface-soft/80",
      )}
    >
      {/* Ligne du haut : icône dans un carré noir arrondi + menu 3 points fantôme */}
      <div className="flex items-start justify-between">
        {stat.icon && (
          <div className="w-10 h-10 rounded-2xl bg-ink text-surface-card grid place-items-center shrink-0">
            {stat.icon}
          </div>
        )}
        <button
          className="w-6 h-6 rounded-full bg-ink/5 text-ink-muted grid place-items-center opacity-40 hover:opacity-100"
          type="button"
          aria-label="Actions"
        >
          <span className="inline-block w-0.5 h-0.5 rounded-full bg-current mx-0.5" />
          <span className="inline-block w-0.5 h-0.5 rounded-full bg-current mx-0.5" />
          <span className="inline-block w-0.5 h-0.5 rounded-full bg-current mx-0.5" />
        </button>
      </div>

      {/* Ligne du bas : gros chiffre + label */}
      <div className="mt-3">
        <div className="text-3xl md:text-4xl font-bold text-ink tabular-nums tracking-tight leading-none">
          {loading ? (
            <span className="inline-block w-24 h-9 rounded bg-ink/5 animate-pulse" />
          ) : (
            stat.value
          )}
        </div>
        <div className="mt-1 text-xs md:text-sm text-ink-muted font-medium leading-snug">
          {stat.label}
        </div>
        {stat.hint && (
          <div className={cn(
            "inline-flex items-center mt-2 px-2 py-0.5 rounded-full text-[11px] font-semibold",
            chipTone[stat.tone || "brand"],
          )}>
            {stat.hint}
          </div>
        )}
      </div>
    </div>
  );
}
