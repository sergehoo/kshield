/**
 * agentsService — Phase 6 refonte cahier des charges §5.
 *
 * Client API pour la supervision des agents locaux structurés :
 * types, heartbeats, configurations versionnées, logs et commandes.
 */
import { api } from "@/lib/api";

// ─── Types alignés sur devices/models_agents.py ────────────────────
export type AgentState =
  | "installing" | "starting" | "running" | "degraded"
  | "stopped" | "crashed" | "updating" | "disabled" | "unreachable";

export type LogLevel = "debug" | "info" | "warning" | "error" | "critical";

export interface LocalAgentTypeDTO {
  id: string;
  code: string;
  label: string;
  description: string;
  module_name: string;
  icon: string;
  capabilities: string[];
  config_schema: Record<string, any>;
  is_active: boolean;
  is_system: boolean;
}

export interface AgentSummaryDTO {
  id: string;
  name: string;
  site_id: number | null;
  site_label: string;
  type_code: string;
  type_label: string;
  version: string;
  last_state: AgentState;
  last_seen_at: string | null;
  is_online: boolean;
  cpu_percent: number;
  memory_percent: number;
  storage_percent: number;
  events_pending: number;
  devices_connected: number;
  devices_expected: number;
  errors_last_hour: number;
  sync_last_success_at: string | null;
}

export interface HeartbeatDTO {
  id: string;
  sent_at: string;
  received_at: string;
  state: AgentState;
  version: string;
  uptime_seconds: number;
  cpu_percent: number;
  memory_percent: number;
  memory_mb: number;
  storage_percent: number;
  storage_free_mb: number;
  network_latency_ms: number;
  events_processed: number;
  events_pending: number;
  devices_connected: number;
  devices_expected: number;
  errors_last_hour: number;
  sync_last_success_at: string | null;
  recent_errors: Array<{ ts: string; msg: string }>;
  metadata: Record<string, any>;
}

export interface AgentConfigurationDTO {
  id: string;
  version: number;
  payload: Record<string, any>;
  checksum: string;
  applied_at: string | null;
  is_current: boolean;
  is_draft: boolean;
  notes: string;
  created_at: string;
  updated_at: string;
}

export interface AgentLogDTO {
  id: string;
  ts: string;
  level: LogLevel;
  message: string;
  context: Record<string, any>;
  source: string;
}

export interface AgentDetailDTO extends AgentSummaryDTO {
  hmac_secret_last_rotated_at: string | null;
  activated_at: string | null;
  created_at: string;
  updated_at: string;
  current_config?: AgentConfigurationDTO | null;
  recent_heartbeats?: HeartbeatDTO[];
}

export interface AgentListFilters {
  site?: number;
  type?: string;
  state?: AgentState;
  online?: "true" | "false";
  q?: string;
  page?: number;
  page_size?: number;
}

// ─── Endpoints ─────────────────────────────────────────────────────
export const agentsService = {
  list: (filters?: AgentListFilters) =>
    api.get<{
      count: number; page: number; page_size: number; num_pages: number;
      results: AgentSummaryDTO[];
    }>("/api/v1/devices/agents/", { params: filters }),

  detail: (agentId: string) =>
    api.get<AgentDetailDTO>(`/api/v1/devices/agents/${agentId}/`),

  heartbeats: (agentId: string, params?: { limit?: number; since?: string }) =>
    api.get<{ results: HeartbeatDTO[]; count: number }>(
      `/api/v1/devices/agents/${agentId}/heartbeats/`,
      { params },
    ),

  logs: (agentId: string, params?: {
    level?: LogLevel; source?: string; q?: string; limit?: number;
  }) =>
    api.get<{ results: AgentLogDTO[]; count: number }>(
      `/api/v1/devices/agents/${agentId}/logs/`,
      { params },
    ),

  listConfigs: (agentId: string) =>
    api.get<{ results: AgentConfigurationDTO[]; count: number }>(
      `/api/v1/devices/agents/${agentId}/configs/`,
    ),

  createConfig: (
    agentId: string,
    body: { payload: Record<string, any>; notes?: string; is_draft?: boolean },
  ) =>
    api.post<AgentConfigurationDTO>(
      `/api/v1/devices/agents/${agentId}/configs/`,
      body,
    ),

  applyConfig: (agentId: string, version: number) =>
    api.post<AgentConfigurationDTO>(
      `/api/v1/devices/agents/${agentId}/configs/${version}/apply/`,
    ),

  sendCommand: (agentId: string, cmd: string, payload?: Record<string, any>) =>
    api.post<{ ok: boolean; command_id: string }>(
      `/api/v1/devices/agents/${agentId}/commands/${cmd}/`,
      payload ?? {},
    ),

  types: () =>
    api.get<{ results: LocalAgentTypeDTO[]; count: number }>(
      "/api/v1/devices/agents/types/",
    ),
};

// ─── Helpers UI ────────────────────────────────────────────────────
export const STATE_LABELS: Record<AgentState, string> = {
  installing:  "Installation",
  starting:    "Démarrage",
  running:     "En cours",
  degraded:    "Dégradé",
  stopped:     "Arrêté",
  crashed:     "Crashé",
  updating:    "Mise à jour",
  disabled:    "Désactivé",
  unreachable: "Injoignable",
};

export type BadgeTone = "ok" | "warn" | "danger" | "info" | "muted" | "brand";

export const STATE_TONES: Record<AgentState, BadgeTone> = {
  installing:  "info",
  starting:    "info",
  running:     "ok",
  degraded:    "warn",
  stopped:     "muted",
  crashed:     "danger",
  updating:    "info",
  disabled:    "muted",
  unreachable: "danger",
};

export const LEVEL_TONES: Record<LogLevel, BadgeTone> = {
  debug:    "muted",
  info:     "info",
  warning:  "warn",
  error:    "danger",
  critical: "danger",
};
