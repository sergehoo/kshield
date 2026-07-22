/**
 * TargetsPanel — Panneau de gestion des équipements vendors gérés par une gateway.
 *
 * Utilisé dans GatewayDetailModal (Phase 3). L'admin peut :
 *   - Lister les targets ZKTeco/Hikvision/Suprema/HID/Dahua/Axis
 *   - Ajouter un nouveau target (form modal)
 *   - Éditer / Supprimer
 *   - Test de connexion (envoie via MQTT à la gateway)
 *   - Ouvrir la porte à distance
 */
import { useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import toast from "react-hot-toast";
import {
  Cpu, Plus, Trash2, Edit3, PlayCircle, Wifi, WifiOff, Radio, X,
} from "lucide-react";

import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Modal } from "@/components/ui/Modal";
import {
  edgeGatewayService,
  type GatewayTarget,
  type GatewayTargetInput,
} from "@/services/enrollment";
import { cn } from "@/lib/cn";

const VENDOR_LABELS: Record<string, string> = {
  zkteco:    "ZKTeco",
  hikvision: "Hikvision",
  suprema:   "Suprema BioStar 2",
  hid:       "HID Global (VertX)",
  dahua:     "Dahua",
  axis:      "Axis",
  onvif:     "ONVIF générique",
  generic:   "Générique",
};

interface Props {
  gatewayId: string;
}

export function TargetsPanel({ gatewayId }: Props) {
  const qc = useQueryClient();
  const [addOpen, setAddOpen] = useState(false);
  const [editing, setEditing] = useState<GatewayTarget | null>(null);

  const { data } = useQuery({
    queryKey: ["gateway-targets", gatewayId],
    queryFn: async () => (await edgeGatewayService.listTargets(gatewayId)).data,
    refetchInterval: 15_000,
  });

  const targets = data?.targets ?? [];

  const invalidate = () =>
    qc.invalidateQueries({ queryKey: ["gateway-targets", gatewayId] });

  const deleteMut = useMutation({
    mutationFn: (tid: string) => edgeGatewayService.deleteTarget(gatewayId, tid),
    onSuccess: () => {
      toast.success("Target supprimé");
      invalidate();
    },
    onError: () => toast.error("Suppression échouée"),
  });

  const handleAction = async (
    tid: string,
    action: "test-connect" | "door-unlock",
  ) => {
    try {
      if (action === "test-connect") {
        await edgeGatewayService.targetTestConnect(gatewayId, tid);
        toast.success("Test de connexion envoyé à la gateway");
      } else {
        await edgeGatewayService.targetDoorUnlock(gatewayId, tid);
        toast.success("Ordre d'ouverture envoyé");
      }
    } catch (e: any) {
      toast.error(e?.response?.data?.error ?? "Action échouée");
    }
  };

  return (
    <Card padded>
      <div className="flex items-center justify-between mb-3">
        <div>
          <h3 className="text-sm font-semibold text-ink flex items-center gap-2">
            <Cpu className="w-4 h-4 text-brand-ink" />
            Équipements vendors ({targets.length})
          </h3>
          <p className="text-xs text-ink-muted mt-0.5">
            ZKTeco · Hikvision · Suprema · HID · Dahua · Axis · ONVIF
          </p>
        </div>
        <Button size="sm" onClick={() => setAddOpen(true)}>
          <Plus className="w-4 h-4 mr-1" /> Ajouter
        </Button>
      </div>

      {targets.length === 0 && (
        <div className="text-center py-6 text-ink-muted text-sm">
          Aucun équipement configuré. Cliquer <b>Ajouter</b> pour connecter un
          RFID/biomètre/caméra à cette gateway.
        </div>
      )}

      <div className="space-y-2">
        {targets.map((t) => (
          <div key={t.id}
               className="flex items-center gap-3 p-3 border rounded-md hover:bg-muted/50">
            <div className={cn(
              "w-8 h-8 rounded-lg grid place-items-center shrink-0",
              t.connected
                ? "bg-success/10 text-success"
                : "bg-surface-soft text-ink-muted",
            )}>
              {t.connected
                ? <Wifi className="w-4 h-4" />
                : <WifiOff className="w-4 h-4" />}
            </div>

            <div className="flex-1 min-w-0">
              <div className="text-sm font-medium text-ink flex items-center gap-2">
                {t.label || `${VENDOR_LABELS[t.vendor] || t.vendor} · ${t.ip}`}
                {!t.enabled && (
                  <span className="text-[10px] px-1.5 py-0.5 bg-warning/20 text-warning rounded">
                    désactivé
                  </span>
                )}
              </div>
              <div className="text-xs text-ink-muted flex items-center gap-2 truncate">
                <span className="text-brand-ink">
                  {VENDOR_LABELS[t.vendor] || t.vendor}
                </span>
                <span>·</span>
                <span className="font-mono">{t.ip}{t.port > 0 ? `:${t.port}` : ""}</span>
                {t.events_count > 0 && (
                  <>
                    <span>·</span>
                    <span>{t.events_count} events</span>
                  </>
                )}
              </div>
            </div>

            <div className="hidden md:flex gap-1">
              <Button size="sm" variant="ghost"
                      onClick={() => handleAction(t.id, "test-connect")}
                      title="Test connexion">
                <Radio className="w-3.5 h-3.5" />
              </Button>
              <Button size="sm" variant="ghost"
                      onClick={() => handleAction(t.id, "door-unlock")}
                      title="Ouvrir porte">
                <PlayCircle className="w-3.5 h-3.5" />
              </Button>
              <Button size="sm" variant="ghost"
                      onClick={() => setEditing(t)}
                      title="Éditer">
                <Edit3 className="w-3.5 h-3.5" />
              </Button>
              <Button size="sm" variant="ghost"
                      onClick={() => {
                        if (confirm(`Supprimer ${t.label || t.ip} ?`)) {
                          deleteMut.mutate(t.id);
                        }
                      }}
                      title="Supprimer">
                <Trash2 className="w-3.5 h-3.5 text-danger" />
              </Button>
            </div>
          </div>
        ))}
      </div>

      {addOpen && (
        <TargetFormModal
          gatewayId={gatewayId}
          onClose={() => setAddOpen(false)}
          onSaved={() => {
            setAddOpen(false);
            invalidate();
          }}
        />
      )}

      {editing && (
        <TargetFormModal
          gatewayId={gatewayId}
          target={editing}
          onClose={() => setEditing(null)}
          onSaved={() => {
            setEditing(null);
            invalidate();
          }}
        />
      )}
    </Card>
  );
}

