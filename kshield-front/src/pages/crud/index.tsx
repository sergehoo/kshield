/**
 * Pages CRUD génériques — 25 vues back-office intégrées via le composant
 * <CrudPage/>.
 *
 * Chaque export ci-dessous est une page complète (list + modal create/edit +
 * delete + pagination + search), montée dans le router.
 */
import { CrudPage, FieldSpec } from "@/components/CrudPage";
import { Badge } from "@/components/ui/Badge";
import { fmtDate, fmtDateTime } from "@/lib/format";
import {
  zonesService, subcontractorsService, tradesService, crewsService,
  workerAssignmentsService, workerCertsService, deviceModelsService,
  deviceMaintenanceService, gatewaysService, visitRequestsService,
  visitPurposesService, visitorPassesService, visitorInvitationsService,
  watchlistsService, fraudRulesService, accessRulesService,
  overtimeRulesGenService, overtimeCalcsService, attendanceCorrectionsService,
  leavesGenService, notificationTemplatesService, reportSchedulesService,
  dashboardsService, retentionPoliciesService, conformityRegistersService,
  mobileDevicesService, aiTemplatesService, featureFlagsService,
} from "@/services";
import type { Column } from "@/components/ui/DataTable";

// ─────────────────────────────────────────────────────────────
// Terrain — Zones, Sous-traitants, Métiers, Équipes, Affectations, Certifications
// ─────────────────────────────────────────────────────────────
const zoneFields: FieldSpec[] = [
  { key: "name", label: "Nom", required: true },
  { key: "code", label: "Code", placeholder: "ZONE-A1" },
  { key: "site", label: "Site (ID)", type: "number" },
  { key: "risk_level", label: "Niveau de risque", type: "select", options: [
    { value: "low", label: "Faible" }, { value: "medium", label: "Moyen" },
    { value: "high", label: "Élevé" }, { value: "extreme", label: "Critique" },
  ]},
  { key: "description", label: "Description", type: "textarea", span: 2 },
];
export const ZonesPage = () => (
  <CrudPage
    title="Zones" service={zonesService} queryKey="zones"
    subtitle="Sous-structures des sites (entrées, zones techniques, restricted…)"
    fields={zoneFields}
    columns={[
      { key: "name",  header: "Nom",     render: (z) => <span className="font-medium">{z.name}</span> },
      { key: "code",  header: "Code",    render: (z) => <code className="text-xs font-mono">{z.code || "—"}</code> },
      { key: "site",  header: "Site",    render: (z) => typeof z.site === "object" ? z.site?.name : `#${z.site}` },
      { key: "risk",  header: "Risque",  render: (z) => <Badge tone={
        z.risk_level === "extreme" ? "danger" : z.risk_level === "high" ? "warn" :
        z.risk_level === "medium" ? "info" : "muted"
      }>{z.risk_level || "—"}</Badge> },
    ]}
  />
);

const subFields: FieldSpec[] = [
  { key: "name", label: "Raison sociale", required: true, span: 2 },
  { key: "code", label: "Code", required: true },
  { key: "contact_name", label: "Contact" },
  { key: "contact_email", label: "Email", type: "email" },
  { key: "contact_phone", label: "Téléphone" },
  { key: "is_active", label: "Actif", type: "checkbox" },
];
export const SubcontractorsPage = () => (
  <CrudPage
    title="Sous-traitants" service={subcontractorsService} queryKey="subcontractors"
    subtitle="Entreprises tierces intervenant sur les chantiers"
    fields={subFields}
    columns={[
      { key: "name",    header: "Raison sociale", render: (s) => <span className="font-medium">{s.name}</span> },
      { key: "code",    header: "Code", render: (s) => <code className="text-xs font-mono">{s.code}</code> },
      { key: "contact", header: "Contact", render: (s) => (
        <div className="text-xs">
          <div>{s.contact_name || "—"}</div>
          <div className="text-ink-soft">{s.contact_email || s.contact_phone || ""}</div>
        </div>
      )},
      { key: "active",  header: "Statut", render: (s) => (
        <Badge tone={s.is_active !== false ? "ok" : "muted"}>{s.is_active !== false ? "Actif" : "Inactif"}</Badge>
      )},
    ]}
  />
);

