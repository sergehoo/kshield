import { ReactNode } from "react";
import { cn } from "@/lib/cn";

type Tone = "ok" | "warn" | "danger" | "info" | "muted" | "brand";

const toneMap: Record<Tone, string> = {
  ok:     "bg-ok/10 text-ok border-ok/20",
  warn:   "bg-warn/10 text-warn border-warn/20",
  danger: "bg-danger/10 text-danger border-danger/20",
  info:   "bg-info/10 text-info border-info/20",
  muted:  "bg-ink/5 text-ink-muted border-surface-border",
  brand:  "bg-brand-500/10 text-brand-ink border-brand-500/20",
};

export function Badge({
  tone = "muted",
  children,
  className,
  dot,
}: {
  tone?: Tone;
  children: ReactNode;
  className?: string;
  dot?: boolean;
}) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 px-2.5 py-1 rounded-full text-xs font-medium border",
        toneMap[tone],
        className,
      )}
    >
      {dot && (
        <span
          className={cn(
            "w-1.5 h-1.5 rounded-full",
            tone === "ok" && "bg-ok animate-pulse-dot",
            tone === "warn" && "bg-warn",
            tone === "danger" && "bg-danger animate-pulse-dot",
            tone === "info" && "bg-info",
            tone === "muted" && "bg-ink-muted",
            tone === "brand" && "bg-brand-500",
          )}
        />
      )}
      {children}
    </span>
  );
}
