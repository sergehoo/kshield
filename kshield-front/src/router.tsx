import { createBrowserRouter, Navigate } from "react-router-dom";
import { AppLayout } from "@/layouts/AppLayout";
import { AuthLayout } from "@/layouts/AuthLayout";

import { LoginPage } from "@/pages/Login";
import { DashboardPage } from "@/pages/Dashboard";
import { DevicesPage } from "@/pages/Devices";
import { DeviceDetailPage } from "@/pages/DeviceDetail";
import { AccessEventsLivePage } from "@/pages/AccessEventsLive";
import { AttendancePage } from "@/pages/Attendance";
import { SitesPage } from "@/pages/Sites";
import { CompaniesPage } from "@/pages/Companies";
import { EmployeesPage } from "@/pages/Employees";
import { WorkersPage } from "@/pages/Workers";
import { BadgesPage } from "@/pages/Badges";
import { BulkEnrollPage } from "@/pages/BulkEnroll";
import { NotificationsPage } from "@/pages/Notifications";
import { AIPage } from "@/pages/AI";
import { SystemStatusPage } from "@/pages/SystemStatus";
import { WorkerDetailPage } from "@/pages/WorkerDetail";
import { NotFoundPage } from "@/pages/NotFound";

export const router = createBrowserRouter([
  {
    path: "/",
    element: <AppLayout />,
    children: [
      { index: true, element: <DashboardPage /> },
      { path: "events", element: <AccessEventsLivePage /> },
      { path: "devices", element: <DevicesPage /> },
      { path: "devices/:id", element: <DeviceDetailPage /> },
      { path: "attendance", element: <AttendancePage /> },
      { path: "sites", element: <SitesPage /> },
      { path: "companies", element: <CompaniesPage /> },
      { path: "employees", element: <EmployeesPage /> },
      { path: "workers", element: <WorkersPage /> },
      { path: "workers/:id", element: <WorkerDetailPage /> },
      { path: "badges", element: <BadgesPage /> },
      { path: "badges/bulk-enroll", element: <BulkEnrollPage /> },
      { path: "notifications", element: <NotificationsPage /> },
      { path: "ai", element: <AIPage /> },
      { path: "system", element: <SystemStatusPage /> },
    ],
  },
  {
    path: "/",
    element: <AuthLayout />,
    children: [{ path: "login", element: <LoginPage /> }],
  },
  { path: "*", element: <NotFoundPage /> },
]);
