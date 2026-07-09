/**
 * Services API — wrappers axios typés. Une fonction par endpoint utile.
 * Les composants importent depuis ici et jamais directement `api`.
 */
import { api } from "@/lib/api";
import type {
  AccessEvent,
  AIConversation,
  AttendanceDay,
  Badge,
  Company,
  Device,
  Employee,
  Notification,
  Paginated,
  Site,
  Worker,
} from "@/types/api";

// ─────────────────────────────────────────────────────────────
// Auth
// ─────────────────────────────────────────────────────────────
export const authService = {
  // POST /api/v1/auth/login/ → { access, refresh, user }
  login: (email: string, password: string, mfa_code?: string) =>
    api.post<{ access: string; refresh: string; user?: any }>(
      "/api/v1/auth/login/",
      { email, password, ...(mfa_code ? { mfa_code } : {}) },
    ),
  refresh: (refresh: string) =>
    api.post<{ access: string }>("/api/v1/auth/token/refresh/", { refresh }),
  me: () => api.get<any>("/api/v1/auth/me/"),
};

// ─────────────────────────────────────────────────────────────
// Devices
// ─────────────────────────────────────────────────────────────
export const devicesService = {
  list: (params?: Record<string, any>) =>
    api.get<Paginated<any>>("/api/v1/devices/devices/", { params }),
  get: (id: number) => api.get<any>(`/api/v1/devices/devices/${id}/`),
  create: (body: any) => api.post<any>("/api/v1/devices/devices/", body),
  update: (id: number, body: any) =>
    api.patch<any>(`/api/v1/devices/devices/${id}/`, body),
  remove: (id: number) => api.delete(`/api/v1/devices/devices/${id}/`),
  testConnection: (id: number) =>
    api.post<any>(`/api/v1/devices/${id}/test-connection/`),
  ping: (id: number) => api.post<any>(`/api/v1/devices/${id}/ping/`),
  restart: (id: number) => api.post<any>(`/api/v1/devices/${id}/restart/`),
  syncNow: (id: number) => api.post<any>(`/api/v1/devices/${id}/sync/`),
  resetConfig: (id: number) => api.post<any>(`/api/v1/devices/${id}/reset-config/`),
  updateFirmware: (id: number, firmware_id?: number) =>
    api.post<any>(`/api/v1/devices/${id}/update-firmware/`, { firmware_id }),
  setMaintenance: (id: number, enabled: boolean) =>
    api.patch<any>(`/api/v1/devices/devices/${id}/`, {
      status: enabled ? "maintenance" : "active",
    }),
  logs: (id: number, params?: any) =>
    api.get<any>(`/api/v1/devices/${id}/logs/`, { params }),
  exportSpec: (id: number) =>
    api.get(`/api/v1/devices/${id}/export/`, { responseType: "blob" }),

  // ZKTeco spécifique
  zkSyncNow: (id: number) => api.post<any>(`/api/v1/devices/${id}/zk-sync/`),
  zkPushUsers: (id: number) => api.post<any>(`/api/v1/devices/${id}/zk-push-users/`),

  // Debug ADMS / firmwares whitebox
  iclockDebug: (id: number) => api.get<any>(`/api/v1/devices/${id}/iclock-debug/`),
  pubApiDebug: () => api.get<any>("/api/v1/devices/pubapi-debug/"),

  // Découverte
  identifyByIp: (ip: string) =>
    api.post<any>("/api/v1/devices/identify-by-ip/", { ip }),

  // ─── Scan réseau ─────────────────────────
  scanStart: (params: {
    ip_range: string;               // "192.168.1.1-254" ou "192.168.1.0/24"
    ports?: number[];               // [80, 443, 4370, 5084, 554, 8000]
    protocols?: string[];           // ["onvif", "zkteco", "wiegand", "osdp"]
    timeout_ms?: number;
  }) => api.post<{ scan_id: string }>("/api/v1/devices/scan/start/", params),
  scanStatus: (scanId: string) =>
    api.get<any>(`/api/v1/devices/scan/${scanId}/`),
  scanCancel: (scanId: string) =>
    api.post<any>(`/api/v1/devices/scan/${scanId}/cancel/`),
  scanAdopt: (scanId: string, ip: string, defaults?: any) =>
    api.post<any>(`/api/v1/devices/scan/${scanId}/adopt/`, { ip, ...defaults }),
};

