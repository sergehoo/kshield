import { Sun, Moon, Monitor } from "lucide-react";
import { useThemeStore, resolveTheme, type ThemeMode } from "@/lib/theme";
import { cn } from "@/lib/cn";

/**
 * Toggle 3-position : Light | Dark | System.
 * Rendu compact en topbar, plus large en settings.
 */
export function ThemeToggle({ compact = false }: { compact?: boolean }) {
  const mode = useThemeStore((s) => s.mode);
  const setMode = useThemeStore((s) => s.setMode);
  const resolved = resolveTheme(mode);

  if (compact) {
    // Version compacte : un seul bouton qui cycle light → dark → system
    const nextMode: ThemeMode =
      mode === "light" ? "dark" : mode === "dark" ? "system" : "light";
    const Icon =
      mode === "light" ? Sun : mode === "dark" ? Moon : Monitor;
    return (
      <button
        onClick={() => setMode(nextMode)}
        className="p-2 rounded-lg text-ink-muted hover:text-ink hover:bg-surface-soft transition"
        title={
          mode === "light"
            ? "Passer en sombre"
            : mode === "dark"
            ? "Passer en automatique (OS)"
            : `Automatique (actuellement ${resolved === "dark" ? "sombre" : "clair"})`
        }
      >
        <Icon className="w-5 h-5" />
      </button>
    );
  }

  return (
    <div className="inline-flex rounded-lg bg-surface-soft p-0.5 border border-surface-border">
      {(
        [
          { key: "light", label: "Clair", icon: Sun },
          { key: "dark", label: "Sombre", icon: Moon },
          { key: "system", label: "Système", icon: Monitor },
        ] as const
      ).map((opt) => (
        <button
          key={opt.key}
          onClick={() => setMode(opt.key as ThemeMode)}
          className={cn(
            "flex items-center gap-1.5 px-3 py-1.5 rounded-md text-xs font-medium transition",
            mode === opt.key
              ? "bg-brand-500 text-white shadow"
              : "text-ink-muted hover:text-ink",
          )}
        >
          <opt.icon className="w-3.5 h-3.5" />
          {opt.label}
        </button>
      ))}
    </div>
  );
}
