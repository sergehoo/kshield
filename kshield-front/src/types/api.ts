/**
 * Types API partagés — dérivés de la doc /api/docs/ du backend Django.
 * Volontairement souples (champs optionnels) pour ne pas casser à chaque
 * changement de serializer côté back.
 */

export type Paginated<T> = {
  count: number;
  next: string | null;
  previous: string | null;
  results: T[];
};

// ─────────────────────────────────────────────────────────────
// Devices / équipements
// ─────────────────────────────────────────────────────────────
export type Device = {
  id: number;
  name: string;
  type: string;          // "face_terminal" | "reader" | "portique" | ...
  serial_number?: string | null;
  ip_address?: string | null;
  port?: number | null;
  status?: "active" | "offline" | "maintenance" | "retired" | string;
  last_heartbeat_at?: string | null;
  firmware_version?: string | null;
  site?: { id: number; name?: string } | number | null;
  model?: {
    id: number;
    brand?: string;
    model_name?: string;
    protocol?: string;
  } | number | null;
  created_at?: string;
  updated_at?: string;
  is_online?: boolean;
  push_mode?: boolean;
};

// ─────────────────────────────────────────────────────────────
// Access events / scans
// ─────────────────────────────────────────────────────────────
export type AccessEventHolderDetail = {
  id: number;
  kind: string;
  kind_label: string;
  name: string;
  reference?: string | null;
  photo_url?: string | null;
  status?: string | null;
  role?: string | null;
  organization?: string | null;
};

export type AccessEventDeviceDetail = {
  id: number;
  name: string;
  serial_number: string;
  model: string;
  type: string;
  type_label: string;
  status: string;
  status_label: string;
  ip_address?: string | null;
  last_heartbeat_at?: string | null;
};

export type AccessEventSiteDetail = {
  id: number;
  name: string;
  code: string;
  type: string;
  type_label: string;
};

export type AccessEventZoneDetail = {
  id: number;
  name: string;
  code: string;
  is_restricted: boolean;
};

export type AccessEventCheckpointDetail = {
  id: number;
  name: string;
  code: string;
  type: string;
  type_label: string;
  mode: string;
  mode_label: string;
  method: string;
  method_label: string;
};

export type AccessDecisionTrace = {
  id: number;
  event: number;
  rules_evaluated: unknown[] | Record<string, unknown>;
  deciding_rule_code?: string | null;
  risk_score: number;
  notes?: string | null;
};

export type AccessDoorCommand = {
  id: number;
  command: string;
  command_label?: string;
  status: string;
  status_label?: string;
  reason?: string | null;
  latency_ms?: number | null;
  created_at?: string;
  updated_at?: string;
  checkpoint?: number | null;
  device?: number | null;
  issued_by?: number | null;
  related_event?: number | null;
};

export type AccessEvent = {
  id: number;
  uuid?: string;
  timestamp: string;
  received_at?: string;
  direction?: "in" | "out" | "pass" | string;
  direction_label?: string;
  method?: "nfc" | "uhf" | "ble" | "qr" | "manual" | string;
  method_label?: string;
  decision?: "granted" | "denied" | "review" | string;
  decision_label?: string;
  denial_reason?: string | null;
  badge_uid?: string | null;
  helmet_uid?: string | null;
  tenant?: number | null;
  device?: { id: number; name?: string } | number | null;
  site?: { id: number; name?: string } | number | null;
  zone?: { id: number; name?: string } | number | null;
  checkpoint?: { id: number; name?: string; type?: string } | number | null;
  operator?: number | null;
  holder_name?: string | null;
  holder_kind?: "employee" | "worker" | "visitor" | string;
  holder_kind_label?: string;
  holder_object_id?: number | null;
  holder_content_type?: number | null;
  latitude?: string | number | null;
  longitude?: string | number | null;
  processing_delay_ms?: number | null;
  holder_detail?: AccessEventHolderDetail | null;
  device_detail?: AccessEventDeviceDetail | null;
  site_detail?: AccessEventSiteDetail | null;
  zone_detail?: AccessEventZoneDetail | null;
  checkpoint_detail?: AccessEventCheckpointDetail | null;
  operator_detail?: { id: number; name: string; email: string } | null;
  decision_trace?: AccessDecisionTrace | null;
  door_commands?: AccessDoorCommand[];
  raw_payload?: Record<string, unknown> | null;
};

// ─────────────────────────────────────────────────────────────
// Sites & companies
// ─────────────────────────────────────────────────────────────
export type Site = {
  id: number;
  name: string;
  code?: string | null;
  address?: string | null;
  company?: { id: number; name?: string } | number | null;
  is_active?: boolean;
  created_at?: string;
};

export type Company = {
  id: number;
  name: string;
  code?: string | null;
  legal_form?: string | null;
  ncc?: string | null;
  is_active?: boolean;
  created_at?: string;
};

// ─────────────────────────────────────────────────────────────
// People
// ─────────────────────────────────────────────────────────────
export type Employee = {
  id: number;
  full_name: string;
  matricule?: string | null;
  email?: string | null;
  phone?: string | null;
  department?: string | null;
  job_title?: string | null;
  photo?: string | null;
  is_active?: boolean;
  company?: { id: number; name?: string } | number | null;
};

export type Worker = {
  id: number;
  full_name: string;
  matricule?: string | null;
  trade?: string | null;
  photo?: string | null;
  helmet?: { id: number; uid?: string } | number | null;
  badge?: { id: number; uid?: string } | number | null;
  site?: { id: number; name?: string } | number | null;
};

// ─────────────────────────────────────────────────────────────
// Badges & helmets
// ─────────────────────────────────────────────────────────────
export type Badge = {
  id: number;
  uid: string;
  tech: "nfc" | "uhf" | "qr" | "ble" | string;
  status: "active" | "suspended" | "revoked" | "lost" | string;
  holder_kind?: string;
  holder_name?: string | null;
  issued_at?: string;
  revoked_at?: string | null;
};

// ─────────────────────────────────────────────────────────────
// Attendance
// ─────────────────────────────────────────────────────────────
export type AttendanceDay = {
  id: number;
  date: string;
  worker?: { id: number; full_name?: string } | number | null;
  first_in?: string | null;
  last_out?: string | null;
  worked_minutes?: number;
  is_late?: boolean;
  overtime_minutes?: number;
  status?: "present" | "absent" | "late" | "partial" | string;
};

// ─────────────────────────────────────────────────────────────
// Notifications
// ─────────────────────────────────────────────────────────────
export type Notification = {
  id: number;
  level: "info" | "warn" | "danger" | "success" | string;
  title: string;
  body?: string | null;
  read_at?: string | null;
  created_at: string;
  category?: string;
};

// ─────────────────────────────────────────────────────────────
// AI assistant
// ─────────────────────────────────────────────────────────────
export type AIMessage = {
  role: "user" | "assistant" | "system" | "tool";
  content: string;
  tool_calls?: any[];
  created_at?: string;
};

export type AIConversation = {
  id: number;
  title?: string;
  created_at: string;
  updated_at: string;
  messages?: AIMessage[];
};
