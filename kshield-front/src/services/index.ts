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
    api.get<Paginated<Device>>("/api/v1/devices/devices/", { params }),
  get: (id: number) => api.get<Device>(`/api/v1/devices/devices/${id}/`),
  create: (body: Partial<Device>) => api.post<Device>("/api/v1/devices/devices/", body),
  update: (id: number, body: Partial<Device>) =>
    api.patch<Device>(`/api/v1/devices/devices/${id}/`, body),
  remove: (id: number) => api.delete(`/api/v1/devices/devices/${id}/`),
  testConnection: (id: number) =>
    api.post<any>(`/api/v1/devices/${id}/test-connection/`),
  zkSyncNow: (id: number) => api.post<any>(`/api/v1/devices/${id}/zk-sync/`),
  zkPushUsers: (id: number) => api.post<any>(`/api/v1/devices/${id}/zk-push-users/`),
  iclockDebug: (id: number) => api.get<any>(`/api/v1/devices/${id}/iclock-debug/`),
  pubApiDebug: () => api.get<any>("/api/v1/devices/pubapi-debug/"),
  identifyByIp: (ip: string) =>
    api.post<any>("/api/v1/devices/identify-by-ip/", { ip }),
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
    api.get<Paginated<Company>>("/api/v1/sites/companies/", { params }),
  create: (body: Partial<Company>) =>
    api.post<Company>("/api/v1/sites/companies/", body),
  update: (id: number, body: Partial<Company>) =>
    api.patch<Company>(`/api/v1/sites/companies/${id}/`, body),
  remove: (id: number) => api.delete(`/api/v1/sites/companies/${id}/`),
};

// ─────────────────────────────────────────────────────────────
// People
// ─────────────────────────────────────────────────────────────
export const employeesService = {
  list: (params?: Record<string, any>) =>
    api.get<Paginated<Employee>>("/api/v1/employees/employees/", { params }),
  create: (body: Partial<Employee>) =>
    api.post<Employee>("/api/v1/employees/employees/", body),
  update: (id: number, body: Partial<Employee>) =>
    api.patch<Employee>(`/api/v1/employees/employees/${id}/`, body),
  remove: (id: number) => api.delete(`/api/v1/employees/employees/${id}/`),
  faceStatus: () => api.get<any>("/api/v1/employees/face/status/"),
};

export const workersService = {
  list: (params?: Record<string, any>) =>
    api.get<Paginated<Worker>>("/api/v1/ouvriers/workers/", { params }),
  get: (id: number) => api.get<Worker>(`/api/v1/ouvriers/workers/${id}/`),
  create: (body: Partial<Worker>) =>
    api.post<Worker>("/api/v1/ouvriers/workers/", body),
  update: (id: number, body: Partial<Worker>) =>
    api.patch<Worker>(`/api/v1/ouvriers/workers/${id}/`, body),
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
};

export const helmetsService = {
  list: (params?: Record<string, any>) =>
    api.get<Paginated<any>>("/api/v1/devices/helmets/", { params }),
  bulkEnroll: (body: any) => api.post("/api/v1/devices/helmets/bulk-enroll/", body),
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
  get: (id: number) => api.get<any>(`/api/v1/sites/companies/${id}/`),
});
