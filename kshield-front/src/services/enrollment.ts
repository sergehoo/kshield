/**
 * KAYDAN SHIELD — service d'enrôlement RFID temps réel.
 *
 * Wrappe les endpoints REST /api/v1/rfid/enrollment/ + /api/v1/devices/*
 * Utilisé conjointement avec `useEnrollmentSession` (WebSocket).
 */
import { api } from "@/lib/api";

export interface EnrollmentSession {
  id: string;
  status: "pending" | "listening" | "completed" | "cancelled" | "timeout" | "error";
  mode: "single" | "bulk";
  site_id: number | null;
  zone_id: number | null;
  reader_id: number | null;
  reader_serial: string | null;
  holder_kind: "worker" | "employee" | "visitor" | "";
  holder_id: number | null;
  scans_count: number;
  valid_count: number;
  duplicate_count: number;
  error_count: number;
  timeout_seconds: number;
  started_at: string | null;
  ended_at: string | null;
  channel_group: string;
  events?: EnrollmentEvent[];
}

export interface EnrollmentEvent {
  id: number | string;
  event_type:
    | "card.detected" | "card.duplicate" | "card.enrolled" | "card.error"
    | "session.start" | "session.stop" | "session.timeout" | "device.error";
  uid?: string;
  device_id?: number | null;
  device_serial?: string;
  rssi?: number | null;
  message?: string;
  payload?: any;
  badge_id?: number | null;
  at?: string;
}

export interface StartSessionParams {
  site_id?: number | null;
  zone_id?: number | null;
  reader_id?: number | null;
  mode?: "single" | "bulk";
  holder_kind?: "worker" | "employee" | "visitor" | "";
  holder_id?: number | null;
  timeout_seconds?: number;
}

export interface ConfirmParams {
  uid: string;
  tech?: "nfc" | "uhf" | "uhf_xerafy" | "qr";
  category?: "worker_rfid" | "employee_rfid" | "visitor_qr";
  holder_kind?: "worker" | "employee" | "visitor" | null;
  holder_id?: number | null;
  valid_until?: string | null;
}

export const enrollmentService = {
  start: (params: StartSessionParams) =>
    api.post<EnrollmentSession>("/api/v1/rfid/enrollment/start/", params),

  stop: (sessionId: string, reason?: string) =>
    api.post<EnrollmentSession>(
      `/api/v1/rfid/enrollment/${sessionId}/stop/`,
      { reason: reason || "" },
    ),

  confirm: (sessionId: string, params: ConfirmParams) =>
    api.post<{ badge_id: number; uid: string; status: string; type: string }>(
      `/api/v1/rfid/enrollment/${sessionId}/confirm/`,
      params,
    ),

  get: (sessionId: string, limit = 100) =>
    api.get<EnrollmentSession>(
      `/api/v1/rfid/enrollment/sessions/${sessionId}/`,
      { params: { limit } },
    ),

  ingest: (params: {
    uid: string;
    session_id?: string;
    device_id?: number;
    rssi?: number;
    extra?: any;
  }) =>
    api.post("/api/v1/rfid/enrollment/ingest/", params),

  exportSession: (sessionId: string, format: "csv" | "pdf" = "csv") =>
    api.get(`/api/v1/rfid/enrollment/sessions/${sessionId}/export/`, {
      params: { format }, responseType: "blob",
    }),
};

// Local Agents (Kaydan Shield Local Agent)
export interface LocalAgent {
  id: string;
  label: string;
  site_id: number | null;
  connected: boolean;
  last_seen_at: string | null;
  version: string;
  os_info: string;
  devices_discovered_count: number;
  created_at: string;
  api_token?: string;      // uniquement au create/rotate
  hmac_secret?: string;    // uniquement au create/rotate
  toml?: string;           // uniquement au create/rotate
}

