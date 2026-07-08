import { useState } from "react";
import { useSearchParams, useNavigate } from "react-router-dom";
import { useMutation } from "@tanstack/react-query";
import { authService } from "@/services";
import { useAuthStore } from "@/lib/auth";
import { toApiError } from "@/lib/api";
import { Input } from "@/components/ui/Input";
import { Button } from "@/components/ui/Button";
import { Eye, EyeOff, Mail, Lock } from "lucide-react";
import toast from "react-hot-toast";

export function LoginPage() {
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  const setTokens = useAuthStore((s) => s.setTokens);
  const setUser = useAuthStore((s) => s.setUser);
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPwd, setShowPwd] = useState(false);

  const mutation = useMutation({
    mutationFn: async () => {
      const r = await authService.login(email, password);
      return r.data;
    },
    onSuccess: async ({ access, refresh, user }) => {
      setTokens({ accessToken: access, refreshToken: refresh });
      // Le backend renvoie déjà `user` dans la réponse login — on l'hydrate direct.
      if (user) {
        setUser(user);
      } else {
        try {
          const me = await authService.me();
          setUser(me.data);
        } catch {
          /* silencieux */
        }
      }
      toast.success("Bienvenue sur KAYDAN SHIELD");
      const next = searchParams.get("next") || "/";
      navigate(next, { replace: true });
    },
    onError: (err) => {
      const e = toApiError(err);
      toast.error(e.status === 401 ? "Identifiants invalides" : e.message);
    },
  });

  return (
    <div className="w-full max-w-md">
      <h2 className="text-2xl font-bold text-ink">Connexion</h2>
      <p className="mt-1 text-sm text-ink-muted">
        Accédez à votre cockpit KAYDAN SHIELD.
      </p>

      <form
        className="mt-8 space-y-4"
        onSubmit={(e) => {
          e.preventDefault();
          if (!email || !password) {
            toast.error("Renseignez email et mot de passe");
            return;
          }
          mutation.mutate();
        }}
      >
        <Input
          label="Email"
          type="email"
          autoComplete="username"
          leftIcon={<Mail className="w-4 h-4" />}
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          placeholder="prenom.nom@kaydangroupe.com"
          required
        />

        <Input
          label="Mot de passe"
          type={showPwd ? "text" : "password"}
          autoComplete="current-password"
          leftIcon={<Lock className="w-4 h-4" />}
          rightIcon={
            <button
              type="button"
              onClick={() => setShowPwd((s) => !s)}
              className="text-ink-soft hover:text-ink"
              tabIndex={-1}
            >
              {showPwd ? <EyeOff className="w-4 h-4" /> : <Eye className="w-4 h-4" />}
            </button>
          }
          value={password}
          onChange={(e) => setPassword(e.target.value)}
          placeholder="••••••••"
          required
        />

        <Button
          type="submit"
          className="w-full justify-center"
          loading={mutation.isPending}
        >
          Se connecter
        </Button>
      </form>

      <div className="mt-6 pt-6 border-t border-surface-border">
        <a
          href={
            (import.meta.env.VITE_API_BASE_URL || "") + "/sso/login/?next=/"
          }
          className="btn-ghost w-full justify-center flex"
        >
          Connexion SSO Keycloak
        </a>
      </div>
    </div>
  );
}
