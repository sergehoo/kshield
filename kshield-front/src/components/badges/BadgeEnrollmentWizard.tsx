/**
 * BadgeEnrollmentWizard — 4 étapes (cahier §3).
 *
 *   1. Type de porteur + sélection (worker / employee / visitor / contractor …)
 *   2. UID du badge (scan lecteur RFID connecté OU saisie manuelle)
 *   3. Attribution : site + zones + niveau d'accès + fenêtre horaire + expiration
 *   4. Confirmation : récap + validation → POST /badges/<id>/assign/
 *
 * Le badge peut être un badge existant (statut "unassigned") ou fraîchement
 * enrôlé via l'inbox RFID (POST /badges/ puis assign).
 */
import { useMemo, useState } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import {
  ArrowLeft, ArrowRight, CheckCircle2, User, Users, UserPlus,
  Hash, MapPin, Shield, CalendarClock, Clock, Radar, Sparkles,
  X, Loader2,
} from "lucide-react";
import toast from "react-hot-toast";

import { Modal } from "@/components/ui/Modal";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Badge } from "@/components/ui/Badge";
import { cn } from "@/lib/cn";
import {
  workersService, employeesService, visitorsService,
  sitesService, zonesService, badgesService,
} from "@/services";
import {
  badgeLifecycleService,
  HolderKind, HOLDER_LABELS, ACCESS_LEVEL_LABELS, AccessLevel,
  BadgeAssignBody,
} from "@/services/badgeLifecycle";

interface Props {
  open: boolean;
  onClose: () => void;
  /** Badge existant à assigner (facultatif — sinon on en crée un via UID). */
  presetBadgeId?: string;
  presetUid?: string;
  presetHolderKind?: HolderKind;
  onDone?: () => void;
}

const HOLDER_KINDS: HolderKind[] = [
  "worker", "employee", "visitor", "contractor",
  "vehicle", "material", "temporary",
];

const WEEKDAYS = [
  { code: "0", label: "Lun" }, { code: "1", label: "Mar" },
  { code: "2", label: "Mer" }, { code: "3", label: "Jeu" },
  { code: "4", label: "Ven" }, { code: "5", label: "Sam" },
  { code: "6", label: "Dim" },
];

