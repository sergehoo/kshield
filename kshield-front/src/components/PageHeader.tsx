import { ReactNode } from "react";
import { LivePulse } from "@/components/LivePulse";

export function PageHeader({
  title,
  subtitle,
  actions,
  live,
  icon,
}: {
  title: string;
  subtitle?: ReactNode;
  actions?: ReactNode;
  live?: boolean;
  icon?: ReactNode;
}) {
  return (
    <div className="mb-6 flex flex-col sm:flex-row sm:items-start sm:justify-between gap-4">
      <div className="flex items-center gap-3 min-w-0">
        {icon && (
          <div className="w-10 h-10 rounded-2xl bg-ink text-surface-card grid place-items-center shrink-0">
            {icon}
          </div>
        )}
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            {/* Style Dappr : titre très gros bold */}
            <h1 className="text-2xl sm:text-3xl md:text-4xl font-bold text-ink tracking-tight leading-tight">
              {title}
            </h1>
            {live && <LivePulse />}
          </div>
          {subtitle && (
            <div className="mt-1.5 text-sm text-ink-muted">{subtitle}</div>
          )}
        </div>
      </div>
      {actions && <div className="flex items-center gap-2 shrink-0">{actions}</div>}
    </div>
  );
}
