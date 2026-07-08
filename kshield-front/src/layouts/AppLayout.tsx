import { useState, useEffect } from "react";
import { Outlet, useLocation, Navigate } from "react-router-dom";
import { Sidebar } from "@/components/Sidebar";
import { Topbar } from "@/components/Topbar";
import { CommandPalette } from "@/components/CommandPalette";
import { useAuthStore } from "@/lib/auth";
import { authService } from "@/services";
import { useRealtimeAlerts } from "@/hooks/useRealtimeAlerts";

export function AppLayout() {
  const isAuthed = useAuthStore((s) => s.isAuthenticated);
  const setUser = useAuthStore((s) => s.setUser);
  const user = useAuthStore((s) => s.user);
  const location = useLocation();
  const [sidebarOpen, setSidebarOpen] = useState(false);
  const [paletteOpen, setPaletteOpen] = useState(false);

  // Hook global : abonnements temps réel aux alertes fraude + notifications
  useRealtimeAlerts();

  // Hydrate profil utilisateur si on n'a que le token
  useEffect(() => {
    if (isAuthed && !user) {
      authService
        .me()
        .then((r) => setUser(r.data))
        .catch(() => void 0);
    }
  }, [isAuthed, user, setUser]);

  // Ferme le sidebar mobile au changement de route
  useEffect(() => {
    setSidebarOpen(false);
  }, [location.pathname]);

  // Raccourci Cmd/Ctrl + K → command palette
  useEffect(() => {
    const onKey = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === "k") {
        e.preventDefault();
        setPaletteOpen((p) => !p);
      }
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, []);

  if (!isAuthed) {
    const next = encodeURIComponent(location.pathname + location.search);
    return <Navigate to={`/login?next=${next}`} replace />;
  }

  return (
    <div className="flex min-h-screen">
      <Sidebar open={sidebarOpen} onClose={() => setSidebarOpen(false)} />
      <div className="flex-1 flex flex-col min-w-0">
        <Topbar
          onMenuClick={() => setSidebarOpen((s) => !s)}
          onSearchClick={() => setPaletteOpen(true)}
        />
        <main className="flex-1 px-4 md:px-6 py-5 min-w-0">
          <Outlet />
        </main>
      </div>
      <CommandPalette open={paletteOpen} onClose={() => setPaletteOpen(false)} />
    </div>
  );
}
