import { Outlet, Navigate } from "react-router-dom";
import { useAuthStore } from "@/lib/auth";
import { ShieldCheck } from "lucide-react";
import { ThemeToggle } from "@/components/ThemeToggle";

export function AuthLayout() {
  const isAuthed = useAuthStore((s) => s.isAuthenticated);
  if (isAuthed) return <Navigate to="/" replace />;

  return (
    <div className="min-h-screen grid lg:grid-cols-2">
      {/* Hero */}
      <aside className="hidden lg:flex relative flex-col justify-between p-12 bg-gradient-to-br from-brand-600/20 via-surface to-info/10">
        <div className="flex items-center gap-2.5">
          <ShieldCheck className="w-8 h-8 text-brand-ink" />
          <div>
            <div className="text-sm font-semibold text-ink">KAYDAN</div>
            <div className="text-xs text-brand-ink tracking-widest font-medium">
              SHIELD
            </div>
          </div>
        </div>
        <div className="max-w-md">
          <h1 className="text-3xl font-bold text-ink leading-tight">
            Cockpit unifié de contrôle d'accès, présence & anti-fraude
          </h1>
          <p className="mt-4 text-ink-muted">
            Surveillez vos chantiers, vos badges et vos terminaux biométriques en
            temps réel. Une seule interface pour piloter toute votre sécurité
            terrain.
          </p>
        </div>
        <div className="text-xs text-ink-soft">
          © {new Date().getFullYear()} KAYDAN GROUPE · Tous droits réservés
        </div>
      </aside>

      <main className="flex items-center justify-center p-6 relative">
        {/* Toggle thème coin haut-droit */}
        <div className="absolute top-4 right-4">
          <ThemeToggle compact />
        </div>
        <Outlet />
      </main>
    </div>
  );
}
