import { createBrowserRouter, useRouteError } from "react-router-dom";
import { AlertOctagon, RefreshCw, Home } from "lucide-react";
import { AppLayout } from "@/layouts/AppLayout";
import { AuthLayout } from "@/layouts/AuthLayout";

// Public
import { LoginPage } from "@/pages/Login";
import { NotFoundPage } from "@/pages/NotFound";

// Cockpit
import { DashboardPage } from "@/pages/Dashboard";
import { AccessEventsLivePage } from "@/pages/AccessEventsLive";
import EventsLivePage from "@/pages/EventsLive";
import { AntifraudPage } from "@/pages/Antifraud";
import { SystemStatusPage } from "@/pages/SystemStatus";

// Terrain
import { SitesPage } from "@/pages/Sites";
import { SiteDetailPage } from "@/pages/SiteDetail";
import { SitesMapPage } from "@/pages/SitesMap";
import { CompaniesPage } from "@/pages/Companies";
import { CompanyDetailPage } from "@/pages/CompanyDetail";
import { EmployeesPage } from "@/pages/Employees";
import { EmployeeDetailPage } from "@/pages/EmployeeDetail";
import { WorkersPage } from "@/pages/Workers";
import { WorkerDetailPage } from "@/pages/WorkerDetail";
import { VisitorsPage } from "@/pages/Visitors";

// Équipements
import { DevicesPage } from "@/pages/Devices";
import { DeviceDetailPage } from "@/pages/DeviceDetail";
import { CamerasPage } from "@/pages/Cameras";
import { CameraDetailPage } from "@/pages/CameraDetail";
import { BadgesPage } from "@/pages/Badges";
import { BulkEnrollPage } from "@/pages/BulkEnroll";
import { HelmetsPage } from "@/pages/Helmets";
import { FaceRecognitionPage } from "@/pages/FaceRecognition";
import { FirmwaresPage } from "@/pages/Firmwares";

// Présence & rapports
import { AttendancePage } from "@/pages/Attendance";
import { RosterPage } from "@/pages/Roster";
import { ReportsPage } from "@/pages/Reports";

// Administration
import { UsersPage } from "@/pages/Users";
import { RolesPage } from "@/pages/Roles";
import { ApiKeysPage } from "@/pages/ApiKeys";
import { LocalAgentsPage } from "@/pages/LocalAgents";
import { AlertsPage } from "@/pages/Alerts";
import { DriversPage } from "@/pages/Drivers";
import { DiscoveryPage } from "@/pages/Discovery";
import { MaintenancePage } from "@/pages/Maintenance";
import { TopologyPage } from "@/pages/Topology";
import { MarketplacePage } from "@/pages/Marketplace";
import { EdgeGatewayPage } from "@/pages/EdgeGateway";
import FleetPage from "@/pages/Fleet";
import { AuditLogPage } from "@/pages/AuditLog";

// Refonte cahier des charges — fronts phases 4, 5, 6
import { AgentsSupervisionPage } from "@/pages/AgentsSupervision";
import { AgentDetailPage } from "@/pages/AgentDetail";
import { DevicesDiscoveryPage } from "@/pages/DevicesDiscovery";
import { SyncConflictsPage } from "@/pages/SyncConflicts";

// Compte
import { NotificationsPage } from "@/pages/Notifications";
import { AIPage } from "@/pages/AI";
import { SettingsPage } from "@/pages/Settings";

// Import + kiosk
import { BulkImportPage } from "@/pages/BulkImport";
import { KioskPage } from "@/pages/Kiosk";
import { ConfigHubPage } from "@/pages/ConfigHub";

// Workflows spécifiques
import { VisitRequestsPage } from "@/pages/VisitRequests";
import { FraudInvestigationsPage } from "@/pages/FraudInvestigations";
import { CamerasLivePage } from "@/pages/CamerasLive";

