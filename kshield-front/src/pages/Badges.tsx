import { useState, useMemo, useRef, useEffect } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import Papa from "papaparse";
import { PageHeader } from "@/components/PageHeader";
import { Card } from "@/components/ui/Card";
import { DataTable, Column } from "@/components/ui/DataTable";
import { Badge as UIBadge } from "@/components/ui/Badge";
import { Input } from "@/components/ui/Input";
import { Button } from "@/components/ui/Button";
import { Modal } from "@/components/ui/Modal";
import { StatsRow } from "@/components/StatsRow";
import { LivePulse } from "@/components/LivePulse";
import {
  badgesService, workersService, employeesService, sitesService, zonesService,
  devicesService,
} from "@/services";
import { toApiError } from "@/lib/api";
import { parseApiErrors, omitEmpty, FieldErrors } from "@/lib/formErrors";
import { FormErrorBanner } from "@/components/FormErrorBanner";
import { RFIDEnrollmentModal } from "@/components/RFIDEnrollmentModal";
import { BadgeEnrollmentWizard } from "@/components/badges/BadgeEnrollmentWizard";
import { fmtDate, fmtRelative, initials } from "@/lib/format";
import { cn } from "@/lib/cn";
import {
  Search, CreditCard, Ban, PauseCircle, PlayCircle, ShieldCheck,
  ShieldOff, AlertTriangle, Plus, Upload, Edit3, Trash2, LayoutGrid,
  List as ListIcon, LinkIcon, Unlink, Zap, Filter, Radar, X, CheckCircle2,
  Download, MapPin, User as UserIcon, Wifi, WifiOff, Trash, RefreshCw,
} from "lucide-react";
import toast from "react-hot-toast";

type Mode = "grid" | "list";
type EnrollMode = "manual" | "live" | "csv";