export function BadgeEnrollmentWizard({
  open, onClose, presetBadgeId, presetUid, presetHolderKind, onDone,
}: Props) {
  const [step, setStep] = useState<1 | 2 | 3 | 4>(1);

  // Étape 1
  const [holderKind, setHolderKind] = useState<HolderKind | "">(presetHolderKind || "");
  const [holderId, setHolderId] = useState<number | "">("");
  const [holderQ, setHolderQ] = useState("");

  // Étape 2
  const [uid, setUid] = useState(presetUid || "");
  const [badgeId, setBadgeId] = useState<string | "">(presetBadgeId || "");
  const [tech, setTech] = useState<"nfc" | "uhf" | "ble" | "qr">("nfc");

  // Étape 3
  const [siteId, setSiteId] = useState<number | "">("");
  const [zoneIds, setZoneIds] = useState<number[]>([]);
  const [accessLevel, setAccessLevel] = useState<AccessLevel>("basic");
  const [windowStart, setWindowStart] = useState("");
  const [windowEnd, setWindowEnd] = useState("");
  const [weekdays, setWeekdays] = useState<string[]>([]);
  const [expiresAt, setExpiresAt] = useState("");
  const [isPermanent, setIsPermanent] = useState(false);
  const [reason, setReason] = useState("");
  const [notes, setNotes] = useState("");

  const reset = () => {
    setStep(1);
    setHolderKind(""); setHolderId(""); setHolderQ("");
    setUid(""); setBadgeId(""); setTech("nfc");
    setSiteId(""); setZoneIds([]); setAccessLevel("basic");
    setWindowStart(""); setWindowEnd(""); setWeekdays([]);
    setExpiresAt(""); setIsPermanent(false);
    setReason(""); setNotes("");
  };

  // ─── Données auxiliaires ────────────────────────────────
  const holderQuery = useQuery({
    queryKey: ["wizard", "holders", holderKind, holderQ],
    queryFn: async () => {
      if (holderKind === "worker") {
        return (await workersService.list({ q: holderQ, page_size: 20 })).data;
      }
      if (holderKind === "employee") {
        return (await employeesService.list({ q: holderQ, page_size: 20 })).data;
      }
      if (holderKind === "visitor") {
        return (await visitorsService.list({ q: holderQ, page_size: 20 })).data;
      }
      return { results: [] };
    },
    enabled: open && ["worker", "employee", "visitor"].includes(holderKind),
  });

  const sites = useQuery({
    queryKey: ["wizard", "sites"],
    queryFn: async () => (await sitesService.list({ page_size: 200 })).data,
    enabled: open,
  });

  const zones = useQuery({
    queryKey: ["wizard", "zones", siteId],
    queryFn: async () =>
      (await zonesService.list({ site: siteId, page_size: 200 })).data,
    enabled: open && !!siteId,
  });

  // Poll de l'inbox RFID pour attraper un scan récent
  const inbox = useQuery({
    queryKey: ["wizard", "rfid-inbox"],
    queryFn: async () => (await badgesService.scanInbox()).data,
    enabled: open && step === 2 && !uid,
    refetchInterval: 2000,
  });

  // ─── Mutations ──────────────────────────────────────────
  const createBadgeMut = useMutation({
    mutationFn: async () => {
      if (badgeId) return { data: { id: badgeId } };
      // Créer un badge à partir de l'UID
      return badgesService.create({ uid, tech });
    },
  });

  const assignMut = useMutation({
    mutationFn: async () => {
      // 1. Assurer qu'on a un badge ID
      const b = await createBadgeMut.mutateAsync();
      const bid = (b as any).data?.id || badgeId;

      const body: BadgeAssignBody = {
        holder_kind: holderKind as HolderKind,
        holder_id: holderId ? Number(holderId) : undefined,
        site_id: siteId ? Number(siteId) : undefined,
        zone_ids: zoneIds.length ? zoneIds : undefined,
        access_level: accessLevel,
        expires_at: !isPermanent && expiresAt ? expiresAt : undefined,
        time_window_start: windowStart || undefined,
        time_window_end: windowEnd || undefined,
        allowed_weekdays: weekdays.length ? weekdays.join(",") : undefined,
        is_permanent: isPermanent,
        reason: reason || undefined,
        notes: notes || undefined,
      };
      return badgeLifecycleService.assign(bid, body);
    },
    onSuccess: (r) => {
      toast.success("Badge attribué avec succès");
      onDone?.();
      onClose();
      reset();
      return r;
    },
    onError: (e: any) =>
      toast.error(e?.response?.data?.error || e?.message || "Erreur"),
  });

  const holderList = (holderQuery.data as any)?.results || [];
  const selectedHolder = holderList.find((h: any) => h.id === holderId);

  const canNext = useMemo(() => {
    if (step === 1) return holderKind && (
      // Pour vehicle/material/temporary/contractor, un label suffit
      ["vehicle", "material", "temporary", "contractor"].includes(holderKind) ||
      !!holderId
    );
    if (step === 2) return !!(uid || badgeId);
    if (step === 3) return !!siteId;
    return true;
  }, [step, holderKind, holderId, uid, badgeId, siteId]);

  return (
    <Modal
      open={open}
      onClose={() => { onClose(); }}
      title="Enrôler et attribuer un badge"
      size="xl"
    >
      {/* Steps header */}
      <ol className="flex items-center gap-2 mb-6">
        {[1, 2, 3, 4].map((n) => (
          <li key={n} className="flex-1 flex items-center gap-2">
            <div className={cn(
              "w-8 h-8 rounded-2xl grid place-items-center text-sm font-semibold shrink-0",
              n < step && "bg-ok text-white",
              n === step && "bg-ink text-white",
              n > step && "bg-ink/5 text-ink-muted",
            )}>
              {n < step ? <CheckCircle2 size={14} /> : n}
            </div>
            <div className="text-xs flex-1 min-w-0">
              <div className={cn(
                "font-semibold truncate",
                n <= step ? "text-ink" : "text-ink-muted",
              )}>
                {n === 1 && "Porteur"}
                {n === 2 && "Badge (UID)"}
                {n === 3 && "Attribution"}
                {n === 4 && "Confirmation"}
              </div>
            </div>
          </li>
        ))}
      </ol>

      {/* Corps */}
      <div className="min-h-[320px]">
        {step === 1 && (
          <Step1
            holderKind={holderKind} setHolderKind={setHolderKind}
            holderId={holderId} setHolderId={setHolderId}
            holderQ={holderQ} setHolderQ={setHolderQ}
            holders={holderList}
            loading={holderQuery.isFetching}
          />
        )}
        {step === 2 && (
          <Step2
            uid={uid} setUid={setUid}
            tech={tech} setTech={setTech}
            inbox={inbox.data}
          />
        )}
        {step === 3 && (
          <Step3
            sites={(sites.data as any)?.results || []}
            zones={(zones.data as any)?.results || []}
            siteId={siteId} setSiteId={setSiteId}
            zoneIds={zoneIds} setZoneIds={setZoneIds}
            accessLevel={accessLevel} setAccessLevel={setAccessLevel}
            windowStart={windowStart} setWindowStart={setWindowStart}
            windowEnd={windowEnd} setWindowEnd={setWindowEnd}
            weekdays={weekdays} setWeekdays={setWeekdays}
            expiresAt={expiresAt} setExpiresAt={setExpiresAt}
            isPermanent={isPermanent} setIsPermanent={setIsPermanent}
            reason={reason} setReason={setReason}
            notes={notes} setNotes={setNotes}
          />
        )}
        {step === 4 && (
          <Step4
            holderKind={holderKind as HolderKind}
            holderLabel={selectedHolder?.full_name || selectedHolder?.name || "—"}
            uid={uid}
            tech={tech}
            siteLabel={(sites.data as any)?.results?.find((s: any) => s.id === siteId)?.label ?? ""}
            zones={((zones.data as any)?.results || [])
              .filter((z: any) => zoneIds.includes(z.id))
              .map((z: any) => z.name || z.label)}
            accessLevel={accessLevel}
            windowStart={windowStart}
            windowEnd={windowEnd}
            weekdays={weekdays}
            expiresAt={expiresAt}
            isPermanent={isPermanent}
            reason={reason}
          />
        )}
      </div>

      {/* Footer */}
      <div className="mt-6 pt-4 border-t border-surface-border/60 flex items-center justify-between">
        <div>
          {step > 1 && (
            <Button
              variant="ghost"
              leftIcon={<ArrowLeft size={14} />}
              onClick={() => setStep((s) => (s > 1 ? ((s - 1) as any) : s))}
            >
              Précédent
            </Button>
          )}
        </div>
        <div className="flex items-center gap-2">
          <Button variant="ghost" onClick={() => { onClose(); reset(); }}>
            Annuler
          </Button>
          {step < 4 ? (
            <Button
              variant="dark"
              rightIcon={<ArrowRight size={14} />}
              disabled={!canNext}
              onClick={() => setStep((s) => ((s + 1) as any))}
            >
              Suivant
            </Button>
          ) : (
            <Button
              variant="primary"
              leftIcon={<Sparkles size={14} />}
              loading={assignMut.isPending}
              onClick={() => assignMut.mutate()}
            >
              Confirmer l'attribution
            </Button>
          )}
        </div>
      </div>
    </Modal>
  );
}

