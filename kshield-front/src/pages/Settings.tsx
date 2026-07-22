import { useState } from "react";
import { useAuthStore } from "@/lib/auth";
import { PageHeader } from "@/components/PageHeader";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Badge } from "@/components/ui/Badge";
import { initials } from "@/lib/format";
import { User, Bell, Shield, Palette, KeyRound, LogOut } from "lucide-react";
import { useNavigate } from "react-router-dom";
import toast from "react-hot-toast";
import { ThemeToggle } from "@/components/ThemeToggle";

/**
 * Page Profil / Paramètres — préférences user et données personnelles.
 */
export function SettingsPage() {
  const user = useAuthStore((s) => s.user);
  const logout = useAuthStore((s) => s.logout);
  const navigate = useNavigate();
  const [pollInterval, setPollInterval] = useState(
    localStorage.getItem("kshield-poll-ms") || "15000",
  );

  const savePreferences = () => {
    localStorage.setItem("kshield-poll-ms", pollInterval);
    toast.success("Préférences sauvegardées");
    // Force reload pour appliquer l'intervalle
    setTimeout(() => window.location.reload(), 500);
  };

  return (
    <div>
      <PageHeader
        title="Profil & Paramètres"
        subtitle="Vos préférences et informations personnelles"
      />

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-4">
        {/* Profil */}
        <Card
          title={
            <span className="flex items-center gap-2">
              <User className="w-4 h-4 text-brand-ink" /> Profil
            </span>
          }
        >
          <div className="flex flex-col items-center text-center pb-4 border-b border-surface-border">
            <div className="w-20 h-20 rounded-2xl bg-brand-500/20 text-brand-ink grid place-items-center text-2xl font-bold border-2 border-brand-500/30">
              {initials(user?.full_name || user?.email)}
            </div>
            <h3 className="mt-3 text-sm font-semibold text-ink">
              {user?.full_name || user?.email || "—"}
            </h3>
            <div className="text-xs text-ink-muted">{user?.email}</div>
            {user?.is_superuser && (
              <Badge tone="danger" className="mt-2">
                Super admin
              </Badge>
            )}
          </div>

          <div className="pt-4 space-y-2 text-sm">
            <Row label="ID utilisateur" value={String(user?.id ?? "—")} mono />
            <Row label="Tenant" value={user?.tenant?.name || "—"} />
            <Row
              label="Rôles"
              value={user?.roles?.join(", ") || "Aucun rôle assigné"}
            />
          </div>

          <button
            onClick={() => {
              logout();
              navigate("/login", { replace: true });
            }}
            className="mt-4 w-full inline-flex items-center justify-center gap-2 px-3.5 py-2 rounded-lg bg-danger/10 hover:bg-danger/20 text-danger text-sm font-medium"
          >
            <LogOut className="w-4 h-4" /> Se déconnecter
          </button>
        </Card>

        {/* Préférences */}
        <Card
          title={
            <span className="flex items-center gap-2">
              <Palette className="w-4 h-4 text-info" /> Préférences interface
            </span>
          }
        >
          <div className="space-y-4">
            <div>
              <div className="text-xs font-medium text-ink-muted mb-2">
                Thème d'affichage
              </div>
              <ThemeToggle />
              <p className="mt-1.5 text-xs text-ink-soft">
                "Système" suit automatiquement les préférences de votre OS.
              </p>
            </div>

            <label className="block">
              <span className="text-xs font-medium text-ink-muted">
                Intervalle de rafraîchissement (ms)
              </span>
              <select
                value={pollInterval}
                onChange={(e) => setPollInterval(e.target.value)}
                className="field mt-1.5 w-full"
              >
                <option value="5000">5 secondes (temps réel intense)</option>
                <option value="10000">10 secondes</option>
                <option value="15000">15 secondes (recommandé)</option>
                <option value="30000">30 secondes</option>
                <option value="60000">1 minute (économie)</option>
              </select>
              <p className="mt-1 text-xs text-ink-soft">
                Fréquence des mises à jour temps réel (dashboard, events live).
              </p>
            </label>

            <Button className="w-full justify-center" onClick={savePreferences}>
              Sauvegarder les préférences
            </Button>
          </div>
        </Card>

        {/* Sécurité */}
        <Card
          title={
            <span className="flex items-center gap-2">
              <Shield className="w-4 h-4 text-warn" /> Sécurité
            </span>
          }
        >
          <div className="space-y-3">
            <div className="p-3 rounded-lg bg-surface-soft/50">
              <div className="flex items-center justify-between">
                <span className="text-sm text-ink">2FA / MFA</span>
                <Badge tone={user?.roles?.includes("mfa") ? "ok" : "muted"}>
                  {user?.roles?.includes("mfa") ? "Activé" : "Désactivé"}
                </Badge>
              </div>
              <p className="mt-1 text-xs text-ink-soft">
                Ajoute une couche d'authentification via app OTP.
              </p>
            </div>

            <div className="p-3 rounded-lg bg-surface-soft/50">
              <div className="flex items-center gap-2 text-sm text-ink mb-2">
                <KeyRound className="w-3.5 h-3.5 text-ink-muted" />
                Changer le mot de passe
              </div>
              <p className="text-xs text-ink-soft mb-2">
                Contactez votre administrateur pour réinitialiser votre mot de passe.
              </p>
            </div>

            <div className="p-3 rounded-lg bg-info/5 border border-info/20">
              <div className="flex items-center gap-2 text-sm text-info mb-1">
                <Bell className="w-3.5 h-3.5" />
                Notifications navigateur
              </div>
              <button
                onClick={() => {
                  if (!("Notification" in window)) {
                    toast.error("Votre navigateur ne supporte pas les notifications");
                    return;
                  }
                  Notification.requestPermission().then((p) => {
                    if (p === "granted") {
                      toast.success("Notifications activées");
                      new Notification("KAYDAN SHIELD", {
                        body: "Les notifications sont actives",
                      });
                    }
                  });
                }}
                className="text-xs text-info hover:underline"
              >
                Activer les notifications desktop
              </button>
            </div>
          </div>
        </Card>
      </div>
    </div>
  );
}

function Row({ label, value, mono }: { label: string; value: string; mono?: boolean }) {
  return (
    <div className="flex items-center justify-between gap-3">
      <dt className="text-xs uppercase tracking-wider text-ink-soft">{label}</dt>
      <dd className={mono ? "text-xs font-mono text-ink" : "text-sm text-ink truncate"}>{value}</dd>
    </div>
  );
}