export const TradesPage = () => (
  <CrudPage
    title="Métiers" service={tradesService} queryKey="trades"
    subtitle="Référentiel des corps de métier BTP"
    fields={[
      { key: "code", label: "Code", required: true, placeholder: "macon" },
      { key: "name", label: "Libellé", required: true, placeholder: "Maçon" },
      { key: "description", label: "Description", type: "textarea", span: 2 },
    ]}
    columns={[
      { key: "code", header: "Code",    render: (t) => <code className="text-xs font-mono">{t.code}</code> },
      { key: "name", header: "Libellé", render: (t) => <span className="font-medium">{t.name}</span> },
      { key: "desc", header: "Description", render: (t) => <span className="text-xs text-ink-muted">{t.description || "—"}</span> },
    ]}
  />
);

export const CrewsPage = () => (
  <CrudPage
    title="Équipes" service={crewsService} queryKey="crews"
    subtitle="Équipes d'ouvriers sous un chef d'équipe"
    fields={[
      { key: "name", label: "Nom", required: true },
      { key: "site", label: "Site (ID)", type: "number" },
      { key: "leader_worker", label: "Chef d'équipe (Worker ID)", type: "number" },
      { key: "description", label: "Description", type: "textarea", span: 2 },
    ]}
    columns={[
      { key: "name", header: "Nom", render: (c) => <span className="font-medium">{c.name}</span> },
      { key: "site", header: "Chantier", render: (c) => typeof c.site === "object" ? c.site?.name : "—" },
      { key: "leader", header: "Chef", render: (c) => c.leader_name || "—" },
    ]}
  />
);

export const WorkerAssignmentsPage = () => (
  <CrudPage
    title="Affectations ouvriers" service={workerAssignmentsService} queryKey="assignments"
    subtitle="Attribution des ouvriers aux chantiers"
    fields={[
      { key: "worker", label: "Ouvrier (ID)", required: true, type: "number" },
      { key: "site", label: "Site (ID)", required: true, type: "number" },
      { key: "crew", label: "Équipe (ID)", type: "number" },
      { key: "start_date", label: "Date début", type: "date" },
      { key: "end_date", label: "Date fin", type: "date" },
    ]}
    columns={[
      { key: "worker", header: "Ouvrier", render: (a) => a.worker_name || `#${a.worker}` },
      { key: "site",   header: "Chantier", render: (a) => a.site_name || `#${a.site}` },
      { key: "start",  header: "Début", render: (a) => fmtDate(a.start_date) },
      { key: "end",    header: "Fin",   render: (a) => a.end_date ? fmtDate(a.end_date) : <Badge tone="ok">En cours</Badge> },
    ]}
  />
);

export const WorkerCertsPage = () => (
  <CrudPage
    title="Certifications ouvriers" service={workerCertsService} queryKey="worker-certs"
    subtitle="Habilitations HSE : CACES, hauteur, électricité, échafaudage…"
    fields={[
      { key: "worker", label: "Ouvrier (ID)", required: true, type: "number" },
      { key: "code", label: "Code", required: true, placeholder: "CACES-R482" },
      { key: "label", label: "Libellé", required: true, span: 2 },
      { key: "issued_at", label: "Délivrée le", type: "date", required: true },
      { key: "valid_until", label: "Valide jusqu'au", type: "date" },
      { key: "notes", label: "Notes", type: "textarea", span: 2 },
    ]}
    columns={[
      { key: "worker", header: "Ouvrier", render: (c) => c.worker_name || `#${c.worker}` },
      { key: "code",   header: "Certification", render: (c) => <div>
        <div className="font-medium text-sm">{c.label}</div>
        <code className="text-xs text-ink-soft font-mono">{c.code}</code>
      </div> },
      { key: "valid", header: "Validité", render: (c) => {
        if (!c.valid_until) return <Badge tone="muted">Sans échéance</Badge>;
        const daysLeft = Math.floor((new Date(c.valid_until).getTime() - Date.now()) / 86400000);
        return <Badge tone={daysLeft < 0 ? "danger" : daysLeft < 30 ? "warn" : "ok"}>
          {daysLeft < 0 ? `Expirée ${fmtDate(c.valid_until)}` : `${daysLeft}j restants`}
        </Badge>;
      }},
    ]}
  />
);