// ─────────────────────────────────────────────────────────────
// Access events
// ─────────────────────────────────────────────────────────────
export const accessEventsService = {
  list: (params?: Record<string, any>) =>
    api.get<Paginated<AccessEvent>>("/api/v1/access/events/", { params }),
  get: (id: number) => api.get<AccessEvent>(`/api/v1/access/events/${id}/`),
};

// ─────────────────────────────────────────────────────────────
// Sites & companies
// ─────────────────────────────────────────────────────────────
export const sitesService = {
  list: (params?: Record<string, any>) =>
    api.get<Paginated<Site>>("/api/v1/sites/sites/", { params }),
  create: (body: Partial<Site>) => api.post<Site>("/api/v1/sites/sites/", body),
  update: (id: number, body: Partial<Site>) =>
    api.patch<Site>(`/api/v1/sites/sites/${id}/`, body),
  remove: (id: number) => api.delete(`/api/v1/sites/sites/${id}/`),
};

export const companiesService = {
  list: (params?: Record<string, any>) =>
    api.get<Paginated<Company>>("/api/v1/core/companies/", { params }),
  create: (body: Partial<Company>) =>
    api.post<Company>("/api/v1/core/companies/", body),
  update: (id: number, body: Partial<Company>) =>
    api.patch<Company>(`/api/v1/core/companies/${id}/`, body),
  remove: (id: number) => api.delete(`/api/v1/core/companies/${id}/`),
};

// ─────────────────────────────────────────────────────────────
// People
// ─────────────────────────────────────────────────────────────
export const employeesService = {
  list: (params?: Record<string, any>) =>
    api.get<Paginated<any>>("/api/v1/employees/employees/", { params }),
  create: (body: any) => api.post<any>("/api/v1/employees/employees/", body),
  update: (id: number, body: any) =>
    api.patch<any>(`/api/v1/employees/employees/${id}/`, body),
  remove: (id: number) => api.delete(`/api/v1/employees/employees/${id}/`),
  faceStatus: () => api.get<any>("/api/v1/employees/face/status/"),
};

export const workersService = {
  list: (params?: Record<string, any>) =>
    api.get<Paginated<any>>("/api/v1/ouvriers/workers/", { params }),
  get: (id: number) => api.get<any>(`/api/v1/ouvriers/workers/${id}/`),
  create: (body: any) => api.post<any>("/api/v1/ouvriers/workers/", body),
  update: (id: number, body: any) =>
    api.patch<any>(`/api/v1/ouvriers/workers/${id}/`, body),
  remove: (id: number) => api.delete(`/api/v1/ouvriers/workers/${id}/`),
  pairBadge: (id: number, badge_id: number) =>
    api.post(`/api/v1/ouvriers/workers/${id}/pair-badge/`, { badge_id }),
  pairHelmet: (id: number, helmet_id: number) =>
    api.post(`/api/v1/ouvriers/workers/${id}/pair-helmet/`, { helmet_id }),
};