export const localAgentsService = {
  list: () =>
    api.get<{ count: number; results: LocalAgent[] }>("/api/v1/devices/local-agents/"),
  get: (id: string) =>
    api.get<LocalAgent>(`/api/v1/devices/local-agents/${id}/`),
  create: (label: string, siteId?: number | null) =>
    api.post<LocalAgent>("/api/v1/devices/local-agents/", {
      label, site_id: siteId || null,
    }),
  remove: (id: string) =>
    api.delete(`/api/v1/devices/local-agents/${id}/`),
  rotateToken: (id: string) =>
    api.post<LocalAgent>(`/api/v1/devices/local-agents/${id}/rotate-token/`),
};

// Alertes système agrégées (agents/devices offline, sessions bloquées, commandes timeout)
export interface SystemAlert {
  id: string;
  type: "agent_offline" | "device_offline" | "session_stalled" | "command_timeout" | "agent_stale";
  severity: "critical" | "warning" | "info";
  title: string;
  detail: string;
  target_url?: string | null;
  target_id?: string | null;
  since?: string | null;
  acknowledged_at?: string | null;
  resolved_at?: string | null;
}

export const systemAlertsService = {
  list: (params?: { include_resolved?: boolean; limit?: number }) => api.get<{
    count: number;
    critical: number;
    warning: number;
    info: number;
    alerts: SystemAlert[];
    at: string;
  }>("/api/v1/devices/alerts/system/", { params }),

  acknowledge: (alertId: string) =>
    api.post<SystemAlert>(`/api/v1/devices/alerts/${alertId}/acknowledge/`),
};

// Stats temps réel — snapshot pour le dashboard
export interface RealtimeStats {
  at: string;
  devices: { total: number; online: number; offline: number; online_ratio: number };
  agents: { total: number; connected: number; disconnected: number };
  enrollment: {
    sessions_active: number;
    scans_last_hour: number;
    enrolled_last_24h: number;
  };
  commands: {
    total_last_hour: number;
    completed_last_hour: number;
    failed_last_hour: number;
    success_ratio: number;
  };
  alerts: { critical: number; warning: number; total: number };
}

export const realtimeStatsService = {
  get: () => api.get<RealtimeStats>("/api/v1/devices/stats/realtime/"),
};

// ═══ Driver Framework (Vague 7) ═══
export interface DriverInfo {
  vendor: string;
  class: string;
  module: string;
  supported_models: string[];
  capabilities: string[];
}

export const driversService = {
  list: () => api.get<{ count: number; drivers: DriverInfo[] }>(
    "/api/v1/devices/drivers/",
  ),
  test: (deviceId: number) => api.post<any>(
    `/api/v1/devices/${deviceId}/driver-test/`,
  ),
};

// ═══ Digital Twin ═══
export interface DeviceTwin {
  device_id: number;
  serial: string;
  reachable: boolean;
  health_score: number;
  health_status: "excellent" | "good" | "degraded" | "critical";
  health_reasons: string[];
  driver_class: string;
  metrics: {
    latency_ms: number | null;
    uptime_seconds: number | null;
    cpu_percent: number | null;
    ram_percent: number | null;
    storage_percent: number | null;
    temperature_c: number | null;
    battery_percent: number | null;
    network_quality: number | null;
  };
  firmware: string;
  hardware: string;
  recent_errors: Array<{ at: string; msg: string }>;
  raw_status: any;
  last_probed_at: string | null;
  last_seen_at: string | null;
  updated_at: string | null;
}

export const twinService = {
  get: (deviceId: number) =>
    api.get<DeviceTwin>(`/api/v1/devices/${deviceId}/twin/`),
  refresh: (deviceId: number) =>
    api.post<any>(`/api/v1/devices/${deviceId}/twin/refresh/`),
};

// ═══ Auto Discovery multi-protocole ═══
export interface DiscoveredNetDevice {
  ip: string;
  mac: string;
  hostname: string;
  vendor: string;
  model: string;
  firmware: string;
  device_type_hint: string;
  protocols_detected: string[];
  already_known: boolean;
  protocols_raw: any;
}

export const discoveryService = {
  scan: (params?: { protocols?: string[]; ip_range?: string; timeout?: number }) =>
    api.post<{ count: number; devices: DiscoveredNetDevice[] }>(
      "/api/v1/devices/discovery/scan/",
      params || {},
    ),
};

