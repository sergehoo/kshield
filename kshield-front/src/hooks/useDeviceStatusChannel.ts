/**
 * useDeviceStatusChannel — WebSocket vers /ws/devices/status/.
 *
 * Écoute les événements globaux : device.connected/disconnected/status.updated,
 * agent.connected/disconnected, device.command.completed/failed.
 */
import { useEffect, useRef, useState } from "react";
import { useAuthStore } from "@/lib/auth";

export type StatusWsStatus = "idle" | "connecting" | "open" | "closed" | "error";

function resolveWsBase(): string {
  // En prod (HTTPS + front servi depuis le même domaine que l'API), on dérive
  // TOUJOURS depuis window.location — plus fiable que VITE_API_URL qui peut
  // ne pas être défini au build ou pointer sur localhost par défaut.
  //
  // En dev (http://localhost:5173) → utilise VITE_API_URL si défini
  // (ex. http://localhost:8000), sinon window.location.
  const isProdSameOrigin = window.location.protocol === "https:";
  if (isProdSameOrigin) {
    return `wss://${window.location.host}`;
  }
  const apiBase = (import.meta.env.VITE_API_URL as string) || "";
  if (apiBase) {
    try {
      const u = new URL(apiBase);
      const proto = u.protocol === "https:" ? "wss:" : "ws:";
      return `${proto}//${u.host}`;
    } catch {
      /* fallback ci-dessous */
    }
  }
  const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
  return `${proto}//${window.location.host}`;
}

export function useDeviceStatusChannel({
  enabled = true,
  onEvent,
}: {
  enabled?: boolean;
  onEvent?: (evt: any) => void;
}) {
  const [status, setStatus] = useState<StatusWsStatus>("idle");
  const [lastEvent, setLastEvent] = useState<any>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const accessToken = useAuthStore((s) => s.accessToken);
  const onEventRef = useRef(onEvent);
  onEventRef.current = onEvent;

  useEffect(() => {
    if (!enabled || !accessToken) {
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
          "[useDeviceStatusChannel] WebSocket indisponible après " +
          `${MAX_ATTEMPTS} tentatives. Vérifier que Django tourne via daphne / ` +
          "runserver (Channels 4+ nécessite daphne en tête d'INSTALLED_APPS).",
        );
        return;
      }
      setStatus("connecting");
      const url = `${resolveWsBase()}/ws/devices/status/?token=${encodeURIComponent(accessToken)}`;
      const ws = new WebSocket(url);
      wsRef.current = ws;

      ws.onopen = () => { attempts = 0; setStatus("open"); };
      ws.onmessage = (msg) => {
        try {
          const data = JSON.parse(msg.data);
          setLastEvent(data);
          onEventRef.current?.(data);
        } catch { /* ignore */ }
      };
      ws.onerror = () => setStatus("error");
      ws.onclose = () => {
        setStatus("closed");
        wsRef.current = null;
        if (cancelled) return;
        attempts += 1;
        const delay = Math.min(1000 * 2 ** attempts, 15000);
        reconnectTimer = setTimeout(connect, delay);
      };
    };

    // ── StrictMode-safe : diffère la création du WS d'un tick.
    // En dev, React monte/démonte les effets deux fois pour détecter les
    // side-effects mal nettoyés. En délayant, on laisse le cleanup passer
    // sans jamais avoir créé de WS orpheline "closed before established".
    deferTimer = setTimeout(connect, 50);

    return () => {
      cancelled = true;
      if (deferTimer) clearTimeout(deferTimer);
      if (reconnectTimer) clearTimeout(reconnectTimer);
      const ws = wsRef.current;
      if (ws) {
        ws.onclose = null;
        ws.onerror = null;
        // Ne close() que si le WS est ouvert — sinon on interromprait le
        // handshake, ce qui produit précisément le warning "closed before
        // established" en boucle en StrictMode.
        if (ws.readyState === WebSocket.OPEN || ws.readyState === WebSocket.CLOSING) {
          ws.close();
        }
        wsRef.current = null;
      }
    };
  }, [enabled, accessToken]);

  return { status, lastEvent };
}
