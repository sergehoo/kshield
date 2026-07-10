/**
 * KAYDAN SHIELD — Administration > Edge Gateway (Vague 9).
 *
 * 3 onglets :
 *   1. Gateways : liste + supervision temps réel + actions
 *   2. Téléchargements : catalogue de packages installateurs par plateforme
 *   3. Assistant : nouveau Gateway + wizard install
 *
 * Le composant utilise `useDeviceStatusChannel` pour recevoir les événements
 * agent.connected/disconnected/stale en direct.
 */
import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import {
  Download, Plus, Server, Wifi, WifiOff, Cpu, RefreshCw, Trash2,
  RotateCw, Radio, Copy, FileDown, ShieldOff, PlayCircle,
  Terminal, Clock, PackageOpen, ChevronRight, Sparkles,
} from "lucide-react";
import toast from "react-hot-toast";

import { PageHeader } from "@/components/PageHeader";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Modal } from "@/components/ui/Modal";
import { Badge } from "@/components/ui/Badge";
import { StatsRow } from "@/components/StatsRow";
import { DownloadPackageModal } from "@/components/DownloadPackageModal";
import {
  edgeGatewayService, Gateway, GatewayPackage,
} from "@/services/enrollment";
import { sitesService as sitesApi } from "@/services";
import { useDeviceStatusChannel } from "@/hooks/useDeviceStatusChannel";
import { cn } from "@/lib/cn";
import { fmtRelative } from "@/lib/format";

type Tab = "gateways" | "downloads" | "wizard";

const PLATFORM_META: Record<string, { label: string; icon: any; color: string }> = {
  windows:      { label: "Windows",       icon: "🪟", color: "text-info" },
  linux_deb:    { label: "Debian/Ubuntu", icon: "🐧", color: "text-warning" },
  linux_rpm:    { label: "Fedora/RHEL",   icon: "🎩", color: "text-warning" },
  linux_sh:     { label: "Linux script",  icon: "📜", color: "text-warning" },
  docker:       { label: "Docker",        icon: "🐳", color: "text-info" },
  raspberry_pi: { label: "Raspberry Pi",  icon: "🥧", color: "text-danger" },
  mini_pc:      { label: "Mini PC",       icon: "🖥️", color: "text-brand-500" },
};

export function EdgeGatewayPage() {
  const [tab, setTab] = useState<Tab>("gateways");
  const [showCreds, setShowCreds] = useState<Gateway | null>(null);
  const [selectedGw, setSelectedGw] = useState<Gateway | null>(null);

  return (
    <div>
      <PageHeader
        title="Edge Gateway"
        subtitle="Installation, appairage et supervision des passerelles clients"
        live
        actions={
          <Button leftIcon={<Plus className="w-4 h-4" />}
                  onClick={() => setTab("wizard")}>
            Nouveau Gateway
          </Button>
        }
      />

      {/* Tabs */}
      <div className="mb-4 border-b border-surface-border flex gap-1 overflow-x-auto">
        {(["gateways", "downloads", "wizard"] as Tab[]).map((k) => (
          <button key={k}
                  onClick={() => setTab(k)}
                  className={cn(
                    "px-4 py-2 text-sm font-medium border-b-2 -mb-px transition",
                    tab === k
                      ? "border-brand-500 text-brand-500"
                      : "border-transparent text-ink-muted hover:text-ink",
                  )}>
            {k === "gateways" && <><Server className="w-3.5 h-3.5 inline mr-1" /> Gateways</>}
            {k === "downloads" && <><Download className="w-3.5 h-3.5 inline mr-1" /> Téléchargements</>}
            {k === "wizard" && <><Sparkles className="w-3.5 h-3.5 inline mr-1" /> Assistant</>}
          </button>
        ))}
      </div>

      {tab === "gateways"  && <GatewaysTab onSelect={setSelectedGw} />}
      {tab === "downloads" && <DownloadsTab />}
      {tab === "wizard"    && <WizardTab onCreated={(gw) => { setShowCreds(gw); setTab("gateways"); }} />}

      {showCreds && <CredsModal gateway={showCreds} onClose={() => setShowCreds(null)} />}
      {selectedGw && (
        <GatewayDetailModal gateway={selectedGw}
                             onClose={() => setSelectedGw(null)} />
      )}
    </div>
  );
}


