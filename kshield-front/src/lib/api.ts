/**
 * Axios instance branchée sur l'API KAYDAN SHIELD.
 *
 * - `VITE_API_BASE_URL` définit l'origine absolue (ex. https://api.kaydanshield.com).
 * - En dev sans variable, `baseURL = ""` → toutes les requêtes passent par le
 *   proxy Vite (voir vite.config.ts).
 * - Un interceptor injecte le JWT stocké dans le auth store.
 * - En 401, on tente un refresh via /api/v1/auth/token/refresh/ ; en cas d'échec,
 *   on purge le store et on redirige vers /login.
 */
import axios, {
  AxiosError,
  AxiosInstance,
  AxiosRequestConfig,
  InternalAxiosRequestConfig,
} from "axios";
import { useAuthStore } from "@/lib/auth";

const BASE_URL = (import.meta.env.VITE_API_BASE_URL || "").replace(/\/$/, "");

export const api: AxiosInstance = axios.create({
  baseURL: BASE_URL,
  timeout: 30_000,
  headers: {
    "Content-Type": "application/json",
    Accept: "application/json",
  },
});

// ─────────────────────────────────────────────────────────────
// Request interceptor — inject Bearer token
// ─────────────────────────────────────────────────────────────
api.interceptors.request.use((config: InternalAxiosRequestConfig) => {
  const { accessToken } = useAuthStore.getState();
  if (accessToken && config.headers) {
    config.headers.set("Authorization", `Bearer ${accessToken}`);
  }
  return config;
});

// ─────────────────────────────────────────────────────────────
// Response interceptor — auto-refresh on 401
// ─────────────────────────────────────────────────────────────
let refreshPromise: Promise<string | null> | null = null;

async function refreshAccessToken(): Promise<string | null> {
  const { refreshToken, setTokens, logout } = useAuthStore.getState();
  if (!refreshToken) {
    logout();
    return null;
  }
  try {
    const r = await axios.post(
      `${BASE_URL}/api/v1/auth/token/refresh/`,
      { refresh: refreshToken },
      { headers: { "Content-Type": "application/json" } },
    );
    const access: string | undefined = r.data?.access;
    if (access) {
      setTokens({ accessToken: access, refreshToken });
      return access;
    }
    logout();
    return null;
  } catch {
    logout();
    return null;
  }
}

api.interceptors.response.use(
  (r) => r,
  async (error: AxiosError) => {
    const original = error.config as AxiosRequestConfig & { _retry?: boolean };
    const status = error.response?.status;

    // Cas 401 → tente un refresh une seule fois
    if (status === 401 && original && !original._retry) {
      original._retry = true;
      refreshPromise = refreshPromise || refreshAccessToken();
      const newAccess = await refreshPromise;
      refreshPromise = null;

      if (newAccess) {
        original.headers = {
          ...(original.headers as any),
          Authorization: `Bearer ${newAccess}`,
        };
        return api.request(original);
      }
      // Refresh échec → redirect login
      if (typeof window !== "undefined" && !window.location.pathname.startsWith("/login")) {
        const next = encodeURIComponent(window.location.pathname + window.location.search);
        window.location.href = `/login?next=${next}`;
      }
    }
    return Promise.reject(error);
  },
);

// ─────────────────────────────────────────────────────────────
// Helpers
// ─────────────────────────────────────────────────────────────
export type ApiError = {
  status?: number;
  message: string;
  detail?: unknown;
};

export function toApiError(err: unknown): ApiError {
  if (axios.isAxiosError(err)) {
    const data = err.response?.data as any;
    const message =
      data?.detail ||
      data?.message ||
      data?.non_field_errors?.[0] ||
      err.message ||
      "Erreur inconnue";
    return { status: err.response?.status, message: String(message), detail: data };
  }
  return { message: err instanceof Error ? err.message : String(err) };
}
