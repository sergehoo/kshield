import { Link } from "react-router-dom";
import { PageHeader } from "@/components/PageHeader";
import { Card } from "@/components/ui/Card";
import {
  Layers, Package, Wifi, PencilRuler, Ticket, Mail, Shield, Bot,
  ToggleLeft, Repeat, FileCheck, ClipboardList, Clock, Wrench,
  UsersRound, ListChecks, ShieldAlert, LayoutDashboard, Award,
} from "lucide-react";

type Item = {
  to: string;
  label: string;
  desc: string;
  icon: React.ComponentType<{ className?: string }>;
};

type Group = { title: string; items: Item[] };

const GROUPS: Group[] = [
  {
    title: "Terrain — référentiels",
    items: [
      { to: "/zones",          label: "Zones",           desc: "Sous-structures des sites (entrées, restricted…)", icon: Layers },
      { to: "/sites/map",      label: "Carte GPS",       desc: "Vue Leaflet des chantiers géolocalisés",           icon: LayoutDashboard },
    ],
  },
  {
    title: "Personnes — extensions",
    items: [
      { to: "/crews",              label: "Équipes",       desc: "Équipes ouvriers avec chef d'équipe",       icon: UsersRound },
      { to: "/worker-assignments", label: "Affectations",  desc: "Attribution ouvriers ↔ chantiers",         icon: ListChecks },
      { to: "/worker-certs",       label: "Certifications HSE", desc: "CACES, hauteur, échafaudage…",         icon: Award },
      { to: "/trades",             label: "Métiers",       desc: "Référentiel des corps de métier BTP",       icon: Wrench },
    ],
  },
  {
    title: "Visiteurs — workflow",
    items: [
      { to: "/visit-requests",      label: "Demandes de visite", desc: "Workflow approve/reject", icon: ClipboardList },
      { to: "/visitor-invitations", label: "Invitations",       desc: "Invitations envoyées aux visiteurs", icon: Mail },
      { to: "/visitor-passes",      label: "Passes émis",       desc: "Passes temporaires QR imprimables", icon: Ticket },
      { to: "/visit-purposes",      label: "Motifs de visite",  desc: "Référentiel des motifs (réunion, livraison…)", icon: PencilRuler },
      { to: "/watchlists",          label: "Listes rouges",     desc: "Personae non gratae", icon: Shield },
    ],
  },
  {
    title: "Équipements — référentiels",
    items: [
      { to: "/device-models",       label: "Catalogue modèles",   desc: "Modèles supportés (ZKTeco, AiFace…)", icon: Package },
      { to: "/device-maintenance",  label: "Maintenance",         desc: "Journal des interventions techniques", icon: Wrench },
      { to: "/gateways",            label: "Gateways BLE",        desc: "Passerelles beacons MOKO/iBeacon", icon: Wifi },
      { to: "/cameras/live",        label: "Mur de caméras",      desc: "Grille live MJPEG plein écran", icon: LayoutDashboard },
      { to: "/badges/bulk-enroll",  label: "Enrôlement en masse", desc: "Batch/CSV/live pour badges & casques", icon: Ticket },
    ],
  },
  {
    title: "Présence — extensions",
    items: [
      { to: "/attendance-corrections", label: "Corrections pointage", desc: "Corrections manuelles (justificatifs)", icon: PencilRuler },
      { to: "/overtime-rules",         label: "Règles heures supp",   desc: "Seuils journaliers/hebdo + multiplicateurs", icon: Clock },
    ],
  },
  {
    title: "Anti-fraude — configuration",
    items: [
      { to: "/fraud-rules",   label: "Règles anti-fraude", desc: "Détections automatiques configurables", icon: ShieldAlert },
      { to: "/conformity",    label: "Registres conformité", desc: "Documents RGPD / HSE / ISO", icon: FileCheck },
    ],
  },
  {
    title: "Rapports & notifications",
    items: [
      { to: "/report-schedules",       label: "Rapports planifiés",  desc: "Exports automatiques (cron)", icon: Repeat },
      { to: "/notification-templates", label: "Templates notif",     desc: "Templates email/SMS/push", icon: Mail },
      { to: "/ai-templates",           label: "Templates IA",        desc: "Prompts assistant IA", icon: Bot },
    ],
  },
  {
    title: "Système",
    items: [
      { to: "/roles",         label: "Rôles & permissions", desc: "RBAC — rôles, portées, permissions", icon: Shield },
      { to: "/feature-flags", label: "Feature flags",       desc: "Activation dynamique des features", icon: ToggleLeft },
    ],
  },
];

/**
 * Hub de configuration — regroupe tous les items "avancés" retirés de la
 * sidebar principale (référentiels rarement modifiés, workflows spécifiques,
 * templates, etc.). Chaque item est une carte cliquable qui pointe vers la
 * page CRUD dédiée.
 */
export function ConfigHubPage() {
  return (
    <div>
      <PageHeader
        title="Configuration"
        subtitle="Référentiels, workflows avancés et paramétrage transverse"
      />

      <div className="space-y-6">
        {GROUPS.map((group) => (
          <section key={group.title}>
            <h2 className="text-xs uppercase tracking-widest text-ink-soft font-semibold mb-2 px-1">
              {group.title}
            </h2>
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-3">
              {group.items.map((item) => (
                <Link
                  key={item.to}
                  to={item.to}
                  className="group flex items-start gap-3 p-4 rounded-xl border border-surface-border bg-surface-card/50 hover:border-brand-500/40 hover:bg-surface-card transition-all"
                >
                  <div className="w-10 h-10 rounded-lg bg-brand-500/10 text-brand-400 grid place-items-center shrink-0 group-hover:bg-brand-500/20 transition">
                    <item.icon className="w-5 h-5" />
                  </div>
                  <div className="min-w-0 flex-1">
                    <div className="text-sm font-semibold text-ink group-hover:text-brand-400 transition">
                      {item.label}
                    </div>
                    <div className="text-xs text-ink-muted mt-0.5">{item.desc}</div>
                  </div>
                </Link>
              ))}
            </div>
          </section>
        ))}
      </div>
    </div>
  );
}
