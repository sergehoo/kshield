/**
 * KAYDAN SHIELD — Modal d'enrôlement RFID temps réel.
 *
 * Workflow :
 *   1. L'opérateur choisit site / zone / lecteur / porteur
 *   2. Clique "Démarrer l'écoute" → POST /rfid/enrollment/start/
 *   3. Ouvre WS /ws/rfid/enrollment/<session_id>/
 *   4. Le lecteur scanne → événement rfid.card.detected arrive en direct
 *   5. Si carte déjà connue → rfid.card.duplicate (bloque)
 *   6. Sinon → l'opérateur confirme → POST /rfid/enrollment/<id>/confirm/
 *   7. Événement rfid.card.enrolled → toast succès + reset
 */
import { useEffect, useMemo, useRef, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  CheckCircle2, XCircle, Wifi, WifiOff, Radar, Loader2,
  User as UserIcon, MapPin, Building2, AlertTriangle, PlayCircle,
  StopCircle, Zap, X, Download,
} from "lucide-react";
import toast from "react-hot-toast";

import { Modal } from "@/components/ui/Modal";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { cn } from "@/lib/cn";
import { fmtRelative } from "@/lib/format";
import {
  devicesService, sitesService, zonesService,
  workersService, employeesService,
} from "@/services";
import { enrollmentService, EnrollmentEvent } from "@/services/enrollment";
import { useEnrollmentSession } from "@/hooks/useEnrollmentSession";

interface Props {
  open: boolean;
  onClose: () => void;
  mode?: "single" | "bulk";
  /** Type de porteur préchoisi (optionnel) */
  presetHolderKind?: "worker" | "employee" | "visitor";
  /** ID du porteur préchoisi (optionnel) */
  presetHolderId?: number;
}

interface CapturedCard {
  uid: string;
  detectedAt: string;
  deviceSerial?: string;
  rssi?: number | null;
  status: "detected" | "duplicate" | "enrolled" | "error";
  existingBadge?: any;
  message?: string;
}

