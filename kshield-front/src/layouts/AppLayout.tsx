import { Outlet, useLocation } from "react-router-dom";
import { Sidebar } from "@/components/Sidebar";
import { Topbar } from "@/components/Topbar";
import { useAuthStore } from "@/lib/auth";
import { Navigate } from "react-router-dom";
import { useEffect } from "react";
import { authService } from "@/services";

export function AppLayout() {
  const isAuthed = useAuthStore((s) => s.isAuthenticated);
  const setUser = useAuthStore((s) => s.setUser);
  const user = useAuthStore((s) => s.user);
  const location = useLocation();

  // Hydrate le profil utilisateur si on n'a que le token
  useEffect(() => {
    if (isAuthed && !user) {
      authService
        .me()
        .then((r) => setUser(r.data))
        .catch(() => void 0);
    }
  }, [isAuthed, user, setUser]);

  if (!isAuthed) {
    const next = encodeURIComponent(location.pathname + location.search);
    return <Navigate to={`/login?next=${next}`} replace />;
  }

  return (
    <div className="flex h-screen overflow-hidden">
      <Sidebar />
      <div className="flex-1 flex flex-col overflow-hidden">
        <Topbar />
        <main className="flex-1 overflow-y-auto px-4 md:px-6 py-5">
          <Outlet />
        </main>
      </div>
    </div>
  );
}
