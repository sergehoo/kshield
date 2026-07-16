import { useState } from "react";
import { NavLink } from "react-router-dom";
import { cn } from "@/lib/cn";
import {
  LayoutDashboard, Cpu, Radar, Building2, MapPin, Users, HardHat,
  CreditCard, ClipboardList, Bell, Sparkles, ShieldCheck, Server,
  Camera, UserCheck, FileSpreadsheet, ShieldAlert,
  Calendar, ScanFace, Package, KeyRound, ScrollText, Shield,
  Cog, Tv2, FileUp, Briefcase, Palmtree, Clock, Smartphone, Archive,
  ChevronDown, ChevronRight, ChevronsLeft, ChevronsRight, Settings2,
  Network,
} from "lucide-react";
import { LivePulse } from "@/components/LivePulse";
import { useAuthStore } from "@/lib/auth";
import { useSidebarStore } from "@/lib/sidebarStore";

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
  defaultCollapsed?: boolean;
};

/**
 * Sidebar épurée — 8 sections principales avec les items essentiels.
 *
 * Principes de regroupement :
 *  - Les pages complémentaires (ex: Cameras + Mur live, Badges + Bulk-enroll)
 *    ne dupliquent plus dans la sidebar : les pages principales exposent des
 *    boutons/liens vers leurs sous-vues directement dans l'UI.
 *  - La section "Référentiels" (repliée par défaut) contient les items rares :
 *    zones, catalogue modèles, motifs de visite, métiers, etc.
 *  - Sections admin masquées automatiquement aux non-staff.
 */
const SECTIONS: NavSection[] = [
  {
    label: "Cockpit",
    items: [
      { to: "/",                     label: "Dashboard",       icon: LayoutDashboard, end: true, badge: <LivePulse label="live" /> },
      { to: "/events",               label: "Événements live", icon: Radar,           end: true },
      { to: "/antifraud",            label: "Anti-fraude",     icon: ShieldAlert,     end: true },
      { to: "/kiosk",                label: "Kiosk plein écran", icon: Tv2,           end: true },
      { to: "/system",               label: "État système",    icon: Server,          end: true },
    ],
  },
  {
    label: "Terrain",
    items: [
      { to: "/sites",         label: "Sites & carte",   icon: MapPin,    end: true },
      { to: "/companies",     label: "Filiales",        icon: Building2, end: true },
      { to: "/subcontractors", label: "Sous-traitants", icon: Briefcase, end: true },
    ],
  },
  {
    label: "Personnes",
    items: [
      { to: "/employees",   label: "Employés",   icon: Users,    end: true },
      { to: "/workers",     label: "Ouvriers",   icon: HardHat,  end: true },
      { to: "/visitors",    label: "Visiteurs",  icon: UserCheck, end: true },
      { to: "/bulk-import", label: "Import CSV", icon: FileUp,   end: true },
    ],
  },
  {
    label: "Équipements",
    items: [
      { to: "/devices",           label: "Terminaux",     icon: Cpu,        end: true },
      { to: "/devices/discovery", label: "Découverte réseau", icon: Radar, end: true },
      { to: "/cameras",           label: "Caméras",       icon: Camera,     end: true },
      { to: "/badges",            label: "Badges",        icon: CreditCard, end: true },
      { to: "/helmets",           label: "Casques BLE",   icon: HardHat,    end: true },
      { to: "/face-recognition",  label: "Reconnaissance faciale", icon: ScanFace, end: true },
      { to: "/firmwares",         label: "Firmwares & OTA", icon: Package,  end: true },
    ],
  },
  {
    label: "Présence & RH",
    items: [
      { to: "/attendance", label: "Feuille présence", icon: ClipboardList, end: true },
      { to: "/roster",     label: "Planning",         icon: Calendar,      end: true },
      { to: "/leaves",     label: "Congés",           icon: Palmtree,      end: true },
      { to: "/overtime-calcs", label: "Heures supp",  icon: Clock,         end: true },
    ],
  },
  {
    label: "Rapports & IA",
    items: [
      { to: "/reports",    label: "Rapports & exports", icon: FileSpreadsheet, end: true },
      { to: "/dashboards", label: "Dashboards custom", icon: LayoutDashboard, end: true },
      { to: "/ai",         label: "Assistant IA",      icon: Sparkles,        end: true },
    ],
  },
  {
    label: "Sécurité",
    defaultCollapsed: true,
    items: [
      { to: "/fraud-investigations", label: "Investigations", icon: ShieldAlert, end: true },
      { to: "/access-rules",         label: "Règles d'accès", icon: Shield,      end: true },
      { to: "/audit",                label: "Journal d'audit", icon: ScrollText, end: true },
      { to: "/retention-policies",   label: "RGPD & rétention", icon: Archive,   end: true },
    ],
  },
  {
    label: "Administration",
    defaultCollapsed: true,
    items: [
      { to: "/users",          label: "Utilisateurs & rôles", icon: Users,      end: true },
      { to: "/api-keys",       label: "Clés API",             icon: KeyRound,   end: true },
      { to: "/edge-gateway",   label: "Edge Gateway",         icon: Server,     end: true },
      { to: "/agents",         label: "Supervision agents",   icon: Cpu,        end: false },
      { to: "/local-agents",   label: "Agents (provisioning)", icon: Server,    end: true },
      { to: "/sync/conflicts", label: "Conflits sync",        icon: Network,    end: true },
      { to: "/drivers",        label: "Drivers",              icon: Cpu,        end: true },
      { to: "/discovery",      label: "Découverte (legacy)",  icon: Radar,      end: true },
      { to: "/topology",       label: "Topologie",            icon: Network,    end: true },
      { to: "/marketplace",    label: "Marketplace",          icon: Package,    end: true },
      { to: "/maintenance",    label: "Maintenance",          icon: Cog,        end: true },
      { to: "/alerts",         label: "Alertes système",      icon: ShieldAlert, end: true },
      { to: "/mobile-devices", label: "Appareils mobiles",    icon: Smartphone, end: true },
      { to: "/config",         label: "Configuration",        icon: Settings2,  end: true },
    ],
  },
  {
    label: "Compte",
    items: [
      { to: "/notifications", label: "Notifications", icon: Bell, end: true },
      { to: "/settings",      label: "Paramètres",    icon: Cog,  end: true },
    ],
  },
];