// ─────────────────────────────────────────────────────────────
// Badges
// ─────────────────────────────────────────────────────────────
export const badgesService = {
  list: (params?: Record<string, any>) =>
    api.get<Paginated<Badge>>("/api/v1/devices/badges/", { params }),
  lookup: (uid: string) =>
    api.get<Badge>("/api/v1/devices/badges/lookup/", { params: { uid } }),
  suspend: (id: number) => api.post(`/api/v1/devices/badges/${id}/suspend/`),
  revoke: (id: number) => api.post(`/api/v1/devices/badges/${id}/revoke/`),
  reactivate: (id: number) => api.post(`/api/v1/devices/badges/${id}/reactivate/`),
  bulkEnroll: (body: any) => api.post("/api/v1/devices/badges/bulk-enroll/", body),
  get: (id: number) => api.get<any>(`/api/v1/devices/badges/${id}/`),
  create: (body: any) => api.post<any>("/api/v1/devices/badges/", body),
  update: (id: number, body: any) => api.patch<any>(`/api/v1/devices/badges/${id}/`, body),
  remove: (id: number) => api.delete(`/api/v1/devices/badges/${id}/`),
  // Enrôlement live via lecteur RFID connecté (inbox Redis)
  // Sans reader_id → agrège tous les lecteurs RFID actifs du tenant.
  scanInbox: (params?: { reader_id?: number | string; since?: string }) =>
    api.get<any>("/api/v1/devices/scan/inbox/", {
      params: { kind: "rfid", ...params },
    }),
  clearScanInbox: (params?: { reader_id?: number | string }) =>
    api.delete<any>("/api/v1/devices/scan/inbox/", {
      params: { kind: "rfid", ...params },
    }),
  // Associer/dissocier à un ouvrier/employé
  associate: (id: number, params: { holder_kind: "worker" | "employee"; holder_id: number }) =>
    api.post(`/api/v1/devices/badges/${id}/associate/`, params),
  dissociate: (id: number) => api.post(`/api/v1/devices/badges/${id}/dissociate/`),
  history: (id: number) => api.get<any>(`/api/v1/devices/badges/${id}/history/`),
};

export const helmetsService = {
  list: (params?: Record<string, any>) =>
    api.get<Paginated<any>>("/api/v1/devices/helmets/", { params }),
  get: (id: number) => api.get<any>(`/api/v1/devices/helmets/${id}/`),
  create: (body: any) => api.post<any>("/api/v1/devices/helmets/", body),
  update: (id: number, body: any) => api.patch<any>(`/api/v1/devices/helmets/${id}/`, body),
  remove: (id: number) => api.delete(`/api/v1/devices/helmets/${id}/`),
  bulkEnroll: (body: any) => api.post("/api/v1/devices/helmets/bulk-enroll/", body),
  // Enrôlement live : le lecteur/gateway BLE scanne les tags à proximité et
  // dépose les codes dans un inbox Redis TTL 10 min.
  scanInbox: (params?: { reader_id?: number | string; since?: string }) =>
    api.get<any>("/api/v1/devices/scan/inbox/", {
      params: { kind: "ble", ...params },
    }),
  clearScanInbox: (params?: { reader_id?: number | string }) =>
    api.delete<any>("/api/v1/devices/scan/inbox/", {
      params: { kind: "ble", ...params },
    }),
  associate: (id: number, worker_id: number) =>
    api.post(`/api/v1/devices/helmets/${id}/pair/`, { worker_id }),
  dissociate: (id: number) =>
    api.post(`/api/v1/devices/helmets/${id}/unpair/`),
};

export const scanInboxService = {
  // GET /api/v1/devices/scan/inbox/ — dépile les scans en attente (utilisé par le
  // mode "capture live" du bulk enrollment). TTL Redis 10 min côté back.
  drain: (params?: Record<string, any>) =>
    api.get<{ scans: any[]; count: number }>("/api/v1/devices/scan/inbox/", { params }),
};

// ─────────────────────────────────────────────────────────────
// Attendance
// ─────────────────────────────────────────────────────────────
export const attendanceService = {
  daysList: (params?: Record<string, any>) =>
    api.get<Paginated<AttendanceDay>>("/api/v1/attendance/days/", { params }),
  todaySummary: () => api.get<any>("/api/v1/attendance/summary/today/"),
  presenceLive: () => api.get<any>("/api/v1/attendance/presence/live/"),
  weeklyOvertime: (params?: Record<string, any>) =>
    api.get<any>("/api/v1/attendance/overtime/weekly/", { params }),
};

// ─────────────────────────────────────────────────────────────
// Notifications
// ─────────────────────────────────────────────────────────────
export const notificationsService = {
  list: (params?: Record<string, any>) =>
    api.get<Paginated<Notification>>("/api/v1/notifications/", { params }),
  unread: () => api.get<{ count: number; results: Notification[] }>(
    "/api/v1/notifications/unread/",
  ),
  markRead: (id: number) => api.post(`/api/v1/notifications/${id}/read/`),
  markAllRead: () => api.post("/api/v1/notifications/read-all/"),
};

