/**
 * DevicesDiscovery — page Phase 5.5 (cahier §2).
 *
 * Liste tous les équipements découverts par les agents / gateways sur le LAN,
 * triés par compatibilité et fraîcheur. Pour chacun l'admin peut :
 *   - lancer un test de connexion
 *   - adopter (1-clic) — crée un Device
 *   - rejeter avec motif
 *   - voir le raw payload
 *
 * Une colonne latérale liste l'historique des sessions de scan.
 */
import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Search, Radar, RefreshCcw, ShieldCheck, ShieldX, PlayCircle,
  Zap, Boxes, Network, ChevronRight, X, Clock, Server,
} from "lucide-react";
import toast from "react-hot-toast";

import { PageHeader } from "@/components/PageHeader";
import { Card } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Modal } from "@/components/ui/Modal";
import { StatsRow, Stat } from "@/components/StatsRow";
import { fmtRelative } from "@/lib/format";
import { sitesService } from "@/services";
import { cn } from "@/lib/cn";
import {
  discoveryService, DiscoveryDTO, Compatibility, DiscoveryStatus,
  COMPATIBILITY_LABELS, COMPATIBILITY_TONES, STATUS_LABELS, STATUS_TONES,
} from "@/services/discovery";

const COMPAT_ORDER: Record<Compatibility, number> = {
  supported: 0, beta: 1, unknown: 2, unsupported: 3,
};

