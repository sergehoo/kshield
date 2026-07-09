/**
 * Kaydan Shield — Administration des Agents locaux.
 *
 * Un LocalAgent = un binaire Python installé sur le LAN d'un client. Il maintient
 * une WebSocket persistante vers /ws/agents/<id>/ et relaie les scans RFID.
 *
 * Cette page permet à un admin de :
 *  - Voir tous les agents du tenant + leur statut connexion en direct
 *  - Provisionner un nouvel agent (génère un TOML téléchargeable)
 *  - Rotate le token (invalide immédiatement l'ancien)
 *  - Supprimer un agent
 */
import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import {
  Plus, Wifi, WifiOff, Copy, Download, RefreshCw, Trash2, Server,
  Terminal, AlertTriangle, CheckCircle2,
} from "lucide-react";
import toast from "react-hot-toast";

import { PageHeader } from "@/components/PageHeader";
import { Card } from "@/components/ui/Card";
import { DataTable, Column } from "@/components/ui/DataTable";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Modal } from "@/components/ui/Modal";
import { Badge } from "@/components/ui/Badge";
import { StatsRow } from "@/components/StatsRow";
import { useDeviceStatusChannel } from "@/hooks/useDeviceStatusChannel";
import { localAgentsService, LocalAgent } from "@/services/enrollment";
import { sitesService } from "@/services";
import { fmtRelative } from "@/lib/format";
import { cn } from "@/lib/cn";

