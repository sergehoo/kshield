import { useEffect, useMemo, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { cn } from "@/lib/cn";
import {
  LayoutDashboard, Cpu, Radar, Building2, MapPin, Users, HardHat,
  CreditCard, ClipboardList, Bell, Sparkles, Server, UploadCloud, Camera,
  UserCheck, FileSpreadsheet, ShieldAlert, Calendar, ScanFace, Package,
  KeyRound, ScrollText, Shield, Cog, ArrowRight, Search, MapIcon,
  Tv2, FileUp,
} from "lucide-react";

type Cmd = {
  id: string;
  label: string;
  hint?: string;
  icon: React.ComponentType<{ className?: string }>;
  action: () => void;
  keywords?: string[];
};

/**
 * Cmd+K / Ctrl+K palette de commandes.
 * Fuzzy filter simple sur label + keywords.
 */
export function CommandPalette({ open, onClose }: { open: boolean; onClose: () => void }) {
  const navigate = useNavigate();
  const [q, setQ] = useState("");
  const [cursor, setCursor] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);

  const commands = useMemo<Cmd[]>(
    () => [
      { id: "home", label: "Dashboard", icon: LayoutDashboard, action: () => navigate("/") },
      { id: "events", label: "Événements live", icon: Radar, action: () => navigate("/events"), keywords: ["scans", "temps réel"] },
      { id: "devices", label: "Équipements", icon: Cpu, action: () => navigate("/devices"), keywords: ["terminaux", "lecteurs"] },
      { id: "cameras", label: "Caméras", icon: Camera, action: () => navigate("/cameras"), keywords: ["vidéo", "surveillance"] },
      { id: "sites", label: "Sites / Chantiers", icon: MapPin, action: () => navigate("/sites") },
      { id: "sites-map", label: "Carte des chantiers", icon: MapIcon, action: () => navigate("/sites/map"), keywords: ["map", "leaflet", "gps"] },
      { id: "kiosk", label: "Kiosk mode (plein écran)", icon: Tv2, action: () => navigate("/kiosk"), keywords: ["dashboard", "affichage"] },
      { id: "bulk-import", label: "Import CSV employés/ouvriers", icon: FileUp, action: () => navigate("/bulk-import"), keywords: ["csv", "batch"] },
      { id: "companies", label: "Filiales", icon: Building2, action: () => navigate("/companies"), keywords: ["filiale", "société", "company"] },
      { id: "employees", label: "Employés", icon: Users, action: () => navigate("/employees") },
      { id: "workers", label: "Ouvriers", icon: HardHat, action: () => navigate("/workers") },
      { id: "visitors", label: "Visiteurs", icon: UserCheck, action: () => navigate("/visitors") },
      { id: "badges", label: "Badges", icon: CreditCard, action: () => navigate("/badges") },
      { id: "helmets", label: "Casques BLE", icon: HardHat, action: () => navigate("/helmets") },
      { id: "bulk", label: "Enrôlement en masse", icon: UploadCloud, action: () => navigate("/badges/bulk-enroll") },
      { id: "attendance", label: "Feuille de présence", icon: ClipboardList, action: () => navigate("/attendance") },
      { id: "roster", label: "Planning hebdomadaire", icon: Calendar, action: () => navigate("/roster") },
      { id: "reports", label: "Rapports & exports", icon: FileSpreadsheet, action: () => navigate("/reports"), keywords: ["excel", "pdf", "export"] },
      { id: "antifraud", label: "Alertes anti-fraude", icon: ShieldAlert, action: () => navigate("/antifraud") },
      { id: "face", label: "Reconnaissance faciale", icon: ScanFace, action: () => navigate("/face-recognition") },
      { id: "firmwares", label: "Firmwares & OTA", icon: Package, action: () => navigate("/firmwares") },
      { id: "system", label: "État système", icon: Server, action: () => navigate("/system"), keywords: ["health", "celery", "redis"] },
      { id: "notifications", label: "Notifications", icon: Bell, action: () => navigate("/notifications") },
      { id: "ai", label: "Assistant IA", icon: Sparkles, action: () => navigate("/ai") },
      { id: "users", label: "Utilisateurs", icon: Users, action: () => navigate("/users") },
      { id: "roles", label: "Rôles & permissions", icon: Shield, action: () => navigate("/roles") },
      { id: "apikeys", label: "Clés API", icon: KeyRound, action: () => navigate("/api-keys") },
      { id: "audit", label: "Journal d'audit", icon: ScrollText, action: () => navigate("/audit") },
      { id: "settings", label: "Paramètres / profil", icon: Cog, action: () => navigate("/settings") },
    ],
    [navigate],
  );

  const filtered = useMemo(() => {
    if (!q.trim()) return commands;
    const needle = q.toLowerCase();
    return commands.filter((c) => {
      const hay = [c.label, ...(c.keywords || [])].join(" ").toLowerCase();
      return hay.includes(needle);
    });
  }, [q, commands]);

  useEffect(() => {
    if (open) {
      setQ("");
      setCursor(0);
      setTimeout(() => inputRef.current?.focus(), 50);
    }
  }, [open]);

  useEffect(() => {
    setCursor(0);
  }, [q]);

  const runCmd = (cmd: Cmd) => {
    cmd.action();
    onClose();
  };

  const onKey = (e: React.KeyboardEvent) => {
    if (e.key === "Escape") {
      onClose();
    } else if (e.key === "ArrowDown") {
      e.preventDefault();
      setCursor((c) => Math.min(c + 1, filtered.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setCursor((c) => Math.max(c - 1, 0));
    } else if (e.key === "Enter") {
      e.preventDefault();
      const cmd = filtered[cursor];
      if (cmd) runCmd(cmd);
    }
  };

  if (!open) return null;

  return (
    <div
      className="fixed inset-0 z-50 flex items-start justify-center pt-24 bg-black/70 backdrop-blur-sm px-4"
      onClick={onClose}
    >
      <div
        className="w-full max-w-xl rounded-2xl border border-surface-border bg-surface-card shadow-2xl overflow-hidden"
        onClick={(e) => e.stopPropagation()}
        onKeyDown={onKey}
      >
        <div className="flex items-center gap-2 px-4 border-b border-surface-border">
          <Search className="w-4 h-4 text-ink-soft shrink-0" />
          <input
            ref={inputRef}
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="Rechercher une page, une action, un raccourci…"
            className="flex-1 py-3.5 bg-transparent outline-none text-sm text-ink placeholder-ink-soft"
          />
          <span className="text-[10px] text-ink-soft px-1.5 py-0.5 rounded border border-surface-border font-mono">
            ESC
          </span>
        </div>

        <div className="max-h-80 overflow-y-auto py-1">
          {filtered.length === 0 && (
            <div className="p-8 text-center text-ink-muted text-sm">
              Aucun résultat pour "{q}"
            </div>
          )}
          {filtered.map((cmd, i) => (
            <button
              key={cmd.id}
              onMouseEnter={() => setCursor(i)}
              onClick={() => runCmd(cmd)}
              className={cn(
                "w-full flex items-center gap-3 px-4 py-2.5 text-left text-sm transition",
                i === cursor
                  ? "bg-brand-500/10 text-brand-ink"
                  : "text-ink hover:bg-surface-soft/50",
              )}
            >
              <cmd.icon className="w-4 h-4 shrink-0" />
              <span className="flex-1">{cmd.label}</span>
              {i === cursor && <ArrowRight className="w-3.5 h-3.5" />}
            </button>
          ))}
        </div>

        <div className="px-4 py-2 border-t border-surface-border text-[11px] text-ink-soft flex gap-4">
          <span>
            <kbd className="font-mono">↑↓</kbd> naviguer
          </span>
          <span>
            <kbd className="font-mono">↵</kbd> ouvrir
          </span>
          <span>
            <kbd className="font-mono">ESC</kbd> fermer
          </span>
        </div>
      </div>
    </div>
  );
}
