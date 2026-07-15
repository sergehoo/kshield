/**
 * eventsService — Phase 2 refonte cahier des charges §1.
 *
 * Client API pour la nomenclature + supervision des événements techniques.
 */
import { api } from "@/lib/api";

// ─── Types alignés sur devices/models_events.py ────────────────────
export type EventCategory =
  | "access" | "attendance" | "rfid" | "ble"
  | "device" | "gateway" | "security" | "system";

export type EventSeverity =
  | "info" | "warning" | "critical" | "emergency";

export type EventResult =
  | "granted" | "denied" | "pending" | "anomaly" | "alert" | "neutral";

export type TransmissionMode =
  | "realtime_cloud" | "gateway_local" | "deferred_sync" | "offline";

export interface DeviceEventDTO {
  id: string;
  code: string;
  category: EventCategory;
  label: string;
  icon?: string;
  color?: string;
  severity: EventSeverity;
  result: EventResult;
  occurred_at: string;
  received_at: string;
  site_id?: number | null;
  site_label?: string;
  zone_id?: number | null;
  device_id?: number | null;
  device_label?: string;
  device_type?: string;
  gateway_id?: string | null;
  gateway_label?: string;
  agent_id?: string | null;
  badge_uid?: string;
  helmet_uid?: string;
  holder_kind?: string;
  holder_ref?: string;
  message?: string;
  transmission_mode: TransmissionMode;
  is_offline: boolean;
  is_synced: boolean;
  photo_url?: string;
  // full uniquement
  payload?: Record<string, any>;
  acknowledgements?: EventAcknowledgementDTO[];
  ack_count?: number;
  is_acknowledged?: boolean;
  is_resolved?: boolean;
}

export interface EventAcknowledgementDTO {
  id: string;
  action: "acknowledge" | "resolve" | "escalate" | "comment" | "evidence" | "reopen";
  user: string;
  user_id: number;
  notes: string;
  evidence_url: string;
  created_at: string;
}

export interface EventTypeDTO {
  code: string;
  label: string;
  severity_default: EventSeverity;
  result_default: EventResult;
  icon: string;
  color: string;
  triggers_alert: boolean;
  requires_ack: boolean;
}

export interface EventFilters {
  period?: "today" | "last_hour" | "last_24h" | "last_7d" | "custom";
  date_from?: string;
  date_to?: string;
  site?: number;
  zone?: number;
  checkpoint?: number;
  gateway?: string;
  agent?: string;
  device?: number;
  type?: string | string[];
  category?: EventCategory;
  severity?: EventSeverity;
  result?: EventResult;
  holder?: string;
  badge?: string;
  has_helmet?: "true" | "false";
  transmission?: TransmissionMode;
  is_offline?: "true" | "false";
  is_synced?: "true" | "false";
  q?: string;
  page?: number;
  page_size?: number;
}

// ─── Endpoints ─────────────────────────────────────────────────────
export const eventsService = {
  list: (filters?: EventFilters) =>
    api.get<{
      count: number; page: number; page_size: number; num_pages: number;
      results: DeviceEventDTO[];
    }>("/api/v1/devices/events/", { params: filters }),

  live: (filters?: EventFilters) =>
    api.get<{
      server_time: string;
      count: number; returned: number;
      ws_url: string;
      stats_24h: {
        total: number;
        by_severity: Record<EventSeverity, number>;
        by_result: Record<string, number>;
      };
      results: DeviceEventDTO[];
    }>("/api/v1/devices/events/live/", { params: filters }),

  detail: (eventId: string) =>
    api.get<DeviceEventDTO>(`/api/v1/devices/events/${eventId}/`),

  acknowledge: (eventId: string, notes?: string) =>
    api.post(`/api/v1/devices/events/${eventId}/acknowledge/`, { notes }),

  resolve: (eventId: string, notes?: string, evidenceUrl?: string) =>
    api.post(`/api/v1/devices/events/${eventId}/resolve/`, {
      notes,
      evidence_url: evidenceUrl,
    }),

  comment: (eventId: string, notes: string) =>
    api.post(`/api/v1/devices/events/${eventId}/comment/`, { notes }),

  types: () =>
    api.get<{
      count: number;
      categories: Record<EventCategory, EventTypeDTO[]>;
    }>("/api/v1/devices/events/types/"),

  exportCsvUrl: (filters?: EventFilters) => {
    const params = new URLSearchParams();
    if (filters) {
      Object.entries(filters).forEach(([k, v]) => {
        if (Array.isArray(v)) {
          v.forEach((x) => params.append(k, String(x)));
        } else if (v !== undefined && v !== null && v !== "") {
          params.append(k, String(v));
        }
      });
    }
    return `/api/v1/devices/events/export.csv?${params}`;
  },
};