// ─────────────────────────────────────────────────────────────
// Équipements — DeviceModels, Maintenance, Gateways
// ─────────────────────────────────────────────────────────────
export const DeviceModelsPage = () => (
  <CrudPage
    title="Modèles d'équipements" service={deviceModelsService} queryKey="device-models"
    subtitle="Catalogue des modèles supportés (ZKTeco, AiFace, Hikvision, MOKO…)"
    fields={[
      { key: "brand", label: "Marque", required: true },
      { key: "model", label: "Modèle", required: true },
      { key: "type", label: "Type", required: true, type: "select", options: [
        { value: "reader_uhf_fixed", label: "Lecteur UHF fixe" },
        { value: "reader_nfc_fixed", label: "Lecteur NFC fixe" },
        { value: "reader_uhf_mobile", label: "Lecteur UHF mobile" },
        { value: "reader_nfc_mobile", label: "Lecteur NFC mobile" },
        { value: "face_terminal", label: "Terminal face" },
        { value: "camera", label: "Caméra" },
        { value: "portique", label: "Portique UHF" },
        { value: "beacon_ble", label: "Beacon BLE" },
        { value: "tag_uhf", label: "Tag UHF" },
        { value: "door_lock", label: "Gâche" },
        { value: "smartphone", label: "Smartphone" },
        { value: "tablet", label: "Tablette" },
      ]},
      { key: "is_active", label: "Actif au catalogue", type: "checkbox" },
    ]}
    columns={[
      { key: "brand", header: "Marque", render: (m) => <span className="font-medium">{m.brand}</span> },
      { key: "model", header: "Modèle", render: (m) => m.model },
      { key: "type",  header: "Type",   render: (m) => <Badge tone="info">{m.type}</Badge> },
      { key: "active",header: "Statut", render: (m) => (
        <Badge tone={m.is_active ? "ok" : "muted"}>{m.is_active ? "Actif" : "Retiré"}</Badge>
      )},
    ]}
  />
);

export const DeviceMaintenancePage = () => (
  <CrudPage
    title="Maintenance équipements" service={deviceMaintenanceService} queryKey="device-maintenance"
    subtitle="Journal des interventions techniques sur les terminaux"
    fields={[
      { key: "device", label: "Device (ID)", required: true, type: "number" },
      { key: "kind", label: "Type", required: true, type: "select", options: [
        { value: "preventive", label: "Préventive" },
        { value: "corrective", label: "Corrective" },
        { value: "swap", label: "Remplacement" },
        { value: "firmware", label: "Mise à jour firmware" },
      ]},
      { key: "scheduled_at", label: "Planifiée le", type: "date" },
      { key: "performed_at", label: "Réalisée le", type: "date" },
      { key: "technician", label: "Technicien" },
      { key: "notes", label: "Notes", type: "textarea", span: 2 },
    ]}
    columns={[
      { key: "device", header: "Équipement", render: (m) => m.device_name || `#${m.device}` },
      { key: "kind",   header: "Type", render: (m) => <Badge tone="info">{m.kind}</Badge> },
      { key: "sched",  header: "Planifiée", render: (m) => fmtDate(m.scheduled_at) },
      { key: "done",   header: "Réalisée", render: (m) =>
        m.performed_at ? <Badge tone="ok" dot>{fmtDate(m.performed_at)}</Badge> : <Badge tone="warn">En attente</Badge>
      },
    ]}
  />
);

export const GatewaysPage = () => (
  <CrudPage
    title="Gateways BLE" service={gatewaysService} queryKey="gateways"
    subtitle="Gateways sur site captant les beacons BLE (MOKO, iBeacon…)"
    fields={[
      { key: "name", label: "Nom", required: true },
      { key: "site", label: "Site (ID)", required: true, type: "number" },
      { key: "serial_number", label: "Numéro de série" },
      { key: "ip_address", label: "IP", placeholder: "192.168.1.50" },
      { key: "is_active", label: "Actif", type: "checkbox" },
    ]}
    columns={[
      { key: "name", header: "Nom", render: (g) => <span className="font-medium">{g.name}</span> },
      { key: "site", header: "Site", render: (g) => g.site_name || `#${g.site}` },
      { key: "ip",   header: "IP",   render: (g) => <code className="text-xs font-mono">{g.ip_address || "—"}</code> },
      { key: "hb",   header: "Dernier signal", render: (g) => g.last_seen_at ? fmtDateTime(g.last_seen_at) : "—" },
      { key: "active", header: "Statut", render: (g) => (
        <Badge tone={g.is_active ? "ok" : "muted"}>{g.is_active ? "Actif" : "Inactif"}</Badge>
      )},
    ]}
  />
);

