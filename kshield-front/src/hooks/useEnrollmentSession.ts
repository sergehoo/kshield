/**
 * useEnrollmentSession — connexion WebSocket temps réel à une session d'enrôlement.
 *
 * Écoute /ws/rfid/enrollment/<sessionId>/?token=<jwt> et publie les événements
 * via les callbacks fournis par le composant.
 */
import { useEffect, useRef, useState } from "react";
import { useAuthStore } from "@/lib/auth";
import type { EnrollmentEvent } from "@/services/enrollment";

export type WsStatus = "idle" | "connecting" | "open" | "closed" | "error";

export interface EnrollmentSessionHookOptions {
  sessionId: string | null;
  enabled: boolean;
  onEvent?: (evt: EnrollmentEvent & { event?: string; extra?: any }) => void;
}

/**
 * Résout l'URL WebSocket à partir de l'URL API (http:// → ws://, https:// → wss://).
 */
function resolveWsBase(): string {
  // En prod HTTPS → same-origin (Traefik proxie /ws/... vers shieldws).
  if (window.location.protocol === "https:") {
    return `wss://${window.location.host}`;
  }
  // En dev : VITE_API_URL si défini, sinon même origine.
  const apiBase = (import.meta.env.VITE_API_URL as string) || "";
  if (apiBase) {
    try {
      const u = new URL(apiBase);
      const proto = u.protocol === "https:" ? "wss:" : "ws:";
      return `${proto}//${u.host}`;
    } catch { /* fallback ci-dessous */ }
  }
  const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
  return `${proto}//${window.location.host}`;
}

export function useEnrollmentSession({
  sessionId, enabled, onEvent,
}: EnrollmentSessionHookOptions) {
  const [status, setStatus] = useState<WsStatus>("idle");
  const [reconnectCount, setReconnectCount] = useState(0);
  const wsRef = useRef<WebSocket | null>(null);
  const accessToken = useAuthStore((s) => s.accessToken);
  const onEventRef = useRef(onEvent);
  onEventRef.current = onEvent;

  useEffect(() => {
    if (!enabled || !sessionId || !accessToken) {
      setStatus("idle");
      return;
    }

    let cancelled = false;
    let reconnectTimer: ReturnType<typeof setTimeout> | null = null;
    let deferTimer: ReturnType<typeof setTimeout> | null = null;
    let attempts = 0;
    const MAX_ATTEMPTS = 5;

    const connect = () => {
      if (cancelled) return;
      if (attempts >= MAX_ATTEMPTS) {
        setStatus("error");
        // eslint-disable-next-line no-console
        console.warn(
          "[useEnrollmentSession] WebSocket indisponible après " +
          `${MAX_ATTEMPTS} tentatives. Vérifier daphne (Channels 4).`,
        );
        return;
      }
      setStatus("connecting");
      const url = `${resolveWsBase()}/ws/rfid/enrollment/${sessionId}/?token=${encodeURIComponent(accessToken)}`;
      const ws = new WebSocket(url);
      wsRef.current = ws;

      ws.onopen = () => {
        attempts = 0;
        setStatus("open");
      };
      ws.onmessage = (msg) => {
        try {
          const data = JSON.parse(msg.data);
          if (onEventRef.current) onEventRef.current(data);
        } catch {
          // ignore malformed
        }
      };
      ws.onerror = () => {
        setStatus("error");
      };
      ws.onclose = () => {
        setStatus("closed");
        wsRef.current = null;
        if (cancelled) return;
        // Backoff exponentiel plafonné à 15s
        attempts += 1;
        const delay = Math.min(1000 * 2 ** attempts, 15000);
        reconnectTimer = setTimeout(() => {
          setReconnectCount((c) => c + 1);
          connect();
        }, delay);
      };
    };

    // StrictMode-safe : diffère la connexion pour laisser passer le
    // cleanup fantôme de React dev sans créer de WS orpheline.
    deferTimer = setTimeout(connect, 50);

    return () => {
      cancelled = true;
      if (deferTimer) clearTimeout(deferTimer);
      if (reconnectTimer) clearTimeout(reconnectTimer);
      const ws = wsRef.current;
      if (ws) {
        ws.onclose = null;
        ws.onerror = null;
        // Ne close() que si le WS est effectivement ouvert : couper un
        // handshake en cours produit le warning "closed before established".
        if (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CLOSING) {
          ws.close();
        }
        wsRef.current = null;
      }
      setStatus("idle");
    };
  }, [sessionId, enabled, accessToken]);

  const send = (payload: any) => {
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(JSON.stringify(payload));
    }
  };

  return { status, send, reconnectCount };
}
