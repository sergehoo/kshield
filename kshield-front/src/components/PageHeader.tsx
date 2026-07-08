import { ReactNode } from "react";
import { LivePulse } from "@/components/LivePulse";

export function PageHeader({
  title,
  subtitle,
  actions,
  live,
}: {
  title: string;
  subtitle?: ReactNode;
  actions?: ReactNode;
  live?: boolean;
}) {
  return (
    <div className="mb-5 flex flex-col sm:flex-row sm:items-end sm:justify-between gap-3">
      <div>
        <div className="flex items-center gap-2">
          <h1 className="text-xl sm:text-2xl font-bold text-ink">{title}</h1>
          {live && <LivePulse />}
        </div>
        {subtitle && (
          <p className="mt-1 text-sm text-ink-muted">{subtitle}</p>
        )}
      </div>
      {actions && <div className="flex items-center gap-2">{actions}</div>}
    </div>
  );
}