// ═══════════════════════════════════════════════════════════════════
// Onglet 1 : liste des Gateways
// ═══════════════════════════════════════════════════════════════════
function GatewaysTab({ onSelect }: { onSelect: (g: Gateway) => void }) {
  const qc = useQueryClient();
  const { data, isFetching } = useQuery({
    queryKey: ["edge-gateways"],
    queryFn: async () => (await edgeGatewayService.list()).data,
    refetchInterval: 10_000,
  });

  useDeviceStatusChannel({
    onEvent: (e: any) => {
      if (e?.event?.startsWith("agent.")) {
        qc.invalidateQueries({ queryKey: ["edge-gateways"] });
      }
    },
  });

  const gateways = data?.gateways || [];
  const stats = {
    total: gateways.length,
    connected: gateways.filter((g) => g.status === "connected").length,
    pending: gateways.filter((g) => g.status === "pending_activation").length,
    revoked: gateways.filter((g) => g.status === "revoked").length,
  };

  return (
    <>
      <StatsRow stats={[
        { label: "Total", value: stats.total, icon: <Server className="w-4 h-4" />, tone: "brand" },
        { label: "Connectés", value: stats.connected, icon: <Wifi className="w-4 h-4" />, tone: "ok" },
        { label: "En attente", value: stats.pending, icon: <Clock className="w-4 h-4" />, tone: "warn" },
        { label: "Révoqués", value: stats.revoked, icon: <ShieldOff className="w-4 h-4" />, tone: "muted" },
      ]} />

      <Card padded={false}>
        {gateways.length === 0 ? (
          <div className="p-12 text-center text-ink-muted text-sm">
            Aucun Gateway. Utilisez l'assistant pour en créer un.
          </div>
        ) : (
          <div className="divide-y divide-surface-border">
            {gateways.map((g) => (
              <GatewayRow key={g.id} gateway={g} onSelect={() => onSelect(g)} />
            ))}
          </div>
        )}
      </Card>
    </>
  );
}


function GatewayRow({ gateway: g, onSelect }: { gateway: Gateway; onSelect: () => void }) {
  const statusMeta: Record<string, { color: string; label: string; icon: any }> = {
    connected:            { color: "text-success", label: "En ligne",      icon: <Wifi className="w-3.5 h-3.5" /> },
    disconnected:         { color: "text-warning", label: "Hors ligne",    icon: <WifiOff className="w-3.5 h-3.5" /> },
    pending_activation:   { color: "text-info",    label: "En attente",    icon: <Clock className="w-3.5 h-3.5" /> },
    activation_expired:   { color: "text-danger",  label: "Expiré",        icon: <Clock className="w-3.5 h-3.5" /> },
    revoked:              { color: "text-danger",  label: "Révoqué",       icon: <ShieldOff className="w-3.5 h-3.5" /> },
  };
  const m = statusMeta[g.status] || statusMeta.disconnected;

  return (
    <button onClick={onSelect}
            className="w-full text-left p-3 hover:bg-surface-soft/40 flex items-center gap-3">
      <div className={cn("w-9 h-9 rounded-lg grid place-items-center",
                          g.status === "connected"
                            ? "bg-success/10 text-success"
                            : "bg-surface-soft text-ink-muted")}>
        <Server className="w-4 h-4" />
      </div>
      <div className="flex-1 min-w-0">
        <div className="text-sm font-medium text-ink flex items-center gap-2 truncate">
          {g.label}
          <span className={cn("inline-flex items-center gap-0.5 text-xs", m.color)}>
            {m.icon}{m.label}
          </span>
        </div>
        <div className="text-xs text-ink-muted flex items-center gap-2 truncate">
          {g.ip_local && <span className="font-mono">{g.ip_local}</span>}
          {g.os_info && <span>· {g.os_info}</span>}
          {g.version && <span className="font-mono">· v{g.version}</span>}
          {g.last_seen_at && <span>· vu {fmtRelative(g.last_seen_at)}</span>}
        </div>
      </div>
      <div className="hidden md:flex items-center gap-2 text-xs text-ink-muted">
        <span>{g.devices_discovered_count} devices</span>
        {g.events_pending > 0 && (
          <span className="text-warning">{g.events_pending} en attente</span>
        )}
      </div>
      <ChevronRight className="w-4 h-4 text-ink-muted" />
    </button>
  );
}