export function BadgesPage() {
  const [mode, setMode] = useState<Mode>("list");
  const [q, setQ] = useState("");
  const [statusFilter, setStatusFilter] = useState("");
  const [techFilter, setTechFilter] = useState("");
  const [siteFilter, setSiteFilter] = useState<number | "">("");
  const [associatedFilter, setAssociatedFilter] = useState("");
  const [expiryFilter, setExpiryFilter] = useState("");
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [page, setPage] = useState(1);
  const [enrollOpen, setEnrollOpen] = useState(false);
  const [bulkOpen, setBulkOpen] = useState(false);
  const [liveEnrollOpen, setLiveEnrollOpen] = useState(false);
  const [wizardOpen, setWizardOpen] = useState(false);
  const [editBadge, setEditBadge] = useState<any | null>(null);
  const [assocBadge, setAssocBadge] = useState<any | null>(null);
  const qc = useQueryClient();
  const pageSize = 30;

  // ─── Data ─────────────────────────────
  const listParams = {
    page_size: pageSize, page,
    search: q || undefined,
    status: statusFilter || undefined,
    tech: techFilter || undefined,
    site: siteFilter || undefined,
    associated: associatedFilter || undefined,
    expiry: expiryFilter || undefined,
  };
  const { data, isLoading } = useQuery({
    queryKey: ["badges", listParams],
    queryFn: async () => (await badgesService.list(listParams)).data,
  });

  const { data: allBadges } = useQuery({
    queryKey: ["badges", "all-stats"],
    queryFn: async () => (await badgesService.list({ page_size: 1000 })).data,
    staleTime: 60_000,
  });

  const stats = useMemo(() => {
    const list = allBadges?.results || [];
    const now = Date.now();
    const expiringSoon = list.filter((b: any) =>
      b.valid_until && new Date(b.valid_until).getTime() - now < 30 * 86400_000
    ).length;
    return {
      total: allBadges?.count || 0,
      active: list.filter((b: any) => b.status === "active").length,
      unassociated: list.filter((b: any) => !b.holder_object_id).length,
      suspended: list.filter((b: any) => b.status === "suspended").length,
      revoked: list.filter((b: any) => b.status === "revoked").length,
      lost: list.filter((b: any) => b.status === "lost").length,
      expiringSoon,
    };
  }, [allBadges]);

  const { data: sites } = useQuery({
    queryKey: ["sites", "for-badges"],
    queryFn: async () => (await sitesService.list({ page_size: 200 })).data,
  });

  // ─── Mutations ─────────────────────────
  const suspendMut = useMutation({
    mutationFn: (id: number) => badgesService.suspend(id),
    onSuccess: () => { toast.success("Badge suspendu"); qc.invalidateQueries({ queryKey: ["badges"] }); },
    onError: (e) => toast.error(toApiError(e).message),
  });
  const revokeMut = useMutation({
    mutationFn: (id: number) => badgesService.revoke(id),
    onSuccess: () => { toast.success("Badge révoqué"); qc.invalidateQueries({ queryKey: ["badges"] }); },
    onError: (e) => toast.error(toApiError(e).message),
  });
  const reactivateMut = useMutation({
    mutationFn: (id: number) => badgesService.reactivate(id),
    onSuccess: () => { toast.success("Badge réactivé"); qc.invalidateQueries({ queryKey: ["badges"] }); },
    onError: (e) => toast.error(toApiError(e).message),
  });
  const deleteMut = useMutation({
    mutationFn: (id: number) => badgesService.remove(id),
    onSuccess: () => { toast.success("Supprimé"); qc.invalidateQueries({ queryKey: ["badges"] }); },
    onError: (e) => toast.error(toApiError(e).message),
  });

  const resetFilters = () => {
    setQ(""); setStatusFilter(""); setTechFilter(""); setSiteFilter("");
    setAssociatedFilter(""); setExpiryFilter(""); setPage(1);
  };

  // ─── Colonnes tableau ─────────────────────
  const columns: Column<any>[] = [
    { key: "uid", header: "UID Badge", render: (b) => (
      <div className="flex items-center gap-2">
        <div className={cn("w-8 h-8 rounded-lg grid place-items-center",
          b.status === "active" ? "bg-brand-500/10 text-brand-400" : "bg-white/5 text-ink-muted"
        )}>
          <CreditCard className="w-4 h-4" />
        </div>
        <code className="text-xs font-mono">{b.uid}</code>
      </div>
    )},
    { key: "tech", header: "Techno", render: (b) => (
      <UIBadge tone={
        b.tech === "nfc" ? "info" : b.tech === "uhf" ? "brand" :
        b.tech === "qr" ? "warn" : "muted"
      }>{(b.tech || b.type || "?").toUpperCase()}</UIBadge>
    )},
    { key: "holder", header: "Porteur", render: (b) => (
      b.holder_name ? (
        <div className="flex items-center gap-1.5 text-xs">
          <UserIcon className="w-3 h-3 text-ink-soft" />
          <span>{b.holder_name}</span>
          {b.holder_kind && <UIBadge tone="muted">{b.holder_kind}</UIBadge>}
        </div>
      ) : <span className="text-ink-soft text-xs">Non associé</span>
    )},
    { key: "site", header: "Site", render: (b) =>
      typeof b.site === "object" ? b.site?.name :
      <span className="text-ink-soft text-xs">—</span>
    },
    { key: "status", header: "Statut", render: (b) => (
      <UIBadge tone={
        b.status === "active" ? "ok" :
        b.status === "suspended" ? "warn" :
        b.status === "revoked" ? "danger" : "muted"
      } dot>{b.status || "—"}</UIBadge>
    )},
    { key: "issued", header: "Émis", render: (b) => (
      <span className="text-xs">{fmtDate(b.issued_at)}</span>
    )},
    { key: "expiry", header: "Expire", render: (b) => {
      if (!b.valid_until) return <span className="text-ink-soft text-xs">—</span>;
      const days = Math.floor((new Date(b.valid_until).getTime() - Date.now()) / 86400000);
      return (
        <UIBadge tone={days < 0 ? "danger" : days < 30 ? "warn" : "ok"}>
          {days < 0 ? "Expiré" : `${days}j`}
        </UIBadge>
      );
    }},
    { key: "actions", header: "", className: "text-right whitespace-nowrap", render: (b) => (
      <div className="inline-flex gap-0.5">
        {!b.holder_object_id && (
          <button onClick={(e) => { e.stopPropagation(); setAssocBadge(b); }}
                  className="p-1.5 rounded-md hover:bg-info/10 text-ink-muted hover:text-info"
                  title="Associer">
            <LinkIcon className="w-3.5 h-3.5" />
          </button>
        )}
        {b.status === "active" && (
          <button onClick={(e) => { e.stopPropagation(); suspendMut.mutate(b.id); }}
                  className="p-1.5 rounded-md hover:bg-warn/10 text-ink-muted hover:text-warn"
                  title="Suspendre">
            <PauseCircle className="w-3.5 h-3.5" />
          </button>
        )}
        {b.status === "suspended" && (
          <button onClick={(e) => { e.stopPropagation(); reactivateMut.mutate(b.id); }}
                  className="p-1.5 rounded-md hover:bg-ok/10 text-ink-muted hover:text-ok"
                  title="Réactiver">
            <PlayCircle className="w-3.5 h-3.5" />
          </button>
        )}
        <button onClick={(e) => { e.stopPropagation(); setEditBadge(b); }}
                className="p-1.5 rounded-md hover:bg-surface-soft text-ink-muted hover:text-ink"
                title="Modifier">
          <Edit3 className="w-3.5 h-3.5" />
        </button>
        {b.status !== "revoked" && (
          <button onClick={(e) => {
            e.stopPropagation();
            if (confirm(`Révoquer définitivement ${b.uid} ?`)) revokeMut.mutate(b.id);
          }} className="p-1.5 rounded-md hover:bg-danger/10 text-ink-muted hover:text-danger"
             title="Révoquer">
            <Ban className="w-3.5 h-3.5" />
          </button>
        )}
      </div>
    )},
  ];

  return (
    <div>
      <PageHeader
        title="Badges RFID / NFC / QR"
        subtitle={`${data?.count ?? 0} badges affichés — ${stats.total} au total`}
        actions={
          <div className="flex items-center gap-2">
            <Button variant="ghost" leftIcon={<Upload className="w-4 h-4" />}
                    onClick={() => setBulkOpen(true)}>
              Enrôlement multiple
            </Button>
            <Button variant="secondary" leftIcon={<Zap className="w-4 h-4" />}
                    onClick={() => setLiveEnrollOpen(true)}>
              Enrôlement temps réel
            </Button>
            <Button variant="dark" leftIcon={<ShieldCheck className="w-4 h-4" />}
                    onClick={() => setWizardOpen(true)}>
              Assistant enrôlement
            </Button>
            <Button leftIcon={<Plus className="w-4 h-4" />} onClick={() => setEnrollOpen(true)}>
              Nouveau badge
            </Button>
          </div>
        }
      />

      {/* Stats */}
      <StatsRow stats={[
        { label: "Total badges", value: stats.total, icon: <CreditCard className="w-4 h-4" />, tone: "brand" },
        { label: "Actifs", value: stats.active, icon: <ShieldCheck className="w-4 h-4" />, tone: "ok",
          onClick: () => setStatusFilter("active") },
        { label: "Non associés", value: stats.unassociated, icon: <Unlink className="w-4 h-4" />, tone: "warn",
          onClick: () => setAssociatedFilter("false") },
        { label: "Suspendus", value: stats.suspended, icon: <PauseCircle className="w-4 h-4" />, tone: "warn",
          onClick: () => setStatusFilter("suspended") },
        { label: "Révoqués", value: stats.revoked, icon: <ShieldOff className="w-4 h-4" />, tone: "danger",
          onClick: () => setStatusFilter("revoked") },
        { label: "Expire <30j", value: stats.expiringSoon, icon: <AlertTriangle className="w-4 h-4" />, tone: "danger",
          onClick: () => setExpiryFilter("soon") },
      ]} />

      {/* Toolbar mode + filtres */}
      <Card padded={false}>
        <div className="p-4 border-b border-surface-border space-y-3">
          <div className="flex flex-col sm:flex-row gap-2">
            <div className="flex-1">
              <Input placeholder="UID, porteur, site…" leftIcon={<Search className="w-4 h-4" />}
                     value={q} onChange={(e) => { setQ(e.target.value); setPage(1); }} />
            </div>
            <select value={techFilter} onChange={(e) => { setTechFilter(e.target.value); setPage(1); }} className="field sm:w-32">
              <option value="">Tous techs</option>
              <option value="nfc">NFC</option>
              <option value="uhf">UHF</option>
              <option value="qr">QR</option>
              <option value="ble">BLE</option>
            </select>
            <button onClick={() => setShowAdvanced(!showAdvanced)}
                    className="flex items-center gap-1 px-3 rounded-lg border border-surface-border text-xs text-ink-muted hover:text-ink hover:bg-surface-soft">
              <Filter className="w-3.5 h-3.5" /> Filtres {showAdvanced ? "▲" : "▼"}
            </button>
            {/* Mode toggle */}
            <div className="inline-flex rounded-lg bg-surface-soft p-0.5 border border-surface-border">
              <button onClick={() => setMode("list")}
                      className={cn("flex items-center gap-1 px-2.5 py-1.5 rounded text-xs",
                        mode === "list" ? "bg-brand-500 text-white" : "text-ink-muted")}
                      title="Vue liste">
                <ListIcon className="w-3.5 h-3.5" /> Liste
              </button>
              <button onClick={() => setMode("grid")}
                      className={cn("flex items-center gap-1 px-2.5 py-1.5 rounded text-xs",
                        mode === "grid" ? "bg-brand-500 text-white" : "text-ink-muted")}
                      title="Vue miniature">
                <LayoutGrid className="w-3.5 h-3.5" /> Grille
              </button>
            </div>
          </div>

          {showAdvanced && (
            <div className="grid grid-cols-2 sm:grid-cols-4 gap-2 pt-2 border-t border-surface-border/60">
              <select value={statusFilter} onChange={(e) => { setStatusFilter(e.target.value); setPage(1); }} className="field">
                <option value="">Tous statuts</option>
                <option value="active">Actifs</option>
                <option value="suspended">Suspendus</option>
                <option value="revoked">Révoqués</option>
                <option value="lost">Perdus</option>
                <option value="expired">Expirés</option>
              </select>
              <select value={siteFilter} onChange={(e) => { setSiteFilter(e.target.value ? Number(e.target.value) : ""); setPage(1); }} className="field">
                <option value="">Tous sites</option>
                {sites?.results?.map((s: any) => <option key={s.id} value={s.id}>{s.name}</option>)}
              </select>
              <select value={associatedFilter} onChange={(e) => { setAssociatedFilter(e.target.value); setPage(1); }} className="field">
                <option value="">Tous</option>
                <option value="true">Associés</option>
                <option value="false">Non associés</option>
              </select>
              <select value={expiryFilter} onChange={(e) => { setExpiryFilter(e.target.value); setPage(1); }} className="field">
                <option value="">Expiration</option>
                <option value="soon">Expire dans 30j</option>
                <option value="expired">Expirés</option>
              </select>
              <button onClick={resetFilters}
                      className="col-span-full sm:col-span-1 h-10 rounded-lg border border-surface-border text-xs hover:bg-surface-soft">
                Réinitialiser
              </button>
            </div>
          )}
        </div>

        {mode === "list" ? (
          <DataTable
            columns={columns} rows={data?.results || []} loading={isLoading}
            rowKey={(b) => b.id}
            emptyLabel="Aucun badge trouvé"
            pagination={{ count: data?.count ?? 0, pageSize, page, onPageChange: setPage }}
          />
        ) : (
          <BadgeGrid badges={data?.results || []} onEdit={setEditBadge} onAssoc={setAssocBadge}
                     onSuspend={(id) => suspendMut.mutate(id)}
                     onReactivate={(id) => reactivateMut.mutate(id)}
                     onRevoke={(id) => revokeMut.mutate(id)} />
        )}
      </Card>

      {/* Modales */}
      <BadgeEnrollModal open={enrollOpen} onClose={() => setEnrollOpen(false)} />
      <BadgeBulkEnrollModal open={bulkOpen} onClose={() => setBulkOpen(false)} />
      <RFIDEnrollmentModal
        open={liveEnrollOpen}
        onClose={() => setLiveEnrollOpen(false)}
        mode="single"
      />
      <BadgeEditModal badge={editBadge} onClose={() => setEditBadge(null)} />
      <BadgeAssocModal badge={assocBadge} onClose={() => setAssocBadge(null)} />
      <BadgeEnrollmentWizard
        open={wizardOpen}
        onClose={() => setWizardOpen(false)}
        onDone={() => qc.invalidateQueries({ queryKey: ["badges"] })}
      />
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────
// Vue grille miniature
// ─────────────────────────────────────────────────────────────────
function BadgeGrid({ badges, onEdit, onAssoc, onSuspend, onReactivate, onRevoke }: {
  badges: any[]; onEdit: (b: any) => void; onAssoc: (b: any) => void;
  onSuspend: (id: number) => void; onReactivate: (id: number) => void; onRevoke: (id: number) => void;
}) {
  if (badges.length === 0) {
    return <div className="p-8 text-center text-ink-muted text-sm">Aucun badge à afficher</div>;
  }
  return (
    <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4 gap-3 p-4">
      {badges.map((b) => {
        const active = b.status === "active";
        const expired = b.valid_until && new Date(b.valid_until).getTime() < Date.now();
        return (
          <div key={b.id}
               className="rounded-2xl border border-surface-border bg-surface-card/60 p-4 hover:border-brand-500/40 transition">
            <div className="flex items-start justify-between mb-3">
              <div className={cn("w-10 h-10 rounded-xl grid place-items-center",
                active ? "bg-brand-500/10 text-brand-400" :
                b.status === "revoked" ? "bg-danger/10 text-danger" : "bg-white/5 text-ink-muted"
              )}>
                <CreditCard className="w-5 h-5" />
              </div>
              <UIBadge tone={
                b.status === "active" ? "ok" :
                b.status === "suspended" ? "warn" :
                b.status === "revoked" ? "danger" : "muted"
              } dot>{b.status || "—"}</UIBadge>
            </div>

            <code className="text-sm font-mono text-ink block truncate">{b.uid}</code>
            <div className="text-[10px] text-ink-soft mt-0.5">
              {(b.tech || b.type || "?").toUpperCase()}
              {expired && <span className="text-danger ml-2">• EXPIRÉ</span>}
            </div>

            <div className="mt-3 pt-3 border-t border-surface-border/60 space-y-1.5 text-xs">
              {b.holder_name ? (
                <div className="flex items-center gap-1">
                  <UserIcon className="w-3 h-3 text-ink-soft" />
                  <span className="text-ink truncate">{b.holder_name}</span>
                </div>
              ) : (
                <div className="text-warn">⚠ Non associé</div>
              )}
              {typeof b.site === "object" && b.site?.name && (
                <div className="flex items-center gap-1 text-ink-muted">
                  <MapPin className="w-3 h-3" />
                  <span className="truncate">{b.site.name}</span>
                </div>
              )}
              <div className="text-ink-soft">
                Émis {fmtDate(b.issued_at)}
                {b.last_scan_at && (<> · Utilisé {fmtRelative(b.last_scan_at)}</>)}
              </div>
            </div>

            <div className="mt-3 flex gap-1 justify-end">
              {!b.holder_object_id && (
                <button onClick={() => onAssoc(b)} title="Associer"
                        className="p-1.5 rounded hover:bg-info/10 text-ink-muted hover:text-info">
                  <LinkIcon className="w-3.5 h-3.5" />
                </button>
              )}
              {b.status === "active" && (
                <button onClick={() => onSuspend(b.id)} title="Suspendre"
                        className="p-1.5 rounded hover:bg-warn/10 text-ink-muted hover:text-warn">
                  <PauseCircle className="w-3.5 h-3.5" />
                </button>
              )}
              {b.status === "suspended" && (
                <button onClick={() => onReactivate(b.id)} title="Réactiver"
                        className="p-1.5 rounded hover:bg-ok/10 text-ink-muted hover:text-ok">
                  <PlayCircle className="w-3.5 h-3.5" />
                </button>
              )}
              <button onClick={() => onEdit(b)} title="Modifier"
                      className="p-1.5 rounded hover:bg-surface-soft text-ink-muted hover:text-ink">
                <Edit3 className="w-3.5 h-3.5" />
              </button>
              {b.status !== "revoked" && (
                <button onClick={() => confirm(`Révoquer ${b.uid} ?`) && onRevoke(b.id)}
                        title="Révoquer"
                        className="p-1.5 rounded hover:bg-danger/10 text-ink-muted hover:text-danger">
                  <Ban className="w-3.5 h-3.5" />
                </button>
              )}
            </div>
          </div>
        );
      })}
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────
// Panneau "mode live" — lecteurs disponibles + statut + dernier scan
// ─────────────────────────────────────────────────────────────────
function LiveReaderPanel({
  readers, selectedReaderId, onSelect, inbox, inboxFetching, dataUpdatedAt,
  scansReceived, lastScan, onClearInbox, clearing,
}: {
  readers: any[];
  selectedReaderId: number | "all";
  onSelect: (id: number | "all") => void;
  inbox: any;
  inboxFetching: boolean;
  dataUpdatedAt: number;
  scansReceived: number;
  lastScan: any | null;
  onClearInbox: () => void;
  clearing: boolean;
}) {
  const now = Date.now();
  // Un lecteur est "en ligne" si heartbeat < 90s
  const isOnline = (r: any) => {
    const hb = r.last_heartbeat_at;
    if (!hb) return false;
    return now - new Date(hb).getTime() < 90_000;
  };
  const onlineCount = readers.filter(isOnline).length;
  const scanQueued = inbox?.count ?? 0;
  const readersCount = inbox?.readers_count ?? readers.length;
  const lastPoll = dataUpdatedAt ? Math.round((now - dataUpdatedAt) / 1000) : null;

  return (
    <div className="space-y-3">
      {/* Bandeau statut global */}
      <div className={cn(
        "p-3 rounded-lg border text-sm",
        readers.length === 0
          ? "bg-warning/5 border-warning/30 text-warning"
          : onlineCount === 0
          ? "bg-danger/5 border-danger/30 text-danger"
          : "bg-info/5 border-info/20 text-ink",
      )}>
        <div className="flex items-start gap-2">
          <Radar className={cn("w-4 h-4 shrink-0 mt-0.5",
            onlineCount > 0 ? "text-info animate-pulse" : "text-danger")} />
          <div className="flex-1">
            {readers.length === 0 ? (
              <>
                <strong>Aucun lecteur RFID enregistré.</strong>{" "}
                Ajoute d'abord un lecteur dans <em>Équipements</em>, puis relance l'enrôlement.
              </>
            ) : onlineCount === 0 ? (
              <>
                <strong>{readers.length} lecteur{readers.length > 1 ? "s" : ""} enregistré{readers.length > 1 ? "s" : ""}, mais aucun en ligne.</strong>{" "}
                Vérifie que le lecteur pousse un heartbeat ou est joignable en réseau.
              </>
            ) : (
              <>
                <strong>{onlineCount}/{readers.length} lecteur{readers.length > 1 ? "s" : ""} en ligne.</strong>{" "}
                Scanne un badge — l'UID sera capturé automatiquement (poll 1.5s).
              </>
            )}
          </div>
        </div>
      </div>

      {/* Sélecteur de lecteur */}
      {readers.length > 0 && (
        <div>
          <div className="flex items-center justify-between mb-1.5">
            <span className="text-xs font-medium text-ink-muted">
              Écoute sur
            </span>
            <button
              type="button"
              onClick={onClearInbox}
              disabled={clearing || scanQueued === 0}
              className="text-xs text-ink-muted hover:text-danger disabled:opacity-40 flex items-center gap-1"
              title="Vider l'inbox des scans reçus"
            >
              <Trash className="w-3 h-3" />
              Vider l'inbox ({scanQueued})
            </button>
          </div>
          <div className="flex flex-wrap gap-1.5">
            <button
              type="button"
              onClick={() => onSelect("all")}
              className={cn(
                "px-2.5 py-1.5 rounded-md text-xs border transition",
                selectedReaderId === "all"
                  ? "border-brand-500 bg-brand-500/10 text-brand-700"
                  : "border-surface-border hover:bg-surface-soft",
              )}
            >
              Tous les lecteurs
              <span className="ml-1 text-ink-muted">({onlineCount} en ligne)</span>
            </button>
            {readers.map((r) => {
              const online = isOnline(r);
              return (
                <button
                  key={r.id}
                  type="button"
                  onClick={() => onSelect(r.id)}
                  className={cn(
                    "px-2.5 py-1.5 rounded-md text-xs border transition flex items-center gap-1.5",
                    selectedReaderId === r.id
                      ? "border-brand-500 bg-brand-500/10 text-brand-700"
                      : "border-surface-border hover:bg-surface-soft",
                  )}
                  title={`Serial ${r.serial_number} · IP ${r.ip_address || "?"}`}
                >
                  {online ? (
                    <Wifi className="w-3 h-3 text-success" />
                  ) : (
                    <WifiOff className="w-3 h-3 text-ink-muted" />
                  )}
                  <span className="font-medium">
                    {r.model?.brand} {r.model?.model || r.serial_number}
                  </span>
                  {r.ip_address && (
                    <span className="text-ink-muted font-mono">{r.ip_address}</span>
                  )}
                </button>
              );
            })}
          </div>
        </div>
      )}

      {/* Zone activité temps réel */}
      <div className="grid grid-cols-3 gap-2 text-center">
        <div className="p-2 rounded-md bg-surface-soft border border-surface-border">
          <div className="text-xs text-ink-muted">Scans reçus</div>
          <div className="text-lg font-bold text-ink">{scansReceived}</div>
        </div>
        <div className="p-2 rounded-md bg-surface-soft border border-surface-border">
          <div className="text-xs text-ink-muted">Lecteurs actifs</div>
          <div className="text-lg font-bold text-ink">
            {selectedReaderId === "all" ? readersCount : 1}
          </div>
        </div>
        <div className="p-2 rounded-md bg-surface-soft border border-surface-border">
          <div className="text-xs text-ink-muted flex items-center justify-center gap-1">
            <RefreshCw className={cn("w-3 h-3",
              inboxFetching && "animate-spin text-info")} />
            Poll
          </div>
          <div className="text-lg font-bold text-ink">
            {lastPoll !== null ? `${lastPoll}s` : "—"}
          </div>
        </div>
      </div>

      {/* Dernier scan */}
      {lastScan && (
        <div className="p-2.5 rounded-md bg-success/5 border border-success/20 text-xs">
          <div className="flex items-center gap-2 text-success mb-1">
            <CheckCircle2 className="w-3.5 h-3.5" />
            <strong>Dernier scan reçu</strong>
            {lastScan.timestamp && (
              <span className="ml-auto text-ink-muted">
                {fmtRelative(lastScan.timestamp)}
              </span>
            )}
          </div>
          <div className="font-mono text-ink">{lastScan.uid}</div>
          {(lastScan.device_serial || lastScan.device_id) && (
            <div className="mt-1 text-ink-muted flex items-center gap-1">
              <Radar className="w-3 h-3" />
              via {lastScan.device_serial || `Device #${lastScan.device_id}`}
              {typeof lastScan.rssi === "number" && (
                <span className="ml-2">RSSI {lastScan.rssi} dBm</span>
              )}
            </div>
          )}
        </div>
      )}

      {/* État "en attente" quand aucun scan */}
      {scansReceived === 0 && readers.length > 0 && onlineCount > 0 && (
        <div className="p-3 text-center border border-dashed border-surface-border rounded-md text-xs text-ink-muted">
          <Radar className="w-5 h-5 mx-auto mb-1 text-info animate-pulse" />
          En attente d'un scan… passe un badge devant le lecteur.
        </div>
      )}
    </div>
  );
}

// ─────────────────────────────────────────────────────────────────
// Modal enrôlement unitaire (manuel OU depuis lecteur live)
// ─────────────────────────────────────────────────────────────────
function BadgeEnrollModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [enrollMode, setEnrollMode] = useState<"manual" | "live">("manual");
  const [selectedReaderId, setSelectedReaderId] = useState<number | "all">("all");
  const [form, setForm] = useState({
    uid: "", tech: "nfc", status: "active",
    holder_kind: "", holder_id: "" as any,
    site: "" as any, valid_until: "",
  });
  const [fieldErrors, setFieldErrors] = useState<FieldErrors>({});
  const [duplicate, setDuplicate] = useState<any | null>(null);
  const [scansReceived, setScansReceived] = useState(0);
  const [lastScan, setLastScan] = useState<any | null>(null);
  const seenUids = useRef<Set<string>>(new Set());
  const qc = useQueryClient();

  // Liste des lecteurs RFID actifs (pour le sélecteur + statut)
  const { data: readersList } = useQuery({
    queryKey: ["rfid-readers"],
    queryFn: async () => {
      const r = await devicesService.list({
        page_size: 100,
        // types RFID/face — le back filtre sur model__type__in
        model__type__in:
          "reader_uhf_fixed,reader_uhf_mobile,reader_nfc_fixed,reader_nfc_mobile,portique,face_terminal",
      });
      return r.data;
    },
    enabled: open && enrollMode === "live",
    refetchInterval: enrollMode === "live" ? 5000 : false,
  });
  const readers: any[] = readersList?.results || [];

  // Polling scan inbox pour mode live — scope au lecteur sélectionné si !== "all"
  const { data: inbox, isFetching: inboxFetching, dataUpdatedAt } = useQuery({
    queryKey: ["badge-scan-inbox", selectedReaderId],
    queryFn: async () => {
      const params = selectedReaderId !== "all"
        ? { reader_id: selectedReaderId }
        : undefined;
      return (await badgesService.scanInbox(params)).data;
    },
    refetchInterval: enrollMode === "live" ? 1500 : false,
    enabled: open && enrollMode === "live",
    retry: false,
  });

  const clearInboxMut = useMutation({
    mutationFn: () => badgesService.clearScanInbox(
      selectedReaderId !== "all" ? { reader_id: selectedReaderId } : undefined,
    ),
    onSuccess: () => {
      toast.success("Inbox de scans vidée");
      seenUids.current.clear();
      setScansReceived(0);
      setLastScan(null);
      qc.invalidateQueries({ queryKey: ["badge-scan-inbox"] });
    },
  });

  // Capture live : dès qu'un nouveau scan arrive, remplit form.uid
  useEffect(() => {
    if (enrollMode !== "live" || !inbox?.scans) return;
    const scans = Array.isArray(inbox.scans) ? inbox.scans : [];
    let picked = false;
    for (const s of scans) {
      const uid = s.uid || s.badge_uid;
      if (uid && !seenUids.current.has(uid)) {
        seenUids.current.add(uid);
        setScansReceived((n) => n + 1);
        setLastScan(s);
        if (!picked) {
          setForm((f) => ({ ...f, uid, tech: s.tech || f.tech }));
          toast.success(`Badge détecté : ${uid}`);
          picked = true;
        }
      }
    }
  }, [inbox, enrollMode]);

  // Reset compteurs quand on change de lecteur ou de mode
  useEffect(() => {
    seenUids.current.clear();
    setScansReceived(0);
    setLastScan(null);
  }, [selectedReaderId, enrollMode]);

  // Vérif duplicate quand UID change
  useEffect(() => {
    if (!form.uid || form.uid.length < 4) { setDuplicate(null); return; }
    const t = setTimeout(async () => {
      try {
        const r = await badgesService.lookup(form.uid);
        setDuplicate(r.data);
      } catch {
        setDuplicate(null);
      }
    }, 400);
    return () => clearTimeout(t);
  }, [form.uid]);

  const { data: workers } = useQuery({
    queryKey: ["workers", "for-enroll"],
    queryFn: async () => (await workersService.list({ page_size: 200 })).data,
    enabled: open && form.holder_kind === "worker",
  });
  const { data: employees } = useQuery({
    queryKey: ["employees", "for-enroll"],
    queryFn: async () => (await employeesService.list({ page_size: 200 })).data,
    enabled: open && form.holder_kind === "employee",
  });
  const { data: sites } = useQuery({
    queryKey: ["sites", "for-enroll"],
    queryFn: async () => (await sitesService.list({ page_size: 200 })).data,
    enabled: open,
  });

  const submitMut = useMutation({
    mutationFn: () => badgesService.create(omitEmpty({
      ...form,
      site: form.site ? Number(form.site) : undefined,
      holder_object_id: form.holder_id ? Number(form.holder_id) : undefined,
    })),
    onSuccess: () => {
      toast.success("Badge enrôlé");
      qc.invalidateQueries({ queryKey: ["badges"] });
      onClose();
      resetLocal();
    },
    onError: (e) => {
      const p = parseApiErrors(e);
      setFieldErrors(p.fieldErrors);
      toast.error(p.globalMessage);
    },
  });

  const resetLocal = () => {
    setForm({ uid: "", tech: "nfc", status: "active", holder_kind: "", holder_id: "", site: "", valid_until: "" });
    setFieldErrors({}); setDuplicate(null); seenUids.current.clear();
  };

  const onSubmit = () => {
    if (!form.uid) { setFieldErrors({ uid: "UID obligatoire" }); return; }
    if (duplicate?.id) {
      toast.error("Ce badge existe déjà — impossible d'enrôler un doublon.");
      return;
    }
    submitMut.mutate();
  };

  return (
    <Modal open={open} onClose={() => { onClose(); resetLocal(); }} size="lg"
      title="Enrôler un badge"
      footer={<>
        <Button variant="ghost" onClick={() => { onClose(); resetLocal(); }}>Annuler</Button>
        <Button onClick={onSubmit} loading={submitMut.isPending} disabled={!!duplicate?.id}>
          Enrôler le badge
        </Button>
      </>}>
      <div className="space-y-4">
        {/* Toggle mode */}
        <div className="flex gap-2">
          <button onClick={() => setEnrollMode("manual")}
                  className={cn("flex-1 p-3 rounded-lg border text-sm transition",
                    enrollMode === "manual"
                      ? "border-brand-500 bg-brand-500/5"
                      : "border-surface-border hover:bg-surface-soft")}>
            <Edit3 className="w-4 h-4 mx-auto mb-1 text-brand-400" />
            Saisie manuelle
          </button>
          <button onClick={() => setEnrollMode("live")}
                  className={cn("flex-1 p-3 rounded-lg border text-sm transition",
                    enrollMode === "live"
                      ? "border-brand-500 bg-brand-500/5"
                      : "border-surface-border hover:bg-surface-soft")}>
            <Radar className="w-4 h-4 mx-auto mb-1 text-info" />
            Depuis lecteur RFID
            <LivePulse label="LIVE" />
          </button>
        </div>

        {enrollMode === "live" && (
          <LiveReaderPanel
            readers={readers}
            selectedReaderId={selectedReaderId}
            onSelect={setSelectedReaderId}
            inbox={inbox}
            inboxFetching={inboxFetching}
            dataUpdatedAt={dataUpdatedAt}
            scansReceived={scansReceived}
            lastScan={lastScan}
            onClearInbox={() => clearInboxMut.mutate()}
            clearing={clearInboxMut.isPending}
          />
        )}

        <Input label="UID du badge" requiredMark placeholder="04:A1:B2:C3 ou hex"
               value={form.uid} onChange={(e) => setForm({...form, uid: e.target.value})}
               error={fieldErrors.uid}
               className="font-mono" />

        {duplicate?.id && (
          <div className="p-3 rounded-lg bg-danger/10 border border-danger/30 text-xs text-danger flex gap-2">
            <AlertTriangle className="w-4 h-4 shrink-0" />
            <div>
              <strong>Ce badge est déjà enrôlé.</strong> Porteur : {duplicate.holder_name || "—"} · Statut : {duplicate.status}.
              L'enrôlement est bloqué.
            </div>
          </div>
        )}

        <div className="grid grid-cols-2 gap-3">
          <label className="block">
            <span className="text-xs font-medium text-ink-muted">Techno</span>
            <select value={form.tech} onChange={(e) => setForm({...form, tech: e.target.value})} className="field w-full mt-1.5">
              <option value="nfc">NFC (13.56 MHz)</option>
              <option value="uhf">UHF (860-960 MHz)</option>
              <option value="qr">QR code</option>
              <option value="ble">BLE beacon</option>
            </select>
          </label>
          <Input label="Date d'expiration" type="date"
                 value={form.valid_until} onChange={(e) => setForm({...form, valid_until: e.target.value})} />

          <label className="block">
            <span className="text-xs font-medium text-ink-muted">Site</span>
            <select value={form.site} onChange={(e) => setForm({...form, site: e.target.value})} className="field w-full mt-1.5">
              <option value="">— Aucun —</option>
              {sites?.results?.map((s: any) => <option key={s.id} value={s.id}>{s.name}</option>)}
            </select>
          </label>

          <label className="block">
            <span className="text-xs font-medium text-ink-muted">Type de porteur</span>
            <select value={form.holder_kind}
                    onChange={(e) => setForm({...form, holder_kind: e.target.value, holder_id: ""})}
                    className="field w-full mt-1.5">
              <option value="">Aucun (badge en pool)</option>
              <option value="worker">Ouvrier</option>
              <option value="employee">Employé</option>
            </select>
          </label>

          {form.holder_kind && (
            <label className="block col-span-2">
              <span className="text-xs font-medium text-ink-muted">
                Associer à {form.holder_kind === "worker" ? "l'ouvrier" : "l'employé"}
              </span>
              <select value={form.holder_id} onChange={(e) => setForm({...form, holder_id: e.target.value})}
                      className="field w-full mt-1.5">
                <option value="">— Sélectionner —</option>
                {(form.holder_kind === "worker" ? workers : employees)?.results?.map((h: any) => (
                  <option key={h.id} value={h.id}>
                    {h.matricule} — {h.first_name} {h.last_name}
                  </option>
                ))}
              </select>
            </label>
          )}
        </div>
      </div>
    </Modal>
  );
}

// ─────────────────────────────────────────────────────────────────
// Modal enrôlement en masse (batch text + CSV + live capture)
// ─────────────────────────────────────────────────────────────────
function BadgeBulkEnrollModal({ open, onClose }: { open: boolean; onClose: () => void }) {
  const [mode, setMode] = useState<EnrollMode>("manual");
  const [text, setText] = useState("");
  const [tech, setTech] = useState("nfc");
  const [items, setItems] = useState<{ uid: string; status?: "ok" | "duplicate" | "error"; msg?: string }[]>([]);
  const seenUids = useRef<Set<string>>(new Set());
  const fileRef = useRef<HTMLInputElement>(null);
  const qc = useQueryClient();

  const { data: inbox } = useQuery({
    queryKey: ["badge-bulk-inbox"],
    queryFn: async () => (await badgesService.scanInbox()).data,
    refetchInterval: mode === "live" ? 1500 : false,
    enabled: open && mode === "live",
    retry: false,
  });

  useEffect(() => {
    if (mode !== "live" || !inbox?.scans) return;
    const fresh: string[] = [];
    for (const s of (inbox.scans || [])) {
      const uid = s.uid || s.badge_uid;
      if (uid && !seenUids.current.has(uid)) {
        seenUids.current.add(uid);
        fresh.push(uid);
      }
    }
    if (fresh.length > 0) {
      setItems((prev) => [...fresh.map((uid) => ({ uid })), ...prev]);
      toast.success(`${fresh.length} nouveau(x) badge(s) capturé(s)`);
    }
  }, [inbox, mode]);

  const parseBatch = () => {
    const lines = text.split(/\r?\n/).map((l) => l.trim()).filter(Boolean);
    const unique = lines.filter((l) => !seenUids.current.has(l));
    unique.forEach((l) => seenUids.current.add(l));
    setItems((prev) => [...unique.map((uid) => ({ uid })), ...prev]);
    setText("");
    toast.success(`${unique.length} UID ajouté(s)`);
  };

  const parseCsv = (file: File) => {
    Papa.parse(file, {
      header: false, skipEmptyLines: true,
      complete: (r) => {
        const uids = (r.data as any[][])
          .map((row) => (row[0] || "").toString().trim())
          .filter((u) => u && !seenUids.current.has(u));
        uids.forEach((u) => seenUids.current.add(u));
        setItems((prev) => [...uids.map((uid) => ({ uid })), ...prev]);
        toast.success(`${uids.length} UID importé(s) du CSV`);
      },
    });
    if (fileRef.current) fileRef.current.value = "";
  };

  const bulkMut = useMutation({
    mutationFn: () => badgesService.bulkEnroll({
      tech,
      items: items.filter((i) => !i.status).map((i) => ({ uid: i.uid })),
    }),
    onSuccess: (r: any) => {
      const created = r.data?.created_count ?? 0;
      const errors = r.data?.errors || [];
      toast.success(`${created} badge(s) créé(s)`);
      setItems((prev) => prev.map((it) => {
        const err = errors.find((e: any) => e.uid === it.uid);
        if (err) return { ...it, status: "error", msg: err.error };
        if (err === undefined && !it.status) return { ...it, status: "ok" };
        return it;
      }));
      qc.invalidateQueries({ queryKey: ["badges"] });
    },
    onError: (e) => toast.error(toApiError(e).message),
  });

  const removeItem = (uid: string) =>
    setItems((prev) => prev.filter((i) => i.uid !== uid));
  const clear = () => { setItems([]); seenUids.current.clear(); };

  return (
    <Modal open={open} onClose={onClose} size="xl"
      title="Enrôlement multiple de badges"
      footer={<>
        <Button variant="ghost" onClick={onClose}>Fermer</Button>
        <Button onClick={() => bulkMut.mutate()} loading={bulkMut.isPending}
                disabled={items.filter((i) => !i.status).length === 0}
                leftIcon={<Zap className="w-4 h-4" />}>
          Enrôler {items.filter((i) => !i.status).length} badges
        </Button>
      </>}>
      <div className="space-y-4">
        {/* Mode sélecteur */}
        <div className="grid grid-cols-3 gap-2">
          {[
            { k: "manual", l: "Coller UIDs", icon: Edit3 },
            { k: "csv",    l: "Import CSV",  icon: Upload },
            { k: "live",   l: "Live scan",   icon: Radar },
          ].map((m) => (
            <button key={m.k} onClick={() => setMode(m.k as EnrollMode)}
                    className={cn("p-2 rounded-lg border text-xs",
                      mode === m.k ? "border-brand-500 bg-brand-500/5" : "border-surface-border")}>
              <m.icon className="w-4 h-4 mx-auto mb-1" />
              {m.l}
            </button>
          ))}
        </div>

        <div className="flex items-center gap-2">
          <label className="block flex-1">
            <span className="text-xs font-medium text-ink-muted">Techno par défaut</span>
            <select value={tech} onChange={(e) => setTech(e.target.value)} className="field w-full mt-1.5">
              <option value="nfc">NFC</option>
              <option value="uhf">UHF</option>
              <option value="qr">QR</option>
              <option value="ble">BLE</option>
            </select>
          </label>
        </div>

        {mode === "manual" && (
          <div>
            <textarea rows={4} value={text} onChange={(e) => setText(e.target.value)}
                      placeholder="Coller les UIDs, un par ligne&#10;04:A1:B2:C3&#10;04:A1:B2:C4"
                      className="field w-full font-mono text-xs" />
            <div className="mt-2 flex justify-end">
              <Button size="sm" onClick={parseBatch} leftIcon={<Plus className="w-3.5 h-3.5" />}
                      disabled={!text.trim()}>
                Ajouter à la liste
              </Button>
            </div>
          </div>
        )}

        {mode === "csv" && (
          <div>
            <input ref={fileRef} type="file" accept=".csv,.txt" className="hidden"
                   onChange={(e) => e.target.files?.[0] && parseCsv(e.target.files[0])} />
            <Button onClick={() => fileRef.current?.click()}
                    leftIcon={<Upload className="w-4 h-4" />}>
              Choisir un CSV
            </Button>
            <p className="mt-2 text-[11px] text-ink-soft">
              Format : un UID par ligne, sans en-tête.
            </p>
          </div>
        )}

        {mode === "live" && (
          <div className="p-3 rounded-lg bg-info/5 border border-info/20 text-xs flex gap-2">
            <Radar className="w-4 h-4 text-info shrink-0" />
            <div>
              <strong>Scannez plusieurs badges</strong> sur un lecteur RFID.
              Chaque UID détecté est ajouté automatiquement (polling 1.5s).
              <LivePulse label="Live" />
            </div>
          </div>
        )}

        {/* Liste des items */}
        {items.length > 0 && (
          <Card padded={false}>
            <div className="p-3 border-b border-surface-border flex items-center justify-between">
              <div className="text-xs">
                <strong>{items.length}</strong> UIDs · {items.filter(i => i.status === "ok").length} OK ·{" "}
                {items.filter(i => i.status === "error").length} erreurs
              </div>
              <Button size="sm" variant="ghost" onClick={clear}>Tout vider</Button>
            </div>
            <ul className="max-h-64 overflow-y-auto">
              {items.map((it) => (
                <li key={it.uid} className={cn("px-3 py-1.5 flex items-center gap-2 text-xs border-b border-surface-border/30",
                  it.status === "ok" && "bg-ok/5",
                  it.status === "error" && "bg-danger/5",
                  it.status === "duplicate" && "bg-warn/5")}>
                  <CreditCard className="w-3.5 h-3.5 text-ink-muted" />
                  <code className="flex-1 font-mono">{it.uid}</code>
                  {it.status === "ok" && <UIBadge tone="ok" dot><CheckCircle2 className="w-3 h-3" /> Créé</UIBadge>}
                  {it.status === "error" && <span className="text-danger text-[10px]">{it.msg}</span>}
                  {!it.status && (
                    <button onClick={() => removeItem(it.uid)}
                            className="p-1 rounded hover:bg-danger/10 text-ink-soft hover:text-danger">
                      <X className="w-3 h-3" />
                    </button>
                  )}
                </li>
              ))}
            </ul>
          </Card>
        )}
      </div>
    </Modal>
  );
}

// ─────────────────────────────────────────────────────────────────
// Modal édition badge (rapide)
// ─────────────────────────────────────────────────────────────────
function BadgeEditModal({ badge, onClose }: { badge: any | null; onClose: () => void }) {
  const [valid_until, setValidUntil] = useState("");
  const [notes, setNotes] = useState("");
  const qc = useQueryClient();

  useEffect(() => {
    setValidUntil(badge?.valid_until || "");
    setNotes(badge?.notes || "");
  }, [badge]);

  const saveMut = useMutation({
    mutationFn: () => badgesService.update(badge.id, omitEmpty({ valid_until, notes })),
    onSuccess: () => {
      toast.success("Badge modifié");
      qc.invalidateQueries({ queryKey: ["badges"] });
      onClose();
    },
    onError: (e) => toast.error(toApiError(e).message),
  });

  if (!badge) return null;
  return (
    <Modal open={!!badge} onClose={onClose} title={`Modifier badge ${badge.uid}`}
      footer={<>
        <Button variant="ghost" onClick={onClose}>Annuler</Button>
        <Button onClick={() => saveMut.mutate()} loading={saveMut.isPending}>Enregistrer</Button>
      </>}>
      <div className="space-y-3">
        <div className="text-xs text-ink-muted">
          UID: <code className="font-mono">{badge.uid}</code>
          {" · "}Statut: <UIBadge tone="info">{badge.status}</UIBadge>
        </div>
        <Input label="Date d'expiration" type="date" value={valid_until}
               onChange={(e) => setValidUntil(e.target.value)} />
        <label className="block">
          <span className="text-xs font-medium text-ink-muted">Notes</span>
          <textarea value={notes} onChange={(e) => setNotes(e.target.value)}
                    rows={3} className="field w-full mt-1.5" />
        </label>
      </div>
    </Modal>
  );
}

// ─────────────────────────────────────────────────────────────────
// Modal association ouvrier/employé
// ─────────────────────────────────────────────────────────────────
function BadgeAssocModal({ badge, onClose }: { badge: any | null; onClose: () => void }) {
  const [kind, setKind] = useState<"worker" | "employee">("worker");
  const [holderId, setHolderId] = useState<string>("");
  const qc = useQueryClient();

  const { data: workers } = useQuery({
    queryKey: ["workers", "for-assoc"],
    queryFn: async () => (await workersService.list({ page_size: 200 })).data,
    enabled: !!badge && kind === "worker",
  });
  const { data: employees } = useQuery({
    queryKey: ["employees", "for-assoc"],
    queryFn: async () => (await employeesService.list({ page_size: 200 })).data,
    enabled: !!badge && kind === "employee",
  });

  const assocMut = useMutation({
    mutationFn: () => badgesService.associate(badge.id, {
      holder_kind: kind, holder_id: Number(holderId),
    }),
    onSuccess: () => {
      toast.success("Badge associé");
      qc.invalidateQueries({ queryKey: ["badges"] });
      onClose();
    },
    onError: (e) => toast.error(toApiError(e).message),
  });

  if (!badge) return null;
  return (
    <Modal open={!!badge} onClose={onClose} title={`Associer badge ${badge.uid}`}
      footer={<>
        <Button variant="ghost" onClick={onClose}>Annuler</Button>
        <Button onClick={() => holderId && assocMut.mutate()} loading={assocMut.isPending}
                disabled={!holderId} leftIcon={<LinkIcon className="w-4 h-4" />}>
          Associer
        </Button>
      </>}>
      <div className="space-y-3">
        <div className="flex gap-2">
          <button onClick={() => setKind("worker")}
                  className={cn("flex-1 p-2 rounded-lg border text-sm",
                    kind === "worker" ? "border-brand-500 bg-brand-500/5" : "border-surface-border")}>
            Ouvrier
          </button>
          <button onClick={() => setKind("employee")}
                  className={cn("flex-1 p-2 rounded-lg border text-sm",
                    kind === "employee" ? "border-brand-500 bg-brand-500/5" : "border-surface-border")}>
            Employé
          </button>
        </div>
        <label className="block">
          <span className="text-xs font-medium text-ink-muted">
            {kind === "worker" ? "Ouvrier à associer" : "Employé à associer"}
          </span>
          <select value={holderId} onChange={(e) => setHolderId(e.target.value)}
                  className="field w-full mt-1.5">
            <option value="">— Sélectionner —</option>
            {(kind === "worker" ? workers : employees)?.results?.map((h: any) => (
              <option key={h.id} value={h.id}>
                {h.matricule} — {h.first_name} {h.last_name}
              </option>
            ))}
          </select>
        </label>
      </div>
    </Modal>
  );
}
