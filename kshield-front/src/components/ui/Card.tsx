import { HTMLAttributes, ReactNode } from "react";
import { cn } from "@/lib/cn";

// On retire `title` de HTMLAttributes car il est typé `string` alors que
// nous voulons accepter des ReactNode (icônes + texte, badges, etc.)
type Props = Omit<HTMLAttributes<HTMLDivElement>, "title"> & {
  title?: ReactNode;
  subtitle?: ReactNode;
  actions?: ReactNode;
  padded?: boolean;
};

export function Card({
  title,
  subtitle,
  actions,
  padded = true,
  className,
  children,
  ...rest
}: Props) {
  const hasHeader = title || subtitle || actions;
  return (
    <section
      className={cn(
        "rounded-2xl border border-surface-border bg-surface-card/70 backdrop-blur-sm shadow-card",
        className,
      )}
      {...rest}
    >
      {hasHeader && (
        <header className="flex items-start justify-between gap-4 px-5 py-4 border-b border-surface-border/60">
          <div className="min-w-0">
            {title && (
              <h2 className="text-sm font-semibold text-ink truncate">{title}</h2>
            )}
            {subtitle && (
              <p className="text-xs text-ink-muted mt-0.5 truncate">{subtitle}</p>
            )}
          </div>
          {actions && <div className="shrink-0 flex items-center gap-2">{actions}</div>}
        </header>
      )}
      <div className={padded ? "p-5" : ""}>{children}</div>
    </section>
  );
}