// ═══════════════════════════════════════════════════════════════════
// Onglet 2 : catalogue de téléchargements
// ═══════════════════════════════════════════════════════════════════
function DownloadsTab() {
  const { data } = useQuery({
    queryKey: ["edge-gateway-packages"],
    queryFn: async () => (await edgeGatewayService.listPackages()).data,
  });

  const groups = data?.by_platform || {};
  const platforms = Object.keys(groups);

  if (platforms.length === 0) {
    return (
      <Card padded>
        <div className="text-center py-8 text-ink-muted text-sm">
          <PackageOpen className="w-8 h-8 mx-auto mb-2 opacity-30" />
          Aucun package publié. L'admin doit en publier via /django-admin/.
        </div>
      </Card>
    );
  }

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
      {platforms.map((pl) => {
        const pkgs = groups[pl];
        const latest = pkgs.find((p) => p.is_latest) || pkgs[0];
        const meta = PLATFORM_META[pl] || { label: pl, icon: "📦", color: "" };
        return <PackageCard key={pl} platform={pl} meta={meta} pkg={latest} others={pkgs} />;
      })}
    </div>
  );
}

function PackageCard({ platform, meta, pkg, others }: {
  platform: string;
  meta: { label: string; icon: any; color: string };
  pkg: GatewayPackage;
  others: GatewayPackage[];
}) {
  const copyCmd = async () => {
    try {
      const r = await edgeGatewayService.installCommand(pkg.id);
      navigator.clipboard.writeText(r.data.command);
      toast.success("Commande copiée");
    } catch { toast.error("Impossible de générer la commande"); }
  };

  return (
    <Card padded>
      <div className="flex items-center gap-2 mb-2">
        <div className="text-2xl">{meta.icon}</div>
        <div className="flex-1">
          <div className="text-sm font-semibold text-ink">{meta.label}</div>
          <code className="text-xs text-ink-soft font-mono">{pkg.name}</code>
        </div>
        <Badge tone="info">v{pkg.version}</Badge>
      </div>

      <div className="text-xs text-ink-muted space-y-1 mb-3">
        <div>📅 {pkg.published_at ? new Date(pkg.published_at).toLocaleDateString("fr-FR") : "—"}</div>
        <div>💾 {formatBytes(pkg.size_bytes)}</div>
        {pkg.checksum_sha256 && (
          <div className="truncate font-mono" title={pkg.checksum_sha256}>
            🔒 SHA256: {pkg.checksum_sha256.slice(0, 16)}…
          </div>
        )}
        {pkg.min_os_version && <div>ℹ️ {pkg.min_os_version}</div>}
      </div>

      {pkg.release_notes && (
        <details className="mb-3 text-xs">
          <summary className="text-ink-muted cursor-pointer">Notes de version</summary>
          <div className="mt-1 p-2 bg-surface-soft rounded text-ink whitespace-pre-wrap">
            {pkg.release_notes}
          </div>
        </details>
      )}

      <div className="flex gap-2">
        {pkg.has_file && (
          <a href={edgeGatewayService.downloadUrl(pkg.id)}
              className="btn-primary text-xs px-3 py-1.5 rounded inline-flex items-center gap-1"
              download>
            <FileDown className="w-3.5 h-3.5" />
            Télécharger
          </a>
        )}
        <Button variant="ghost" size="sm"
                leftIcon={<Copy className="w-3.5 h-3.5" />}
                onClick={copyCmd}>
          Commande d'install
        </Button>
      </div>

      {others.length > 1 && (
        <div className="mt-2 text-xs text-ink-muted">
          {others.length - 1} version{others.length > 2 ? "s antérieures" : " antérieure"}
        </div>
      )}
    </Card>
  );
}


