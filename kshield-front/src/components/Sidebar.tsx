import { NavLink } from "react-router-dom";
import { cn } from "@/lib/cn";
import {
  LayoutDashboard, Cpu, Radar, Building2, MapPin, Users, HardHat,
  CreditCard, ClipboardList, Bell, Sparkles, ShieldCheck, Server,
  UploadCloud, Camera, UserCheck, FileSpreadsheet, ShieldAlert,
  Calendar, ScanFace, Package, KeyRound, ScrollText, Shield, User,
  Cog, MapIcon, Tv2, FileUp,
} from "lucide-react";
import { LivePulse } from "@/components/LivePulse";
import { useAuthStore } from "@/lib/auth";

type NavItem = {
  to: string;
  label: string;
  icon: React.ComponentType<{ className?: string }>;
  end?: boolean;
  badge?: React.ReactNode;
};

type NavSection = {
  label: string;
  items: NavItem[];
};

const SECTIONS: NavSection[] = [
  {
    label: "Cockpit",
    items: [
      { to: "/", label: "Dashboard", icon: LayoutDashboard, end: true, badge: <LivePulse label="live" /> },
      { to: "/events", label: "Événements live", icon: Radar },
      { to: "/antifraud", label: "Anti-fraude", icon: ShieldAlert },
      { to: "/kiosk", label: "Kiosk (plein écran)", icon: Tv2 },
      { to: "/system", label: "État système", icon: Server },
    ],
  },
  {
    label: "Terrain",
    items: [
      { to: "/sites", label: "Sites", icon: MapPin },
      { to: "/sites/map", label: "Carte des chantiers", icon: MapIcon },
      { to: "/companies", label: "Sociétés", icon: Building2 },
      { to: "/employees", label: "Employés", icon: Users },
      { to: "/workers", label: "Ouvriers", icon: HardHat },
      { to: "/visitors", label: "Visiteurs", icon: UserCheck },
      { to: "/bulk-import", label: "Import en masse (CSV)", icon: FileUp },
    ],
  },
  {
    label: "Équipements",
    items: [
      { to: "/devices", label: "Terminaux", icon: Cpu },
      { to: "/cameras", label: "Caméras", icon: Camera },
      { to: "/badges", label: "Badges", icon: CreditCard },
      { to: "/helmets", label: "Casques BLE", icon: HardHat },
      { to: "/badges/bulk-enroll", label: "Enrôlement en masse", icon: UploadCloud },
      { to: "/face-recognition", label: "Reconnaissance faciale", icon: ScanFace },
      { to: "/firmwares", label: "Firmwares & OTA", icon: Package },
    ],
  },
  {
    label: "Présence & rapports",
    items: [
      { to: "/attendance", label: "Feuille de présence", icon: ClipboardList },
      { to: "/roster", label: "Planning", icon: Calendar },
      { to: "/reports", label: "Rapports & exports", icon: FileSpreadsheet },
    ],
  },
  {
    label: "Administration",
    items: [
      { to: "/users", label: "Utilisateurs", icon: User },
      { to: "/roles", label: "Rôles & permissions", icon: Shield },
      { to: "/api-keys", label: "Clés API", icon: KeyRound },
      { to: "/audit", label: "Journal d'audit", icon: ScrollText },
    ],
  },
  {
    label: "Compte",
    items: [
      { to: "/notifications", label: "Notifications", icon: Bell },
      { to: "/ai", label: "Assistant IA", icon: Sparkles },
      { to: "/settings", label: "Paramètres", icon: Cog },
    ],
  },
];

export function Sidebar({ open, onClose }: { open?: boolean; onClose?: () => void }) {
  const user = useAuthStore((s) => s.user);

  // Filtre les sections selon les droits (super admin voit tout, sinon on masque
  // "Administration" pour les non-staff).
  const isAdmin = user?.is_superuser || user?.is_staff;
  const filteredSections = SECTIONS.filter((sec) => {
    if (sec.label === "Administration" && !isAdmin) return false;
    return true;
  });

  return (
    <>
      {/* Backdrop mobile */}
      {open && (
        <div
          className="fixed inset-0 bg-black/60 backdrop-blur-sm z-30 lg:hidden"
          onClick={onClose}
        />
      )}

      <aside
        className={cn(
          "fixed lg:sticky top-0 z-40 h-screen w-64 shrink-0 flex flex-col",
          "border-r border-surface-border bg-surface-soft/60 backdrop-blur-xl",
          "transition-transform duration-200 ease-out",
          open ? "translate-x-0" : "-translate-x-full lg:translate-x-0",
        )}
      >
        {/* Brand */}
        <div className="flex items-center gap-2.5 px-5 h-16 border-b border-surface-border shrink-0">
          <ShieldCheck className="w-6 h-6 text-brand-500" />
          <div className="flex flex-col leading-tight">
            <span className="text-sm font-semibold text-ink">KAYDAN</span>
            <span className="text-[10px] font-medium text-brand-500 tracking-widest">
              SHIELD
            </span>
          </div>
        </div>

        {/* Nav */}
        <nav className="flex-1 py-3 px-2 space-y-4 overflow-y-auto">
          {filteredSections.map((section) => (
            <div key={section.label}>
              <div className="px-3 mb-1 text-[10px] uppercase tracking-widest text-ink-soft font-semibold">
                {section.label}
              </div>
              <div className="space-y-0.5">
                {section.items.map((item) => (
                  <NavLink
                    key={item.to}
                    to={item.to}
                    end={item.end}
                    onClick={onClose}
                    className={({ isActive }) =>
                      cn(
                        "flex items-center gap-3 px-3 py-2 rounded-lg text-sm transition",
                        isActive
                          ? "bg-brand-500/10 text-brand-400 border-l-2 border-brand-500"
                          : "text-ink-muted hover:text-ink hover:bg-surface-soft",
                      )
                    }
                  >
                    <item.icon className="w-4 h-4 shrink-0" />
                    <span className="truncate flex-1">{item.label}</span>
                    {item.badge}
                  </NavLink>
                ))}
              </div>
            </div>
          ))}
        </nav>

        <div className="px-4 py-3 border-t border-surface-border text-[11px] text-ink-soft shrink-0">
          v1.0 · {new Date().getFullYear()} KAYDAN
        </div>
      </aside>
    </>
  );
}