// CRUD pages (25 pages générées via <CrudPage />)
import {
  ZonesPage, SubcontractorsPage, TradesPage, CrewsPage,
  WorkerAssignmentsPage, WorkerCertsPage, DeviceModelsPage,
  DeviceMaintenancePage, GatewaysPage, VisitPurposesPage,
  VisitorPassesPage, VisitorInvitationsPage, WatchlistsPage,
  FraudRulesPage, AccessRulesPage, OvertimeRulesPage, OvertimeCalcsPage,
  AttendanceCorrectionsPage, LeavesPage, NotificationTemplatesPage,
  FeatureFlagsPage, ReportSchedulesPage, DashboardsPage,
  RetentionPoliciesPage, ConformityRegistersPage, MobileDevicesPage,
  AITemplatesPage,
} from "@/pages/crud";

// ─────────────────────────────────────────────────────────────
// Fallback erreur route (loaders, actions, render errors du router)
// ─────────────────────────────────────────────────────────────
function RouteErrorFallback() {
  const err = useRouteError() as any;
  const isDev = import.meta.env.DEV;
  const message = err?.message || (typeof err === "string" ? err : "Erreur inconnue");

  return (
    <div className="min-h-[70vh] flex items-center justify-center p-6">
      <div className="max-w-lg w-full rounded-2xl border border-danger/30 bg-danger/5 p-6 shadow-card">
        <div className="flex items-start gap-3">
          <AlertOctagon className="w-6 h-6 text-danger shrink-0 mt-0.5" />
          <div className="flex-1 min-w-0">
            <h2 className="text-lg font-semibold text-ink">
              Cette page a rencontré une erreur
            </h2>
            <p className="mt-1 text-sm text-ink-muted">
              Tu peux recharger, ou revenir au dashboard.
            </p>
            {isDev && (
              <pre className="mt-3 text-[11px] font-mono text-danger bg-surface p-3 rounded-lg overflow-auto max-h-56 whitespace-pre-wrap">
                {message}
                {err?.stack ? "\n\n" + err.stack : ""}
              </pre>
            )}
            <div className="mt-4 flex gap-2">
              <button
                onClick={() => window.location.reload()}
                className="inline-flex items-center gap-2 px-3.5 py-2 rounded-lg bg-brand-500 hover:bg-brand-600 text-white text-sm font-medium"
              >
                <RefreshCw className="w-4 h-4" /> Recharger
              </button>
              <a
                href="/"
                className="inline-flex items-center gap-2 px-3.5 py-2 rounded-lg border border-surface-border text-ink hover:bg-surface-soft text-sm font-medium"
              >
                <Home className="w-4 h-4" /> Dashboard
              </a>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────
// Router
// ─────────────────────────────────────────────────────────────
export const router = createBrowserRouter([
  {
    path: "/",
    element: <AppLayout />,
    errorElement: <RouteErrorFallback />,
    children: [
      { index: true, element: <DashboardPage /> },

      // Cockpit
      { path: "events", element: <AccessEventsLivePage /> },
      { path: "events/live", element: <EventsLivePage /> },
      { path: "antifraud", element: <AntifraudPage /> },
      { path: "system", element: <SystemStatusPage /> },

      // Terrain
      { path: "sites", element: <SitesPage /> },
      { path: "sites/map", element: <SitesMapPage /> },
      { path: "sites/:id", element: <SiteDetailPage /> },
      { path: "companies", element: <CompaniesPage /> },
      { path: "companies/:id", element: <CompanyDetailPage /> },
      { path: "employees", element: <EmployeesPage /> },
      { path: "employees/:id", element: <EmployeeDetailPage /> },
      { path: "workers", element: <WorkersPage /> },
      { path: "workers/:id", element: <WorkerDetailPage /> },
      { path: "visitors", element: <VisitorsPage /> },

      // Équipements
      { path: "devices", element: <DevicesPage /> },
      { path: "devices/:id", element: <DeviceDetailPage /> },
      { path: "cameras", element: <CamerasPage /> },
      { path: "cameras/:id", element: <CameraDetailPage /> },
      { path: "badges", element: <BadgesPage /> },
      { path: "badges/bulk-enroll", element: <BulkEnrollPage /> },
      { path: "helmets", element: <HelmetsPage /> },
      { path: "face-recognition", element: <FaceRecognitionPage /> },
      { path: "firmwares", element: <FirmwaresPage /> },

      // Présence & rapports
      { path: "attendance", element: <AttendancePage /> },
      { path: "roster", element: <RosterPage /> },
      { path: "reports", element: <ReportsPage /> },

      // Administration
      { path: "users", element: <UsersPage /> },
      { path: "roles", element: <RolesPage /> },
      { path: "local-agents", element: <LocalAgentsPage /> },
      { path: "agents", element: <AgentsSupervisionPage /> },
      { path: "agents/:id", element: <AgentDetailPage /> },
      { path: "devices/discovery", element: <DevicesDiscoveryPage /> },
      { path: "sync/conflicts", element: <SyncConflictsPage /> },
      { path: "alerts", element: <AlertsPage /> },
      { path: "drivers", element: <DriversPage /> },
      { path: "discovery", element: <DiscoveryPage /> },
      { path: "maintenance", element: <MaintenancePage /> },
      { path: "topology", element: <TopologyPage /> },
      { path: "marketplace", element: <MarketplacePage /> },
      { path: "edge-gateway", element: <EdgeGatewayPage /> },
      { path: "fleet", element: <FleetPage /> },
      { path: "api-keys", element: <ApiKeysPage /> },
      { path: "audit", element: <AuditLogPage /> },

      // Import + kiosk + hub configuration
      { path: "bulk-import", element: <BulkImportPage /> },
      { path: "config", element: <ConfigHubPage /> },

      // ─── CRUD génériques : terrain ─────────────
      { path: "zones", element: <ZonesPage /> },
      { path: "subcontractors", element: <SubcontractorsPage /> },
      { path: "trades", element: <TradesPage /> },
      { path: "crews", element: <CrewsPage /> },
      { path: "worker-assignments", element: <WorkerAssignmentsPage /> },
      { path: "worker-certs", element: <WorkerCertsPage /> },

      // ─── CRUD : équipements ─────────────
      { path: "device-models", element: <DeviceModelsPage /> },
      { path: "device-maintenance", element: <DeviceMaintenancePage /> },
      { path: "gateways", element: <GatewaysPage /> },
      { path: "cameras/live", element: <CamerasLivePage /> },

      // ─── CRUD : visiteurs workflow ─────────────
      { path: "visit-requests", element: <VisitRequestsPage /> },
      { path: "visit-purposes", element: <VisitPurposesPage /> },
      { path: "visitor-passes", element: <VisitorPassesPage /> },
      { path: "visitor-invitations", element: <VisitorInvitationsPage /> },
      { path: "watchlists", element: <WatchlistsPage /> },

      // ─── CRUD : sécurité ─────────────
      { path: "fraud-rules", element: <FraudRulesPage /> },
      { path: "fraud-investigations", element: <FraudInvestigationsPage /> },
      { path: "access-rules", element: <AccessRulesPage /> },

      // ─── CRUD : RH avancé ─────────────
      { path: "leaves", element: <LeavesPage /> },
      { path: "overtime-rules", element: <OvertimeRulesPage /> },
      { path: "overtime-calcs", element: <OvertimeCalcsPage /> },
      { path: "attendance-corrections", element: <AttendanceCorrectionsPage /> },

      // ─── CRUD : config & reporting ─────────────
      { path: "notification-templates", element: <NotificationTemplatesPage /> },
      { path: "feature-flags", element: <FeatureFlagsPage /> },
      { path: "report-schedules", element: <ReportSchedulesPage /> },
      { path: "dashboards", element: <DashboardsPage /> },
      { path: "mobile-devices", element: <MobileDevicesPage /> },
      { path: "ai-templates", element: <AITemplatesPage /> },

      // ─── CRUD : RGPD ─────────────
      { path: "retention-policies", element: <RetentionPoliciesPage /> },
      { path: "conformity", element: <ConformityRegistersPage /> },

      // Compte
      { path: "notifications", element: <NotificationsPage /> },
      { path: "ai", element: <AIPage /> },
      { path: "settings", element: <SettingsPage /> },
    ],
  },

  // Kiosk mode — hors layout classique (plein écran)
  { path: "/kiosk", element: <KioskPage /> },
  {
    path: "/",
    element: <AuthLayout />,
    children: [{ path: "login", element: <LoginPage /> }],
  },
  { path: "*", element: <NotFoundPage /> },
]);