export function DevicesDiscoveryPage() {
  const qc = useQueryClient();
  const [q, setQ] = useState("");
  const [compat, setCompat] = useState<Compatibility | "all">("all");
  const [status, setStatus] = useState<DiscoveryStatus | "auto">("auto");
  const [detail, setDetail] = useState<DiscoveryDTO | null>(null);
  const [rejectModal, setRejectModal] = useState<DiscoveryDTO | null>(null);
  const [adoptModal, setAdoptModal] = useState<DiscoveryDTO | null>(null);

  const { data, isLoading, refetch, isFetching } = useQuery({
    queryKey: ["discovery", "list", { status, compat }],
    queryFn: async () => (await discoveryService.list({
      ...(status !== "auto" ? { status } : {}),
      ...(compat !== "all" ? { compatibility: compat } : {}),
      limit: 200,
    })).data,
    refetchInterval: 15_000,
  });

  const { data: scans } = useQuery({
    queryKey: ["discovery", "scans"],
    queryFn: async () => (await discoveryService.scans({ limit: 8 })).data,
    refetchInterval: 30_000,
  });

  const invalidate = () => {
    qc.invalidateQueries({ queryKey: ["discovery", "list"] });
  };

  const items = data?.results ?? [];

  const filtered = useMemo(() => {
    let list = items;
    if (q.trim()) {
      const n = q.trim().toLowerCase();
      list = list.filter(
        (d) =>
          d.mac_address?.toLowerCase().includes(n) ||
          d.ip_address?.toLowerCase().includes(n) ||
          d.hostname?.toLowerCase().includes(n) ||
          d.vendor?.toLowerCase().includes(n) ||
          d.model?.toLowerCase().includes(n) ||
          d.device_type?.toLowerCase().includes(n),
      );
    }
    return [...list].sort(
      (a, b) =>
        (COMPAT_ORDER[a.compatibility] ?? 9) -
        (COMPAT_ORDER[b.compatibility] ?? 9) ||
        new Date(b.last_seen_at).getTime() -
        new Date(a.last_seen_at).getTime(),
    );
  }, [items, q]);

  const stats: Stat[] = useMemo(() => {
    const supported = items.filter((d) => d.compatibility === "supported").length;
    const beta = items.filter((d) => d.compatibility === "beta").length;
    const unknown = items.filter((d) => d.compatibility === "unknown").length;
    const unsupported = items.filter((d) => d.compatibility === "unsupported").length;
    return [
      { label: "Total détectés",     value: items.length,     icon: <Boxes size={18} />,       tone: "brand" },
      { label: "Compatibles",        value: supported,        icon: <ShieldCheck size={18} />, tone: "ok" },
      { label: "Bêta",               value: beta,             icon: <Zap size={18} />,         tone: "warn" },
      { label: "Non supportés",      value: unsupported,      icon: <ShieldX size={18} />,     tone: "danger" },
      { label: "Inconnus",           value: unknown,          icon: <Network size={18} />,     tone: "info" },
    ];
  }, [items]);

  return (
    <div>
      <PageHeader
        title="Découverte réseau"
        subtitle="Équipements détectés par les agents et gateways — adoption en un clic."
        icon={<Radar size={20} />}
        live={isFetching}
        actions={
          <button
            onClick={() => refetch()}
            className="inline-flex items-center gap-2 rounded-xl px-4 py-2.5 text-sm font-medium bg-ink text-surface-card hover:bg-ink/85"
          >
            <RefreshCcw size={16} /> Rafraîchir
          </button>
        }
      />

      <StatsRow stats={stats} loading={isLoading} />

      <div className="grid grid-cols-1 xl:grid-cols-4 gap-4">
        {/* Colonne gauche : filtres + liste */}
        <div className="xl:col-span-3 space-y-4">
          <Card padded>
            <div className="flex flex-col md:flex-row md:items-center gap-3">
              <div className="relative flex-1 max-w-md">
                <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-ink-muted" />
                <Input
                  value={q}
                  onChange={(e) => setQ(e.target.value)}
                  placeholder="Rechercher MAC, IP, hostname, marque…"
                  className="pl-9"
                />
              </div>
              <select
                value={compat}
                onChange={(e) => setCompat(e.target.value as any)}
                className="rounded-xl border border-surface-border bg-surface-card px-3 py-2 text-sm text-ink"
              >
                <option value="all">Toutes compatibilités</option>
                {(["supported", "beta", "unknown", "unsupported"] as Compatibility[]).map((c) => (
                  <option key={c} value={c}>{COMPATIBILITY_LABELS[c]}</option>
                ))}
              </select>
              <select
                value={status}
                onChange={(e) => setStatus(e.target.value as any)}
                className="rounded-xl border border-surface-border bg-surface-card px-3 py-2 text-sm text-ink"
              >
                <option value="auto">Auto (détecté + testé)</option>
                {(Object.keys(STATUS_LABELS) as DiscoveryStatus[]).map((s) => (
                  <option key={s} value={s}>{STATUS_LABELS[s]}</option>
                ))}
              </select>
            </div>
          </Card>

          {isLoading ? (
            <div className="rounded-3xl bg-surface-soft/60 h-64 animate-pulse" />
          ) : filtered.length === 0 ? (
            <Card padded>
              <div className="py-14 text-center text-ink-muted">
                <Radar className="mx-auto mb-2 opacity-40" size={28} />
                <p className="text-sm">Aucun équipement en attente d'adoption.</p>
                <p className="text-xs mt-1">
                  Lance un scan depuis la gateway ou l'agent local pour peupler cette liste.
                </p>
              </div>
            </Card>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-3">
              {filtered.map((d) => (
                <DiscoveryCard
                  key={d.id}
                  d={d}
                  onOpen={() => setDetail(d)}
                  onAdopt={() => setAdoptModal(d)}
                  onReject={() => setRejectModal(d)}
                  onTest={async () => {
                    await discoveryService.test(d.id);
                    toast.success(`Test lancé sur ${d.ip_address || d.mac_address}`);
                    invalidate();
                  }}
                />
              ))}
            </div>
          )}
        </div>

        {/* Colonne droite : historique scans */}
        <Card title="Sessions de scan" padded className="xl:col-span-1">
          <ul className="space-y-2 max-h-[600px] overflow-y-auto pr-1">
            {(scans?.results ?? []).map((s) => (
              <li key={s.id} className="rounded-xl bg-surface-soft/60 p-3">
                <div className="flex items-center gap-2">
                  <Server size={12} className="text-ink-muted shrink-0" />
                  <span className="text-sm text-ink font-medium truncate">
                    {s.gateway_label || "Gateway ?"}
                  </span>
                  <Badge tone={s.status === "completed" ? "ok" : s.status === "failed" ? "danger" : "info"}>
                    {s.status}
                  </Badge>
                </div>
                <div className="mt-2 text-xs text-ink-muted flex items-center gap-2 flex-wrap">
                  <span className="inline-flex items-center gap-1">
                    <Clock size={11} /> {fmtRelative(s.created_at)}
                  </span>
                  <span>· {s.devices_detected} détectés</span>
                  <span>· {s.devices_new} nouveaux</span>
                </div>
                {s.protocols_used?.length > 0 && (
                  <div className="mt-1.5 flex flex-wrap gap-1">
                    {s.protocols_used.map((p) => (
                      <span key={p} className="text-[10px] font-mono uppercase bg-ink/5 text-ink-muted px-1.5 py-0.5 rounded">
                        {p}
                      </span>
                    ))}
                  </div>
                )}
                {s.error && (
                  <div className="mt-1.5 text-[11px] text-danger">{s.error}</div>
                )}
              </li>
            ))}
            {(!scans || scans.results.length === 0) && (
              <li className="py-6 text-center text-ink-muted text-xs">
                Aucun scan enregistré.
              </li>
            )}
          </ul>
        </Card>
      </div>

      {/* Modal détail */}
      {detail && (
        <DiscoveryDetailModal
          d={detail}
          onClose={() => setDetail(null)}
          onAdopt={() => { setAdoptModal(detail); setDetail(null); }}
          onReject={() => { setRejectModal(detail); setDetail(null); }}
        />
      )}
      {rejectModal && (
        <RejectModal
          d={rejectModal}
          onClose={() => setRejectModal(null)}
          onDone={() => { setRejectModal(null); invalidate(); }}
        />
      )}
      {adoptModal && (
        <AdoptModal
          d={adoptModal}
          onClose={() => setAdoptModal(null)}
          onDone={() => { setAdoptModal(null); invalidate(); }}
        />
      )}
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════
// Carte compacte
// ═══════════════════════════════════════════════════════════════
function DiscoveryCard({
  d, onOpen, onAdopt, onReject, onTest,
}: {
  d: DiscoveryDTO;
  onOpen: () => void; onAdopt: () => void;
  onReject: () => void; onTest: () => void;
}) {
  const compat = COMPATIBILITY_TONES[d.compatibility];
  const st = STATUS_TONES[d.status];

  return (
    <div className="rounded-3xl bg-surface-card p-4 shadow-dappr">
      <div className="flex items-start justify-between gap-3">
        <button onClick={onOpen} className="text-left min-w-0 flex-1">
          <div className="flex items-center gap-2 flex-wrap">
            <h3 className="text-base font-semibold text-ink truncate max-w-[220px]">
              {d.hostname || d.vendor || d.mac_address}
            </h3>
            <Badge tone={compat}>{COMPATIBILITY_LABELS[d.compatibility]}</Badge>
            <Badge tone={st} dot>{STATUS_LABELS[d.status]}</Badge>
          </div>
          <div className="mt-1 text-xs text-ink-muted flex flex-wrap items-center gap-2">
            <span className="font-mono">{d.ip_address || "—"}</span>
            <span aria-hidden>·</span>
            <span className="font-mono">{d.mac_address}</span>
            {d.vendor && (
              <>
                <span aria-hidden>·</span>
                <span>{d.vendor} {d.model || ""}</span>
              </>
            )}
          </div>
        </button>
        <ChevronRight size={16} className="text-ink-muted shrink-0 mt-1" />
      </div>

      <div className="mt-3 flex flex-wrap items-center gap-2 text-[11px]">
        {(d.protocols ?? []).slice(0, 4).map((p) => (
          <span key={p} className="uppercase font-mono bg-ink/5 text-ink-muted px-1.5 py-0.5 rounded">
            {p}
          </span>
        ))}
        {d.ports?.length > 0 && (
          <span className="text-ink-muted">Ports : {d.ports.slice(0, 4).join(", ")}</span>
        )}
      </div>

      <div className="mt-2 text-[11px] text-ink-muted">
        Détecté {fmtRelative(d.first_seen_at)} · Vu {fmtRelative(d.last_seen_at)}
        {d.gateway_label ? ` · via ${d.gateway_label}` : ""}
      </div>

      <div className="mt-3 flex flex-wrap items-center gap-2">
        <Button size="sm" variant="dark" leftIcon={<Zap size={12} />} onClick={onAdopt}>
          Adopter
        </Button>
        <Button size="sm" variant="secondary" leftIcon={<PlayCircle size={12} />} onClick={onTest}>
          Tester
        </Button>
        <Button size="sm" variant="ghost" leftIcon={<X size={12} />} onClick={onReject}>
          Rejeter
        </Button>
      </div>
    </div>
  );
}

// ═══════════════════════════════════════════════════════════════
// Modals : détail + reject + adopt
// ═══════════════════════════════════════════════════════════════
function DiscoveryDetailModal({
  d, onClose, onAdopt, onReject,
}: {
  d: DiscoveryDTO; onClose: () => void;
  onAdopt: () => void; onReject: () => void;
}) {
  return (
    <Modal open onClose={onClose} title={d.hostname || d.vendor || d.mac_address} size="lg">
      <div className="grid grid-cols-1 md:grid-cols-2 gap-3 text-sm">
        <Info k="MAC" v={<code className="font-mono">{d.mac_address}</code>} />
        <Info k="IP" v={<code className="font-mono">{d.ip_address || "—"}</code>} />
        <Info k="Hostname" v={d.hostname || "—"} />
        <Info k="Vendor / Model" v={`${d.vendor || "?"} / ${d.model || "?"}`} />
        <Info k="Firmware" v={d.firmware_version || "—"} />
        <Info k="Type" v={d.device_type_label || d.device_type || "—"} />
        <Info k="Détecté via" v={d.detected_via || "—"} />
        <Info k="Compatibilité" v={<Badge tone={COMPATIBILITY_TONES[d.compatibility]}>{COMPATIBILITY_LABELS[d.compatibility]}</Badge>} />
        <Info k="Gateway" v={d.gateway_label || "—"} />
        <Info k="Site" v={d.site_label || "—"} />
        <Info k="Latence (ms)" v={d.latency_ms ?? "—"} />
        <Info k="Dernier test" v={
          d.last_test_at ? (
            <span className={d.last_test_success ? "text-ok" : "text-danger"}>
              {fmtRelative(d.last_test_at)} — {d.last_test_success ? "OK" : d.last_test_error || "échec"}
            </span>
          ) : "—"
        } />
      </div>

      {d.raw_payload && (
        <details className="mt-4">
          <summary className="text-xs text-ink-muted cursor-pointer">Raw payload</summary>
          <pre className="mt-2 max-h-64 overflow-auto rounded-xl bg-obsidian text-white/90 p-3 text-[11px] font-mono">
            {JSON.stringify(d.raw_payload, null, 2)}
          </pre>
        </details>
      )}

      <div className="mt-6 flex flex-wrap items-center gap-2">
        <Button variant="dark" leftIcon={<Zap size={14} />} onClick={onAdopt}>Adopter</Button>
        <Button variant="ghost" leftIcon={<X size={14} />} onClick={onReject}>Rejeter</Button>
      </div>
    </Modal>
  );
}

function Info({ k, v }: { k: string; v: React.ReactNode }) {
  return (
    <div className="rounded-xl bg-surface-soft/60 p-2.5">
      <div className="text-[11px] text-ink-muted uppercase tracking-wide">{k}</div>
      <div className="text-sm text-ink mt-0.5 truncate">{v}</div>
    </div>
  );
}

function RejectModal({
  d, onClose, onDone,
}: { d: DiscoveryDTO; onClose: () => void; onDone: () => void }) {
  const [reason, setReason] = useState("");
  const mut = useMutation({
    mutationFn: () => discoveryService.reject(d.id, reason || undefined),
    onSuccess: () => { toast.success("Équipement rejeté"); onDone(); },
    onError: (e: any) => toast.error(e?.response?.data?.error || "Erreur"),
  });
  return (
    <Modal open onClose={onClose} title="Rejeter cet équipement" size="sm">
      <p className="text-sm text-ink-muted mb-3">
        Motif optionnel — utile pour l'audit et la reprise ultérieure.
      </p>
      <Input
        value={reason}
        onChange={(e) => setReason(e.target.value)}
        placeholder="Ex: doublon, hors périmètre, modèle non homologué…"
      />
      <div className="mt-4 flex items-center gap-2 justify-end">
        <Button variant="ghost" onClick={onClose}>Annuler</Button>
        <Button variant="danger" loading={mut.isPending} onClick={() => mut.mutate()}>
          Rejeter
        </Button>
      </div>
    </Modal>
  );
}

function AdoptModal({
  d, onClose, onDone,
}: { d: DiscoveryDTO; onClose: () => void; onDone: () => void }) {
  const [name, setName] = useState(d.hostname || `${d.vendor} ${d.model}`.trim() || d.mac_address);
  const [siteId, setSiteId] = useState<number | "">(d.site_id ?? "");
  const [driver, setDriver] = useState<string>("");

  const { data: sites } = useQuery({
    queryKey: ["sites", "for-discovery"],
    queryFn: async () => (await sitesService.list({ page_size: 200 })).data,
  });

  const mut = useMutation({
    mutationFn: () =>
      discoveryService.adopt(d.id, {
        name,
        site_id: siteId ? Number(siteId) : undefined,
        driver: driver || undefined,
      }),
    onSuccess: (r) => {
      toast.success(`Équipement adopté — device #${r.data?.device_id}`);
      onDone();
    },
    onError: (e: any) => toast.error(e?.response?.data?.error || "Erreur"),
  });

  return (
    <Modal open onClose={onClose} title="Adopter — créer un Device" size="md">
      <div className="space-y-3">
        <div>
          <label className="text-xs text-ink-muted uppercase tracking-wide">Nom</label>
          <Input value={name} onChange={(e) => setName(e.target.value)} />
        </div>
        <div>
          <label className="text-xs text-ink-muted uppercase tracking-wide">Site</label>
          <select
            value={siteId}
            onChange={(e) => setSiteId(e.target.value ? Number(e.target.value) : "")}
            className="mt-1 w-full rounded-xl border border-surface-border bg-surface-card px-3 py-2 text-sm text-ink"
          >
            <option value="">— aucun —</option>
            {sites?.results?.map((s: any) => (
              <option key={s.id} value={s.id}>{s.label || s.name}</option>
            ))}
          </select>
        </div>
        <div>
          <label className="text-xs text-ink-muted uppercase tracking-wide">
            Driver (override, optionnel)
          </label>
          <Input
            value={driver}
            onChange={(e) => setDriver(e.target.value)}
            placeholder="hikvision, zkteco, suprema, …"
          />
        </div>
        <div className="text-xs text-ink-muted">
          Signature détectée : <code className="font-mono">{d.vendor} / {d.detected_via}</code>.
          Laisse vide pour utiliser le driver auto-sélectionné.
        </div>
      </div>

      <div className="mt-5 flex items-center gap-2 justify-end">
        <Button variant="ghost" onClick={onClose}>Annuler</Button>
        <Button variant="dark" leftIcon={<Zap size={14} />} loading={mut.isPending} onClick={() => mut.mutate()}>
          Adopter et créer
        </Button>
      </div>
    </Modal>
  );
}

export default DevicesDiscoveryPage;