// ─────────────────────────────────────────────────────────────
// Visiteurs — workflow
// ─────────────────────────────────────────────────────────────
export const VisitPurposesPage = () => (
  <CrudPage
    title="Motifs de visite" service={visitPurposesService} queryKey="visit-purposes"
    fields={[
      { key: "code", label: "Code", required: true, placeholder: "meeting" },
      { key: "label", label: "Libellé", required: true, placeholder: "Réunion" },
      { key: "requires_appointment", label: "Rendez-vous obligatoire", type: "checkbox" },
      { key: "default_duration_minutes", label: "Durée par défaut (min)", type: "number" },
    ]}
    columns={[
      { key: "code",  header: "Code",   render: (p) => <code className="text-xs font-mono">{p.code}</code> },
      { key: "label", header: "Libellé", render: (p) => <span className="font-medium">{p.label}</span> },
      { key: "duration", header: "Durée", render: (p) => `${p.default_duration_minutes || 0} min` },
      { key: "req", header: "RDV requis", render: (p) => (
        <Badge tone={p.requires_appointment ? "warn" : "muted"}>{p.requires_appointment ? "Oui" : "Non"}</Badge>
      )},
    ]}
  />
);

export const VisitorPassesPage = () => (
  <CrudPage
    title="Passes visiteurs" service={visitorPassesService} queryKey="visitor-passes"
    subtitle="Passes temporaires générés (QR imprimable)"
    hideDefaultActions
    fields={[
      { key: "visitor", label: "Visiteur (ID)", required: true, type: "number" },
      { key: "site", label: "Site (ID)", required: true, type: "number" },
      { key: "valid_from", label: "Valide du", type: "date", required: true },
      { key: "valid_until", label: "Valide jusqu'au", type: "date", required: true },
      { key: "purpose", label: "Motif" },
    ]}
    columns={[
      { key: "visitor", header: "Visiteur", render: (p) => p.visitor_name || `#${p.visitor}` },
      { key: "site",    header: "Site",     render: (p) => p.site_name || `#${p.site}` },
      { key: "valid",   header: "Validité", render: (p) => `${fmtDate(p.valid_from)} → ${fmtDate(p.valid_until)}` },
      { key: "status",  header: "Statut", render: (p) => (
        <Badge tone={p.is_used ? "muted" : "ok"}>{p.is_used ? "Utilisé" : "Actif"}</Badge>
      )},
    ]}
  />
);

export const VisitorInvitationsPage = () => (
  <CrudPage
    title="Invitations visiteurs" service={visitorInvitationsService} queryKey="visitor-invitations"
    fields={[
      { key: "guest_email", label: "Email invité", required: true, type: "email" },
      { key: "guest_name", label: "Nom invité", required: true },
      { key: "site", label: "Site (ID)", type: "number" },
      { key: "visit_at", label: "Date de visite", type: "date" },
      { key: "message", label: "Message personnel", type: "textarea", span: 2 },
    ]}
    columns={[
      { key: "guest",  header: "Invité", render: (i) => (
        <div><div className="font-medium">{i.guest_name}</div><div className="text-xs text-ink-soft">{i.guest_email}</div></div>
      )},
      { key: "visit",  header: "Date visite", render: (i) => fmtDateTime(i.visit_at) },
      { key: "status", header: "Statut", render: (i) => (
        <Badge tone={i.status === "accepted" ? "ok" : i.status === "declined" ? "danger" : "warn"}>
          {i.status || "en attente"}
        </Badge>
      )},
    ]}
  />
);

export const WatchlistsPage = () => (
  <CrudPage
    title="Listes de surveillance" service={watchlistsService} queryKey="watchlists"
    subtitle="Personas persona non grata ou à contrôler"
    fields={[
      { key: "full_name", label: "Nom complet", required: true },
      { key: "id_number", label: "Numéro pièce d'identité" },
      { key: "reason", label: "Motif", type: "textarea", span: 2 },
      { key: "severity", label: "Niveau", type: "select", options: [
        { value: "warn", label: "Alerter" }, { value: "block", label: "Bloquer" },
      ]},
      { key: "added_by", label: "Ajoutée par" },
    ]}
    columns={[
      { key: "name", header: "Personne", render: (w) => <span className="font-medium">{w.full_name}</span> },
      { key: "id",   header: "N° pièce",  render: (w) => <code className="text-xs font-mono">{w.id_number || "—"}</code> },
      { key: "sev",  header: "Niveau", render: (w) => (
        <Badge tone={w.severity === "block" ? "danger" : "warn"} dot>{w.severity}</Badge>
      )},
      { key: "reason", header: "Motif", render: (w) => <span className="text-xs truncate max-w-xs block">{w.reason || "—"}</span> },
    ]}
  />
);