// ═══════════════════════════════════════════════════════════════════
// Onglet 3 : Assistant création
// ═══════════════════════════════════════════════════════════════════
function WizardTab({ onCreated }: { onCreated: (gw: Gateway) => void }) {
  const [label, setLabel] = useState("");
  const [siteId, setSiteId] = useState<number | "">("");

  const { data: sites } = useQuery({
    queryKey: ["sites", "for-gateway"],
    queryFn: async () => (await sitesApi.list({ page_size: 200 })).data,
  });

  const createMut = useMutation({
    mutationFn: () => edgeGatewayService.create(label, siteId ? Number(siteId) : null),
    onSuccess: (r) => {
      toast.success("Gateway créé — token d'activation généré");
      onCreated(r.data);
    },
    onError: (e: any) => toast.error(e?.response?.data?.error || "Erreur"),
  });

  return (
    <Card padded>
      <div className="max-w-2xl mx-auto space-y-4">
        <div className="rounded-md border border-info/20 bg-info/5 p-3 text-xs text-ink">
          <div className="font-medium mb-1 flex items-center gap-1">
            <Sparkles className="w-3.5 h-3.5 text-info" /> Assistant Kaydan Edge Gateway
          </div>
          Ce workflow te guide à travers 4 étapes :
          <ol className="ml-4 mt-1 list-decimal space-y-0.5">
            <li>Créer le Gateway ici — un token d'activation à usage unique est généré</li>
            <li>Télécharger le package pour la machine hôte (Windows/Linux/Docker/Pi)</li>
            <li>Installer sur la machine hôte avec la commande copier-collable</li>
            <li>Le Gateway s'auto-appaire au premier boot et devient "En ligne"</li>
          </ol>
        </div>

        <Input label="Nom du Gateway *"
               placeholder="ex. Chantier Riviera-01"
               value={label}
               onChange={(e) => setLabel(e.target.value)}
               requiredMark />

        <label className="block">
          <span className="text-xs font-medium text-ink-muted">Site rattaché (optionnel)</span>
          <select className="field w-full mt-1.5" value={siteId}
                  onChange={(e) => setSiteId(e.target.value ? Number(e.target.value) : "")}>
            <option value="">— Aucun —</option>
            {sites?.results?.map((s: any) => (
              <option key={s.id} value={s.id}>{s.name}</option>
            ))}
          </select>
        </label>

        <Button leftIcon={<Sparkles className="w-4 h-4" />}
                onClick={() => createMut.mutate()}
                loading={createMut.isPending}
                disabled={!label}>
          Créer le Gateway
        </Button>
      </div>
    </Card>
  );
}


