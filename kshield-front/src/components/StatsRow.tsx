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
  brand:  "text-brand-400 bg-brand-500/10 border-brand-500/20",
  ok:     "text-ok bg-ok/10 border-ok/20",
  warn:   "text-warn bg-warn/10 border-warn/20",
  danger: "text-danger bg-danger/10 border-danger/20",
  info:   "text-info bg-info/10 border-info/20",
  muted:  "text-ink-muted bg-white/5 border-white/10",
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
  const tone = stat.tone || "brand";
  const clickable = !!stat.onClick;

  return (
    <div
      onClick={stat.onClick}
      className={cn(
        "rounded-xl border bg-surface-card/60 p-3 transition-all",
        toneMap[tone].split(" ").filter((c) => c.startsWith("border-")).join(" "),
        clickable && "cursor-pointer hover:bg-surface-card hover:scale-[1.02]",
      )}
    >
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0 flex-1">
          <div className="text-[10px] uppercase tracking-wider text-ink-soft font-semibold truncate">
            {stat.label}
          </div>
          <div className="mt-1 text-xl font-bold text-ink tabular-nums">
            {loading ? (
              <span className="inline-block w-10 h-5 rounded bg-surface-soft animate-pulse" />
            ) : (
              stat.value
            )}
          </div>
          {stat.hint && (
            <div className="text-[10px] text-ink-soft mt-0.5 truncate">{stat.hint}</div>
          )}
        </div>
        {stat.icon && (
          <div
            className={cn(
              "w-9 h-9 rounded-lg grid place-items-center shrink-0 border",
              toneMap[tone],
            )}
          >
            {stat.icon}
          </div>
        )}
      </div>
    </div>
  );
}
