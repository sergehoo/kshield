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