// ─────────────────────────────────────────────────────────────
// Anti-fraude — règles
// ─────────────────────────────────────────────────────────────
export const FraudRulesPage = () => (
  <CrudPage
    title="Règles anti-fraude" service={fraudRulesService} queryKey="fraud-rules"
    subtitle="Configuration des détections automatiques"
    fields={[
      { key: "code", label: "Code", required: true, placeholder: "duplicate_badge" },
      { key: "name", label: "Nom", required: true, span: 2 },
      { key: "severity", label: "Sévérité", type: "select", required: true, options: [
        { value: "low", label: "Basse" }, { value: "medium", label: "Moyenne" },
        { value: "high", label: "Haute" }, { value: "critical", label: "Critique" },
      ]},
      { key: "is_active", label: "Active", type: "checkbox" },
      { key: "description", label: "Description", type: "textarea", span: 2 },
    ]}
    columns={[
      { key: "name", header: "Règle", render: (r) => (
        <div><div className="font-medium">{r.name}</div><code className="text-xs text-ink-soft font-mono">{r.code}</code></div>
      )},
      { key: "sev",  header: "Sévérité", render: (r) => (
        <Badge tone={r.severity === "critical" ? "danger" : r.severity === "high" ? "warn" : "info"}>{r.severity}</Badge>
      )},
      { key: "active", header: "Active", render: (r) => (
        <Badge tone={r.is_active ? "ok" : "muted"}>{r.is_active ? "Oui" : "Non"}</Badge>
      )},
    ]}
  />
);

// ─────────────────────────────────────────────────────────────
// Access rules
// ─────────────────────────────────────────────────────────────
export const AccessRulesPage = () => (
  <CrudPage
    title="Règles d'accès" service={accessRulesService} queryKey="access-rules"
    subtitle="Autorisations d'accès par site / zone / horaires"
    fields={[
      { key: "name", label: "Nom", required: true, span: 2 },
      { key: "site", label: "Site (ID)", type: "number" },
      { key: "zone", label: "Zone (ID)", type: "number" },
      { key: "holder_kind", label: "Type porteur", type: "select", options: [
        { value: "employee", label: "Employés" }, { value: "worker", label: "Ouvriers" },
        { value: "visitor", label: "Visiteurs" },
      ]},
      { key: "allowed_from", label: "Autorisé de", placeholder: "07:00" },
      { key: "allowed_to", label: "Autorisé à", placeholder: "19:00" },
      { key: "is_active", label: "Active", type: "checkbox" },
    ]}
    columns={[
      { key: "name",   header: "Nom", render: (r) => <span className="font-medium">{r.name}</span> },
      { key: "site",   header: "Portée", render: (r) => (
        <div className="text-xs">
          {r.site_name && <div>📍 {r.site_name}</div>}
          {r.zone_name && <div className="text-ink-soft">📌 {r.zone_name}</div>}
        </div>
      )},
      { key: "hours",  header: "Horaires", render: (r) =>
        r.allowed_from && r.allowed_to ? <code className="text-xs">{r.allowed_from} — {r.allowed_to}</code> : "24/7"
      },
      { key: "active", header: "Statut", render: (r) => (
        <Badge tone={r.is_active ? "ok" : "muted"}>{r.is_active ? "Active" : "Inactive"}</Badge>
      )},
    ]}
  />
);

// ─────────────────────────────────────────────────────────────
// Pointage RH — Overtime, Corrections, Leaves
// ─────────────────────────────────────────────────────────────
export const OvertimeRulesPage = () => (
  <CrudPage
    title="Règles heures supplémentaires" service={overtimeRulesGenService} queryKey="overtime-rules"
    fields={[
      { key: "name", label: "Nom", required: true, span: 2 },
      { key: "company", label: "Société (ID)", type: "number" },
      { key: "weekly_hours_threshold", label: "Seuil hebdo (h)", type: "number", placeholder: "40" },
      { key: "daily_hours_threshold", label: "Seuil quotidien (h)", type: "number", placeholder: "8" },
      { key: "multiplier_25", label: "×1.25 après (h)", type: "number" },
      { key: "multiplier_50", label: "×1.50 après (h)", type: "number" },
      { key: "is_active", label: "Active", type: "checkbox" },
    ]}
    columns={[
      { key: "name", header: "Nom", render: (r) => <span className="font-medium">{r.name}</span> },
      { key: "th",   header: "Seuils", render: (r) =>
        `${r.daily_hours_threshold || "?"}h/j · ${r.weekly_hours_threshold || "?"}h/sem`
      },
      { key: "active", header: "Statut", render: (r) => (
        <Badge tone={r.is_active ? "ok" : "muted"}>{r.is_active ? "Active" : "Inactive"}</Badge>
      )},
    ]}
  />
);