// ─────────────────────────────────────────────────────────────
// AI assistant
// ─────────────────────────────────────────────────────────────
export const aiService = {
  conversations: () =>
    api.get<Paginated<AIConversation>>("/api/v1/ai/conversations/"),
  getConversation: (id: number) =>
    api.get<AIConversation>(`/api/v1/ai/conversations/${id}/`),
  sendMessage: (conversationId: number | null, message: string) =>
    api.post<any>("/api/v1/ai/chat/", {
      conversation_id: conversationId,
      message,
    }),
};

// ─────────────────────────────────────────────────────────────
// System / status
// ─────────────────────────────────────────────────────────────
export const systemService = {
  status: () => api.get<any>("/api/v1/core/system/status/"),
  healthz: () => api.get<any>("/healthz"),
};

// ─────────────────────────────────────────────────────────────
// Cameras — vidéosurveillance ONVIF/RTSP
// ─────────────────────────────────────────────────────────────
export const camerasService = {
  list: (params?: Record<string, any>) =>
    api.get<Paginated<any>>("/api/v1/devices/cameras/", { params }),
  get: (id: number) => api.get<any>(`/api/v1/devices/cameras/${id}/`),
  create: (body: any) => api.post<any>("/api/v1/devices/cameras/", body),
  update: (id: number, body: any) =>
    api.patch<any>(`/api/v1/devices/cameras/${id}/`, body),
  remove: (id: number) => api.delete(`/api/v1/devices/cameras/${id}/`),
  discover: () => api.post<any>("/api/v1/devices/cameras/discover/"),
  probeRtsp: (url: string) =>
    api.post<any>("/api/v1/devices/cameras/probe-rtsp/", { url }),
  streamUrl: (id: number) => `/api/v1/devices/cameras/${id}/stream.mjpg`,
};

// ─────────────────────────────────────────────────────────────
// Visitors — gestion visiteurs + badges temporaires
// ─────────────────────────────────────────────────────────────
export const visitorsService = {
  list: (params?: Record<string, any>) =>
    api.get<Paginated<any>>("/api/v1/visitors/visitors/", { params }),
  get: (id: number) => api.get<any>(`/api/v1/visitors/visitors/${id}/`),
  create: (body: any) => api.post<any>("/api/v1/visitors/visitors/", body),
  update: (id: number, body: any) =>
    api.patch<any>(`/api/v1/visitors/visitors/${id}/`, body),
  remove: (id: number) => api.delete(`/api/v1/visitors/visitors/${id}/`),
  checkIn: (id: number) => api.post(`/api/v1/visitors/visitors/${id}/checkin/`),
  checkOut: (id: number) => api.post(`/api/v1/visitors/visitors/${id}/checkout/`),
};

// ─────────────────────────────────────────────────────────────
// Reports — export & agrégations
// ─────────────────────────────────────────────────────────────
export const reportsService = {
  list: (params?: Record<string, any>) =>
    api.get<Paginated<any>>("/api/v1/reports/reports/", { params }),
  attendanceExcel: (params: { date_from?: string; date_to?: string; site?: number }) =>
    api.get("/api/v1/reports/attendance/excel/", { params, responseType: "blob" }),
  attendancePdf: (params: { date_from?: string; date_to?: string; site?: number }) =>
    api.get("/api/v1/reports/attendance/pdf/", { params, responseType: "blob" }),
  overtimeExcel: (params: { week_start?: string; site?: number }) =>
    api.get("/api/v1/reports/overtime/excel/", { params, responseType: "blob" }),
  eventsExcel: (params: any) =>
    api.get("/api/v1/reports/events/excel/", { params, responseType: "blob" }),
};

