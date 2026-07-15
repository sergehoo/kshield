/**
 * useEventsLive — Hook temps réel pour la vue Events Live.
 *
 * Responsabilités (cahier des charges §1.3) :
 *   - Chargement initial via REST (/events/live/)
 *   - Souscription WebSocket au flux temps réel
 *   - Buffer + déduplication (rejeus MQTT/WS possibles)
 *   - Pause/reprise du flux (le buffer continue en tâche de fond)
 *   - Reprise automatique après coupure réseau (exponential backoff)
 *   - Fallback polling toutes les 15s si WS indisponible
 *   - Compteur d'événements pending pendant la pause
 *   - Filtres appliqués aussi bien au fetch initial qu'à l'affichage live
 */
import { useCallback, useEffect, useMemo, useRef, useState } from "react";

import { eventsService, type DeviceEventDTO, type EventFilters } from "@/services/events";
import { useAuthStore } from "@/lib/auth";

// ═══════════════════════════════════════════════════════════════════
// Config
// ═══════════════════════════════════════════════════════════════════
const INITIAL_LIMIT = 100;
const MAX_BUFFER_SIZE = 500;
const WS_RECONNECT_MIN_MS = 1000;
const WS_RECONNECT_MAX_MS = 30_000;
const POLLING_FALLBACK_MS = 15_000;

// ═══════════════════════════════════════════════════════════════════
// Types retour hook
// ═══════════════════════════════════════════════════════════════════
export interface UseEventsLiveState {
  /** Liste triée par occurred_at desc (plus récent en premier). */
  events: DeviceEventDTO[];
  /** Statut du canal temps réel. */
  wsStatus: "connecting" | "connected" | "disconnected" | "reconnecting" | "polling";
  /** Compteur d'events reçus pendant la pause (à afficher dans un badge "reprendre"). */
  pendingCount: number;
  /** True si l'utilisateur a mis en pause le flux. */
  isPaused: boolean;
  pause: () => void;
  resume: () => void;
  clear: () => void;
  /** Statistiques agrégées 24h (retournées par l'endpoint /live/). */
  stats24h?: {
    total: number;
    by_severity: Record<string, number>;
    by_result: Record<string, number>;
  };
  /** True pendant le premier fetch. */
  loading: boolean;
  /** Erreur éventuelle (chargement initial ou WS échec définitif). */
  error?: string;
  /** Nombre total d'events matchant les filtres côté serveur. */
  totalCount: number;
  /** Rafraîchir manuellement (fetch REST). */
  refetch: () => Promise<void>;
}

// ═══════════════════════════════════════════════════════════════════
// Helper : construction URL WebSocket same-origin
// ═══════════════════════════════════════════════════════════════════
function buildWsUrl(path: string, token: string): string {
  const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
  const host = window.location.host;
  const cleaned = path.startsWith("/") ? path : `/${path}`;
  return `${proto}//${host}${cleaned}?token=${encodeURIComponent(token)}`;
}