// ═══════════════════════════════════════════════════════════════════
// TargetFormModal — form add/edit
// ═══════════════════════════════════════════════════════════════════
function TargetFormModal({
  gatewayId,
  target,
  onClose,
  onSaved,
}: {
  gatewayId: string;
  target?: GatewayTarget;
  onClose: () => void;
  onSaved: () => void;
}) {
  const isEdit = !!target;
  const [form, setForm] = useState<GatewayTargetInput>({
    label:    target?.label ?? "",
    vendor:   target?.vendor ?? "hikvision",
    ip:       target?.ip ?? "",
    port:     target?.port ?? 0,
    username: target?.username ?? "",
    password: "",   // jamais préchargé depuis l'API
    enabled:  target?.enabled ?? true,
  });

  const [busy, setBusy] = useState(false);

  const submit = async () => {
    if (!form.ip || !form.vendor) {
      toast.error("Vendor et IP requis");
      return;
    }
    setBusy(true);
    try {
      // Ne pas envoyer password si vide et en mode edit (garde l'existant)
      const body = { ...form };
      if (isEdit && !form.password) {
        delete body.password;
      }
      if (isEdit && target) {
        await edgeGatewayService.updateTarget(gatewayId, target.id, body);
        toast.success("Target mis à jour");
      } else {
        await edgeGatewayService.createTarget(gatewayId, body);
        toast.success("Target ajouté");
      }
      onSaved();
    } catch (e: any) {
      toast.error(e?.response?.data?.error ?? "Erreur");
    } finally {
      setBusy(false);
    }
  };

  return (
    <Modal
      open
      onClose={onClose}
      title={isEdit ? `Éditer target — ${target?.label}` : "Nouveau target vendor"}
      size="md"
    >
      <div className="space-y-3">
        <div>
          <label className="text-xs text-ink-muted mb-1 block">Nom convivial</label>
          <Input
            placeholder="Portail entrée principale"
            value={form.label}
            onChange={(e) => setForm({ ...form, label: e.target.value })}
          />
        </div>

        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="text-xs text-ink-muted mb-1 block">Vendor *</label>
            <select
              className="w-full h-9 border rounded px-2 text-sm"
              value={form.vendor}
              onChange={(e) => setForm({ ...form, vendor: e.target.value })}
            >
              {Object.entries(VENDOR_LABELS).map(([k, l]) => (
                <option key={k} value={k}>{l}</option>
              ))}
            </select>
          </div>
          <div>
            <label className="text-xs text-ink-muted mb-1 block">Port (0 = défaut)</label>
            <Input type="number"
                   value={form.port}
                   onChange={(e) => setForm({ ...form, port: Number(e.target.value) })} />
          </div>
        </div>

        <div>
          <label className="text-xs text-ink-muted mb-1 block">Adresse IP *</label>
          <Input placeholder="192.168.1.20"
                 value={form.ip}
                 onChange={(e) => setForm({ ...form, ip: e.target.value })} />
        </div>

        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="text-xs text-ink-muted mb-1 block">Username</label>
            <Input value={form.username}
                   onChange={(e) => setForm({ ...form, username: e.target.value })} />
          </div>
          <div>
            <label className="text-xs text-ink-muted mb-1 block">
              Password {isEdit && <span className="opacity-50">(laisser vide pour conserver)</span>}
            </label>
            <Input type="password"
                   value={form.password}
                   onChange={(e) => setForm({ ...form, password: e.target.value })} />
          </div>
        </div>

        <div className="flex items-center gap-2 pt-2">
          <input
            type="checkbox"
            id="enabled"
            checked={!!form.enabled}
            onChange={(e) => setForm({ ...form, enabled: e.target.checked })}
          />
          <label htmlFor="enabled" className="text-sm">
            Activé (l'agent tentera de s'y connecter au boot)
          </label>
        </div>

        <div className="flex justify-end gap-2 pt-2">
          <Button variant="secondary" onClick={onClose}>
            <X className="w-4 h-4 mr-1" /> Annuler
          </Button>
          <Button onClick={submit} disabled={busy}>
            {busy ? "..." : (isEdit ? "Enregistrer" : "Créer")}
          </Button>
        </div>
      </div>
    </Modal>
  );
}