// ─────────────────────────────────────────────────────────────
// Anti-fraude
// ─────────────────────────────────────────────────────────────
export const antifraudService = {
  alertsList: (params?: Record<string, any>) =>
    api.get<Paginated<any>>("/api/v1/antifraud/alerts/", { params }),
  alertResolve: (id: number, note?: string) =>
    api.post(`/api/v1/antifraud/alerts/${id}/resolve/`, { note }),
  alertDismiss: (id: number, note?: string) =>
    api.post(`/api/v1/antifraud/alerts/${id}/dismiss/`, { note }),
  rulesList: () => api.get<Paginated<any>>("/api/v1/antifraud/rules/"),
  rulesUpdate: (id: number, body: any) =>
    api.patch(`/api/v1/antifraud/rules/${id}/`, body),
};

// ─────────────────────────────────────────────────────────────
// Attendance — plannings & congés & overtime rules
// ─────────────────────────────────────────────────────────────
export const rosterService = {
  list: (params?: Record<string, any>) =>
    api.get<Paginated<any>>("/api/v1/attendance/rosters/", { params }),
  create: (body: any) => api.post("/api/v1/attendance/rosters/", body),
  update: (id: number, body: any) =>
    api.patch(`/api/v1/attendance/rosters/${id}/`, body),
  remove: (id: number) => api.delete(`/api/v1/attendance/rosters/${id}/`),
};

export const leavesService = {
  list: (params?: Record<string, any>) =>
    api.get<Paginated<any>>("/api/v1/attendance/leaves/", { params }),
  create: (body: any) => api.post("/api/v1/attendance/leaves/", body),
  approve: (id: number) => api.patch(`/api/v1/attendance/leaves/${id}/`, { status: "approved" }),
  reject: (id: number) => api.patch(`/api/v1/attendance/leaves/${id}/`, { status: "rejected" }),
};

export const overtimeRulesService = {
  list: (params?: Record<string, any>) =>
    api.get<Paginated<any>>("/api/v1/attendance/overtime-rules/", { params }),
  create: (body: any) => api.post("/api/v1/attendance/overtime-rules/", body),
  update: (id: number, body: any) =>
    api.patch(`/api/v1/attendance/overtime-rules/${id}/`, body),
};

// ─────────────────────────────────────────────────────────────
// Face recognition
// ─────────────────────────────────────────────────────────────
export const faceService = {
  status: () => api.get<any>("/api/v1/employees/face/status/"),
  enrollEmployee: (id: number, photo: File) => {
    const fd = new FormData();
    fd.append("photo", photo);
    return api.post(`/api/v1/employees/${id}/face-enroll/`, fd, {
      headers: { "Content-Type": "multipart/form-data" },
    });
  },
  pushToTerminals: () =>
    api.post<any>("/api/v1/devices/face/push-templates/"),
  pullFromTerminals: () =>
    api.post<any>("/api/v1/devices/face/pull-templates/"),
};

// ─────────────────────────────────────────────────────────────
// OTA / firmwares
// ─────────────────────────────────────────────────────────────
export const firmwaresService = {
  list: (params?: Record<string, any>) =>
    api.get<Paginated<any>>("/api/v1/devices/firmwares/", { params }),
  create: (body: any) => api.post("/api/v1/devices/firmwares/", body),
  otaList: (params?: Record<string, any>) =>
    api.get<Paginated<any>>("/api/v1/devices/ota/", { params }),
  scheduleUpdate: (body: any) => api.post("/api/v1/devices/ota/", body),
};

// ─────────────────────────────────────────────────────────────
// Users / Roles / API keys (RBAC)
// ─────────────────────────────────────────────────────────────
export const usersService = {
  list: (params?: Record<string, any>) =>
    api.get<Paginated<any>>("/api/v1/auth/users/", { params }),
  get: (id: number) => api.get<any>(`/api/v1/auth/users/${id}/`),
  create: (body: any) => api.post<any>("/api/v1/auth/users/", body),
  update: (id: number, body: any) =>
    api.patch<any>(`/api/v1/auth/users/${id}/`, body),
  remove: (id: number) => api.delete(`/api/v1/auth/users/${id}/`),
};

export const rolesService = {
  list: () => api.get<Paginated<any>>("/api/v1/auth/roles/"),
  create: (body: any) => api.post("/api/v1/auth/roles/", body),
  update: (id: number, body: any) => api.patch(`/api/v1/auth/roles/${id}/`, body),
  remove: (id: number) => api.delete(`/api/v1/auth/roles/${id}/`),
};

