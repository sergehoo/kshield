import { useNavigate } from "react-router-dom";
import { useAuthStore } from "@/lib/auth";
import { initials } from "@/lib/format";
import { useQuery } from "@tanstack/react-query";
import { notificationsService } from "@/services";
import { Bell, LogOut, Search } from "lucide-react";

export function Topbar() {
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

  return (
    <header className="sticky top-0 z-40 flex items-center gap-3 h-16 px-4 md:px-6 border-b border-surface-border bg-surface/70 backdrop-blur-md">
      {/* Search */}
      <div className="flex-1 max-w-xl relative">
        <Search className="w-4 h-4 absolute left-3 top-1/2 -translate-y-1/2 text-ink-soft pointer-events-none" />
        <input
          className="w-full pl-10 pr-3 py-2 rounded-lg bg-surface-soft/60 border border-surface-border text-sm text-ink placeholder-ink-soft focus:outline-none focus:ring-2 focus:ring-brand-500/40"
          placeholder="Rechercher un employé, badge, site…"
        />
      </div>

      <div className="flex items-center gap-2">
        <button
          onClick={() => navigate("/notifications")}
          className="relative p-2 rounded-lg text-ink-muted hover:text-ink hover:bg-surface-soft transition-colors"
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
            <div className="w-8 h-8 rounded-full bg-brand-500/20 text-brand-400 grid place-items-center text-xs font-semibold">
              {initials(user.full_name || user.email)}
            </div>
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
              className="p-2 rounded-lg text-ink-muted hover:text-danger hover:bg-danger/10 transition-colors"
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