export function LocalAgentsPage() {
  const qc = useQueryClient();
  const [newOpen, setNewOpen] = useState(false);
  const [credsModal, setCredsModal] = useState<LocalAgent | null>(null);
  const [label, setLabel] = useState("");
  const [siteId, setSiteId] = useState<number | "">("");

  const { data, isLoading } = useQuery({
    queryKey: ["local-agents"],
    queryFn: async () => (await localAgentsService.list()).data,
    refetchInterval: 10_000,
  });

  const { data: sites } = useQuery({
    queryKey: ["sites", "for-agents"],
    queryFn: async () => (await sitesService.list({ page_size: 200 })).data,
  });

  // Refresh la liste dès qu'un event agent.connected/disconnected arrive
  useDeviceStatusChannel({
    onEvent: (evt: any) => {
      if (evt?.event === "agent.connected" || evt?.event === "agent.disconnected") {
        qc.invalidateQueries({ queryKey: ["local-agents"] });
      }
    },
  });

  const agents = data?.results || [];
  const onlineCount = agents.filter((a) => a.connected).length;

  const createMut = useMutation({
    mutationFn: () => localAgentsService.create(label, siteId ? Number(siteId) : null),
    onSuccess: (r) => {
      toast.success("Agent créé");
      setCredsModal(r.data);
      setNewOpen(false); setLabel(""); setSiteId("");
      qc.invalidateQueries({ queryKey: ["local-agents"] });
    },
    onError: (e: any) => toast.error(e?.response?.data?.error || "Erreur"),
  });

  const rotateMut = useMutation({
    mutationFn: (id: string) => localAgentsService.rotateToken(id),
    onSuccess: (r) => {
      toast.success("Token régénéré — l'ancien est révoqué");
      setCredsModal(r.data);
      qc.invalidateQueries({ queryKey: ["local-agents"] });
    },
  });

  const removeMut = useMutation({
    mutationFn: (id: string) => localAgentsService.remove(id),
    onSuccess: () => {
      toast.success("Agent supprimé");
      qc.invalidateQueries({ queryKey: ["local-agents"] });
    },
  });

  const columns: Column<LocalAgent>[] = [
    {
      key: "label", header: "Agent",
      render: (a) => (
        <div className="flex items-center gap-2">
          <div className={cn("w-8 h-8 rounded-lg grid place-items-center",
            a.connected ? "bg-success/10 text-success" : "bg-surface-soft text-ink-muted")}>
            <Server className="w-4 h-4" />
          </div>
          <div>
            <div className="text-sm font-medium text-ink">{a.label}</div>
            <code className="text-xs font-mono text-ink-soft">{a.id.slice(0, 8)}…</code>
          </div>
        </div>
      ),
    },
    {
      key: "connected", header: "Connexion",
      render: (a) => a.connected ? (
        <Badge tone="ok"><Wifi className="w-3 h-3 mr-1 inline" />En ligne</Badge>
      ) : (
        <Badge tone="muted"><WifiOff className="w-3 h-3 mr-1 inline" />Hors ligne</Badge>
      ),
    },
    {
      key: "last_seen", header: "Dernier signe",
      render: (a) => a.last_seen_at ? fmtRelative(a.last_seen_at) : "Jamais",
    },
    {
      key: "devices", header: "Devices vus",
      render: (a) => a.devices_discovered_count || "—",
    },
    {
      key: "version", header: "Version",
      render: (a) => (
        <span className="text-xs font-mono text-ink-muted">
          {a.version || "—"}
        </span>
      ),
    },
    {
      key: "actions", header: "", className: "text-right",
      render: (a) => (
        <div className="flex items-center justify-end gap-1">
          <button
            onClick={() => confirm("Rotate le token ? L'ancien cessera immédiatement de fonctionner.")
              && rotateMut.mutate(a.id)}
            className="p-1.5 rounded-md hover:bg-warning/10 text-ink-muted hover:text-warning"
            title="Régénérer le token">
            <RefreshCw className="w-3.5 h-3.5" />
          </button>
          <button
            onClick={() => confirm(`Supprimer l'agent "${a.label}" ?`) && removeMut.mutate(a.id)}
            className="p-1.5 rounded-md hover:bg-danger/10 text-ink-muted hover:text-danger"
            title="Supprimer">
            <Trash2 className="w-3.5 h-3.5" />
          </button>
        </div>
      ),
    },
  ];

  return (
    <div>
      <PageHeader
        title="Agents locaux"
        subtitle={`${agents.length} agent${agents.length > 1 ? "s" : ""} · ${onlineCount} en ligne`}
        live
        actions={
          <Button leftIcon={<Plus className="w-4 h-4" />} onClick={() => setNewOpen(true)}>
            Nouvel agent
          </Button>
        }
      />

      <StatsRow stats={[
        { label: "Total agents", value: agents.length, icon: <Server className="w-4 h-4" />, tone: "brand" },
        { label: "En ligne",     value: onlineCount,   icon: <Wifi className="w-4 h-4" />,   tone: "ok" },
        { label: "Hors ligne",   value: agents.length - onlineCount,
          icon: <WifiOff className="w-4 h-4" />, tone: "muted" },
        { label: "Devices vus",
          value: agents.reduce((s, a) => s + (a.devices_discovered_count || 0), 0),
          icon: <Terminal className="w-4 h-4" />, tone: "info" },
      ]} />

      <Card padded={false}>
        <DataTable
          columns={columns}
          rows={agents}
          loading={isLoading}
          rowKey={(a) => a.id}
          emptyLabel="Aucun agent local — commence par créer un provisioning ci-dessus"
        />
      </Card>

      {/* Modal création */}
      <Modal open={newOpen} onClose={() => setNewOpen(false)} title="Provisionner un nouvel agent"
             footer={<>
               <Button variant="ghost" onClick={() => setNewOpen(false)}>Annuler</Button>
               <Button onClick={() => createMut.mutate()} loading={createMut.isPending}
                       disabled={!label}>Créer l'agent</Button>
             </>}>
        <div className="space-y-3">
          <div className="p-3 rounded-md bg-info/5 border border-info/20 text-xs text-ink">
            <strong>Un agent = un binaire Python</strong> installé sur le LAN client.
            Il maintiendra une WebSocket vers Kaydan Shield et relaiera les scans RFID des lecteurs locaux.
          </div>
          <Input label="Nom de l'agent" placeholder="ex. Chantier Riviera-01" value={label}
                 onChange={(e) => setLabel(e.target.value)} requiredMark />
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
        </div>
      </Modal>

      {/* Modal credentials (affiché après create/rotate) */}
      {credsModal && (
        <CredsModal agent={credsModal} onClose={() => setCredsModal(null)} />
      )}
    </div>
  );
}