export function RFIDEnrollmentModal({
  open, onClose, mode = "single", presetHolderKind, presetHolderId,
}: Props) {
  const qc = useQueryClient();

  // ─── State session + form ─────────────────────────────
  const [sessionId, setSessionId] = useState<string | null>(null);
  const [sessionStatus, setSessionStatus] = useState<string>("");
  const [siteId, setSiteId] = useState<number | "">("");
  const [zoneId, setZoneId] = useState<number | "">("");
  const [readerId, setReaderId] = useState<number | "">("");
  const [holderKind, setHolderKind] = useState<"" | "worker" | "employee" | "visitor">(presetHolderKind || "");
  const [holderId, setHolderId] = useState<number | "">(presetHolderId || "");
  const [tech, setTech] = useState<"nfc" | "uhf" | "uhf_xerafy" | "qr">("nfc");
  const [validUntil, setValidUntil] = useState("");

  const [cards, setCards] = useState<CapturedCard[]>([]);
  const [timeline, setTimeline] = useState<(EnrollmentEvent & { event?: string })[]>([]);
  const cardsRef = useRef<Map<string, CapturedCard>>(new Map());

  // ─── Data — sites, zones, lecteurs, porteurs ─────────
  const { data: sites } = useQuery({
    queryKey: ["sites", "for-enroll"],
    queryFn: async () => (await sitesService.list({ page_size: 200 })).data,
    enabled: open,
  });
  const { data: zones } = useQuery({
    queryKey: ["zones", "for-enroll", siteId],
    queryFn: async () => (await zonesService.list({
      site: siteId || undefined, page_size: 200,
    })).data,
    enabled: open && !!siteId,
  });
  const { data: readers } = useQuery({
    queryKey: ["rfid-readers", "for-enroll", siteId],
    queryFn: async () => (await devicesService.list({
      page_size: 200,
      site: siteId || undefined,
      model__type__in:
        "reader_uhf_fixed,reader_uhf_mobile,reader_nfc_fixed,reader_nfc_mobile,portique,face_terminal",
    })).data,
    enabled: open,
    refetchInterval: 5000,
  });
  const { data: holders } = useQuery({
    queryKey: ["holders", "for-enroll", holderKind],
    queryFn: async () => {
      if (holderKind === "worker")   return (await workersService.list({ page_size: 200 })).data;
      if (holderKind === "employee") return (await employeesService.list({ page_size: 200 })).data;
      return { results: [] };
    },
    enabled: open && !!holderKind,
  });

  // Lecteur sélectionné + son statut
  const selectedReader = useMemo(
    () => (readers?.results || []).find((r: any) => r.id === readerId),
    [readerId, readers],
  );
  const isReaderOnline = useMemo(() => {
    if (!selectedReader?.last_heartbeat_at) return false;
    const age = Date.now() - new Date(selectedReader.last_heartbeat_at).getTime();
    return age < 90_000;
  }, [selectedReader]);

  // ─── WebSocket ────────────────────────────────────────
  const { status: wsStatus, reconnectCount } = useEnrollmentSession({
    sessionId,
    enabled: !!sessionId && sessionStatus === "listening",
    onEvent: (evt: any) => {
      // Timeline (max 100)
      setTimeline((t) => [...t.slice(-99), evt]);

      const ev = evt.event || evt.event_type;
      if (ev === "rfid.card.detected" || ev === "card.detected") {
        const uid = evt.uid as string;
        const card: CapturedCard = {
          uid,
          detectedAt: evt.at || new Date().toISOString(),
          deviceSerial: evt.device_serial,
          rssi: evt.rssi,
          status: "detected",
        };
        cardsRef.current.set(uid, card);
        setCards(Array.from(cardsRef.current.values()));
        toast.success(`Carte détectée : ${uid}`);
      } else if (ev === "rfid.card.duplicate" || ev === "card.duplicate") {
        const uid = evt.uid as string;
        const existing = cardsRef.current.get(uid);
        const card: CapturedCard = {
          ...(existing || { uid, detectedAt: evt.at, status: "detected" }),
          status: "duplicate",
          existingBadge: evt.existing_badge,
        };
        cardsRef.current.set(uid, card);
        setCards(Array.from(cardsRef.current.values()));
        toast.error(`Doublon : ${uid} est déjà enrôlé`);
      } else if (ev === "rfid.card.enrolled" || ev === "card.enrolled") {
        const uid = evt.uid as string;
        const existing = cardsRef.current.get(uid);
        const card: CapturedCard = {
          ...(existing || { uid, detectedAt: evt.at, status: "detected" }),
          status: "enrolled",
        };
        cardsRef.current.set(uid, card);
        setCards(Array.from(cardsRef.current.values()));
      } else if (ev === "session.listening" || ev === "session.start") {
        setSessionStatus("listening");
      } else if (ev === "session.completed" || ev === "session.cancelled") {
        setSessionStatus(evt.status || "completed");
      }
    },
  });

  // ─── Mutations ────────────────────────────────────────
  const startMut = useMutation({
    mutationFn: () =>
      enrollmentService.start({
        site_id: siteId || null,
        zone_id: zoneId || null,
        reader_id: readerId || null,
        mode,
        holder_kind: holderKind || "",
        holder_id: holderId || null,
        timeout_seconds: 180,
      }),
    onSuccess: (r) => {
      const s = r.data;
      setSessionId(s.id);
      setSessionStatus(s.status);
      toast.success("Session ouverte — approche une carte du lecteur");
    },
    onError: (e: any) => {
      const msg = e?.response?.data?.error || "Impossible d'ouvrir la session";
      toast.error(msg);
    },
  });

  const stopMut = useMutation({
    mutationFn: (reason: string) =>
      enrollmentService.stop(sessionId!, reason),
    onSuccess: () => {
      toast.success("Session fermée");
      setSessionStatus("completed");
    },
  });

  const confirmMut = useMutation({
    mutationFn: (uid: string) =>
      enrollmentService.confirm(sessionId!, {
        uid, tech,
        category: holderKind === "worker" ? "worker_rfid"
                : holderKind === "employee" ? "employee_rfid"
                : holderKind === "visitor" ? "visitor_qr"
                : "worker_rfid",
        holder_kind: holderKind || null,
        holder_id: holderId || null,
        valid_until: validUntil || null,
      }),
    onSuccess: (r, uid) => {
      const card = cardsRef.current.get(uid);
      if (card) {
        card.status = "enrolled";
        cardsRef.current.set(uid, card);
        setCards(Array.from(cardsRef.current.values()));
      }
      toast.success(`Badge ${r.data.uid} créé`);
      qc.invalidateQueries({ queryKey: ["badges"] });
      // En mode single, on ferme après 1 succès
      if (mode === "single") {
        setTimeout(() => closeSelf(), 700);
      }
    },
    onError: (e: any) => {
      const msg = e?.response?.data?.error || "Erreur de confirmation";
      toast.error(msg);
    },
  });

  // ─── Reset local ─────────────────────────────────────
  const resetLocal = () => {
    setSessionId(null);
    setSessionStatus("");
    setCards([]);
    setTimeline([]);
    cardsRef.current.clear();
  };

  const closeSelf = () => {
    if (sessionId && sessionStatus === "listening") {
      stopMut.mutate("close");
    }
    resetLocal();
    onClose();
  };

  const downloadReport = async (format: "csv" | "pdf") => {
    if (!sessionId) return;
    try {
      const r = await enrollmentService.exportSession(sessionId, format);
      const url = URL.createObjectURL(new Blob([r.data]));
      const a = document.createElement("a");
      a.href = url;
      a.download = `enrollment_${sessionId}.${format}`;
      a.click();
      URL.revokeObjectURL(url);
    } catch {
      toast.error("Export impossible");
    }
  };

  useEffect(() => {
    if (!open) resetLocal();
  }, [open]);

  // ─── UI ──────────────────────────────────────────────
  const canStart = !sessionId && !startMut.isPending;
  const isListening = sessionStatus === "listening";

  return (
    <Modal open={open} onClose={closeSelf} size="xl"
      title={mode === "bulk" ? "Enrôlement RFID en masse" : "Enrôler un badge RFID"}
      footer={
        <div className="flex gap-2 justify-end w-full">
          <Button variant="ghost" onClick={closeSelf}>
            Fermer
          </Button>
          {sessionId && cards.length > 0 && (
            <>
              <Button variant="ghost" size="sm" leftIcon={<Download className="w-3.5 h-3.5" />}
                      onClick={() => downloadReport("csv")}>
                CSV
              </Button>
              <Button variant="ghost" size="sm" leftIcon={<Download className="w-3.5 h-3.5" />}
                      onClick={() => downloadReport("pdf")}>
                PDF
              </Button>
            </>
          )}
          {isListening && (
            <Button variant="secondary" leftIcon={<StopCircle className="w-4 h-4" />}
                    onClick={() => stopMut.mutate("cancel")}
                    loading={stopMut.isPending}>
              Arrêter l'écoute
            </Button>
          )}
          {canStart && (
            <Button leftIcon={<PlayCircle className="w-4 h-4" />}
                    onClick={() => startMut.mutate()}
                    loading={startMut.isPending}
                    disabled={!readerId && !siteId}>
              Démarrer l'écoute
            </Button>
          )}
        </div>
      }>
      <div className="space-y-4">
        {/* ── Bandeau statut WS ───────────────────────────── */}
        {sessionId && (
          <div className={cn(
            "p-3 rounded-lg border flex items-center gap-2 text-sm",
            wsStatus === "open"     ? "bg-success/5 border-success/30 text-success"
            : wsStatus === "connecting" ? "bg-info/5 border-info/30 text-info"
            : "bg-warning/5 border-warning/30 text-warning",
          )}>
            {wsStatus === "open" ? <Wifi className="w-4 h-4 animate-pulse" />
              : wsStatus === "connecting" ? <Loader2 className="w-4 h-4 animate-spin" />
              : <WifiOff className="w-4 h-4" />}
            <span className="font-medium">
              {wsStatus === "open" ? "Connexion temps réel active"
                : wsStatus === "connecting" ? "Connexion en cours…"
                : `Déconnecté — tentative de reconnexion (${reconnectCount})`}
            </span>
            <span className="ml-auto text-xs">Session {sessionId.slice(0, 8)} · {sessionStatus}</span>
          </div>
        )}

        {/* ── Setup (avant démarrage) ─────────────────────── */}
        {!sessionId && (
          <div className="grid grid-cols-2 gap-3">
            <label className="block">
              <span className="text-xs font-medium text-ink-muted flex items-center gap-1">
                <Building2 className="w-3 h-3" /> Site
              </span>
              <select className="field w-full mt-1.5" value={siteId}
                      onChange={(e) => { setSiteId(e.target.value ? Number(e.target.value) : ""); setZoneId(""); }}>
                <option value="">— Tous —</option>
                {sites?.results?.map((s: any) => (
                  <option key={s.id} value={s.id}>{s.name}</option>
                ))}
              </select>
            </label>

            <label className="block">
              <span className="text-xs font-medium text-ink-muted flex items-center gap-1">
                <MapPin className="w-3 h-3" /> Zone
              </span>
              <select className="field w-full mt-1.5" value={zoneId} disabled={!siteId}
                      onChange={(e) => setZoneId(e.target.value ? Number(e.target.value) : "")}>
                <option value="">— Toutes —</option>
                {zones?.results?.map((z: any) => (
                  <option key={z.id} value={z.id}>{z.name}</option>
                ))}
              </select>
            </label>

            <label className="block col-span-2">
              <span className="text-xs font-medium text-ink-muted flex items-center gap-1">
                <Radar className="w-3 h-3" /> Lecteur RFID *
              </span>
              <select className="field w-full mt-1.5" value={readerId}
                      onChange={(e) => setReaderId(e.target.value ? Number(e.target.value) : "")}>
                <option value="">— Tous les lecteurs disponibles —</option>
                {(readers?.results || []).map((r: any) => {
                  const online = r.last_heartbeat_at
                    && (Date.now() - new Date(r.last_heartbeat_at).getTime() < 90_000);
                  return (
                    <option key={r.id} value={r.id}>
                      {online ? "● " : "○ "}
                      {r.model?.brand} {r.model?.model || r.serial_number}
                      {r.ip_address ? ` (${r.ip_address})` : ""}
                    </option>
                  );
                })}
              </select>
              {selectedReader && (
                <div className="text-xs mt-1 flex items-center gap-1">
                  {isReaderOnline ? (
                    <><Wifi className="w-3 h-3 text-success" />
                      <span className="text-success">Lecteur en ligne</span></>
                  ) : (
                    <><WifiOff className="w-3 h-3 text-warning" />
                      <span className="text-warning">Dernier heartbeat il y a plus de 90 s</span></>
                  )}
                </div>
              )}
            </label>

            <label className="block">
              <span className="text-xs font-medium text-ink-muted flex items-center gap-1">
                <UserIcon className="w-3 h-3" /> Associer à
              </span>
              <select className="field w-full mt-1.5" value={holderKind}
                      onChange={(e) => { setHolderKind(e.target.value as any); setHolderId(""); }}>
                <option value="">Aucun (badge en pool)</option>
                <option value="worker">Ouvrier</option>
                <option value="employee">Employé</option>
              </select>
            </label>

            <label className="block">
              <span className="text-xs font-medium text-ink-muted">
                {holderKind === "worker" ? "Ouvrier" : holderKind === "employee" ? "Employé" : "—"}
              </span>
              <select className="field w-full mt-1.5" value={holderId} disabled={!holderKind}
                      onChange={(e) => setHolderId(e.target.value ? Number(e.target.value) : "")}>
                <option value="">— Sélectionner —</option>
                {(holders?.results || []).map((h: any) => (
                  <option key={h.id} value={h.id}>
                    {h.matricule} — {h.first_name} {h.last_name}
                  </option>
                ))}
              </select>
            </label>

            <label className="block">
              <span className="text-xs font-medium text-ink-muted">Technologie</span>
              <select className="field w-full mt-1.5" value={tech}
                      onChange={(e) => setTech(e.target.value as any)}>
                <option value="nfc">NFC (13.56 MHz)</option>
                <option value="uhf">UHF (860-960 MHz)</option>
                <option value="uhf_xerafy">Xerafy (casque)</option>
                <option value="qr">QR code</option>
              </select>
            </label>

            <Input label="Date d'expiration" type="date" value={validUntil}
                   onChange={(e) => setValidUntil(e.target.value)} />
          </div>
        )}

        {/* ── Zone active — cartes détectées ───────────────── */}
        {sessionId && (
          <>
            <div className="grid grid-cols-4 gap-2 text-center text-xs">
              <div className="p-2 rounded-md bg-surface-soft border border-surface-border">
                <div className="text-ink-muted">Détectées</div>
                <div className="text-lg font-bold text-ink">{cards.length}</div>
              </div>
              <div className="p-2 rounded-md bg-success/5 border border-success/20">
                <div className="text-success">Valides</div>
                <div className="text-lg font-bold text-success">
                  {cards.filter((c) => c.status === "detected" || c.status === "enrolled").length}
                </div>
              </div>
              <div className="p-2 rounded-md bg-danger/5 border border-danger/20">
                <div className="text-danger">Doublons</div>
                <div className="text-lg font-bold text-danger">
                  {cards.filter((c) => c.status === "duplicate").length}
                </div>
              </div>
              <div className="p-2 rounded-md bg-info/5 border border-info/20">
                <div className="text-info">Enrôlées</div>
                <div className="text-lg font-bold text-info">
                  {cards.filter((c) => c.status === "enrolled").length}
                </div>
              </div>
            </div>

            {cards.length === 0 && isListening && (
              <div className="p-6 text-center border border-dashed border-surface-border rounded-md">
                <Radar className="w-8 h-8 mx-auto mb-2 text-info animate-pulse" />
                <div className="text-sm font-medium text-ink">En attente d'une carte…</div>
                <div className="text-xs text-ink-muted mt-1">
                  Passe une carte devant le lecteur — l'UID sera capturé instantanément.
                </div>
              </div>
            )}

            <div className="space-y-1.5 max-h-72 overflow-auto">
              {cards.map((c) => (
                <CardRow key={c.uid} card={c}
                         canConfirm={c.status === "detected"}
                         onConfirm={() => confirmMut.mutate(c.uid)}
                         confirming={confirmMut.isPending && confirmMut.variables === c.uid} />
              ))}
            </div>

            {/* Timeline (5 derniers events) */}
            {timeline.length > 0 && (
              <details className="border border-surface-border rounded-md">
                <summary className="p-2 cursor-pointer text-xs text-ink-muted flex items-center gap-1">
                  <Zap className="w-3 h-3" /> Journal temps réel ({timeline.length})
                </summary>
                <div className="max-h-40 overflow-auto text-xs font-mono p-2 space-y-0.5">
                  {timeline.slice(-30).reverse().map((e, i) => (
                    <div key={i} className="text-ink-muted">
                      <span className="text-info">
                        {(e.at || "").slice(11, 19)}
                      </span>{" "}
                      <span className="text-ink">{e.event || e.event_type}</span>
                      {e.uid && <span className="ml-2">{e.uid}</span>}
                      {e.message && <span className="ml-2 italic">{e.message}</span>}
                    </div>
                  ))}
                </div>
              </details>
            )}
          </>
        )}
      </div>
    </Modal>
  );
}