// ═══ Vague 8 — Maintenance prédictive ═══
export interface MaintenanceTicket {
  id: string;
  device_id: string;
  device_serial: string | null;
  kind: string;
  severity: "info" | "warning" | "critical";
  status: "open" | "in_progress" | "resolved" | "cancelled";
  title: string;
  description: string;
  prediction: any;
  confidence: number;
  created_by_engine: boolean;
  assigned_to: number | null;
  scheduled_for: string | null;
  resolved_at: string | null;
  resolution_notes: string;
  created_at: string;
}

export const maintenanceService = {
  list: (params?: { status?: string; severity?: string; device_id?: string; limit?: number }) =>
    api.get<{ count: number; tickets: MaintenanceTicket[] }>(
      "/api/v1/devices/maintenance/tickets/", { params },
    ),
  get: (id: string) =>
    api.get<MaintenanceTicket>(`/api/v1/devices/maintenance/tickets/${id}/`),
  create: (body: Partial<MaintenanceTicket>) =>
    api.post<MaintenanceTicket>("/api/v1/devices/maintenance/tickets/", body),
  update: (id: string, body: Partial<MaintenanceTicket>) =>
    api.patch<MaintenanceTicket>(`/api/v1/devices/maintenance/tickets/${id}/`, body),
  remove: (id: string) =>
    api.delete(`/api/v1/devices/maintenance/tickets/${id}/`),
};

// ═══ Vague 8 — Topologie réseau ═══
export interface TopologyResponse {
  tenant: { id: number; name: string; devices_total: number; agents_total: number };
  sites: Array<{
    id: number; name: string; code: string;
    company: { id: number; name: string } | null;
    devices_total: number; devices_online: number;
    zones: Array<{ id: number; name: string; devices_total: number; devices_online: number }>;
  }>;
  devices: Array<any>;
  agents: Array<any>;
}

export const topologyService = {
  get: () => api.get<TopologyResponse>("/api/v1/devices/topology/"),
};

// ═══ Vague 8 — Plugin Marketplace ═══
export interface PluginCatalogItem {
  vendor: string;
  name: string;
  protocols: string[];
  verified?: boolean;
  coming_soon?: boolean;
  installed: boolean;
}

// ═══ Vague 9 — Edge Gateway ═══
export interface GatewayPackage {
  id: number;
  name: string;
  platform: string;
  platform_label: string;
  version: string;
  size_bytes: number;
  checksum_sha256: string;
  release_notes: string;
  published_at: string | null;
  is_latest: boolean;
  min_os_version: string;
  file_url: string | null;
  docker_image: string;
  has_file: boolean;
}

export interface Gateway {
  id: string;
  label: string;
  site_id: number | null;
  status: "connected" | "disconnected" | "pending_activation" | "activation_expired" | "revoked";
  connected: boolean;
  last_seen_at: string | null;
  activated_at: string | null;
  revoked_at: string | null;
  activation_expires_at: string | null;
  ip_local: string | null;
  ip_public: string | null;
  os_info: string;
  version: string;
  uptime_seconds: number | null;
  events_pending: number;
  devices_discovered_count: number;
  mqtt_status: string;
  ws_status: string;
  cloud_status: string;
  created_at: string;
  // secrets — visibles au create/rotate uniquement
  api_token?: string;
  hmac_secret?: string;
  activation_token?: string;
  activation_pairing_url?: string;
  activation_ttl_hours?: number;
}

