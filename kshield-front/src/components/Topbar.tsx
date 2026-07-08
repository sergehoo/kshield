import { useNavigate } from "react-router-dom";
import { useAuthStore } from "@/lib/auth";
import { initials } from "@/lib/format";
import { useQuery } from "@tanstack/react-query";
import { notificationsService } from "@/services";
import { Bell, LogOut, Search, Menu, Command } from "lucide-react";
import { ThemeToggle } from "@/components/ThemeToggle";

type Props = {
  onMenuClick?: () => void;
  onSearchClick?: () => void;
};

export function Topbar({ onMenuClick, onSearchClick }: Props) {
  const navigate = useNavigate();
  const user = useAuthStore((s) => s.user);
  const logout = useAuthStore((s) => s.logout);

  const { data: unread } = useQuery({
    queryKey: ["notifications", "unread"],
    queryFn: async () => (await notificationsService.unread()).data,
    refetchInterval: 30_000,
    refetchIntervalInBackground: false,
  });

  const unreadCount = unread?.count ?? 0;
  const isMac = typeof navigator !== "undefined" && /Mac/i.test(navigator.platform);

  return (
    <header className="sticky top-0 z-30 flex items-center gap-2 h-16 px-3 md:px-6 border-b border-surface-border bg-surface/80 backdrop-blur-md">
      {/* Menu burger (mobile) */}
      <button
        onClick={onMenuClick}
        className="lg:hidden p-2 rounded-lg text-ink-muted hover:text-ink hover:bg-surface-soft"
        aria-label="Menu"
      >
        <Menu className="w-5 h-5" />
      </button>

      {/* Search — ouvre command palette */}
      <button
        onClick={onSearchClick}
        className="flex-1 max-w-xl flex items-center gap-2 pl-3 pr-2 py-2 rounded-lg bg-surface-soft/60 border border-surface-border text-sm text-ink-soft hover:border-brand-500/40 transition-all group"
      >
        <Search className="w-4 h-4" />
        <span className="flex-1 text-left">Rechercher, aller à…</span>
        <span className="hidden md:inline-flex items-center gap-1 px-1.5 py-0.5 rounded border border-surface-border text-[10px] font-mono">
          {isMac ? (
            <>
              <Command className="w-3 h-3" />K
            </>
          ) : (
            "Ctrl+K"
          )}
        </span>
      </button>

      <div className="flex items-center gap-2 ml-auto">
        <ThemeToggle compact />

        <button
          onClick={() => navigate("/notifications")}
          className="relative p-2 rounded-lg text-ink-muted hover:text-ink hover:bg-surface-soft"
          aria-label="Notifications"
        >
          <Bell className="w-5 h-5" />
          {unreadCount > 0 && (
            <span className="absolute -top-0.5 -right-0.5 min-w-[16px] h-4 px-1 rounded-full bg-danger text-white text-[10px] font-bold flex items-center justify-center">
              {unreadCount > 99 ? "99+" : unreadCount}
            </span>
          )}
        </button>

        {user && (
          <div className="flex items-center gap-2 pl-2 ml-1 border-l border-surface-border">
            <button
              onClick={() => navigate("/settings")}
              className="w-8 h-8 rounded-full bg-brand-500/20 text-brand-400 grid place-items-center text-xs font-semibold hover:ring-2 hover:ring-brand-500/40 transition"
              title="Profil & paramètres"
            >
              {initials(user.full_name || user.email)}
            </button>
            <div className="hidden md:flex flex-col leading-tight">
              <span className="text-xs font-medium text-ink truncate max-w-[160px]">
                {user.full_name || user.email}
              </span>
              <span className="text-[10px] text-ink-soft truncate">
                {user.tenant?.name || (user.is_superuser ? "Super admin" : "")}
              </span>
            </div>
            <button
              onClick={() => {
                logout();
                navigate("/login", { replace: true });
              }}
              className="p-2 rounded-lg text-ink-muted hover:text-danger hover:bg-danger/10"
              title="Déconnexion"
            >
              <LogOut className="w-4 h-4" />
            </button>
          </div>
        )}
      </div>
    </header>
  );
}
