/**
 * syncService — Phase 4 refonte cahier des charges §4.5.
 *
 * Client API pour l'observation des batches Edge Sync et la résolution
 * des conflits (cloud_wins / edge_wins / merge / ignore / escalated).
 */
import { api } from "@/lib/api";

export type SyncDirection = "up" | "down" | "bidirectional";
export type SyncStatus =
  | "pending" | "in_progress" | "completed" | "failed" | "cancelled";
export type Resolution =
  | "pending" | "cloud_wins" | "edge_wins" | "merge" | "ignore" | "escalated";

export interface SyncBatchDTO {
  id: string;
  batch_id: string;
  gateway_id: string;
  direction: SyncDirection;
  status: SyncStatus;
  priority: number;
  started_at: string;
  processed_at: string | null;
  duration_ms: number;
  items_declared: number;
  items_uploaded: number;
  items_processed: number;
  items_succeeded: number;
  items_failed: number;
  items_conflicted: number;
  payload_size_bytes: number;
}

export interface SyncConflictDTO {
  id: string;
  batch_id: string;
  batch_batch_id: string;
  gateway_label: string;
  entity_type: string;
  entity_key: string;
  edge_version: string;
  cloud_version: string;
  edge_payload: any;
  cloud_payload: any;
  resolution: Resolution;
  resolution_notes: string;
  resolved_by: string | null;
  resolved_at: string | null;
  created_at: string;
}

export const syncService = {
  batches: (gatewayId: string, params?: { status?: SyncStatus; direction?: SyncDirection; limit?: number }) =>
    api.get<{ count: number; results: SyncBatchDTO[] }>(
      `/api/v1/devices/edge/gateways/${gatewayId}/sync/batches/`,
      { params },
    ),

  conflicts: (params?: { resolution?: Resolution; limit?: number }) =>
    api.get<{ count: number; results: SyncConflictDTO[] }>(
      "/api/v1/devices/edge/sync/conflicts/",
      { params },
    ),

  resolveConflict: (
    conflictId: string,
    resolution: Exclude<Resolution, "pending">,
    notes?: string,
  ) =>
    api.post<{ ok: boolean; conflict: SyncConflictDTO }>(
      `/api/v1/devices/edge/sync/conflicts/${conflictId}/resolve/`,
      { resolution, notes },
    ),
};

// ─── UI helpers ────────────────────────────────────────────────────
export const RESOLUTION_LABELS: Record<Resolution, string> = {
  pending:    "En attente",
  cloud_wins: "Cloud prioritaire",
  edge_wins:  "Edge prioritaire",
  merge:      "Fusion",
  ignore:     "Ignorer",
  escalated:  "Escaladé",
};

export const RESOLUTION_TONES: Record<Resolution,
  "ok" | "warn" | "danger" | "info" | "muted" | "brand"> = {
  pending:    "warn",
  cloud_wins: "info",
  edge_wins:  "brand",
  merge:      "ok",
  ignore:     "muted",
  escalated:  "danger",
};
