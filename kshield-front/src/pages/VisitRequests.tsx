import { useState } from "react";
import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import { PageHeader } from "@/components/PageHeader";
import { Card } from "@/components/ui/Card";
import { Badge } from "@/components/ui/Badge";
import { Button } from "@/components/ui/Button";
import { Input } from "@/components/ui/Input";
import { DataTable, Column } from "@/components/ui/DataTable";
import { visitRequestsService } from "@/services";
import { toApiError } from "@/lib/api";
import { fmtDateTime, fmtRelative } from "@/lib/format";
import { CheckCircle2, XCircle, Ban, Search, Calendar, User as UserIcon } from "lucide-react";
import { cn } from "@/lib/cn";
import toast from "react-hot-toast";

/**
 * Workflow des demandes de visite :
 *   pending → approve/reject → si approve → checkin/checkout
 */
export function VisitRequestsPage() {
  const [status, setStatus] = useState<string>("pending");
  const [q, setQ] = useState("");
  const qc = useQueryClient();

  const { data, isLoading } = useQuery({
    queryKey: ["visit-requests", status, q],
    queryFn: async () =>
      (
        await visitRequestsService.list({
          status: status || undefined,
          search: q || undefined,
          ordering: "-visit_at",
          page_size: 100,
        })
      ).data,
  });

  const approve = useMutation({
    mutationFn: (id: number) => visitRequestsService.approve(id),
    onSuccess: () => {
      toast.success("Demande approuvée");
      qc.invalidateQueries({ queryKey: ["visit-requests"] });
    },
    onError: (e) => toast.error(toApiError(e).message),
  });

  const reject = useMutation({
    mutationFn: (id: number) => {
      const note = prompt("Motif du refus (optionnel) :");
      return visitRequestsService.reject(id, note || undefined);
    },
    onSuccess: () => {
      toast.success("Demande refusée");
      qc.invalidateQueries({ queryKey: ["visit-requests"] });
    },
    onError: (e) => toast.error(toApiError(e).message),
  });

  const cancel = useMutation({
    mutationFn: (id: number) => visitRequestsService.cancel(id),
    onSuccess: () => {
      toast.success("Annulée");
      qc.invalidateQueries({ queryKey: ["visit-requests"] });
    },
    onError: (e) => toast.error(toApiError(e).message),
  });

  const columns: Column<any>[] = [
    {
      key: "visitor",
      header: "Visiteur",
      render: (r) => (
        <div className="flex items-center gap-2.5">
          <div className="w-8 h-8 rounded-full bg-info/20 text-info grid place-items-center">
            <UserIcon className="w-4 h-4" />
          </div>
          <div>
            <div className="text-sm font-medium">
              {r.visitor_name || r.guest_name || "—"}
            </div>
            <div className="text-xs text-ink-soft">
              {r.company_name || r.guest_email || ""}
            </div>
          </div>
        </div>
      ),
    },
    {
      key: "when",
      header: "Date visite",
      render: (r) => (
        <div>
          <div className="text-sm">{fmtDateTime(r.visit_at)}</div>
          <div className="text-xs text-ink-soft">{fmtRelative(r.visit_at)}</div>
        </div>
      ),
    },
    { key: "purpose", header: "Motif", render: (r) => r.purpose_label || r.reason || "—" },
    { key: "host", header: "Hôte", render: (r) => r.host_email || r.host_name || "—" },
    {
      key: "status",
      header: "Statut",
      render: (r) => {
        const tone =
          r.status === "approved" ? "ok" :
          r.status === "rejected" ? "danger" :
          r.status === "cancelled" ? "muted" :
          r.status === "completed" ? "info" : "warn";
        return <Badge tone={tone} dot>{r.status || "pending"}</Badge>;
      },
    },
    {
      key: "actions",
      header: "",
      className: "text-right whitespace-nowrap",
      render: (r) => {
        if (r.status === "pending") {
          return (
            <div className="inline-flex gap-1">
              <button
                onClick={() => approve.mutate(r.id)}
                className="p-1.5 rounded-md hover:bg-ok/10 text-ink-muted hover:text-ok"
                title="Approuver"
              >
                <CheckCircle2 className="w-3.5 h-3.5" />
              </button>
              <button
                onClick={() => reject.mutate(r.id)}
                className="p-1.5 rounded-md hover:bg-danger/10 text-ink-muted hover:text-danger"
                title="Refuser"
              >
                <XCircle className="w-3.5 h-3.5" />
              </button>
            </div>
          );
        }
        if (r.status === "approved") {
          return (
            <button
              onClick={() => cancel.mutate(r.id)}
              className="p-1.5 rounded-md hover:bg-warn/10 text-ink-muted hover:text-warn"
              title="Annuler"
            >
              <Ban className="w-3.5 h-3.5" />
            </button>
          );
        }
        return null;
      },
    },
  ];

  return (
    <div>
      <PageHeader
        title="Demandes de visite"
        subtitle={`${data?.count ?? 0} demandes — ${status === "pending" ? "en attente" : status || "toutes"}`}
      />

      <Card padded={false}>
        <div className="p-4 border-b border-surface-border flex flex-col sm:flex-row gap-2">
          <div className="flex-1">
            <Input
              placeholder="Rechercher par nom, société…"
              leftIcon={<Search className="w-4 h-4" />}
              value={q}
              onChange={(e) => setQ(e.target.value)}
            />
          </div>
          <div className="inline-flex rounded-lg bg-surface-soft p-0.5 border border-surface-border">
            {(
              [
                { key: "pending",   label: "En attente" },
                { key: "approved",  label: "Approuvées" },
                { key: "rejected",  label: "Refusées" },
                { key: "",          label: "Toutes" },
              ] as const
            ).map((f) => (
              <button
                key={f.key}
                onClick={() => setStatus(f.key)}
                className={cn(
                  "px-3 py-1.5 rounded-md text-xs font-medium transition",
                  status === f.key ? "bg-brand-500 text-white" : "text-ink-muted hover:text-ink",
                )}
              >
                {f.label}
              </button>
            ))}
          </div>
        </div>
        <DataTable
          columns={columns}
          rows={data?.results || []}
          loading={isLoading}
          rowKey={(r) => r.id}
          emptyLabel="Aucune demande à ce statut"
          emptyIcon={<Calendar className="w-8 h-8 mx-auto text-ink-soft mb-2" />}
        />
      </Card>
    </div>
  );
}
