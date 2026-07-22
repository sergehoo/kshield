import { useMemo, useState } from "react";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { PageHeader } from "@/components/PageHeader";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
import { StatsRow } from "@/components/StatsRow";
import { notificationsService } from "@/services";
import { toApiError } from "@/lib/api";
import { fmtRelative } from "@/lib/format";
import type { Notification } from "@/types/api";
import { Bell, CheckCheck, AlertTriangle, Info, ShieldAlert, CheckCircle2 } from "lucide-react";
import { cn } from "@/lib/cn";
import toast from "react-hot-toast";

function iconFor(level: string) {
  if (level === "danger") return <ShieldAlert className="w-4 h-4 text-danger" />;
  if (level === "warn") return <AlertTriangle className="w-4 h-4 text-warn" />;
  if (level === "success") return <CheckCircle2 className="w-4 h-4 text-ok" />;
  return <Info className="w-4 h-4 text-info" />;
}

export function NotificationsPage() {
  const qc = useQueryClient();
  const [levelFilter, setLevelFilter] = useState<string>("");

  const { data, isLoading } = useQuery({
    queryKey: ["notifications", "all", levelFilter],
    queryFn: async () =>
      (await notificationsService.list({
        page_size: 100, ordering: "-created_at",
        level: levelFilter || undefined,
      })).data,
    refetchInterval: 30_000,
  });

  const stats = useMemo(() => {
    const list = data?.results || [];
    return {
      total: data?.count || 0,
      unread: list.filter((n: any) => !n.read_at).length,
      danger: list.filter((n: any) => n.level === "danger").length,
      warn: list.filter((n: any) => n.level === "warn").length,
      info: list.filter((n: any) => n.level === "info" || n.level === "success").length,
    };
  }, [data]);

  const markAll = useMutation({
    mutationFn: () => notificationsService.markAllRead(),
    onSuccess: () => {
      toast.success("Toutes marquées comme lues");
      qc.invalidateQueries({ queryKey: ["notifications"] });
    },
    onError: (e) => toast.error(toApiError(e).message),
  });

  const markOne = useMutation({
    mutationFn: (id: number) => notificationsService.markRead(id),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["notifications"] }),
  });

  const unreadCount = data?.results?.filter((n) => !n.read_at).length ?? 0;

  return (
    <div>
      <PageHeader
        title="Notifications"
        subtitle={`${data?.count ?? 0} notifications · ${unreadCount} non lues`}
        actions={
          unreadCount > 0 && (
            <Button
              variant="ghost"
              size="sm"
              leftIcon={<CheckCheck className="w-3.5 h-3.5" />}
              onClick={() => markAll.mutate()}
              loading={markAll.isPending}
            >
              Tout marquer lu
            </Button>
          )
        }
      />

      <StatsRow stats={[
        { label: "Total",     value: stats.total,  icon: <Bell className="w-4 h-4" />,        tone: "brand" },
        { label: "Non lues",  value: stats.unread, icon: <Bell className="w-4 h-4" />,        tone: "warn" },
        { label: "Critiques", value: stats.danger, icon: <ShieldAlert className="w-4 h-4" />, tone: "danger",
          onClick: () => setLevelFilter("danger") },
        { label: "Alertes",   value: stats.warn,   icon: <AlertTriangle className="w-4 h-4" />, tone: "warn",
          onClick: () => setLevelFilter("warn") },
        { label: "Infos",     value: stats.info,   icon: <Info className="w-4 h-4" />,        tone: "info",
          onClick: () => setLevelFilter("info") },
      ]} />

      <Card padded={false}>
        <div className="p-3 border-b border-surface-border flex gap-2 items-center">
          <select value={levelFilter} onChange={(e) => setLevelFilter(e.target.value)} className="field w-48">
            <option value="">Tous niveaux</option>
            <option value="danger">Critiques</option>
            <option value="warn">Alertes</option>
            <option value="info">Infos</option>
            <option value="success">Succès</option>
          </select>
        </div>
        {isLoading && <div className="p-8 text-center text-ink-muted">Chargement…</div>}
        {!isLoading && data?.results?.length === 0 && (
          <div className="p-10 text-center">
            <Bell className="w-8 h-8 mx-auto text-ink-soft mb-2" />
            <div className="text-sm text-ink-muted">Aucune notification</div>
          </div>
        )}
        <ul className="divide-y divide-surface-border/50">
          {data?.results?.map((n: Notification) => (
            <li
              key={n.id}
              className={cn(
                "flex gap-3 px-5 py-3.5 transition-colors",
                !n.read_at && "bg-brand-500/5",
                "hover:bg-surface-soft/40",
              )}
            >
              <div className="mt-0.5 shrink-0">{iconFor(n.level)}</div>
              <div className="flex-1 min-w-0">
                <div className="flex items-center gap-2">
                  <span className="text-sm font-medium text-ink truncate">{n.title}</span>
                  {!n.read_at && (
                    <span className="w-1.5 h-1.5 rounded-full bg-brand-500 shrink-0" />
                  )}
                </div>
                {n.body && (
                  <div className="mt-0.5 text-xs text-ink-muted">{n.body}</div>
                )}
                <div className="mt-1 text-[11px] text-ink-soft">
                  {fmtRelative(n.created_at)}
                  {n.category && ` · ${n.category}`}
                </div>
              </div>
              {!n.read_at && (
                <button
                  onClick={() => markOne.mutate(n.id)}
                  className="shrink-0 text-xs text-brand-ink hover:text-brand-ink"
                >
                  Marquer lu
                </button>
              )}
            </li>
          ))}
        </ul>
      </Card>
    </div>
  );
}
