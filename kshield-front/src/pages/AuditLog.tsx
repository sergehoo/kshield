import { useState, useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import { PageHeader } from "@/components/PageHeader";
import { Card } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { Input } from "@/components/ui/Input";
import { DataTable, Column } from "@/components/ui/DataTable";
import { StatsRow } from "@/components/StatsRow";
import { auditService } from "@/services";
import { fmtDateTime, fmtRelative } from "@/lib/format";
import { Search, ScrollText, LogIn, LogOut, Trash, Edit, Plus } from "lucide-react";

export function AuditLogPage() {
  const [q, setQ] = useState("");
  const [action, setAction] = useState("");

  const { data, isLoading } = useQuery({
    queryKey: ["audit", q, action],
    queryFn: async () =>
      (
        await auditService.list({
          page_size: 100,
          search: q || undefined,
          action: action || undefined,
          ordering: "-created_at",
        })
      ).data,
  });

  const stats = useMemo(() => {
    const list = data?.results || [];
    const oneHourAgo = Date.now() - 3600_000;
    return {
      total: data?.count || 0,
      lastHour: list.filter((e: any) => new Date(e.created_at).getTime() > oneHourAgo).length,
      creates: list.filter((e: any) => (e.action || "").includes("create")).length,
      updates: list.filter((e: any) => (e.action || "").includes("update")).length,
      deletes: list.filter((e: any) => (e.action || "").includes("delete")).length,
      logins: list.filter((e: any) => (e.action || "").includes("login")).length,
    };
  }, [data]);

  const columns: Column<any>[] = [
    {
      key: "when",
      header: "Quand",
      width: "160px",
      render: (e) => (
        <div>
          <div className="text-xs text-ink">{fmtDateTime(e.created_at)}</div>
          <div className="text-[10px] text-ink-soft">{fmtRelative(e.created_at)}</div>
        </div>
      ),
    },
    {
      key: "actor",
      header: "Utilisateur",
      render: (e) => (
        <div className="text-sm">
          <div className="text-ink font-medium">{e.actor_email || e.user_email || "system"}</div>
          <div className="text-xs text-ink-soft font-mono">{e.actor_ip || e.ip || "—"}</div>
        </div>
      ),
    },
    {
      key: "action",
      header: "Action",
      render: (e) => (
        <Badge
          tone={
            e.action?.includes("delete") || e.action?.includes("revoke")
              ? "danger"
              : e.action?.includes("create") || e.action?.includes("add")
              ? "ok"
              : e.action?.includes("update") || e.action?.includes("modify")
              ? "warn"
              : "info"
          }
        >
          {e.action || e.event_type}
        </Badge>
      ),
    },
    {
      key: "target",
      header: "Cible",
      render: (e) => (
        <div className="text-xs">
          {e.target_model && (
            <div className="text-ink">
              {e.target_model} <span className="text-ink-soft">#{e.target_id}</span>
            </div>
          )}
          {e.description && (
            <div className="text-ink-muted mt-0.5">{e.description}</div>
          )}
        </div>
      ),
    },
  ];

  return (
    <div>
      <PageHeader
        title="Journal d'audit"
        subtitle={`${data?.count ?? 0} entrées — toutes les actions sensibles`}
      />

      <StatsRow stats={[
        { label: "Total entrées",  value: stats.total,    icon: <ScrollText className="w-4 h-4" />, tone: "brand" },
        { label: "Dernière heure", value: stats.lastHour, icon: <ScrollText className="w-4 h-4" />, tone: "info" },
        { label: "Créations",      value: stats.creates,  icon: <Plus className="w-4 h-4" />,       tone: "ok",
          onClick: () => setAction("create") },
        { label: "Modifications",  value: stats.updates,  icon: <Edit className="w-4 h-4" />,       tone: "warn",
          onClick: () => setAction("update") },
        { label: "Suppressions",   value: stats.deletes,  icon: <Trash className="w-4 h-4" />,      tone: "danger",
          onClick: () => setAction("delete") },
        { label: "Logins",         value: stats.logins,   icon: <LogIn className="w-4 h-4" />,      tone: "muted",
          onClick: () => setAction("login") },
      ]} />

      <Card padded={false}>
        <div className="p-4 border-b border-surface-border flex gap-2">
          <div className="flex-1">
            <Input
              placeholder="Rechercher par utilisateur, cible, description…"
              leftIcon={<Search className="w-4 h-4" />}
              value={q}
              onChange={(e) => setQ(e.target.value)}
            />
          </div>
          <select
            value={action}
            onChange={(e) => setAction(e.target.value)}
            className="field w-48"
          >
            <option value="">Toutes actions</option>
            <option value="create">Création</option>
            <option value="update">Modification</option>
            <option value="delete">Suppression</option>
            <option value="login">Login</option>
            <option value="logout">Logout</option>
            <option value="access_granted">Accès autorisé</option>
            <option value="access_denied">Accès refusé</option>
          </select>
        </div>
        <DataTable
          columns={columns}
          rows={data?.results || []}
          loading={isLoading}
          rowKey={(e) => e.id}
          emptyLabel="Aucune entrée d'audit"
        />
      </Card>
    </div>
  );
}
