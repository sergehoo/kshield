/**
 * badgeLifecycleService — Phase 3 refonte cahier des charges §3.
 *
 * Client API pour le cycle de vie complet du badge (12 états) :
 * assign / unassign / suspend / resume / expire / report-lost /
 * report-stolen / disable / enable / revoke / destroy / archive / history.
 */
import { api } from "@/lib/api";

export type HolderKind =
  | "worker" | "employee" | "visitor" | "contractor"
  | "vehicle" | "material" | "temporary" | "unknown";

export type AccessLevel =
  | "basic" | "restricted" | "elevated" | "vip" | "emergency";

export interface BadgeAssignBody {
  holder_kind: HolderKind;
  holder_id?: number;
  holder_label?: string;
  site_id?: number;
  zone_ids?: number[];
  access_level?: AccessLevel;
  expires_at?: string;
  activated_at?: string;
  time_window_start?: string;
  time_window_end?: string;
  allowed_weekdays?: string;
  is_permanent?: boolean;
  reason?: string;
  validated_by_id?: number;
  notes?: string;
  metadata?: Record<string, any>;
}

export interface AssignmentDTO {
  id: string;
  holder_kind: HolderKind;
  holder_label: string;
  holder_id: number | null;
  site_id: number | null;
  site_label: string;
  access_level: AccessLevel;
  assigned_at: string;
  activated_at: string | null;
  expires_at: string | null;
  time_window_start: string | null;
  time_window_end: string | null;
  allowed_weekdays: string;
  is_permanent: boolean;
  reason: string;
  assigned_by: string | null;
  validated_by: string | null;
  closed_at: string | null;
  close_reason: string;
  close_notes: string;
  closed_by: string | null;
  notes: string;
  is_active: boolean;
}

export const badgeLifecycleService = {
  assign: (badgeId: string, body: BadgeAssignBody) =>
    api.post<{ ok: boolean; assignment: AssignmentDTO }>(
      `/api/v1/devices/badges/${badgeId}/assign/`,
      body,
    ),

  action: (badgeId: string, action:
    | "unassign" | "suspend" | "resume" | "expire" | "report-lost"
    | "report-stolen" | "disable" | "enable" | "revoke" | "destroy" | "archive",
    body?: { reason?: string; notes?: string }) =>
    api.post<any>(
      `/api/v1/devices/badges/${badgeId}/${action}/`,
      body ?? {},
    ),

  history: (badgeId: string) =>
    api.get<{ results: any[] }>(
      `/api/v1/devices/badges/${badgeId}/history/`,
    ),
};

export const HOLDER_LABELS: Record<HolderKind, string> = {
  worker:     "Ouvrier",
  employee:   "Employé",
  visitor:    "Visiteur",
  contractor: "Sous-traitant",
  vehicle:    "Véhicule",
  material:   "Matériel",
  temporary:  "Temporaire",
  unknown:    "Inconnu",
};

export const ACCESS_LEVEL_LABELS: Record<AccessLevel, string> = {
  basic:      "Standard",
  restricted: "Restreint",
  elevated:   "Élevé",
  vip:        "VIP",
  emergency:  "Urgence",
};