const otCalcsColumns: Column<any>[] = [
  { key: "who",  header: "Personne", render: (o) => o.worker_name || o.employee_name || `#${o.worker || o.employee}` },
  { key: "week", header: "Semaine", render: (o) => fmtDate(o.week_start) },
  { key: "reg",  header: "Heures régulières", render: (o) => `${o.regular_minutes ? Math.round(o.regular_minutes/60) : 0}h` },
  { key: "ot",   header: "Heures supp", render: (o) => <span className="text-warn font-medium">{o.overtime_minutes ? Math.round(o.overtime_minutes/60) : 0}h</span> },
  { key: "amount", header: "Prime", render: (o) => o.amount ? `${o.amount} XOF` : "—" },
];
export const OvertimeCalcsPage = () => (
  <CrudPage
    title="Calculs heures supp" service={overtimeCalcsService} queryKey="overtime-calcs"
    hideDefaultActions
    fields={[
      { key: "worker", label: "Ouvrier (ID)", type: "number" },
      { key: "employee", label: "Employé (ID)", type: "number" },
      { key: "week_start", label: "Semaine du", type: "date", required: true },
      { key: "regular_minutes", label: "Minutes régulières", type: "number" },
      { key: "overtime_minutes", label: "Minutes supp", type: "number" },
    ]}
    columns={otCalcsColumns}
  />
);

export const AttendanceCorrectionsPage = () => (
  <CrudPage
    title="Corrections pointage" service={attendanceCorrectionsService} queryKey="corrections"
    subtitle="Corrections manuelles des présences (justificatifs, oublis…)"
    fields={[
      { key: "attendance_day", label: "AttendanceDay (ID)", required: true, type: "number" },
      { key: "reason", label: "Motif", type: "textarea", required: true, span: 2 },
      { key: "new_first_in", label: "Nouvelle entrée", placeholder: "08:00" },
      { key: "new_last_out", label: "Nouvelle sortie", placeholder: "17:00" },
    ]}
    columns={[
      { key: "day",    header: "Jour", render: (c) => c.attendance_date ? fmtDate(c.attendance_date) : `Day #${c.attendance_day}` },
      { key: "who",    header: "Personne", render: (c) => c.holder_name || "—" },
      { key: "by",     header: "Par", render: (c) => c.performed_by_name || "—" },
      { key: "reason", header: "Motif", render: (c) => <span className="text-xs">{c.reason}</span> },
    ]}
  />
);

export const LeavesPage = () => (
  <CrudPage
    title="Demandes de congés" service={leavesGenService} queryKey="leaves"
    fields={[
      { key: "employee", label: "Employé (ID)", type: "number" },
      { key: "worker", label: "Ouvrier (ID)", type: "number" },
      { key: "type", label: "Type", type: "select", required: true, options: [
        { value: "annual", label: "Congés annuels" },
        { value: "sick", label: "Maladie" },
        { value: "unpaid", label: "Sans solde" },
        { value: "family", label: "Événement familial" },
        { value: "other", label: "Autre" },
      ]},
      { key: "start_date", label: "Du", type: "date", required: true },
      { key: "end_date", label: "Au", type: "date", required: true },
      { key: "reason", label: "Motif", type: "textarea", span: 2 },
    ]}
    columns={[
      { key: "who",   header: "Personne", render: (l) => l.holder_name || `#${l.employee || l.worker}` },
      { key: "type",  header: "Type", render: (l) => <Badge tone="info">{l.type}</Badge> },
      { key: "range", header: "Période", render: (l) => `${fmtDate(l.start_date)} → ${fmtDate(l.end_date)}` },
      { key: "status", header: "Statut", render: (l) => (
        <Badge tone={l.status === "approved" ? "ok" : l.status === "rejected" ? "danger" : "warn"} dot>
          {l.status || "en attente"}
        </Badge>
      )},
    ]}
  />
);

// ─────────────────────────────────────────────────────────────
// Config
// ─────────────────────────────────────────────────────────────
export const NotificationTemplatesPage = () => (
  <CrudPage
    title="Templates notifications" service={notificationTemplatesService} queryKey="notif-templates"
    subtitle="Templates configurables pour les notifications sortantes"
    fields={[
      { key: "code", label: "Code", required: true, placeholder: "late_arrival" },
      { key: "channel", label: "Canal", type: "select", options: [
        { value: "email", label: "Email" }, { value: "sms", label: "SMS" },
        { value: "push", label: "Push mobile" }, { value: "in_app", label: "In-app" },
      ]},
      { key: "subject", label: "Sujet", span: 2 },
      { key: "body", label: "Corps (Jinja)", type: "textarea", span: 2 },
      { key: "is_active", label: "Active", type: "checkbox" },
    ]}
    columns={[
      { key: "code",    header: "Code", render: (t) => <code className="text-xs font-mono">{t.code}</code> },
      { key: "channel", header: "Canal", render: (t) => <Badge tone="info">{t.channel}</Badge> },
      { key: "subject", header: "Sujet", render: (t) => <span className="text-xs">{t.subject || "—"}</span> },
      { key: "active",  header: "Statut", render: (t) => (
        <Badge tone={t.is_active ? "ok" : "muted"}>{t.is_active ? "Active" : "Désactivée"}</Badge>
      )},
    ]}
  />
);