// ═══════════════════════════════════════════════════════════════════
// Hook principal
// ═══════════════════════════════════════════════════════════════════
export function useEventsLive(filters: EventFilters = {}): UseEventsLiveState {
  const [events, setEvents] = useState<DeviceEventDTO[]>([]);
  const [totalCount, setTotalCount] = useState(0);
  const [stats24h, setStats24h] = useState<UseEventsLiveState["stats24h"]>();
  const [wsStatus, setWsStatus] =
    useState<UseEventsLiveState["wsStatus"]>("connecting");
  const [pendingCount, setPendingCount] = useState(0);
  const [isPaused, setIsPaused] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | undefined>();

  const wsRef = useRef<WebSocket | null>(null);
  const wsUrlRef = useRef<string | undefined>();
  const reconnectDelayRef = useRef(WS_RECONNECT_MIN_MS);
  const reconnectTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);
  const pollingTimerRef = useRef<ReturnType<typeof setInterval> | null>(null);
  const seenIdsRef = useRef<Set<string>>(new Set());
  const bufferRef = useRef<DeviceEventDTO[]>([]);
  const isPausedRef = useRef(false);
  const filtersKey = useMemo(() => JSON.stringify(filters), [filters]);

  const accessToken = useAuthStore((s) => s.accessToken);

  // ─── Fetch initial ───────────────────────────────────────────
  const fetchInitial = useCallback(async () => {
    setLoading(true);
    setError(undefined);
    try {
      const params = { ...filters, page_size: INITIAL_LIMIT } as EventFilters;
      const { data } = await eventsService.live(params);
      seenIdsRef.current = new Set(data.results.map((e) => e.id));
      setEvents(data.results);
      setTotalCount(data.count);
      setStats24h(data.stats_24h);
      wsUrlRef.current = data.ws_url;
    } catch (e: any) {
      setError(e?.response?.data?.error ?? e.message ?? "Erreur chargement");
    } finally {
      setLoading(false);
    }
  }, [filtersKey]);   // eslint-disable-line react-hooks/exhaustive-deps

  // ─── Application filtres côté client (WS reçoit tout) ────────
  const matchesFilters = useCallback(
    (event: DeviceEventDTO): boolean => {
      if (filters.site && event.site_id !== filters.site) return false;
      if (filters.device && event.device_id !== filters.device) return false;
      if (filters.gateway && event.gateway_id !== filters.gateway) return false;
      if (filters.category && event.category !== filters.category) return false;
      if (filters.severity && event.severity !== filters.severity) return false;
      if (filters.result && event.result !== filters.result) return false;
      if (filters.badge && event.badge_uid !== filters.badge) return false;
      if (filters.type) {
        const types = Array.isArray(filters.type) ? filters.type : [filters.type];
        if (!types.includes(event.code)) return false;
      }
      return true;
    },
    [filters],
  );

  // ─── Ajout d'un event (dedup + tri + buffer si pause) ────────
  const addEvent = useCallback(
    (event: DeviceEventDTO) => {
      // Déduplication forte par ID
      if (seenIdsRef.current.has(event.id)) return;
      seenIdsRef.current.add(event.id);

      // Applique les filtres client
      if (!matchesFilters(event)) return;

      if (isPausedRef.current) {
        bufferRef.current.push(event);
        setPendingCount(bufferRef.current.length);
        return;
      }

      setEvents((prev) => {
        const next = [event, ...prev];
        if (next.length > MAX_BUFFER_SIZE) {
          next.length = MAX_BUFFER_SIZE;
        }
        return next;
      });
      setTotalCount((c) => c + 1);
    },
    [matchesFilters],
  );

  // ─── Pause / reprise ─────────────────────────────────────────
  const pause = useCallback(() => {
    isPausedRef.current = true;
    setIsPaused(true);
  }, []);

  const resume = useCallback(() => {
    isPausedRef.current = false;
    setIsPaused(false);
    if (bufferRef.current.length > 0) {
      const toFlush = bufferRef.current;
      bufferRef.current = [];
      setPendingCount(0);
      setEvents((prev) => {
        const next = [...toFlush, ...prev];
        if (next.length > MAX_BUFFER_SIZE) next.length = MAX_BUFFER_SIZE;
        return next;
      });
    }
  }, []);

  const clear = useCallback(() => {
    setEvents([]);
    seenIdsRef.current.clear();
    bufferRef.current = [];
    setPendingCount(0);
  }, []);

  // ─── Connexion WebSocket ─────────────────────────────────────
  useEffect(() => {
    if (!wsUrlRef.current || !accessToken) return;

    const url = buildWsUrl(wsUrlRef.current, accessToken);

    const connect = () => {
      setWsStatus((s) => (s === "connected" ? "reconnecting" : "connecting"));
      try {
        const ws = new WebSocket(url);
        wsRef.current = ws;

        ws.onopen = () => {
          setWsStatus("connected");
          reconnectDelayRef.current = WS_RECONNECT_MIN_MS;
          // Stop polling fallback si actif
          if (pollingTimerRef.current) {
            clearInterval(pollingTimerRef.current);
            pollingTimerRef.current = null;
          }
        };

        ws.onmessage = (msg) => {
          try {
            const parsed = JSON.parse(msg.data);
            if (parsed.type === "event" && parsed.data) {
              addEvent(parsed.data as DeviceEventDTO);
            } else if (parsed.type === "hello") {
              // ignore
            } else if (parsed.type === "pong") {
              // keepalive
            }
          } catch (e) {
            // ignore malformed
          }
        };

        ws.onerror = () => {
          // ne pas set status ici — onclose viendra ensuite
        };

        ws.onclose = () => {
          wsRef.current = null;
          setWsStatus("reconnecting");
          // Exponential backoff
          const delay = reconnectDelayRef.current;
          reconnectDelayRef.current = Math.min(delay * 2, WS_RECONNECT_MAX_MS);
          reconnectTimerRef.current = setTimeout(() => {
            if (reconnectDelayRef.current >= WS_RECONNECT_MAX_MS) {
              // Fallback polling après plusieurs échecs
              startPollingFallback();
            }
            connect();
          }, delay);
        };
      } catch (e) {
        setWsStatus("disconnected");
        startPollingFallback();
      }
    };

    const startPollingFallback = () => {
      if (pollingTimerRef.current) return;
      setWsStatus("polling");
      pollingTimerRef.current = setInterval(async () => {
        try {
          const { data } = await eventsService.list({
            ...filters, page_size: 30,
          });
          data.results.forEach((e) => addEvent(e));
        } catch {
          // ignore
        }
      }, POLLING_FALLBACK_MS);
    };

    connect();

    // Cleanup
    return () => {
      if (reconnectTimerRef.current) clearTimeout(reconnectTimerRef.current);
      if (pollingTimerRef.current) clearInterval(pollingTimerRef.current);
      if (wsRef.current) {
        wsRef.current.onclose = null;   // évite reconnect au unmount
        wsRef.current.close();
        wsRef.current = null;
      }
    };
  }, [wsUrlRef.current, accessToken, addEvent, filtersKey]);   // eslint-disable-line react-hooks/exhaustive-deps

  // ─── Fetch au mount + refetch quand filtres changent ─────────
  useEffect(() => {
    fetchInitial();
  }, [fetchInitial]);

  return {
    events, wsStatus, pendingCount, isPaused,
    pause, resume, clear,
    stats24h, loading, error, totalCount,
    refetch: fetchInitial,
  };
}