// ─────────────────────────────────────────────────────────────
// Ligne de carte capturée
// ─────────────────────────────────────────────────────────────
function CardRow({ card, canConfirm, onConfirm, confirming }: {
  card: CapturedCard;
  canConfirm: boolean;
  onConfirm: () => void;
  confirming: boolean;
}) {
  const statusMeta: Record<CapturedCard["status"], { icon: any; bg: string; label: string; color: string }> = {
    detected:  { icon: <Radar className="w-4 h-4" />,         bg: "bg-info/5 border-info/20",       label: "Détectée",       color: "text-info" },
    duplicate: { icon: <AlertTriangle className="w-4 h-4" />, bg: "bg-danger/5 border-danger/30",   label: "Doublon",        color: "text-danger" },
    enrolled:  { icon: <CheckCircle2 className="w-4 h-4" />,  bg: "bg-success/5 border-success/30", label: "Enrôlée",        color: "text-success" },
    error:     { icon: <XCircle className="w-4 h-4" />,       bg: "bg-danger/5 border-danger/30",   label: "Erreur",         color: "text-danger" },
  };
  const meta = statusMeta[card.status];

  return (
    <div className={cn("p-2.5 rounded-md border flex items-center gap-3", meta.bg)}>
      <div className={cn("shrink-0", meta.color)}>{meta.icon}</div>
      <div className="flex-1 min-w-0">
        <div className="font-mono text-sm text-ink truncate">{card.uid}</div>
        <div className="text-xs text-ink-muted flex items-center gap-2 flex-wrap">
          <span className={meta.color}>{meta.label}</span>
          {card.deviceSerial && <span>· {card.deviceSerial}</span>}
          {typeof card.rssi === "number" && <span>· RSSI {card.rssi} dBm</span>}
          <span>· {fmtRelative(card.detectedAt)}</span>
          {card.existingBadge && (
            <span className="text-danger">
              · déjà associé à {card.existingBadge.holder?.label || `badge #${card.existingBadge.id}`}
            </span>
          )}
        </div>
      </div>
      {canConfirm && (
        <Button size="sm" onClick={onConfirm} loading={confirming}
                leftIcon={<CheckCircle2 className="w-3.5 h-3.5" />}>
          Confirmer
        </Button>
      )}
      {card.status === "duplicate" && (
        <span className="text-xs text-danger flex items-center gap-1">
          <X className="w-3 h-3" /> Bloqué
        </span>
      )}
    </div>
  );
}