// ═══════════════════════════════════════════════════════════════════
// Modal credentials — visible juste après create/rotate
// ═══════════════════════════════════════════════════════════════════
function CredsModal({ gateway, onClose }: { gateway: Gateway; onClose: () => void }) {
  const copy = (text: string, label: string) => {
    navigator.clipboard.writeText(text).then(() => toast.success(`${label} copié`));
  };

  return (
    <Modal open onClose={onClose} title="Appairage du Gateway" size="lg"
           footer={<Button onClick={onClose}>OK, terminé</Button>}>
      <div className="space-y-3 text-sm">
        <div className="rounded-md border border-warning/30 bg-warning/5 p-3 text-xs">
          <strong>Ce token ne s'affiche qu'une seule fois.</strong> Copie-le maintenant ou copie
          la commande d'installation qui l'inclut déjà.
        </div>

        <div className="grid grid-cols-[110px_1fr_auto] gap-2 items-center">
          <span className="text-ink-muted text-xs">Gateway ID</span>
          <code className="font-mono text-xs bg-surface-soft p-2 rounded truncate">{gateway.id}</code>
          <button onClick={() => copy(gateway.id, "ID")}
                  className="p-1.5 hover:bg-surface-soft rounded"><Copy className="w-3.5 h-3.5" /></button>

          <span className="text-ink-muted text-xs">Token activation</span>
          <code className="font-mono text-xs bg-surface-soft p-2 rounded truncate">
            {gateway.activation_token}
          </code>
          <button onClick={() => copy(gateway.activation_token || "", "Token")}
                  className="p-1.5 hover:bg-surface-soft rounded"><Copy className="w-3.5 h-3.5" /></button>
        </div>

        {gateway.activation_ttl_hours && (
          <div className="text-xs text-ink-muted">
            ⏱️ Expire dans {gateway.activation_ttl_hours} h. Regénère si nécessaire depuis la fiche du Gateway.
          </div>
        )}

        {gateway.activation_pairing_url && (
          <div className="grid grid-cols-1 md:grid-cols-[1fr_auto] gap-3 items-start">
            <div>
              <div className="text-xs font-medium text-ink-muted mb-1">
                Lien d'appairage (à ouvrir depuis la machine hôte)
              </div>
              <div className="flex gap-2">
                <code className="flex-1 text-xs bg-surface-soft p-2 rounded truncate">
                  {gateway.activation_pairing_url}
                </code>
                <button onClick={() => copy(gateway.activation_pairing_url || "", "URL")}
                        className="p-1.5 hover:bg-surface-soft rounded"><Copy className="w-4 h-4" /></button>
              </div>
              <div className="text-[10px] text-ink-muted mt-1">
                Astuce : scanne le QR ci-contre avec le smartphone de la machine cliente
                pour l'ouvrir directement.
              </div>
            </div>
            <div className="text-center">
              <img
                src={`/api/v1/devices/edge-gateway/${gateway.id}/pairing-qr.png`}
                alt="QR code d'appairage"
                className="w-40 h-40 border border-surface-border rounded p-1 bg-white"
              />
              <div className="text-[10px] text-ink-muted mt-1">QR code d'appairage</div>
            </div>
          </div>
        )}

        <div className="rounded-md border border-info/20 bg-info/5 p-3 text-xs">
          <div className="font-medium mb-1">📥 Prochaine étape</div>
          Va dans l'onglet <strong>Téléchargements</strong> pour récupérer le package
          Windows/Linux/Docker, puis copie la <strong>commande d'installation</strong>{" "}
          qui pré-remplit automatiquement le token.
        </div>
      </div>
    </Modal>
  );
}