// ═══════════════════════════════════════════════════════════════
// STEP 1 — Sélection porteur
// ═══════════════════════════════════════════════════════════════
function Step1({
  holderKind, setHolderKind,
  holderId, setHolderId,
  holderQ, setHolderQ,
  holders, loading,
}: any) {
  const needsPerson = ["worker", "employee", "visitor"].includes(holderKind);
  return (
    <div className="space-y-4">
      <div>
        <label className="text-xs uppercase tracking-wide text-ink-muted">
          Type de porteur
        </label>
        <div className="mt-2 grid grid-cols-2 md:grid-cols-4 gap-2">
          {HOLDER_KINDS.map((k) => (
            <button
              key={k}
              onClick={() => { setHolderKind(k); setHolderId(""); }}
              className={cn(
                "rounded-2xl p-3 text-sm font-medium transition-colors border",
                holderKind === k
                  ? "bg-ink text-white border-ink"
                  : "bg-surface-soft/40 text-ink border-transparent hover:border-ink/20",
              )}
            >
              {HOLDER_LABELS[k]}
            </button>
          ))}
        </div>
      </div>

      {needsPerson && (
        <div>
          <label className="text-xs uppercase tracking-wide text-ink-muted">
            Sélectionner un {HOLDER_LABELS[holderKind as HolderKind].toLowerCase()}
          </label>
          <Input
            value={holderQ}
            onChange={(e) => setHolderQ(e.target.value)}
            placeholder="Recherche par nom, matricule…"
            className="mt-2"
          />
          <div className="mt-2 max-h-52 overflow-y-auto rounded-xl border border-surface-border/60">
            {loading && (
              <div className="p-3 text-center text-sm text-ink-muted">
                <Loader2 className="inline animate-spin mr-2" size={14} />
                Recherche…
              </div>
            )}
            {!loading && holders.length === 0 && (
              <div className="p-3 text-center text-sm text-ink-muted">
                Aucun résultat.
              </div>
            )}
            {holders.map((h: any) => {
              const label = h.full_name || h.name ||
                            `${h.first_name || ""} ${h.last_name || ""}`.trim() ||
                            `#${h.id}`;
              return (
                <button
                  key={h.id}
                  onClick={() => setHolderId(h.id)}
                  className={cn(
                    "w-full text-left px-3 py-2 text-sm hover:bg-surface-soft/60 flex items-center gap-2",
                    holderId === h.id && "bg-ink/5",
                  )}
                >
                  <User size={14} className="text-ink-muted" />
                  <span className="truncate">{label}</span>
                  {holderId === h.id && (
                    <CheckCircle2 size={14} className="ml-auto text-ok" />
                  )}
                </button>
              );
            })}
          </div>
        </div>
      )}

      {!needsPerson && holderKind && (
        <div className="rounded-xl bg-info/5 border border-info/20 p-3 text-xs text-ink">
          Type <strong>{HOLDER_LABELS[holderKind as HolderKind]}</strong> — le badge
          sera attribué au titulaire abstrait sans besoin de sélectionner une
          personne. Tu pourras préciser plus tard le rattachement (véhicule,
          matériel, etc.).
        </div>
      )}
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════
// STEP 2 — UID (scan ou saisie)
// ═══════════════════════════════════════════════════════════════
function Step2({ uid, setUid, tech, setTech, inbox }: any) {
  const lastScan = inbox?.scans?.[0];
  return (
    <div className="space-y-4">
      <div>
        <label className="text-xs uppercase tracking-wide text-ink-muted">
          Technologie
        </label>
        <div className="mt-2 flex flex-wrap gap-2">
          {(["nfc", "uhf", "ble", "qr"] as const).map((t) => (
            <button
              key={t}
              onClick={() => setTech(t)}
              className={cn(
                "px-4 py-2 rounded-xl text-sm font-medium uppercase transition-colors",
                tech === t
                  ? "bg-ink text-white"
                  : "bg-ink/5 text-ink hover:bg-ink/10",
              )}
            >
              {t}
            </button>
          ))}
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div>
          <label className="text-xs uppercase tracking-wide text-ink-muted">
            UID du badge
          </label>
          <Input
            value={uid}
            onChange={(e) => setUid(e.target.value.toUpperCase())}
            placeholder="Ex: 04A8B2C1..."
            className="mt-2 font-mono"
          />
          <p className="mt-2 text-xs text-ink-muted">
            Saisis manuellement, ou approche le badge d'un lecteur connecté —
            le scan sera capté ici automatiquement.
          </p>
        </div>

        <div className="rounded-2xl bg-surface-soft/60 p-4">
          <div className="flex items-center gap-2 text-sm font-semibold text-ink">
            <Radar size={16} /> Scan en direct
          </div>
          {lastScan ? (
            <div className="mt-3">
              <div className="text-2xl font-mono font-bold text-ok">
                {lastScan.uid}
              </div>
              <div className="text-[11px] text-ink-muted mt-1">
                détecté sur lecteur {lastScan.reader_id || "?"}
              </div>
              <Button
                size="sm"
                variant="dark"
                className="mt-3"
                onClick={() => setUid(lastScan.uid)}
              >
                Utiliser cet UID
              </Button>
            </div>
          ) : (
            <div className="mt-3 text-xs text-ink-muted">
              En attente d'un scan… présente un badge devant un lecteur RFID
              connecté au réseau Shield.
            </div>
          )}
        </div>
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════
// STEP 3 — Attribution
// ═══════════════════════════════════════════════════════════════
function Step3({
  sites, zones, siteId, setSiteId, zoneIds, setZoneIds,
  accessLevel, setAccessLevel,
  windowStart, setWindowStart, windowEnd, setWindowEnd,
  weekdays, setWeekdays,
  expiresAt, setExpiresAt, isPermanent, setIsPermanent,
  reason, setReason, notes, setNotes,
}: any) {
  const toggleZone = (id: number) =>
    setZoneIds(zoneIds.includes(id)
      ? zoneIds.filter((z: number) => z !== id)
      : [...zoneIds, id]);
  const toggleDay = (code: string) =>
    setWeekdays(weekdays.includes(code)
      ? weekdays.filter((d: string) => d !== code)
      : [...weekdays, code]);

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
      <div>
        <label className="text-xs uppercase tracking-wide text-ink-muted">Site</label>
        <select
          value={siteId}
          onChange={(e) => { setSiteId(e.target.value ? Number(e.target.value) : ""); setZoneIds([]); }}
          className="mt-1 w-full rounded-xl border border-surface-border bg-white px-3 py-2 text-sm"
        >
          <option value="">— choisir un site —</option>
          {sites.map((s: any) => (
            <option key={s.id} value={s.id}>{s.label || s.name}</option>
          ))}
        </select>
      </div>

      <div>
        <label className="text-xs uppercase tracking-wide text-ink-muted">
          Niveau d'accès
        </label>
        <select
          value={accessLevel}
          onChange={(e) => setAccessLevel(e.target.value as AccessLevel)}
          className="mt-1 w-full rounded-xl border border-surface-border bg-white px-3 py-2 text-sm"
        >
          {(Object.keys(ACCESS_LEVEL_LABELS) as AccessLevel[]).map((k) => (
            <option key={k} value={k}>{ACCESS_LEVEL_LABELS[k]}</option>
          ))}
        </select>
      </div>

      <div className="md:col-span-2">
        <label className="text-xs uppercase tracking-wide text-ink-muted">
          Zones autorisées
        </label>
        <div className="mt-2 flex flex-wrap gap-2 min-h-[42px] p-2 rounded-xl bg-surface-soft/40">
          {zones.length === 0 && (
            <span className="text-xs text-ink-muted italic">
              Aucune zone disponible pour ce site.
            </span>
          )}
          {zones.map((z: any) => (
            <button
              key={z.id}
              onClick={() => toggleZone(z.id)}
              className={cn(
                "px-2.5 py-1 rounded-lg text-xs font-medium transition-colors",
                zoneIds.includes(z.id)
                  ? "bg-ink text-white"
                  : "bg-white text-ink hover:bg-ink/5",
              )}
            >
              {z.name || z.label}
            </button>
          ))}
        </div>
      </div>

      <div>
        <label className="text-xs uppercase tracking-wide text-ink-muted">
          Fenêtre horaire (début)
        </label>
        <Input type="time" value={windowStart} onChange={(e) => setWindowStart(e.target.value)} className="mt-1" />
      </div>

      <div>
        <label className="text-xs uppercase tracking-wide text-ink-muted">
          Fenêtre horaire (fin)
        </label>
        <Input type="time" value={windowEnd} onChange={(e) => setWindowEnd(e.target.value)} className="mt-1" />
      </div>

      <div className="md:col-span-2">
        <label className="text-xs uppercase tracking-wide text-ink-muted">
          Jours autorisés
        </label>
        <div className="mt-2 flex flex-wrap gap-2">
          {WEEKDAYS.map((d) => (
            <button
              key={d.code}
              onClick={() => toggleDay(d.code)}
              className={cn(
                "w-12 h-9 rounded-lg text-xs font-semibold transition-colors",
                weekdays.includes(d.code)
                  ? "bg-ink text-white"
                  : "bg-ink/5 text-ink hover:bg-ink/10",
              )}
            >
              {d.label}
            </button>
          ))}
          <span className="text-xs text-ink-muted self-center ml-2">
            Vide = tous les jours autorisés.
          </span>
        </div>
      </div>

      <div>
        <label className="text-xs uppercase tracking-wide text-ink-muted">
          Expiration
        </label>
        <Input
          type="datetime-local"
          value={expiresAt}
          onChange={(e) => setExpiresAt(e.target.value)}
          disabled={isPermanent}
          className="mt-1"
        />
        <label className="mt-2 flex items-center gap-2 text-xs text-ink cursor-pointer">
          <input
            type="checkbox"
            checked={isPermanent}
            onChange={(e) => setIsPermanent(e.target.checked)}
            className="rounded"
          />
          Badge permanent (aucune expiration)
        </label>
      </div>

      <div>
        <label className="text-xs uppercase tracking-wide text-ink-muted">
          Motif
        </label>
        <Input
          value={reason}
          onChange={(e) => setReason(e.target.value)}
          placeholder="Ex: mission chantier, badge visiteur…"
          className="mt-1"
        />
      </div>

      <div className="md:col-span-2">
        <label className="text-xs uppercase tracking-wide text-ink-muted">
          Notes (optionnel)
        </label>
        <textarea
          value={notes}
          onChange={(e) => setNotes(e.target.value)}
          rows={2}
          className="mt-1 w-full rounded-xl border border-surface-border bg-white px-3 py-2 text-sm"
        />
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════
// STEP 4 — Récap + confirmation
// ═══════════════════════════════════════════════════════════════
function Step4({
  holderKind, holderLabel, uid, tech, siteLabel, zones,
  accessLevel, windowStart, windowEnd, weekdays,
  expiresAt, isPermanent, reason,
}: any) {
  return (
    <div className="space-y-3">
      <div className="rounded-3xl bg-ink text-white p-6">
        <div className="text-xs uppercase text-white/60 tracking-wide">
          Attribution à confirmer
        </div>
        <div className="mt-2 text-2xl font-bold">
          {HOLDER_LABELS[holderKind as HolderKind]} · {holderLabel}
        </div>
        <div className="mt-1 text-sm text-white/80">
          Badge <span className="font-mono">{uid}</span> · {tech.toUpperCase()}
        </div>
      </div>

      <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
        <RecapRow icon={<MapPin size={14} />} label="Site"    value={siteLabel || "—"} />
        <RecapRow icon={<Shield size={14} />} label="Niveau"  value={ACCESS_LEVEL_LABELS[accessLevel as AccessLevel]} />
        <RecapRow icon={<Users size={14} />}  label="Zones"   value={zones?.length ? zones.join(", ") : "toutes"} />
        <RecapRow
          icon={<Clock size={14} />}
          label="Fenêtre horaire"
          value={windowStart && windowEnd ? `${windowStart} – ${windowEnd}` : "24 h / 24"}
        />
        <RecapRow
          icon={<CalendarClock size={14} />}
          label="Jours"
          value={
            weekdays?.length
              ? weekdays.map((d: string) => WEEKDAYS.find((w) => w.code === d)?.label).join(", ")
              : "tous"
          }
        />
        <RecapRow
          icon={<CalendarClock size={14} />}
          label="Expiration"
          value={isPermanent ? "Permanent" : expiresAt ? new Date(expiresAt).toLocaleString("fr-FR") : "—"}
        />
        {reason && (
          <div className="md:col-span-2">
            <RecapRow icon={<Hash size={14} />} label="Motif" value={reason} />
          </div>
        )}
      </div>

      <div className="rounded-xl bg-info/5 border border-info/20 p-3 text-xs text-ink">
        En confirmant, un enregistrement <strong>BadgeAssignment</strong>
        immuable sera créé et sera versé au journal d'audit RGPD. Un événement
        BADGE_ASSIGNED sera émis en temps réel.
      </div>
    </div>
  );
}

function RecapRow({ icon, label, value }: { icon: React.ReactNode; label: string; value: React.ReactNode }) {
  return (
    <div className="rounded-2xl bg-surface-soft/60 p-3">
      <div className="text-[11px] text-ink-muted uppercase tracking-wide flex items-center gap-1">
        {icon} {label}
      </div>
      <div className="text-sm text-ink font-medium mt-1 truncate">{value}</div>
    </div>
  );
}

export default BadgeEnrollmentWizard;
