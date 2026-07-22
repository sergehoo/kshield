import { useState, useMemo } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { PageHeader } from "@/components/PageHeader";
import { Card } from "@/components/ui/Card";
import { DataTable, Column } from "@/components/ui/DataTable";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { Modal } from "@/components/ui/Modal";
import { StatsRow } from "@/components/StatsRow";
import { usersService } from "@/services";
import { toApiError } from "@/lib/api";
import { fmtDateTime, initials } from "@/lib/format";
import { Plus, Search, User, Trash2, ShieldCheck, UserX, Users as UsersIcon } from "lucide-react";
import toast from "react-hot-toast";

export function UsersPage() {
  const [q, setQ] = useState("");
  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({
    email: "", password: "", first_name: "", last_name: "", phone: "",
  });
  const qc = useQueryClient();

  const [statusFilter, setStatusFilter] = useState("");

  const { data, isLoading } = useQuery({
    queryKey: ["users", q, statusFilter],
    queryFn: async () =>
      (await usersService.list({
        page_size: 200, search: q || undefined,
        is_active: statusFilter === "active" ? true : statusFilter === "inactive" ? false : undefined,
      })).data,
  });

  const { data: allUsers } = useQuery({
    queryKey: ["users", "all-stats"],
    queryFn: async () => (await usersService.list({ page_size: 500 })).data,
    staleTime: 30_000,
  });

  const stats = useMemo(() => {
    const list = allUsers?.results || [];
    return {
      total: allUsers?.count || 0,
      active: list.filter((u: any) => u.is_active).length,
      superuser: list.filter((u: any) => u.is_superuser).length,
      staff: list.filter((u: any) => u.is_staff && !u.is_superuser).length,
      mfa: list.filter((u: any) => u.mfa_enabled).length,
    };
  }, [allUsers]);

  const createMut = useMutation({
    mutationFn: () => usersService.create(form),
    onSuccess: () => {
      toast.success("Utilisateur créé");
      setOpen(false);
      setForm({ email: "", password: "", first_name: "", last_name: "", phone: "" });
      qc.invalidateQueries({ queryKey: ["users"] });
    },
    onError: (e) => toast.error(toApiError(e).message),
  });

  const removeMut = useMutation({
    mutationFn: (id: number) => usersService.remove(id),
    onSuccess: () => {
      toast.success("Utilisateur supprimé");
      qc.invalidateQueries({ queryKey: ["users"] });
    },
    onError: (e) => toast.error(toApiError(e).message),
  });

  const columns: Column<any>[] = [
    {
      key: "user",
      header: "Utilisateur",
      render: (u) => (
        <div className="flex items-center gap-2.5">
          {u.photo ? (
            <img src={u.photo} alt="" className="w-8 h-8 rounded-full object-cover" />
          ) : (
            <div className="w-8 h-8 rounded-full bg-brand-500/20 text-brand-ink grid place-items-center text-xs font-semibold">
              {initials(u.full_name || u.email)}
            </div>
          )}
          <div>
            <div className="text-sm font-medium text-ink">
              {u.full_name || `${u.first_name || ""} ${u.last_name || ""}`.trim() || u.email}
            </div>
            <div className="text-xs text-ink-soft">{u.email}</div>
          </div>
        </div>
      ),
    },
    { key: "phone", header: "Téléphone", render: (u) => u.phone || "—" },
    {
      key: "tenant",
      header: "Tenant",
      render: (u) =>
        typeof u.tenant === "object" && u.tenant ? u.tenant.name : "—",
    },
    {
      key: "roles",
      header: "Statut",
      render: (u) => (
        <div className="flex gap-1">
          {u.is_superuser && <Badge tone="danger">Super admin</Badge>}
          {u.is_staff && !u.is_superuser && <Badge tone="warn">Staff</Badge>}
          {!u.is_active && <Badge tone="muted">Désactivé</Badge>}
          {u.mfa_enabled && (
            <Badge tone="ok">
              <ShieldCheck className="w-3 h-3" /> MFA
            </Badge>
          )}
        </div>
      ),
    },
    { key: "last_login", header: "Dernière connexion", render: (u) => u.last_login ? fmtDateTime(u.last_login) : "Jamais" },
    {
      key: "actions",
      header: "",
      className: "text-right",
      render: (u) => (
        <button
          onClick={() => {
            if (confirm(`Supprimer l'utilisateur ${u.email} ?`)) removeMut.mutate(u.id);
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
        title="Utilisateurs"
        subtitle={`${data?.count ?? 0} utilisateurs back-office`}
        actions={
          <Button leftIcon={<Plus className="w-4 h-4" />} onClick={() => setOpen(true)}>
            Nouvel utilisateur
          </Button>
        }
      />

      <StatsRow stats={[
        { label: "Total users",  value: stats.total,     icon: <UsersIcon className="w-4 h-4" />,   tone: "brand" },
        { label: "Actifs",       value: stats.active,    icon: <User className="w-4 h-4" />,       tone: "ok",
          onClick: () => setStatusFilter("active") },
        { label: "Super admins", value: stats.superuser, icon: <ShieldCheck className="w-4 h-4" />, tone: "danger" },
        { label: "Staff",        value: stats.staff,     icon: <ShieldCheck className="w-4 h-4" />, tone: "warn" },
        { label: "MFA activé",   value: stats.mfa,       icon: <ShieldCheck className="w-4 h-4" />, tone: "info" },
      ]} />

      <Card padded={false}>
        <div className="p-4 border-b border-surface-border flex flex-col sm:flex-row gap-2">
          <div className="flex-1">
            <Input
              placeholder="Rechercher…"
              leftIcon={<Search className="w-4 h-4" />}
              value={q}
              onChange={(e) => setQ(e.target.value)}
            />
          </div>
          <select value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)} className="field sm:w-40">
            <option value="">Tous</option>
            <option value="active">Actifs</option>
            <option value="inactive">Désactivés</option>
          </select>
        </div>
        <DataTable
          columns={columns}
          rows={data?.results || []}
          loading={isLoading}
          rowKey={(u) => u.id}
        />
      </Card>

      <Modal
        open={open}
        onClose={() => setOpen(false)}
        title="Nouvel utilisateur"
        footer={
          <>
            <Button variant="ghost" onClick={() => setOpen(false)}>Annuler</Button>
            <Button
              onClick={() => form.email && form.password && createMut.mutate()}
              loading={createMut.isPending}
              disabled={!form.email || !form.password}
            >
              Créer
            </Button>
          </>
        }
      >
        <div className="space-y-3">
          <Input
            label="Email *"
            type="email"
            value={form.email}
            onChange={(e) => setForm({ ...form, email: e.target.value })}
            required
          />
          <Input
            label="Mot de passe * (min. 10 caractères)"
            type="password"
            value={form.password}
            onChange={(e) => setForm({ ...form, password: e.target.value })}
            required
          />
          <div className="grid grid-cols-2 gap-3">
            <Input
              label="Prénom"
              value={form.first_name}
              onChange={(e) => setForm({ ...form, first_name: e.target.value })}
            />
            <Input
              label="Nom"
              value={form.last_name}
              onChange={(e) => setForm({ ...form, last_name: e.target.value })}
            />
          </div>
          <Input
            label="Téléphone"
            value={form.phone}
            onChange={(e) => setForm({ ...form, phone: e.target.value })}
          />
        </div>
      </Modal>
    </div>
  );
}