// ═══════════════════════════════════════════════════════════════════
// Modal détail Gateway — logs live + actions
// ═══════════════════════════════════════════════════════════════════
function GatewayDetailModal({ gateway, onClose }: {
  gateway: Gateway; onClose: () => void;
}) {
  const qc = useQueryClient();
  const [downloadModalOpen, setDownloadModalOpen] = useState(false);

  const { data: full } = useQuery({
    queryKey: ["edge-gateway", gateway.id],
    queryFn: async () => (await edgeGatewayService.get(gateway.id)).data,
    refetchInterval: 5000,
  });
  const { data: logs } = useQuery({
    queryKey: ["edge-gateway-logs", gateway.id],
    queryFn: async () => (await edgeGatewayService.logs(gateway.id)).data,
    refetchInterval: 3000,
  });

  const g = full || gateway;

  const call = (fn: () => Promise<any>, msgOk: string) => {
    fn().then(() => toast.success(msgOk))
        .then(() => qc.invalidateQueries({ queryKey: ["edge-gateway"] }))
        .catch(() => toast.error("Action échouée"));
  };

  return (
    <Modal open onClose={onClose} title={g.label} size="xl"
           footer={<Button onClick={onClose}>Fermer</Button>}>
      <div className="space-y-4">
        <div className="grid grid-cols-2 md:grid-cols-4 gap-2 text-xs">
          <Tile label="Statut" value={g.status}
                 tone={g.status === "connected" ? "ok"
                       : g.status === "revoked" ? "danger" : "warn"} />
          <Tile label="IP locale"  value={g.ip_local || "—"} />
          <Tile label="IP publique" value={g.ip_public || "—"} />
          <Tile label="OS"         value={g.os_info || "—"} />
          <Tile label="Version"    value={g.version || "—"} />
          <Tile label="Uptime"     value={fmtUptime(g.uptime_seconds)} />
          <Tile label="Devices"    value={g.devices_discovered_count} />
          <Tile label="Events en attente" value={g.events_pending}
                 tone={g.events_pending > 0 ? "warn" : "ok"} />
        </div>

        <div className="grid grid-cols-3 gap-2">
          <StatusChip label="MQTT" value={g.mqtt_status} />
          <StatusChip label="WebSocket" value={g.ws_status} />
          <StatusChip label="Cloud" value={g.cloud_status} />
        </div>

        {/* Actions */}
        <div className="flex flex-wrap gap-2">
          {/* Bouton principal : télécharger le package personnalisé */}
          <Button size="sm"
                  leftIcon={<Download className="w-3.5 h-3.5" />}
                  onClick={() => setDownloadModalOpen(true)}>
            Télécharger installateur
          </Button>
          <Button size="sm" variant="secondary"
                  leftIcon={<RefreshCw className="w-3.5 h-3.5" />}
                  onClick={() => call(() => edgeGatewayService.forceSync(g.id),
                                       "Sync forcée")}>
            Forcer sync
          </Button>
          <Button size="sm" variant="secondary"
                  leftIcon={<Radio className="w-3.5 h-3.5" />}
                  onClick={() => call(() => edgeGatewayService.scanNetwork(g.id),
                                       "Scan lancé")}>
            Scan réseau
          </Button>
          <Button size="sm" variant="secondary"
                  leftIcon={<PlayCircle className="w-3.5 h-3.5" />}
                  onClick={() => confirm("Redémarrer le Gateway ?")
                                   && call(() => edgeGatewayService.restart(g.id), "Redémarrage")}>
            Redémarrer
          </Button>
          <Button size="sm" variant="ghost"
                  leftIcon={<RotateCw className="w-3.5 h-3.5" />}
                  onClick={() => confirm("Régénérer le token d'activation ?")
                                   && call(() => edgeGatewayService.rotateActivation(g.id),
                                             "Token régénéré")}>
            Rotate token
          </Button>
          {g.status !== "revoked" ? (
            <Button size="sm" variant="danger"
                    leftIcon={<ShieldOff className="w-3.5 h-3.5" />}
                    onClick={() => confirm("Révoquer ce Gateway ?")
                                     && call(() => edgeGatewayService.revoke(g.id), "Révoqué")}>
              Révoquer
            </Button>
          ) : (
            <Button size="sm" variant="secondary"
                    leftIcon={<RotateCw className="w-3.5 h-3.5" />}
                    onClick={() => call(() => edgeGatewayService.reactivate(g.id),
                                         "Réactivé — nouveau token généré")}>
              Réactiver
            </Button>
          )}
          <Button size="sm" variant="ghost"
                  leftIcon={<Trash2 className="w-3.5 h-3.5" />}
                  onClick={() => confirm("Supprimer définitivement ?")
                                   && call(() => edgeGatewayService.remove(g.id).then(onClose),
                                             "Supprimé")}>
            Supprimer
          </Button>
        </div>

        {/* Logs live */}
        <div>
          <div className="text-xs font-medium text-ink-muted mb-1.5 flex items-center gap-1">
            <Terminal className="w-3.5 h-3.5" /> Logs temps réel
          </div>
          <div className="border border-surface-border rounded max-h-64 overflow-auto p-2 font-mono text-xs bg-surface-soft">
            {(logs?.logs || []).slice(-100).reverse().map((l: any, i: number) => (
              <div key={i} className="text-ink-muted">
                <span className="text-info">{(l.at || "").slice(11, 19)}</span>
                {" "}<span className="text-ink">{l.type}</span>
                {" "}{l.ip_local && <span>ip={l.ip_local}</span>}
                {" "}{l.events_pending != null && <span>pending={l.events_pending}</span>}
              </div>
            ))}
            {(!logs?.logs || logs.logs.length === 0) && (
              <div className="text-ink-muted p-3 text-center">Aucun log récent</div>
            )}
          </div>
        </div>

        {/* Devices découverts */}
        {full?.devices_discovered && full.devices_discovered.length > 0 && (
          <div>
            <div className="text-xs font-medium text-ink-muted mb-1.5 flex items-center gap-1">
              <Cpu className="w-3.5 h-3.5" /> Équipements découverts
            </div>
            <div className="max-h-40 overflow-auto text-xs space-y-0.5">
              {full.devices_discovered.map((d: any, i: number) => (
                <div key={i} className="p-1.5 rounded bg-surface-soft flex items-center gap-2">
                  <span className="font-mono">{d.ip || d.serial}</span>
                  <span className="text-ink-muted">
                    {d.vendor} {d.model}
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}
      </div>

      {/* Modale de téléchargement du package personnalisé */}
      <DownloadPackageModal
        open={downloadModalOpen}
        onClose={() => setDownloadModalOpen(false)}
        gatewayId={g.id}
        gatewayLabel={g.label}
      />
    </Modal>
  );
}

// ═══════════════════════════════════════════════════════════════════
// Helpers
// ═══════════════════════════════════════════════════════════════════
function Tile({ label, value, tone }: {
  label: string; value: any; tone?: "ok" | "warn" | "danger";
}) {
  const toneMap = { ok: "border-success/20 bg-success/5",
                     warn: "border-warning/20 bg-warning/5",
                     danger: "border-danger/20 bg-danger/5" };
  return (
    <div className={cn("rounded border p-2",
                        tone ? toneMap[tone] : "border-surface-border bg-surface-soft")}>
      <div className="text-[10px] uppercase text-ink-muted tracking-wider">{label}</div>
      <div className="text-sm font-medium text-ink truncate mt-0.5">{String(value)}</div>
    </div>
  );
}

function StatusChip({ label, value }: { label: string; value: string }) {
  const meta: Record<string, string> = {
    ok: "text-success bg-success/10 border-success/30",
    degraded: "text-warning bg-warning/10 border-warning/30",
    down: "text-danger bg-danger/10 border-danger/30",
    unknown: "text-ink-muted bg-surface-soft border-surface-border",
  };
  return (
    <div className={cn("rounded border px-2 py-1 text-xs flex items-center justify-between",
                        meta[value] || meta.unknown)}>
      <span>{label}</span>
      <span className="font-mono">{value}</span>
    </div>
  );
}

function formatBytes(b: number): string {
  if (!b) return "—";
  const mb = b / (1024 * 1024);
  return mb > 1 ? `${mb.toFixed(1)} MB` : `${(b / 1024).toFixed(1)} KB`;
}

function fmtUptime(seconds: number | null | undefined): string {
  if (seconds == null) return "—";
  const d = Math.floor(seconds / 86400);
  const h = Math.floor((seconds % 86400) / 3600);
  if (d > 0) return `${d}j ${h}h`;
  const m = Math.floor((seconds % 3600) / 60);
  return h > 0 ? `${h}h ${m}m` : `${m}m`;
}
