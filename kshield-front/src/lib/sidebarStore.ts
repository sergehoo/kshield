/**
 * Sidebar UI state — collapsed mode + sections déployées.
 * Persisté localStorage pour survivre aux rechargements de page.
 */
import { create } from "zustand";
import { persist, createJSONStorage } from "zustand/middleware";

type SidebarState = {
  collapsed: boolean;
  toggle: () => void;
  setCollapsed: (v: boolean) => void;
  // Sections repliées (par label) — vide par défaut = toutes déployées
  collapsedSections: string[];
  toggleSection: (label: string) => void;
};

export const useSidebarStore = create<SidebarState>()(
  persist(
    (set, get) => ({
      collapsed: false,
      toggle: () => set({ collapsed: !get().collapsed }),
      setCollapsed: (v) => set({ collapsed: v }),
      collapsedSections: [],
      toggleSection: (label) => {
        const cs = get().collapsedSections;
        set({
          collapsedSections: cs.includes(label)
            ? cs.filter((l) => l !== label)
            : [...cs, label],
        });
      },
    }),
    {
      name: "kshield-sidebar",
      storage: createJSONStorage(() => localStorage),
    },
  ),
);
