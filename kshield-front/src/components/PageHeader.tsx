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
          // <div> plutôt que <p> car certaines pages passent du JSX riche
          // (icônes, badges, flex containers) dans le subtitle, ce qui viole
          // les règles HTML si on utilise <p>.
          <div className="mt-1 text-sm text-ink-muted">{subtitle}</div>
        )}
      </div>
      {actions && <div className="flex items-center gap-2">{actions}</div>}
    </div>
  );
}
