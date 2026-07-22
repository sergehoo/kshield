import { ReactNode } from "react";
import { cn } from "@/lib/cn";
import { ArrowUpRight, ArrowDownRight } from "lucide-react";

type Props = {
  label: string;
  value: ReactNode;
  icon?: ReactNode;
  hint?: ReactNode;
  trend?: number; // positive = up, negative = down (% ou brut)
  loading?: boolean;
  accent?: "brand" | "info" | "ok" | "warn" | "danger";
};

const accentMap = {
  brand: "text-brand-ink bg-brand-500/10",
  info: "text-info bg-info/10",
  ok: "text-ok bg-ok/10",
  warn: "text-warn bg-warn/10",
  danger: "text-danger bg-danger/10",
};

export function KpiCard({
  label,
  value,
  icon,
  hint,
  trend,
  loading,
  accent = "brand",
}: Props) {
  return (
    <div className="rounded-2xl border border-surface-border bg-surface-card/70 p-5 shadow-card">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="text-xs uppercase tracking-wider text-ink-muted font-medium">
            {label}
          </div>
          <div className="mt-1.5 text-2xl font-bold text-ink">
            {loading ? (
              <span className="inline-block w-16 h-6 rounded bg-surface-soft animate-pulse" />
            ) : (
              value
            )}
          </div>
          {hint && <div className="mt-1 text-xs text-ink-soft">{hint}</div>}
        </div>
        {icon && (
          <div
            className={cn(
              "w-10 h-10 rounded-xl grid place-items-center shrink-0",
              accentMap[accent],
            )}
          >
            {icon}
          </div>
        )}
      </div>

      {trend !== undefined && (
        <div className="mt-3 flex items-center gap-1 text-xs">
          {trend >= 0 ? (
            <ArrowUpRight className="w-3.5 h-3.5 text-ok" />
          ) : (
            <ArrowDownRight className="w-3.5 h-3.5 text-danger" />
          )}
          <span className={cn(trend >= 0 ? "text-ok" : "text-danger", "font-medium")}>
            {trend >= 0 ? "+" : ""}
            {trend}%
          </span>
          <span className="text-ink-soft">vs période précédente</span>
        </div>
      )}
    </div>
  );
}