export const roleAssignmentsService = {
  list: (params?: Record<string, any>) =>
    api.get<Paginated<any>>("/api/v1/auth/role-assignments/", { params }),
  create: (body: any) => api.post("/api/v1/auth/role-assignments/", body),
  remove: (id: number) => api.delete(`/api/v1/auth/role-assignments/${id}/`),
};

export const apiKeysService = {
  list: (params?: Record<string, any>) =>
    api.get<Paginated<any>>("/api/v1/auth/api-keys/", { params }),
  create: (body: any) => api.post<any>("/api/v1/auth/api-keys/", body),
  remove: (id: number) => api.delete(`/api/v1/auth/api-keys/${id}/`),
};

// ─────────────────────────────────────────────────────────────
// Audit log
// ─────────────────────────────────────────────────────────────
export const auditService = {
  list: (params?: Record<string, any>) =>
    api.get<Paginated<any>>("/api/v1/audit/entries/", { params }),
};

// ─────────────────────────────────────────────────────────────
// Employees — enrich existing service
// ─────────────────────────────────────────────────────────────
Object.assign(employeesService, {
  get: (id: number) => api.get<any>(`/api/v1/employees/employees/${id}/`),
  pushToZk: (id: number) => api.post(`/api/v1/employees/${id}/push-to-zk/`),
});

// ─────────────────────────────────────────────────────────────
// Sites detail + companies detail
// ─────────────────────────────────────────────────────────────
Object.assign(sitesService, {
  get: (id: number) => api.get<any>(`/api/v1/sites/sites/${id}/`),
});
Object.assign(companiesService, {
  get: (id: number) => api.get<any>(`/api/v1/core/companies/${id}/`),
});

// ─────────────────────────────────────────────────────────────
// Factory : CRUD service générique pour éviter la duplication.
// ─────────────────────────────────────────────────────────────
export function makeCrudService(basePath: string) {
  const p = basePath.replace(/\/$/, "");
  return {
    list: (params?: Record<string, any>) =>
      api.get<Paginated<any>>(`${p}/`, { params }),
    get: (id: number | string) => api.get<any>(`${p}/${id}/`),
    create: (body: any) => api.post<any>(`${p}/`, body),
    update: (id: number | string, body: any) =>
      api.patch<any>(`${p}/${id}/`, body),
    remove: (id: number | string) => api.delete(`${p}/${id}/`),
  };
}

// ─────────────────────────────────────────────────────────────
// Terrain — sous-structures
// ─────────────────────────────────────────────────────────────
export const zonesService              = makeCrudService("/api/v1/sites/zones");
export const checkpointsService        = makeCrudService("/api/v1/sites/checkpoints");
export const openingHoursService       = makeCrudService("/api/v1/sites/opening-hours");
export const sitePoliciesService       = makeCrudService("/api/v1/sites/policies");
export const subcontractorsService     = makeCrudService("/api/v1/ouvriers/subcontractors");
export const tradesService             = makeCrudService("/api/v1/ouvriers/trades");
export const crewsService              = makeCrudService("/api/v1/ouvriers/crews");
export const workerAssignmentsService  = makeCrudService("/api/v1/ouvriers/assignments");
export const workerCertsService        = makeCrudService("/api/v1/ouvriers/certifications");

// ─────────────────────────────────────────────────────────────
// Équipements — étendus
// ─────────────────────────────────────────────────────────────
export const deviceModelsService       = makeCrudService("/api/v1/devices/models");
export const deviceMaintenanceService  = makeCrudService("/api/v1/devices/maintenances");
export const deviceHeartbeatsService   = makeCrudService("/api/v1/devices/heartbeats");
export const helmetPairingsService     = makeCrudService("/api/v1/devices/pairings");
export const otaUpdatesService         = makeCrudService("/api/v1/devices/ota");
export const gatewaysService           = makeCrudService("/api/v1/devices/gateways");

