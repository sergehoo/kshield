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
import { AuditLogPage } from "@/pages/AuditLog";

// Compte
import { NotificationsPage } from "@/pages/Notifications";
import { AIPage } from "@/pages/AI";
import { SettingsPage } from "@/pages/Settings";

// Import + kiosk
import { BulkImportPage } from "@/pages/BulkImport";
import { KioskPage } from "@/pages/Kiosk";

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
      { path: "api-keys", element: <ApiKeysPage /> },
      { path: "audit", element: <AuditLogPage /> },

      // Import + kiosk (accessibles depuis les autres pages)
      { path: "bulk-import", element: <BulkImportPage /> },

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
