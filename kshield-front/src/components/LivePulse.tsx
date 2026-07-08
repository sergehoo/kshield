import { cn } from "@/lib/cn";

/**
 * Petit "vivant" indicator — dot vert clignotant + label optionnel.
 * Utilisé pour signaler qu'une vue est en polling temps réel.
 */
export function LivePulse({
  label = "LIVE",
  active = true,
  className,
}: {
  label?: string;
  active?: boolean;
  className?: string;
}) {
  return (
    <span
      className={cn(
        "inline-flex items-center gap-2 px-2 py-0.5 rounded-full text-[10px] font-semibold tracking-wider uppercase",
        active
          ? "text-ok bg-ok/10 border border-ok/20"
          : "text-ink-muted bg-white/5 border border-white/10",
        className,
      )}
    >
      <span
        className={cn(
          "w-1.5 h-1.5 rounded-full",
          active ? "bg-ok animate-pulse-dot" : "bg-ink-soft",
        )}
      />
      {label}
    </span>
  );
}
