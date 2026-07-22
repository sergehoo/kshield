/**
 * Theme store — clair, sombre, ou système.
 * Applique la classe `.dark` sur <html> pour que Tailwind switch les variables.
 */
import { create } from "zustand";
import { persist, createJSONStorage } from "zustand/middleware";

export type ThemeMode = "light" | "dark" | "system";

type ThemeState = {
  mode: ThemeMode;
  setMode: (m: ThemeMode) => void;
  toggle: () => void;
};

function systemPrefersDark(): boolean {
  return typeof window !== "undefined"
    ? window.matchMedia("(prefers-color-scheme: dark)").matches
    : true;
}

/**
 * Résout un mode "system" en dark|light selon la préférence OS.
 */
export function resolveTheme(mode: ThemeMode): "dark" | "light" {
  if (mode === "system") return systemPrefersDark() ? "dark" : "light";
  return mode;
}

/**
 * Applique la classe .dark ou .light sur <html> ET définit color-scheme.
 * Appelé au boot (main.tsx) et à chaque changement de mode.
 */
export function applyTheme(mode: ThemeMode) {
  if (typeof document === "undefined") return;
  const resolved = resolveTheme(mode);
  const html = document.documentElement;
  html.classList.toggle("dark", resolved === "dark");
  html.classList.toggle("light", resolved === "light");
  html.dataset.theme = resolved;
  html.style.colorScheme = resolved;
  document
    .querySelector('meta[name="theme-color"]')
    ?.setAttribute("content", resolved === "dark" ? "#0a0e14" : "#f6f8fb");
}

export const useThemeStore = create<ThemeState>()(
  persist(
    (set, get) => ({
      mode: "system",
      setMode: (m) => {
        set({ mode: m });
        applyTheme(m);
      },
      toggle: () => {
        // Si en system → passe au contraire de la préférence OS
        const current = resolveTheme(get().mode);
        const next: ThemeMode = current === "dark" ? "light" : "dark";
        set({ mode: next });
        applyTheme(next);
      },
    }),
    {
      name: "kshield-theme",
      storage: createJSONStorage(() => localStorage),
    },
  ),
);

// Écoute les changements de préférence OS quand on est en mode "system"
if (typeof window !== "undefined") {
  const mq = window.matchMedia("(prefers-color-scheme: dark)");
  mq.addEventListener?.("change", () => {
    const store = useThemeStore.getState();
    if (store.mode === "system") applyTheme("system");
  });
}