export const edgeGatewayService = {
  // Packages
  listPackages: (params?: { platform?: string; latest?: boolean }) =>
    api.get<{ count: number; packages: GatewayPackage[]; by_platform: Record<string, GatewayPackage[]> }>(
      "/api/v1/devices/edge-gateway/packages/", { params },
    ),
  installCommand: (pkgId: number, gatewayId?: string) =>
    api.get<{ command: string; platform: string; requires_token: boolean }>(
      `/api/v1/devices/edge-gateway/packages/${pkgId}/install-command/`,
      { params: gatewayId ? { gateway_id: gatewayId } : undefined },
    ),
  downloadUrl: (pkgId: number) =>
    `/api/v1/devices/edge-gateway/packages/${pkgId}/download/`,

  // Gateways
  list: () =>
    api.get<{ count: number; gateways: Gateway[] }>("/api/v1/devices/edge-gateway/"),
  create: (label: string, siteId?: number | null) =>
    api.post<Gateway>("/api/v1/devices/edge-gateway/", { label, site_id: siteId || null }),
  get: (id: string) =>
    api.get<Gateway & { devices_discovered: any[] }>(`/api/v1/devices/edge-gateway/${id}/`),
  update: (id: string, body: Partial<Gateway>) =>
    api.patch<Gateway>(`/api/v1/devices/edge-gateway/${id}/`, body),
  remove: (id: string) =>
    api.delete(`/api/v1/devices/edge-gateway/${id}/`),
  rotateActivation: (id: string) =>
    api.post<Gateway>(`/api/v1/devices/edge-gateway/${id}/rotate-activation/`),
  revoke: (id: string) =>
    api.post<Gateway>(`/api/v1/devices/edge-gateway/${id}/revoke/`),
  reactivate: (id: string) =>
    api.post<Gateway>(`/api/v1/devices/edge-gateway/${id}/reactivate/`),

  // Actions
  restart: (id: string) =>
    api.post(`/api/v1/devices/edge-gateway/${id}/restart/`),
  forceSync: (id: string) =>
    api.post(`/api/v1/devices/edge-gateway/${id}/force-sync/`),
  scanNetwork: (id: string, protocols?: string[]) =>
    api.post(`/api/v1/devices/edge-gateway/${id}/scan-network/`, { protocols }),
  triggerUpdate: (id: string, packageId: number) =>
    api.post(`/api/v1/devices/edge-gateway/${id}/update/`, { package_id: packageId }),

  // Supervision
  logs: (id: string) =>
    api.get<{ count: number; logs: any[] }>(`/api/v1/devices/edge-gateway/${id}/logs/`),
  devices: (id: string) =>
    api.get<{ count: number; devices: any[] }>(`/api/v1/devices/edge-gateway/${id}/devices/`),

  // Download personnalisé — Phase 1 : génère un ZIP avec config injectée.
  // Utilisation : ouvre un nouvel onglet ou déclenche le browser pour DL.
  //   window.open(edgeGatewayService.downloadPackageUrl(id, "windows_exe"));
  // ou fetch + blob si on veut afficher un spinner :
  //   const r = await api.get(edgeGatewayService.downloadPackageUrl(...), { responseType: "blob" });
  downloadPackageUrl: (id: string, platform: string) =>
    `/api/v1/devices/edge-gateway/${id}/download/?platform=${encodeURIComponent(platform)}`,
  downloadPackageBlob: (id: string, platform: string) =>
    api.get(`/api/v1/devices/edge-gateway/${id}/download/`, {
      params: { platform },
      responseType: "blob",
    }),
};

export const marketplaceService = {
  list: () => api.get<{ count: number; plugins: PluginCatalogItem[] }>(
    "/api/v1/devices/marketplace/plugins/",
  ),
  upload: (file: File) => {
    const fd = new FormData();
    fd.append("file", file);
    return api.post("/api/v1/devices/marketplace/plugins/upload/", fd, {
      headers: { "Content-Type": "multipart/form-data" },
    });
  },
};

// Device commands
export const deviceCommandService = {
  send: (deviceId: number, kind: string, payload?: any, timeoutSeconds?: number) =>
    api.post(`/api/v1/devices/${deviceId}/commands/`, {
      kind, payload: payload || {}, timeout_seconds: timeoutSeconds,
    }),
  get: (commandId: string) =>
    api.get(`/api/v1/devices/commands/${commandId}/`),
  status: (deviceId: number) =>
    api.get(`/api/v1/devices/${deviceId}/status/`),
};
