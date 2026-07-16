/**
 * discoveryService — Phase 5 refonte cahier des charges §2.
 *
 * Client API pour la découverte et l'adoption des équipements détectés
 * par les agents / gateways sur le LAN.
 */
import { api } from "@/lib/api";

export type DiscoveryStatus =
  | "detected" | "tested" | "adopted" | "rejected"
  | "conflict" | "stale" | "reactivated" | "duplicate"
  | "invalid" | "quarantined" | "archived";

export type Compatibility = "supported" | "beta" | "unsupported" | "unknown";

export interface DiscoveryDTO {
  id: string;
  status: DiscoveryStatus;
  status_label?: string;
  compatibility: Compatibility;

  mac_address: string;
  ip_address: string;
  hostname: string;

  vendor: string;
  model: string;
  firmware_version: string;
  device_type: string;
  device_type_label?: string;
  detected_via: string;

  protocols: string[];
  ports: number[];
  latency_ms: number;

  gateway_id: string | null;
  gateway_label: string;
  site_id: number | null;
  site_label: string;
  scan_id: string | null;

  adopted_device_id: number | null;

  first_seen_at: string;
  last_seen_at: string;
  last_test_at?: string | null;
  last_test_success?: boolean;
  last_test_error?: string;
  adopted_at?: string | null;
  adopted_by?: string;
  rejected_at?: string | null;
  rejected_reason?: string;
  raw_payload?: Record<string, any>;
}

export interface DiscoveryScanDTO {
  id: string;
  gateway_id: string | null;
  gateway_label: string;
  site_id: number | null;
  site_label: string;
  protocols_used: string[];
  duration_ms: number;
  devices_detected: number;
  devices_new: number;
  devices_updated: number;
  status: string;
  error: string;
  created_at: string;
}

export interface DiscoveryFilters {
  status?: DiscoveryStatus;
  vendor?: string;
  gateway?: string;
  compatibility?: Compatibility;
  limit?: number;
}

export const discoveryService = {
  list: (params?: DiscoveryFilters) =>
    api.get<{ count: number; results: DiscoveryDTO[] }>(
      "/api/v1/devices/discovery/",
      { params },
    ),

  detail: (id: string) =>
    api.get<DiscoveryDTO>(`/api/v1/devices/discovery/${id}/`),

  test: (id: string) =>
    api.post<any>(`/api/v1/devices/discovery/${id}/test/`),

  adopt: (id: string, body?: {
    site_id?: number;
    checkpoint_id?: number;
    name?: string;
    driver?: string;
  }) =>
    api.post<any>(`/api/v1/devices/discovery/${id}/adopt/`, body ?? {}),

  reject: (id: string, reason?: string) =>
    api.post<any>(`/api/v1/devices/discovery/${id}/reject/`, { reason }),

  reactivate: (id: string) =>
    api.post<any>(`/api/v1/devices/discovery/${id}/reactivate/`),

  scans: (params?: { gateway?: string; limit?: number }) =>
    api.get<{ count: number; results: DiscoveryScanDTO[] }>(
      "/api/v1/devices/discovery/scans/",
      { params },
    ),
};

// ─── UI helpers ────────────────────────────────────────────────────
export const COMPATIBILITY_TONES: Record<Compatibility,
  "ok" | "warn" | "danger" | "muted"> = {
  supported:   "ok",
  beta:        "warn",
  unsupported: "danger",
  unknown:     "muted",
};

export const COMPATIBILITY_LABELS: Record<Compatibility, string> = {
  supported:   "Compatible",
  beta:        "Bêta",
  unsupported: "Non supporté",
  unknown:     "Inconnu",
};

export const STATUS_LABELS: Record<DiscoveryStatus, string> = {
  detected:    "Détecté",
  tested:      "Testé",
  adopted:     "Adopté",
  rejected:    "Rejeté",
  conflict:    "Conflit",
  stale:       "Périmé",
  reactivated: "Réactivé",
  duplicate:   "Doublon",
  invalid:     "Invalide",
  quarantined: "En quarantaine",
  archived:    "Archivé",
};

export const STATUS_TONES: Record<DiscoveryStatus,
  "ok" | "warn" | "danger" | "info" | "muted" | "brand"> = {
  detected:    "info",
  tested:      "brand",
  adopted:     "ok",
  rejected:    "muted",
  conflict:    "warn",
  stale:       "warn",
  reactivated: "info",
  duplicate:   "warn",
  invalid:     "danger",
  quarantined: "danger",
  archived:    "muted",
};
