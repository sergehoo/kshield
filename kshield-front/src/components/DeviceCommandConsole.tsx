/**
 * DeviceCommandConsole — envoi de commandes ad-hoc à un équipement + historique.
 *
 * Affiche un dropdown des commandes disponibles + payload JSON éditable,
 * envoie via POST /devices/<id>/commands/, poll le résultat.
 */
import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Terminal, Send, CheckCircle2, XCircle, Clock } from "lucide-react";
import toast from "react-hot-toast";

import { Button } from "@/components/ui/Button";
import { deviceCommandService } from "@/services/enrollment";
import { cn } from "@/lib/cn";
import { fmtRelative } from "@/lib/format";
import { useDeviceStatusChannel } from "@/hooks/useDeviceStatusChannel";

const AVAILABLE_KINDS = [
  { value: "PING_DEVICE",           label: "Ping",                       payload: "{}" },
  { value: "SYNC_DEVICE",           label: "Synchroniser",               payload: "{}" },
  { value: "GET_DEVICE_INFO",       label: "Info équipement",            payload: "{}" },
  { value: "GET_DEVICE_STATUS",     label: "Statut équipement",          payload: "{}" },
  { value: "GET_DEVICE_LOGS",       label: "Logs",                       payload: "{}" },
  { value: "RESTART_DEVICE",        label: "Redémarrer",                 payload: "{}" },
  { value: "START_RFID_ENROLLMENT", label: "Démarrer écoute RFID",       payload: '{"timeout_seconds": 60}' },
  { value: "STOP_RFID_ENROLLMENT",  label: "Arrêter écoute RFID",        payload: "{}" },
  { value: "READ_RFID_CARD",        label: "Lire une carte",             payload: "{}" },
];

interface Props {
  deviceId: number;
}

interface CommandLog {
  id: string;
  kind: string;
  status: string;
  sent_at?: string;
  completed_at?: string;
  error?: string;
  response?: any;
}

export function DeviceCommandConsole({ deviceId }: Props) {
  const [kind, setKind] = useState(AVAILABLE_KINDS[0].value);
  const [payloadText, setPayloadText] = useState(AVAILABLE_KINDS[0].payload);
  const [history, setHistory] = useState<CommandLog[]>([]);
  const qc = useQueryClient();

  // Poll incremental — refetch chaque commande en cours
  useQuery({
    queryKey: ["device-commands-poll", deviceId, history.length],
    queryFn: async () => {
      const updates = await Promise.all(
        history
          .filter((h) => h.status === "pending" || h.status === "sent" || h.status === "acknowledged")
          .map((h) => deviceCommandService.get(h.id).then((r) => r.data as any)),
      );
      if (updates.length > 0) {
        setHistory((old) =>
          old.map((h) => {
            const u = updates.find((x: any) => x.id === h.id);
            return u ? { ...h, ...u } : h;
          }),
        );
      }
      return updates;
    },
    refetchInterval: 2000,
    enabled: history.some((h) => ["pending", "sent", "acknowledged"].includes(h.status)),
  });

  // WS pour recevoir command.completed / command.failed en direct
  useDeviceStatusChannel({
    onEvent: (evt: any) => {
      if (evt?.device_id !== deviceId) return;
      if (evt.event === "device.command.completed" || evt.event === "device.command.failed") {
        setHistory((old) => old.map((h) => h.id === evt.command_id
          ? {
              ...h,
              status: evt.event === "device.command.completed" ? "completed" : "failed",
              completed_at: evt.at,
              response: evt.response,
              error: evt.error,
            }
          : h));
      }
    },
  });

  const sendMut = useMutation({
    mutationFn: () => {
      let payload = {};
      try { payload = JSON.parse(payloadText); } catch { throw new Error("Payload JSON invalide"); }
      return deviceCommandService.send(deviceId, kind, payload);
    },
    onSuccess: (r) => {
      const c = r.data as any;
      setHistory((old) => [
        { id: c.id, kind: c.kind, status: c.status, sent_at: c.sent_at },
        ...old,
      ].slice(0, 20));
      toast.success(`Commande ${kind} envoyée`);
    },
    onError: (e: any) => toast.error(e?.message || "Erreur d'envoi"),
  });

  return (
    <div className="space-y-3">
      <div className="flex items-center gap-2 text-sm font-medium text-ink">
        <Terminal className="w-4 h-4" />
        Console de commandes
      </div>

      <div className="grid grid-cols-1 md:grid-cols-[240px_1fr_auto] gap-2">
        <select className="field" value={kind}
                onChange={(e) => {
                  const k = e.target.value;
                  setKind(k);
                  const def = AVAILABLE_KINDS.find((x) => x.value === k);
                  if (def) setPayloadText(def.payload);
                }}>
          {AVAILABLE_KINDS.map((k) => (
            <option key={k.value} value={k.value}>{k.label}</option>
          ))}
        </select>

        <input className="field font-mono text-xs"
               placeholder='{"key": "value"}'
               value={payloadText}
               onChange={(e) => setPayloadText(e.target.value)} />

        <Button leftIcon={<Send className="w-3.5 h-3.5" />}
                loading={sendMut.isPending} onClick={() => sendMut.mutate()}>
          Envoyer
        </Button>
      </div>

      {/* Historique */}
      {history.length > 0 && (
        <div className="border border-surface-border rounded-md overflow-hidden">
          <div className="text-xs text-ink-muted px-3 py-1.5 bg-surface-soft">
            Dernières commandes
          </div>
          <div className="divide-y divide-surface-border max-h-72 overflow-auto text-xs">
            {history.map((h) => (
              <CommandRow key={h.id} log={h} />
            ))}
          </div>
        </div>
      )}
    </div>
  );
}

function CommandRow({ log }: { log: CommandLog }) {
  const statusMeta: Record<string, { icon: any; color: string; label: string }> = {
    pending:      { icon: <Clock className="w-3 h-3" />,         color: "text-ink-muted", label: "En attente" },
    sent:         { icon: <Clock className="w-3 h-3" />,         color: "text-info",       label: "Envoyée" },
    acknowledged: { icon: <Clock className="w-3 h-3" />,         color: "text-info",       label: "Acquittée" },
    completed:    { icon: <CheckCircle2 className="w-3 h-3" />,  color: "text-success",    label: "Terminée" },
    failed:       { icon: <XCircle className="w-3 h-3" />,       color: "text-danger",     label: "Échec" },
    timeout:      { icon: <XCircle className="w-3 h-3" />,       color: "text-warning",    label: "Timeout" },
  };
  const meta = statusMeta[log.status] || statusMeta["pending"];
  return (
    <div className="px-3 py-2 flex items-center gap-2">
      <span className={cn("flex items-center gap-1", meta.color)}>
        {meta.icon}
        <span className="font-mono">{log.kind}</span>
      </span>
      <span className={cn("ml-auto text-[10px] uppercase tracking-wider", meta.color)}>
        {meta.label}
      </span>
      {log.sent_at && (
        <span className="text-ink-muted">
          {fmtRelative(log.completed_at || log.sent_at)}
        </span>
      )}
      {log.error && (
        <span className="text-danger truncate max-w-40" title={log.error}>· {log.error}</span>
      )}
    </div>
  );
}