// ─────────────────────────────────────────────────────────────
// Visiteurs — workflow complet
// ─────────────────────────────────────────────────────────────
export const visitRequestsService = {
  ...makeCrudService("/api/v1/visitors/requests"),
  approve: (id: number) => api.post(`/api/v1/visitors/requests/${id}/approve/`),
  reject: (id: number, note?: string) =>
    api.post(`/api/v1/visitors/requests/${id}/reject/`, { note }),
  cancel: (id: number) => api.post(`/api/v1/visitors/requests/${id}/cancel/`),
};
export const visitPurposesService      = makeCrudService("/api/v1/visitors/purposes");
export const visitorPassesService      = makeCrudService("/api/v1/visitors/passes");
export const visitorInvitationsService = makeCrudService("/api/v1/visitors/invitations");
export const watchlistsService         = makeCrudService("/api/v1/visitors/watchlists");

// ─────────────────────────────────────────────────────────────
// Anti-fraude — règles & investigations
// ─────────────────────────────────────────────────────────────
export const fraudRulesService = makeCrudService("/api/v1/antifraud/rules");
export const fraudInvestigationsService = {
  ...makeCrudService("/api/v1/antifraud/investigations"),
  close: (id: number, verdict: "confirmed" | "false_positive", note?: string) =>
    api.post(`/api/v1/antifraud/investigations/${id}/close/`, { verdict, note }),
};

// ─────────────────────────────────────────────────────────────
// Access control — règles d'accès
// ─────────────────────────────────────────────────────────────
export const accessRulesService = makeCrudService("/api/v1/access/rules");

// ─────────────────────────────────────────────────────────────
// Pointage RH
// ─────────────────────────────────────────────────────────────
export const overtimeRulesGenService    = makeCrudService("/api/v1/attendance/overtime-rules");
export const overtimeCalcsService       = makeCrudService("/api/v1/attendance/overtime");
export const attendanceCorrectionsService = makeCrudService("/api/v1/attendance/corrections");
export const rostersService             = makeCrudService("/api/v1/attendance/rosters");
export const leavesGenService           = makeCrudService("/api/v1/attendance/leaves");
export const punchesService             = makeCrudService("/api/v1/attendance/punches");

// ─────────────────────────────────────────────────────────────
// Notifications config
// ─────────────────────────────────────────────────────────────
export const notificationTemplatesService = makeCrudService("/api/v1/notifications/templates");

// ─────────────────────────────────────────────────────────────
// Reporting
// ─────────────────────────────────────────────────────────────
export const reportSchedulesService = makeCrudService("/api/v1/reports/schedules");
export const dashboardsService      = makeCrudService("/api/v1/reports/dashboards");
export const dashboardWidgetsService = makeCrudService("/api/v1/reports/widgets");
export const executiveDigestsService = {
  ...makeCrudService("/api/v1/reports/digests"),
  action: (id: number, verb: string) =>
    api.post(`/api/v1/reports/digests/${id}/action/${verb}/`),
};

// ─────────────────────────────────────────────────────────────
// RGPD / conformité
// ─────────────────────────────────────────────────────────────
export const retentionPoliciesService  = makeCrudService("/api/v1/audit/retention-policies");
export const dataExportsService = {
  ...makeCrudService("/api/v1/audit/data-exports"),
  generate: (id: number) => api.post(`/api/v1/audit/data-exports/${id}/generate/`),
};
export const conformityRegistersService = makeCrudService("/api/v1/audit/conformity");

// ─────────────────────────────────────────────────────────────
// Mobile & AI templates & feature flags
// ─────────────────────────────────────────────────────────────
export const mobileDevicesService = makeCrudService("/api/v1/mobile/devices");
export const aiTemplatesService   = makeCrudService("/api/v1/ai/templates");
export const featureFlagsService  = makeCrudService("/api/v1/core/feature-flags");

// ─────────────────────────────────────────────────────────────
// Face reco test
// ─────────────────────────────────────────────────────────────
export const faceTestService = {
  identify: (photo: File) => {
    const fd = new FormData();
    fd.append("photo", photo);
    return api.post<any>("/api/v1/employees/face/identify/", fd, {
      headers: { "Content-Type": "multipart/form-data" },
    });
  },
};