export const FeatureFlagsPage = () => (
  <CrudPage
    title="Feature flags" service={featureFlagsService} queryKey="feature-flags"
    subtitle="Activation dynamique des fonctionnalités"
    fields={[
      { key: "code", label: "Code", required: true, placeholder: "face_reco_v2" },
      { key: "is_enabled", label: "Activé", type: "checkbox" },
      { key: "description", label: "Description", type: "textarea", span: 2 },
    ]}
    columns={[
      { key: "code",  header: "Code", render: (f) => <code className="text-xs font-mono">{f.code}</code> },
      { key: "desc",  header: "Description", render: (f) => <span className="text-xs text-ink-muted">{f.description || "—"}</span> },
      { key: "state", header: "État", render: (f) => (
        <Badge tone={f.is_enabled ? "ok" : "muted"} dot>{f.is_enabled ? "ON" : "OFF"}</Badge>
      )},
    ]}
  />
);

// ─────────────────────────────────────────────────────────────
// Reporting / Dashboards / Digests
// ─────────────────────────────────────────────────────────────
export const ReportSchedulesPage = () => (
  <CrudPage
    title="Rapports planifiés" service={reportSchedulesService} queryKey="report-schedules"
    subtitle="Rapports générés et envoyés automatiquement"
    fields={[
      { key: "name", label: "Nom", required: true, span: 2 },
      { key: "report_kind", label: "Type", type: "select", options: [
        { value: "attendance_daily", label: "Présence journalière" },
        { value: "attendance_weekly", label: "Présence hebdo" },
        { value: "overtime_weekly", label: "Heures supp hebdo" },
        { value: "audit_monthly", label: "Audit mensuel" },
      ]},
      { key: "cron", label: "Cron", placeholder: "0 8 * * 1" },
      { key: "recipients", label: "Destinataires (emails)", type: "textarea", span: 2 },
      { key: "is_active", label: "Active", type: "checkbox" },
    ]}
    columns={[
      { key: "name",  header: "Nom", render: (r) => <span className="font-medium">{r.name}</span> },
      { key: "kind",  header: "Type", render: (r) => <Badge tone="info">{r.report_kind}</Badge> },
      { key: "cron",  header: "Cron", render: (r) => <code className="text-xs">{r.cron || "—"}</code> },
      { key: "next",  header: "Prochaine exécution", render: (r) => r.next_run_at ? fmtDateTime(r.next_run_at) : "—" },
      { key: "active",header: "Statut", render: (r) => (
        <Badge tone={r.is_active ? "ok" : "muted"}>{r.is_active ? "ON" : "OFF"}</Badge>
      )},
    ]}
  />
);

export const DashboardsPage = () => (
  <CrudPage
    title="Dashboards configurables" service={dashboardsService} queryKey="dashboards"
    fields={[
      { key: "name", label: "Nom", required: true, span: 2 },
      { key: "layout", label: "Layout (JSON)", type: "textarea", span: 2 },
      { key: "is_default", label: "Défaut", type: "checkbox" },
    ]}
    columns={[
      { key: "name",   header: "Nom", render: (d) => <span className="font-medium">{d.name}</span> },
      { key: "widgets",header: "Widgets", render: (d) => d.widgets_count ?? "—" },
      { key: "default",header: "", render: (d) => d.is_default ? <Badge tone="brand">Défaut</Badge> : null },
    ]}
  />
);