export function Sidebar({ open, onClose }: { open?: boolean; onClose?: () => void }) {
  const user = useAuthStore((s) => s.user);
  const { collapsed, toggle, collapsedSections, toggleSection } = useSidebarStore();

  const [initedDefaults, setInitedDefaults] = useState(false);
  if (!initedDefaults) {
    setInitedDefaults(true);
    if (collapsedSections.length === 0) {
      SECTIONS.filter((s) => s.defaultCollapsed).forEach((s) => toggleSection(s.label));
    }
  }

  const isAdmin = user?.is_superuser || user?.is_staff;
  const filteredSections = SECTIONS.filter((sec) => {
    if (!isAdmin && (sec.label === "Administration" || sec.label === "Sécurité")) {
      return false;
    }
    return true;
  });

  const width = collapsed ? "w-16" : "w-60";

  return (
    <>
      {open && (
        <div
          className="fixed inset-0 bg-black/60 backdrop-blur-sm z-30 lg:hidden"
          onClick={onClose}
        />
      )}

      <aside
        className={cn(
          "fixed lg:sticky top-3 lg:top-3 z-40 shrink-0 flex flex-col",
          // Style Dappr : sidebar flottante noire arrondie
          "bg-ink text-white rounded-3xl m-3 h-[calc(100vh-1.5rem)]",
          "transition-all duration-200 ease-out",
          width,
          open ? "translate-x-0" : "-translate-x-full lg:translate-x-0",
        )}
      >
        {/* Brand — logo Kaydan Shield */}
        <div className={cn(
          "flex items-center h-16 border-b border-white/10 shrink-0",
          collapsed ? "justify-center px-2" : "gap-2.5 px-5",
        )}>
          <ShieldCheck className="w-6 h-6 text-brand-400 shrink-0" />
          {!collapsed && (
            <div className="flex flex-col leading-tight">
              <span className="text-sm font-semibold text-white">KAYDAN</span>
              <span className="text-[10px] font-medium text-brand-400 tracking-widest">
                SHIELD
              </span>
            </div>
          )}
        </div>

        {/* Nav */}
        <nav className={cn(
          "flex-1 py-3 space-y-3 overflow-y-auto text-[13px]",
          collapsed ? "px-1.5" : "px-2",
        )}>
          {filteredSections.map((section) => {
            const isSectionCollapsed = collapsedSections.includes(section.label);
            return (
              <div key={section.label}>
                {!collapsed && (
                  <button
                    onClick={() => toggleSection(section.label)}
                    className="w-full px-3 mb-1 flex items-center justify-between text-[11px] uppercase tracking-widest text-white/70 font-semibold hover:text-white transition"
                  >
                    <span>{section.label}</span>
                    {isSectionCollapsed ? (
                      <ChevronRight className="w-3.5 h-3.5" />
                    ) : (
                      <ChevronDown className="w-3.5 h-3.5" />
                    )}
                  </button>
                )}

                {collapsed && <div className="mx-2 mb-1 h-px bg-white/10" />}

                {(collapsed || !isSectionCollapsed) && (
                  <div className="space-y-0.5">
                    {section.items.map((item) => (
                      <NavLink
                        key={item.to}
                        to={item.to}
                        end={item.end}
                        onClick={onClose}
                        title={collapsed ? item.label : undefined}
                        className={({ isActive }) =>
                          cn(
                            "flex items-center rounded-xl transition group",
                            collapsed ? "justify-center p-2.5" : "gap-3 px-3 py-2",
                            isActive
                              ? "bg-white text-ink font-semibold shadow-sm"
                              : "text-white/75 hover:text-white hover:bg-white/10",
                          )
                        }
                      >
                        <item.icon className="w-4 h-4 shrink-0" />
                        {!collapsed && (
                          <>
                            <span className="truncate flex-1">{item.label}</span>
                            {item.badge}
                          </>
                        )}
                      </NavLink>
                    ))}
                  </div>
                )}
              </div>
            );
          })}
        </nav>

        {/* Footer */}
        <div className={cn(
          "border-t border-white/10 shrink-0 flex items-center gap-2",
          collapsed ? "flex-col p-2" : "px-3 py-2 justify-between",
        )}>
          {!collapsed && (
            <div className="text-[11px] text-white/40">
              v1.0 · {new Date().getFullYear()}
            </div>
          )}
          <button
            onClick={toggle}
            className="p-1.5 rounded-md hover:bg-white/10 text-white/60 hover:text-white transition"
            title={collapsed ? "Déployer" : "Réduire"}
          >
            {collapsed ? <ChevronsRight className="w-4 h-4" /> : <ChevronsLeft className="w-4 h-4" />}
          </button>
        </div>
      </aside>
    </>
  );
}
