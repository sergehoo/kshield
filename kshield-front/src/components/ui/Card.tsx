import { HTMLAttributes, ReactNode } from "react";
import { cn } from "@/lib/cn";

// On retire `title` de HTMLAttributes car il est typé `string` alors que
// nous voulons accepter des ReactNode (icônes + texte, badges, etc.)
type Props = Omit<HTMLAttributes<HTMLDivElement>, "title"> & {
  title?: ReactNode;
  subtitle?: ReactNode;
  actions?: ReactNode;
  padded?: boolean;
  /** Style Dappr : fond noir + texte blanc (pour CTA importants). */
  dark?: boolean;
};

export function Card({
  title,
  subtitle,
  actions,
  padded = true,
  dark = false,
  className,
  children,
  ...rest
}: Props) {
  const hasHeader = title || subtitle || actions;
  return (
    <section
      className={cn(
        // Style Dappr : rounded-3xl, fond gris uni, pas de bordure, ombre légère
        "rounded-3xl border shadow-dappr transition-colors",
        dark ? "border-white/10 bg-obsidian text-white" : "border-surface-border/60 bg-surface-card",
        className,
      )}
      {...rest}
    >
      {hasHeader && (
        <header className={cn(
          "flex items-start justify-between gap-4 px-5 py-4",
          dark ? "border-b border-white/10" : "border-b border-surface-border/40",
        )}>
          <div className="min-w-0">
            {title && (
              <h2 className={cn(
                "text-sm font-semibold truncate",
                dark ? "text-white" : "text-ink",
              )}>
                {title}
              </h2>
            )}
            {subtitle && (
              <p className={cn(
                "text-xs mt-0.5 truncate",
                dark ? "text-white/60" : "text-ink-muted",
              )}>
                {subtitle}
              </p>
            )}
          </div>
          {actions && <div className="shrink-0 flex items-center gap-2">{actions}</div>}
        </header>
      )}
      <div className={padded ? "p-5" : ""}>{children}</div>
    </section>
  );
}
