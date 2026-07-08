import { NavLink } from "react-router-dom";
import { cn } from "@/lib/cn";
import {
  LayoutDashboard,
  Cpu,
  Radar,
  Building2,
  MapPin,
  Users,
  HardHat,
  CreditCard,
  ClipboardList,
  Bell,
  Sparkles,
  ShieldCheck,
  Server,
  UploadCloud,
} from "lucide-react";

type NavItem = {
  to: string;
  label: string;
  icon: React.ComponentType<{ className?: string }>;
  end?: boolean;
};

const NAV: NavItem[] = [
  { to: "/", label: "Dashboard", icon: LayoutDashboard, end: true },
  { to: "/events", label: "Événements live", icon: Radar },
  { to: "/devices", label: "Équipements", icon: Cpu },
  { to: "/attendance", label: "Feuille présence", icon: ClipboardList },
  { to: "/sites", label: "Sites", icon: MapPin },
  { to: "/companies", label: "Sociétés", icon: Building2 },
  { to: "/employees", label: "Employés", icon: Users },
  { to: "/workers", label: "Ouvriers", icon: HardHat },
  { to: "/badges", label: "Badges", icon: CreditCard },
  { to: "/badges/bulk-enroll", label: "Enrôlement en masse", icon: UploadCloud },
  { to: "/notifications", label: "Notifications", icon: Bell },
  { to: "/ai", label: "Assistant IA", icon: Sparkles },
  { to: "/system", label: "État système", icon: Server },
];

export function Sidebar() {
  return (
    <aside className="hidden lg:flex flex-col w-60 shrink-0 border-r border-surface-border bg-surface-soft/40 backdrop-blur-sm">
      {/* Brand */}
      <div className="flex items-center gap-2.5 px-5 h-16 border-b border-surface-border">
        <ShieldCheck className="w-6 h-6 text-brand-500" />
        <div className="flex flex-col leading-tight">
          <span className="text-sm font-semibold text-ink">KAYDAN</span>
          <span className="text-[10px] font-medium text-brand-500 tracking-widest">
            SHIELD
          </span>
        </div>
      </div>

      {/* Nav */}
      <nav className="flex-1 py-3 px-2 space-y-0.5 overflow-y-auto">
        {NAV.map((item) => (
          <NavLink
            key={item.to}
            to={item.to}
            end={item.end}
            className={({ isActive }) =>
              cn(
                "flex items-center gap-3 px-3 py-2 rounded-lg text-sm transition-all",
                isActive
                  ? "bg-brand-500/10 text-brand-400 border-l-2 border-brand-500"
                  : "text-ink-muted hover:text-ink hover:bg-surface-soft",
              )
            }
          >
            <item.icon className="w-4 h-4" />
            <span className="truncate">{item.label}</span>
          </NavLink>
        ))}
      </nav>

      <div className="px-4 py-3 border-t border-surface-border text-[11px] text-ink-soft">
        v1.0 · {new Date().getFullYear()}
      </div>
    </aside>
  );
}
