import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { PageHeader } from "@/components/PageHeader";
import { Card } from "@/components/ui/Card";
import { DataTable, Column } from "@/components/ui/DataTable";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Modal } from "@/components/ui/Modal";
import { apiKeysService } from "@/services";
import { toApiError } from "@/lib/api";
import { fmtDateTime } from "@/lib/format";
import { Plus, Key, Trash2, Copy, AlertTriangle } from "lucide-react";
import toast from "react-hot-toast";

export function ApiKeysPage() {
  const [open, setOpen] = useState(false);
  const [reveal, setReveal] = useState<{ public_id: string; secret: string } | null>(null);
  const [form, setForm] = useState({ name: "", scope: "read", expires_at: "" });
  const qc = useQueryClient();

  const { data, isLoading } = useQuery({
    queryKey: ["api-keys"],
    queryFn: async () => (await apiKeysService.list({ page_size: 100 })).data,
  });

  const createMut = useMutation({
    mutationFn: () => apiKeysService.create(form),
    onSuccess: (r: any) => {
      toast.success("Clé API créée — copiez le secret maintenant !");
      setReveal({
        public_id: r.data?.public_id,
        secret: r.data?.secret,
      });
      setOpen(false);
      setForm({ name: "", scope: "read", expires_at: "" });
      qc.invalidateQueries({ queryKey: ["api-keys"] });
    },
    onError: (e) => toast.error(toApiError(e).message),
  });

  const removeMut = useMutation({
    mutationFn: (id: number) => apiKeysService.remove(id),
    onSuccess: () => {
      toast.success("Clé révoquée");
      qc.invalidateQueries({ queryKey: ["api-keys"] });
    },
    onError: (e) => toast.error(toApiError(e).message),
  });

  const columns: Column<any>[] = [
    {
      key: "name",
      header: "Nom",
      render: (k) => (
        <div className="flex items-center gap-2.5">
          <Key className="w-4 h-4 text-brand-400" />
          <div>
            <div className="text-sm font-medium text-ink">{k.name}</div>
            <code className="text-xs text-ink-soft font-mono">{k.public_id}</code>
          </div>
        </div>
      ),
    },
    { key: "scope", header: "Scope", render: (k) => <Badge tone="info">{k.scope}</Badge> },
    {
      key: "status",
      header: "Statut",
      render: (k) => (
        <Badge tone={k.is_active && !k.revoked_at ? "ok" : "muted"} dot>
          {k.revoked_at ? "Révoquée" : k.is_active ? "Active" : "Désactivée"}
        </Badge>
      ),
    },
    { key: "last", header: "Dernière utilisation", render: (k) => k.last_used_at ? fmtDateTime(k.last_used_at) : "Jamais" },
    { key: "expires", header: "Expire", render: (k) => k.expires_at ? fmtDateTime(k.expires_at) : "Jamais" },
    {
      key: "actions",
      header: "",
      className: "text-right",
      render: (k) => (
        <button
          onClick={() => {
            if (confirm(`Révoquer la clé "${k.name}" ?`)) removeMut.mutate(k.id);
          }}
          className="p-1.5 rounded-md hover:bg-danger/10 text-ink-muted hover:text-danger"
        >
          <Trash2 className="w-3.5 h-3.5" />
        </button>
      ),
    },
  ];

  return (
    <div>
      <PageHeader
        title="Clés API"
        subtitle={`${data?.count ?? 0} clés — utilisées par les apps mobiles, gateways BLE, intégrations tierces`}
        actions={
          <Button leftIcon={<Plus className="w-4 h-4" />} onClick={() => setOpen(true)}>
            Nouvelle clé
          </Button>
        }
      />

      <Card padded={false}>
        <DataTable
          columns={columns}
          rows={data?.results || []}
          loading={isLoading}
          rowKey={(k) => k.id}
        />
      </Card>

      {/* Modal création */}
      <Modal
        open={open}
        onClose={() => setOpen(false)}
        title="Nouvelle clé API"
        footer={
          <>
            <Button variant="ghost" onClick={() => setOpen(false)}>Annuler</Button>
            <Button
              onClick={() => form.name && createMut.mutate()}
              loading={createMut.isPending}
              disabled={!form.name}
            >
              Créer la clé
            </Button>
          </>
        }
      >
        <div className="space-y-3">
          <Input
            label="Nom descriptif *"
            placeholder="Ex: Mobile app iOS prod"
            value={form.name}
            onChange={(e) => setForm({ ...form, name: e.target.value })}
          />
          <div className="grid grid-cols-2 gap-3">
            <label className="block">
              <span className="text-xs font-medium text-ink-muted">Portée</span>
              <select
                value={form.scope}
                onChange={(e) => setForm({ ...form, scope: e.target.value })}
                className="field mt-1.5 w-full"
              >
                <option value="read">Lecture seule</option>
                <option value="write">Lecture + écriture</option>
                <option value="ingest">Ingest (gateway/mobile)</option>
                <option value="admin">Admin</option>
              </select>
            </label>
            <Input
              label="Expire le (optionnel)"
              type="date"
              value={form.expires_at}
              onChange={(e) => setForm({ ...form, expires_at: e.target.value })}
            />
          </div>
        </div>
      </Modal>

      {/* Modal révélation du secret — 1 seule fois */}
      <Modal
        open={!!reveal}
        onClose={() => setReveal(null)}
        title="Clé API créée"
        size="lg"
        footer={
          <Button onClick={() => setReveal(null)}>J'ai copié le secret</Button>
        }
      >
        <div className="rounded-lg bg-warn/10 border border-warn/20 p-3 flex gap-2 mb-4">
          <AlertTriangle className="w-4 h-4 text-warn shrink-0 mt-0.5" />
          <div className="text-xs text-ink">
            <strong>Copiez le secret dès maintenant</strong> — il ne sera plus jamais
            affiché. Si vous le perdez, vous devrez créer une nouvelle clé.
          </div>
        </div>
        <div className="space-y-3">
          <div>
            <div className="text-xs text-ink-muted mb-1">Public ID</div>
            <div className="flex items-center gap-2 p-2 rounded bg-surface-soft font-mono text-xs">
              <code className="flex-1 break-all">{reveal?.public_id}</code>
              <button
                onClick={() => {
                  if (reveal) navigator.clipboard.writeText(reveal.public_id);
                  toast.success("Public ID copié");
                }}
                className="p-1 rounded hover:bg-surface"
              >
                <Copy className="w-3.5 h-3.5" />
              </button>
            </div>
          </div>
          <div>
            <div className="text-xs text-ink-muted mb-1">Secret (à copier maintenant)</div>
            <div className="flex items-center gap-2 p-2 rounded bg-danger/10 border border-danger/20 font-mono text-xs">
              <code className="flex-1 break-all">{reveal?.secret}</code>
              <button
                onClick={() => {
                  if (reveal) navigator.clipboard.writeText(reveal.secret);
                  toast.success("Secret copié");
                }}
                className="p-1 rounded hover:bg-surface"
              >
                <Copy className="w-3.5 h-3.5" />
              </button>
            </div>
          </div>
        </div>
      </Modal>
    </div>
  );
}
