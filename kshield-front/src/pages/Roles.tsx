import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { PageHeader } from "@/components/PageHeader";
import { Card } from "@/components/ui/Card";
import { DataTable, Column } from "@/components/ui/DataTable";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Modal } from "@/components/ui/Modal";
import { rolesService } from "@/services";
import { toApiError } from "@/lib/api";
import { Plus, Shield, Lock } from "lucide-react";
import toast from "react-hot-toast";

export function RolesPage() {
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({ code: "", name: "", description: "", scope: "tenant" });
  const qc = useQueryClient();

  const { data, isLoading } = useQuery({
    queryKey: ["roles"],
    queryFn: async () => (await rolesService.list()).data,
  });

  const createMut = useMutation({
    mutationFn: () => rolesService.create(form),
    onSuccess: () => {
      toast.success("Rôle créé");
      setOpen(false);
      setForm({ code: "", name: "", description: "", scope: "tenant" });
      qc.invalidateQueries({ queryKey: ["roles"] });
    },
    onError: (e) => toast.error(toApiError(e).message),
  });

  const columns: Column<any>[] = [
    {
      key: "name",
      header: "Rôle",
      render: (r) => (
        <div className="flex items-center gap-2.5">
          <div className="w-8 h-8 rounded-lg bg-brand-500/10 text-brand-400 grid place-items-center">
            <Shield className="w-4 h-4" />
          </div>
          <div>
            <div className="text-sm font-medium text-ink">{r.name}</div>
            <code className="text-xs text-ink-soft font-mono">{r.code}</code>
          </div>
        </div>
      ),
    },
    { key: "scope", header: "Portée", render: (r) => <Badge tone="info">{r.scope || "tenant"}</Badge> },
    { key: "desc", header: "Description", render: (r) => r.description || "—" },
    {
      key: "perms",
      header: "Permissions",
      render: (r) => (
        <div className="flex items-center gap-1 text-xs">
          <Lock className="w-3.5 h-3.5 text-ink-soft" />
          <span>{r.permissions?.length ?? 0}</span>
        </div>
      ),
    },
    {
      key: "system",
      header: "",
      render: (r) => r.is_system ? <Badge tone="warn">Système</Badge> : null,
    },
  ];

  return (
    <div>
      <PageHeader
        title="Rôles"
        subtitle={`${data?.count ?? data?.results?.length ?? 0} rôles RBAC`}
        actions={
          <Button leftIcon={<Plus className="w-4 h-4" />} onClick={() => setOpen(true)}>
            Nouveau rôle
          </Button>
        }
      />
      <Card padded={false}>
        <DataTable
          columns={columns}
          rows={data?.results || []}
          loading={isLoading}
          rowKey={(r) => r.id}
        />
      </Card>

      <Modal
        open={open}
        onClose={() => setOpen(false)}
        title="Nouveau rôle"
        footer={
          <>
            <Button variant="ghost" onClick={() => setOpen(false)}>Annuler</Button>
            <Button
              onClick={() => form.code && form.name && createMut.mutate()}
              loading={createMut.isPending}
              disabled={!form.code || !form.name}
            >
              Créer
            </Button>
          </>
        }
      >
        <div className="space-y-3">
          <div className="grid grid-cols-2 gap-3">
            <Input
              label="Code * (snake_case)"
              placeholder="site_manager"
              value={form.code}
              onChange={(e) => setForm({ ...form, code: e.target.value })}
            />
            <label className="block">
              <span className="text-xs font-medium text-ink-muted">Portée</span>
              <select
                value={form.scope}
                onChange={(e) => setForm({ ...form, scope: e.target.value })}
                className="field mt-1.5 w-full"
              >
                <option value="tenant">Tenant</option>
                <option value="site">Site</option>
                <option value="company">Société</option>
                <option value="global">Global</option>
              </select>
            </label>
          </div>
          <Input
            label="Nom d'affichage *"
            value={form.name}
            onChange={(e) => setForm({ ...form, name: e.target.value })}
          />
          <Input
            label="Description"
            value={form.description}
            onChange={(e) => setForm({ ...form, description: e.target.value })}
          />
        </div>
      </Modal>
    </div>
  );
}
