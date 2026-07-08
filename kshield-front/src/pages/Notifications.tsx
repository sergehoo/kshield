import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { PageHeader } from "@/components/PageHeader";
import { Card } from "@/components/ui/Card";
import { Button } from "@/components/ui/Button";
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

  const { data, isLoading } = useQuery({
    queryKey: ["notifications", "all"],
    queryFn: async () =>
      (await notificationsService.list({ page_size: 100, ordering: "-created_at" })).data,
    refetchInterval: 30_000,
  });

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

      <Card padded={false}>
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
                  className="shrink-0 text-xs text-brand-500 hover:text-brand-400"
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
