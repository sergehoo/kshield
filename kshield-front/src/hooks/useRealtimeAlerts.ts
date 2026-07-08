/**
 * useRealtimeAlerts — poll les nouvelles alertes anti-fraude et
 * les notifications non lues, puis :
 *   - Affiche un toast pour chaque nouvelle alerte
 *   - Envoie une notification desktop (si permission)
 *   - Joue un bip discret sur les alertes critical
 *
 * Design tolérant aux erreurs : si les endpoints n'existent pas côté back,
 * on log en debug et on continue silencieusement.
 */
import { useEffect, useRef } from "react";
import { useQuery } from "@tanstack/react-query";
import { antifraudService, notificationsService } from "@/services";
import { useAuthStore } from "@/lib/auth";
import toast from "react-hot-toast";

const POLL_MS = 20_000;

export function useRealtimeAlerts() {
  const isAuthed = useAuthStore((s) => s.isAuthenticated);
  const seenAlertIds = useRef<Set<number>>(new Set());
  const seenNotifIds = useRef<Set<number>>(new Set());
  const firstRun = useRef(true);

  const alerts = useQuery({
    queryKey: ["realtime", "antifraud"],
    queryFn: async () =>
      (
        await antifraudService.alertsList({
          status: "open",
          ordering: "-created_at",
          page_size: 10,
        })
      ).data,
    refetchInterval: POLL_MS,
    refetchIntervalInBackground: true,
    enabled: isAuthed,
    retry: false,
  });

  const notifs = useQuery({
    queryKey: ["realtime", "notifications"],
    queryFn: async () => (await notificationsService.unread()).data,
    refetchInterval: POLL_MS,
    refetchIntervalInBackground: true,
    enabled: isAuthed,
    retry: false,
  });

  // Detect new alerts
  useEffect(() => {
    const list = alerts.data?.results || [];
    // Premier run : on marque tout comme vu (pas de spam au login)
    if (firstRun.current) {
      list.forEach((a: any) => seenAlertIds.current.add(a.id));
      // notifs aussi
      (notifs.data?.results || []).forEach((n: any) => seenNotifIds.current.add(n.id));
      firstRun.current = false;
      return;
    }

    const fresh = list.filter((a: any) => !seenAlertIds.current.has(a.id));
    fresh.forEach((a: any) => {
      seenAlertIds.current.add(a.id);
      const title = a.rule_name || a.rule?.name || "Alerte anti-fraude";
      const body = a.description || "";
      const severity = a.severity || "info";

      // Toast in-app
      toast.error(`🚨 ${title}${body ? ` — ${body.slice(0, 80)}` : ""}`, {
        duration: severity === "critical" ? 10_000 : 6_000,
      });

      // Desktop notification (si permission accordée)
      if (
        typeof Notification !== "undefined" &&
        Notification.permission === "granted"
      ) {
        try {
          const n = new Notification(`KAYDAN SHIELD — ${title}`, {
            body,
            tag: `alert-${a.id}`,
            requireInteraction: severity === "critical",
            icon: "/favicon.svg",
          });
          n.onclick = () => {
            window.focus();
            window.location.href = "/antifraud";
            n.close();
          };
        } catch {
          /* silencieux */
        }
      }

      // Petit bip audio pour les critical (WebAudio pour éviter dépendance)
      if (severity === "critical") {
        beep();
      }
    });
  }, [alerts.data, notifs.data]);

  // Detect new notifs (info/warn)
  useEffect(() => {
    if (firstRun.current) return;
    const list = notifs.data?.results || [];
    const fresh = list.filter((n: any) => !seenNotifIds.current.has(n.id));
    fresh.forEach((n: any) => {
      seenNotifIds.current.add(n.id);
      const isImportant = ["danger", "warn"].includes(n.level);
      if (!isImportant) return;
      toast(n.title, { icon: n.level === "danger" ? "⚠️" : "🔔" });
    });
  }, [notifs.data]);
}

// Bip WebAudio 2 notes
let audioCtx: AudioContext | null = null;
function beep() {
  try {
    if (!audioCtx) audioCtx = new AudioContext();
    const ctx = audioCtx;
    const now = ctx.currentTime;
    [880, 660].forEach((f, i) => {
      const osc = ctx.createOscillator();
      const gain = ctx.createGain();
      osc.frequency.value = f;
      osc.type = "sine";
      gain.gain.setValueAtTime(0.0001, now + i * 0.15);
      gain.gain.exponentialRampToValueAtTime(0.15, now + i * 0.15 + 0.01);
      gain.gain.exponentialRampToValueAtTime(0.0001, now + i * 0.15 + 0.12);
      osc.connect(gain).connect(ctx.destination);
      osc.start(now + i * 0.15);
      osc.stop(now + i * 0.15 + 0.15);
    });
  } catch {
    /* silencieux */
  }
}