// ─────────────────────────────────────────────────────────────
// RGPD
// ─────────────────────────────────────────────────────────────
export const RetentionPoliciesPage = () => (
  <CrudPage
    title="Politiques de rétention" service={retentionPoliciesService} queryKey="retention"
    subtitle="Durée de conservation des données (RGPD)"
    fields={[
      { key: "model_label", label: "Modèle Django", required: true, placeholder: "access_control.AccessEvent" },
      { key: "retention_days", label: "Rétention (jours)", type: "number", required: true },
      { key: "action_on_expire", label: "Action à expiration", type: "select", options: [
        { value: "delete", label: "Supprimer" },
        { value: "anonymize", label: "Anonymiser" },
        { value: "archive", label: "Archiver" },
      ]},
      { key: "description", label: "Description", type: "textarea", span: 2 },
    ]}
    columns={[
      { key: "model",  header: "Modèle", render: (p) => <code className="text-xs font-mono">{p.model_label}</code> },
      { key: "days",   header: "Rétention", render: (p) => <Badge tone="info">{p.retention_days}j</Badge> },
      { key: "action", header: "Action", render: (p) => p.action_on_expire || "supprimer" },
    ]}
  />
);

export const ConformityRegistersPage = () => (
  <CrudPage
    title="Registres de conformité" service={conformityRegistersService} queryKey="conformity"
    subtitle="Documents et attestations de conformité RGPD/HSE"
    fields={[
      { key: "title", label: "Titre", required: true, span: 2 },
      { key: "kind", label: "Type", type: "select", options: [
        { value: "gdpr", label: "RGPD" },
        { value: "iso", label: "ISO" },
        { value: "hse", label: "HSE" },
        { value: "other", label: "Autre" },
      ]},
      { key: "issued_at", label: "Émis le", type: "date" },
      { key: "expires_at", label: "Expire le", type: "date" },
      { key: "notes", label: "Notes", type: "textarea", span: 2 },
    ]}
    columns={[
      { key: "title", header: "Titre", render: (r) => <span className="font-medium">{r.title}</span> },
      { key: "kind",  header: "Type", render: (r) => <Badge tone="info">{r.kind || "other"}</Badge> },
      { key: "valid", header: "Validité", render: (r) => {
        if (!r.expires_at) return <Badge tone="muted">—</Badge>;
        const days = Math.floor((new Date(r.expires_at).getTime() - Date.now()) / 86400000);
        return <Badge tone={days < 0 ? "danger" : days < 30 ? "warn" : "ok"}>
          {days < 0 ? "Expiré" : `${days}j restants`}
        </Badge>;
      }},
    ]}
  />
);

// ─────────────────────────────────────────────────────────────
// Mobile & AI templates
// ─────────────────────────────────────────────────────────────
export const MobileDevicesPage = () => (
  <CrudPage
    title="Appareils mobiles" service={mobileDevicesService} queryKey="mobile-devices"
    subtitle="Smartphones/tablettes enregistrés pour l'app mobile agents terrain"
    fields={[
      { key: "device_id", label: "Device ID", required: true, span: 2 },
      { key: "platform", label: "Plateforme", type: "select", options: [
        { value: "android", label: "Android" }, { value: "ios", label: "iOS" },
      ]},
      { key: "owner_email", label: "Utilisateur (email)" },
      { key: "app_version", label: "Version app" },
      { key: "is_active", label: "Actif", type: "checkbox" },
    ]}
    columns={[
      { key: "device", header: "Device", render: (m) => (
        <div><code className="text-xs font-mono">{m.device_id}</code></div>
      )},
      { key: "platform", header: "OS", render: (m) => <Badge tone="info">{m.platform}</Badge> },
      { key: "owner",    header: "Utilisateur", render: (m) => m.owner_email || "—" },
      { key: "version",  header: "Version app", render: (m) => m.app_version || "—" },
      { key: "last",     header: "Dernière connexion", render: (m) => m.last_seen_at ? fmtDateTime(m.last_seen_at) : "—" },
    ]}
  />
);

export const AITemplatesPage = () => (
  <CrudPage
    title="Templates IA" service={aiTemplatesService} queryKey="ai-templates"
    subtitle="Prompts et templates pour l'assistant IA"
    fields={[
      { key: "code", label: "Code", required: true, placeholder: "onboarding_worker" },
      { key: "name", label: "Nom", required: true, span: 2 },
      { key: "system_prompt", label: "System prompt", type: "textarea", span: 2 },
      { key: "user_prompt_template", label: "User prompt (Jinja)", type: "textarea", span: 2 },
      { key: "is_active", label: "Active", type: "checkbox" },
    ]}
    columns={[
      { key: "code",   header: "Code", render: (t) => <code className="text-xs font-mono">{t.code}</code> },
      { key: "name",   header: "Nom", render: (t) => <span className="font-medium">{t.name}</span> },
      { key: "active", header: "Statut", render: (t) => (
        <Badge tone={t.is_active ? "ok" : "muted"}>{t.is_active ? "Active" : "Désactivée"}</Badge>
      )},
    ]}
  />
);
