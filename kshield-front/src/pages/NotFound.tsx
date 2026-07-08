import { Link } from "react-router-dom";
import { Home, ShieldOff } from "lucide-react";

export function NotFoundPage() {
  return (
    <div className="min-h-[70vh] flex flex-col items-center justify-center text-center">
      <ShieldOff className="w-14 h-14 text-ink-soft" />
      <h1 className="mt-4 text-2xl font-bold text-ink">404 — Page introuvable</h1>
      <p className="mt-2 text-sm text-ink-muted">
        Cette page n'existe pas ou vous n'y avez pas accès.
      </p>
      <Link to="/" className="btn-primary mt-6 inline-flex">
        <Home className="w-4 h-4" /> Retour au dashboard
      </Link>
    </div>
  );
}