// ─────────────────────────────────────────────────────────────
// Modal affichant les credentials + TOML téléchargeable
// ─────────────────────────────────────────────────────────────
function CredsModal({ agent, onClose }: { agent: LocalAgent; onClose: () => void }) {
  const copy = (text: string, label: string) => {
    navigator.clipboard.writeText(text).then(() => toast.success(`${label} copié`));
  };
  const downloadToml = () => {
    if (!agent.toml) return;
    const blob = new Blob([agent.toml], { type: "text/plain" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = `kshield-agent-${agent.id.slice(0, 8)}.toml`;
    a.click();
    URL.revokeObjectURL(url);
  };

  return (
    <Modal open onClose={onClose} title="Configuration de l'agent" size="lg"
           footer={<Button onClick={onClose}>OK, j'ai copié</Button>}>
      <div className="space-y-4">
        <div className="p-3 rounded-md bg-warning/5 border border-warning/30 text-xs flex gap-2">
          <AlertTriangle className="w-4 h-4 text-warning shrink-0 mt-0.5" />
          <div>
            <strong>Ces secrets ne s'affichent qu'une seule fois.</strong>{" "}
            Copie-les maintenant dans un gestionnaire de mots de passe, ou télécharge
            directement le fichier TOML ci-dessous et copie-le sur la machine cliente.
          </div>
        </div>

        <div className="grid grid-cols-[100px_1fr_auto] gap-2 items-center text-sm">
          <span className="text-ink-muted">Agent ID</span>
          <code className="font-mono text-xs bg-surface-soft p-2 rounded">{agent.id}</code>
          <button onClick={() => copy(agent.id, "Agent ID")}
                  className="p-1.5 hover:bg-surface-soft rounded">
            <Copy className="w-3.5 h-3.5" />
          </button>

          <span className="text-ink-muted">Token</span>
          <code className="font-mono text-xs bg-surface-soft p-2 rounded truncate">
            {agent.api_token}
          </code>
          <button onClick={() => copy(agent.api_token || "", "Token")}
                  className="p-1.5 hover:bg-surface-soft rounded">
            <Copy className="w-3.5 h-3.5" />
          </button>

          <span className="text-ink-muted">HMAC</span>
          <code className="font-mono text-xs bg-surface-soft p-2 rounded truncate">
            {agent.hmac_secret}
          </code>
          <button onClick={() => copy(agent.hmac_secret || "", "HMAC secret")}
                  className="p-1.5 hover:bg-surface-soft rounded">
            <Copy className="w-3.5 h-3.5" />
          </button>
        </div>

        {agent.toml && (
          <div>
            <div className="flex items-center justify-between mb-1.5">
              <span className="text-xs font-medium text-ink-muted">
                Fichier <code>~/.kshield-agent.toml</code>
              </span>
              <div className="flex items-center gap-1">
                <button onClick={() => copy(agent.toml || "", "Config TOML")}
                        className="text-xs text-ink-muted hover:text-ink flex items-center gap-1">
                  <Copy className="w-3 h-3" /> Copier
                </button>
                <button onClick={downloadToml}
                        className="text-xs text-ink-muted hover:text-ink flex items-center gap-1 ml-2">
                  <Download className="w-3 h-3" /> Télécharger
                </button>
              </div>
            </div>
            <pre className="text-xs font-mono bg-surface-soft p-3 rounded-md overflow-auto max-h-80">
              {agent.toml}
            </pre>
          </div>
        )}

        <div className="p-3 rounded-md bg-info/5 border border-info/20 text-xs">
          <div className="font-medium text-ink mb-1 flex items-center gap-1">
            <CheckCircle2 className="w-3.5 h-3.5 text-info" /> Prochaines étapes
          </div>
          <ol className="ml-4 list-decimal space-y-0.5 text-ink">
            <li>Copie ce fichier vers <code>~/.kshield-agent.toml</code> sur la machine du LAN client</li>
            <li>Édite la section <code>[[readers]]</code> pour déclarer les lecteurs RFID physiques</li>
            <li>Installe l'agent : <code>pip install -e ~/path/to/agent/</code></li>
            <li>Vérifie : <code>kshield-agent doctor</code></li>
            <li>Lance en foreground : <code>kshield-agent run</code></li>
          </ol>
        </div>
      </div>
    </Modal>
  );
}
